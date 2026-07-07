import os
import json
import asyncio
import logging
import time
import re
from dataclasses import asdict

import librosa
from google import genai
from google.genai import types
from config import GEMINI_KEYS, DIR_OUTPUT, FONT_SIZE_HOOK, FONT_SIZE_BODY, DIR_TEMP, WIDTH, HEIGHT
try:
    from config import (
        THREADS_MAX, 
        SUBTITLE_MIN_ACCURACY, 
        DOWNLOAD_TIMEOUT, 
        RENDER_TIMEOUT_FACTOR,
        CONFIDENCE_THRESHOLD_HOOK,
        CONFIDENCE_THRESHOLD_BODY,
        CONFIDENCE_THRESHOLD_CTA
    )
except ImportError:
    THREADS_MAX = 4
    SUBTITLE_MIN_ACCURACY = 0.70
    DOWNLOAD_TIMEOUT = 90.0
    RENDER_TIMEOUT_FACTOR = 15.0 
    CONFIDENCE_THRESHOLD_HOOK = 0.30
    CONFIDENCE_THRESHOLD_BODY = 0.45
    CONFIDENCE_THRESHOLD_CTA = 0.60

# Memastikan RENDER_TIMEOUT_FACTOR tetap tinggi jika ter-import dari config lama
RENDER_TIMEOUT_FACTOR = 15.0 

from downloader import download_video_clips, download_youtube_retention_video
from effects import process_background_clip
from subtitle_engine.orchestrator import SubtitleEngineV2
from audio import generate_voiceover_with_timestamps, validate_timeline_invariants
from audio_sync_optimizer import optimize_subtitle_timing, _to_dict_list, _to_wordtimestamp_list

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger("video_pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Poin 7: Event Code Resmi untuk Standardisasi Log Produksi
EV_GEMINI_ROTATION    = "VP100"
EV_GEMINI_LIMIT       = "VP101"
EV_GEMINI_CRASH       = "VP102"
EV_DOWNLOAD_TIMEOUT   = "VP200"
EV_DOWNLOAD_FAIL      = "VP201"
EV_SUBTITLE_REJECT    = "VP300"
EV_SUBTITLE_WARN      = "VP301"
EV_SUBTITLE_OPTIMIZED = "VP302"
EV_TIMELINE_VALIDATED = "VP303"
EV_RENDER_START       = "VP400"
EV_RENDER_TIMEOUT     = "VP401"
EV_RENDER_FAIL        = "VP402"
EV_PIPELINE_SUCCESS   = "VP500"

RETRY_ERRORS = ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED", "TIMEOUT", "CONNECTION"]

class GeminiClientPool:
    """Poin 3: Client Pool reuse object tanpa instansiasi berulang saat runtime."""
    def __init__(self, api_keys: list):
        if not api_keys:
            raise ValueError("❌ Tidak ada GEMINI_API_KEY yang ditemukan di GitHub Secrets.")
        self.api_keys = api_keys
        self.clients = [genai.Client(api_key=key) for key in api_keys]
        self.cooldowns = [0.0] * len(api_keys)
        self.current_index = 0
        self.lock = asyncio.Lock()

    async def get_client_and_rotate(self):
        async with self.lock:
            now = time.time()
            for _ in range(len(self.api_keys)):
                idx = self.current_index
                self.current_index = (self.current_index + 1) % len(self.api_keys)
                
                if now >= self.cooldowns[idx]:
                    return self.clients[idx], idx
            
            future_cooldowns = [t - now for t in self.cooldowns]
            min_wait = min(future_cooldowns)
            min_idx = future_cooldowns.index(min_wait)
            wait_time = max(1.0, min_wait + 1.0)
            logger.warning("[%s] Semua API Key cooldown. Menidurkan pipeline %.1f detik...", EV_GEMINI_LIMIT, wait_time)
            
        await asyncio.sleep(wait_time)
        async with self.lock:
            self.cooldowns[min_idx] = 0.0
            return self.clients[min_idx], min_idx

    async def set_cooldown(self, index: int, duration: int = 180):
        async with self.lock:
            self.cooldowns[index] = time.time() + duration

client_pool = GeminiClientPool(GEMINI_KEYS)

def clean_and_parse_json(raw_text: str) -> dict | list:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    
    first_brace = cleaned.find('{')
    first_bracket = cleaned.find('[')
    
    start_idx = min(idx for idx in (first_brace, first_bracket) if idx != -1) if (first_brace != -1 or first_bracket != -1) else -1
    if start_idx == -1:
        raise ValueError("Format JSON respons tidak valid.")
        
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(cleaned[start_idx:])
    return obj

async def call_groq_fallback(prompt: str, is_json: bool = True) -> str:
    import os
    import requests
    import asyncio
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY tidak dikonfigurasi di environment/secrets.")
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Menggunakan model Llama 3.3 70B yang stabil untuk instruksi terstruktur
    model = "llama-3.3-70b-versatile"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 1.0,
        "response_format": {"type": "json_object"} if is_json else None
    }
    
    loop = asyncio.get_running_loop()
    try:
        response = await loop.run_in_executor(
            None, lambda: requests.post(url, json=payload, headers=headers, timeout=20)
        )
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        else:
            raise RuntimeError(f"Groq API mengembalikan status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"❌ Groq fallback gagal: {e}")
        raise e

async def call_gemini_with_retry(prompt: str, is_json: bool = True, temperature: float = None) -> str:
    max_attempts = max(5, len(GEMINI_KEYS) * 2)
    config_args = {"response_mime_type": "application/json" if is_json else None}
    if temperature is not None:
        config_args["temperature"] = temperature
    config = types.GenerateContentConfig(**config_args)
    
    last_err = None
    for attempt in range(max_attempts):
        client, idx = await client_pool.get_client_and_rotate()
        try:
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=config)
            return response.text.strip()
        except Exception as e:
            last_err = e
            err_msg = str(e)
            if any(x.lower() in err_msg.lower() for x in RETRY_ERRORS):
                backoff_delay = 2 ** attempt
                logger.warning("[%s] Eror terdeteksi. Karantina Slot-%d. Backoff %d detik.", EV_GEMINI_ROTATION, idx + 1, backoff_delay)
                await client_pool.set_cooldown(idx, duration=60 + backoff_delay)
                await asyncio.sleep(backoff_delay)
                continue
            logger.warning("[%s] Gangguan API Gemini: %s. Mencoba model lain/kunci lain.", EV_GEMINI_CRASH, e)
            
    # Jika Gemini gagal total, coba Groq API Fallback
    logger.warning("⚠️ Semua percobaan Gemini gagal atau rate-limited. Memicu fallback ke Groq API...")
    try:
        res = await call_groq_fallback(prompt, is_json)
        logger.info("✅ Sukses mendapatkan konten cadangan dari Groq API.")
        return res
    except Exception as groq_err:
        logger.error(f"❌ Groq API Fallback gagal juga: {groq_err}")
        if last_err:
            raise last_err
        raise RuntimeError("Seluruh penyedia AI (Gemini & Groq) gagal merespon.")


def get_indonesia_trending_searches() -> list:
    """Mengambil kata kunci pencarian terpopuler hari ini di Indonesia dari Google Trends RSS."""
    import urllib.request
    import xml.etree.ElementTree as ET
    url = "https://trends.google.com/trending/rss?geo=ID"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
        
        root = ET.fromstring(xml_data)
        trends = []
        for item in root.findall(".//item"):
            title = item.find("title")
            if title is not None and title.text:
                trends.append(title.text.strip())
        return trends[:5]
    except Exception as e:
        logger.warning("⚠️ Gagal mengambil Google Trends: %s", e)
        return []


async def analyze_comments_with_gemini(comments: list) -> str:
    """Menganalisis komentar penonton dengan Gemini dan menghasilkan insight konten berikutnya."""
    if not comments:
        return ""
    comments_text = "\n".join(f"- {c}" for c in comments[:15])
    prompt = (
        "Kamu adalah analis konten TikTok/YouTube yang ahli.\n"
        "Berikut adalah komentar-komentar dari penonton pada video edukasi psikologi yang sedang viral:\n\n"
        f"{comments_text}\n\n"
        "Analisis komentar di atas dan jawab dalam 2-3 kalimat ringkas:\n"
        "1. Apa topik atau pertanyaan yang paling sering muncul dari penonton?\n"
        "2. Berikan 1 rekomendasi ide konten lanjutan yang paling relevan berdasarkan komentar ini.\n\n"
        "OUTPUT: Jawab langsung dalam bahasa Indonesia, tanpa format JSON, cukup 2-3 kalimat."
    )
    try:
        result = await call_gemini_with_retry(prompt, is_json=False)
        return result.strip() if result else ""
    except Exception as e:
        logger.warning("⚠️ Gagal menganalisis komentar dengan Gemini: %s", e)
        return ""

# NICHE_CONFIG dipindahkan ke config/channels.json

async def generate_structured_script(channel_cfg: dict) -> dict:
    logger.info("🧠 Gemini sedang merancang naskah berstruktur otomatis...")
    import random
    
    config = channel_cfg
    chosen_theme = random.choice(config["themes"])
    logger.info("🎯 Tema terpilih: %s", chosen_theme)
    
    # Baca riwayat naskah untuk mencegah repetisi ide (lewat Firebase / cadangan Lokal)
    exclude_prompt = ""
    try:
        import firebase_connector
        recent_entries = firebase_connector.get_recent_history(60)
        if recent_entries:
            recent_hooks = [item["hook"] for item in recent_entries if "hook" in item]
            
            exclude_prompt = (
                "\n\nHINDARI MEMBUAT TOPIK YANG SAMA ATAU MIRIP DENGAN DAFTAR DI BAWAH INI "
                "agar konten selalu unik. Daftar 60 Hook/Topik terakhir yang sudah pernah dibuat:\n" +
                "\n".join(f"- {h}" for h in recent_hooks)
            )
    except Exception as e:
        logger.warning(" Gagal membaca riwayat naskah: %s", e)

    # ⭐ LEVEL 5: Ambil naskah paling populer sebagai contoh gaya sukses untuk AI
    performance_prompt = ""
    try:
        import firebase_connector
        top_scripts = firebase_connector.get_top_performing_scripts(limit=3)
        if top_scripts:
            performance_prompt = (
                "\n\nBELAJAR DARI NASKAH SUKSES BERIKUT (dari konten dengan views tertinggi):\n"
                "Analisis gaya hook, panjang kalimat, dan cara penyampaian naskah-naskah ini, "
                "lalu buat naskah baru yang meniru POLA penulisannya (bukan isinya):\n"
            )
            for i, sc in enumerate(top_scripts, 1):
                views = sc.get("views", 0)
                caption = sc.get("caption", "")
                performance_prompt += f"\n[Naskah Sukses #{i} — {views:,} views]\n{caption}\n"
            logger.info("⭐ Level 5: Menyuntikkan %d naskah sukses ke prompt Gemini.", len(top_scripts))
    except Exception as e:
        logger.warning("⚠️ Gagal mengambil naskah populer untuk feedback loop: %s", e)

    # ⭐ LEVEL 5 ADVANCED: Ambil insight dari analisis komentar penonton
    comment_insight_prompt = ""
    try:
        import firebase_connector
        insight = firebase_connector.get_latest_comment_insight()
        if insight:
            comment_insight_prompt = (
                f"\n\nINSIGHT KOMENTAR PENONTON TERAKHIR (Gunakan ini untuk arah topik konten):\n"
                f"\"{insight}\"\n"
                f"Sesuaikan topik atau sudut pandang naskah agar menjawab/merefleksikan insight di atas."
            )
            logger.info("⭐ Level 5 Advanced: Menyuntikkan insight komentar penonton.")
    except Exception as e:
        logger.warning("⚠️ Gagal mengambil insight komentar: %s", e)

    # ⭐ LEVEL 5 A/B TESTING: Periksa apakah ada hook kandidat B dari percobaan sebelumnya
    hook_candidate = ""
    try:
        import firebase_connector
        hook_candidate = firebase_connector.get_best_hook_candidate()
        if hook_candidate:
            logger.info("🎯 A/B Testing: Menggunakan Hook kandidat B hasil A/B test sebelumnya: '%s'", hook_candidate)
    except Exception as e:
        logger.warning("⚠️ Gagal mengambil hook kandidat B: %s", e)

    # Tentukan apakah kita akan memicu pembuatan A/B hook untuk run saat ini (peluang 25%)
    trigger_ab_test = random.random() < 0.25
    ab_test_instruction = ""
    if trigger_ab_test and not hook_candidate:
        ab_test_instruction = (
            "\n8. 'hook_b': Hasilkan SATU variasi hook alternatif (versi B) yang berbeda gaya/pendekatan dengan 'hook' utama, tapi membahas subjek yang sama. Format teks harus KAPITAL, maks 10 kata. Contoh: 'JANGAN SAMPAI TANDUK KEPALA KAMU DIATUR ORANG LAIN'\n"
        )
        logger.info("🎯 A/B Testing: Menginstruksikan Gemini untuk membuat Hook B alternatif.")

    hook_rule = "1. 'hook': Kalimat pembuka KAPITAL yang mengejutkan, provokatif, dan membuat penonton TERPAKSA berhenti scroll. Maks 10 kata. SANGAT PENTING: JANGAN gunakan pola kalimat yang repetitif (hindari memulai dengan 'TAHUKAH KAMU', 'FAKTA', atau 'ALASAN'). Gunakan variasi struktur kalimat ekstrem setiap kalinya (contoh: kutipan menohok, pertanyaan psikologis, pernyataan kontra-intuitif, atau ancaman halus). Contoh: 'OTAK KAMU SEDANG DIMANIPULASI TANPA KAMU SADAR'\n"
    if hook_candidate:
        hook_rule = f"1. 'hook': Teks hook harus sama persis dengan teks ini: '{hook_candidate}' (Jangan diubah satu kata pun!)\n"

    # ⭐ LEVEL 6 TREND JACKING: Ambil kata kunci yang sedang tren di Indonesia
    trends_prompt = ""
    try:
        trends = get_indonesia_trending_searches()
        if trends:
            trends_prompt = (
                f"\n\nKATA KUNCI TREN INDONESIA HARI INI: {', '.join(trends)}\n"
                f"Jika memungkinkan dan terasa alami, kaitkan atau hubungkan materi konten dengan salah satu tren di atas "
                f"untuk menunggangi gelombang pencarian (Trend Jacking) tanpa memaksakan."
            )
            logger.info("⭐ Level 6: Mengintegrasikan %d tren teratas ke dalam prompt.", len(trends))
    except Exception as e:
        logger.warning("⚠️ Gagal mengintegrasikan tren jacking: %s", e)

    prompt = (
        f"{config['system_prompt']}"
        f"TEMA UTAMA: Konten kali ini HARUS berfokus membahas tentang: {chosen_theme}.\n\n"
        "ATURAN WAJIB:\n"
        f"{hook_rule}"
        "2. 'story': Penjelasan mendalam yang emosional, menggunakan angka/statistik spesifik (misal '93% orang tidak sadar'), analogi sederhana, dan membangun rasa penasaran. MINIMAL 4 kalimat, MAKSIMAL 6 kalimat. Pastikan total kata naskah (hook + story + cta) tidak melebihi 110 kata agar total durasi suara selalu di bawah 60 detik (idealnya 35-50 detik). Gunakan koma dan titik dengan baik agar intonasi suara natural saat dibacakan.\n"
        "3. 'cta': Ajakan bertindak yang personal dan mendesak, maks 2 kalimat. PENTING: Kalimat terakhir dari cta ini HARUS dirancang menggantung di akhir kata dan secara tata bahasa menyambung kembali dengan mulus (seamless loop) ke kata pertama pada kalimat HOOK utama agar video bisa ditonton berulang kali secara melingkar tanpa terputus. Contoh jika HOOK = 'KENAPA KAMU MISKIN', maka akhir CTA bisa berbunyi '...dan itulah alasan utama...' sehingga saat diputar ulang ia tersambung menjadi '...dan itulah alasan utama KENAPA KAMU MISKIN'.\n"
        "4. 'caption': Judul deskripsi postingan TikTok/Shorts yang membuat penasaran, ditambah beberapa hashtag yang sangat viral dan relevan (contoh: #ruangpikir #motivation #mindset #fyp #viral). Panjang maksimal 150 karakter.\n"
        f"5. 'tags': Array berisi 5-10 kata kunci/tag bahasa Inggris yang paling relevan dengan isi video untuk keperluan SEO (misal {config['tags_example']}).\n"
        "6. 'category_id': ID kategori YouTube yang paling cocok untuk jenis konten ini dalam bentuk string (gunakan '22' untuk People & Blogs, atau '27' untuk Education).\n"
        "7. 'interactive_comment': Satu kalimat pertanyaan pancingan diskusi yang sangat interaktif dan memicu penonton untuk berdiskusi/menulis komentar di kolom komentar (maks 15 kata). Contoh: 'Apakah kamu pernah memanipulasi seseorang untuk mendapatkan apa yang kamu mau?'\n"
        "8. 'yt_title': Judul video YouTube yang dioptimasi untuk SEO. Harus kuat, provokatif, mengandung kata kunci utama, dan TIDAK mengandung hashtag. Panjang maksimal 90 karakter. Contoh: 'Fakta Psikologi Gelap yang Tersembunyi di Balik Pujian Bertubi-Tubi'\n"
        "9. 'yt_description': Deskripsi video YouTube yang lengkap dan dioptimasi untuk mesin pencari (SEO). Struktur: (a) 2 kalimat ringkasan konten yang engaging, (b) poin-poin utama yang dibahas (bullet list), (c) kalimat CTA mengajak subscribe dan follow, (d) semua hashtag yang relevan. Total panjang 300-500 karakter. Tulis dalam Bahasa Indonesia.\n"
        f"{ab_test_instruction}\n"
        "GAYA BAHASA: Gunakan Bahasa Indonesia percakapan yang natural, energetik, dan terasa personal seolah berbicara langsung ke satu orang.\n"
        f"OUTPUT: Hanya JSON murni dengan key 'hook', 'story', 'cta', 'caption', 'tags', 'category_id', 'interactive_comment', 'yt_title', dan 'yt_description'. Jika diinstruksikan A/B test, sertakan key 'hook_b'. Tidak ada teks lain di luar JSON.{exclude_prompt}{performance_prompt}{comment_insight_prompt}{trends_prompt}"
    )
    res = await call_gemini_with_retry(prompt, is_json=True, temperature=1.25)
    parsed_json = clean_and_parse_json(res)

    # Jika Gemini menghasilkan Hook alternatif B, simpan untuk run berikutnya
    if isinstance(parsed_json, dict) and "hook_b" in parsed_json:
        try:
            import firebase_connector
            firebase_connector.save_hook_candidate(parsed_json["hook_b"])
        except Exception as e:
            logger.warning("⚠️ Gagal menyimpan hook kandidat B ke database: %s", e)

    if isinstance(parsed_json, dict):
        parsed_json["niche"] = config.get("niche", "Unknown")
        parsed_json["theme"] = chosen_theme

    return parsed_json

async def extract_keywords_from_script(script_text: str, aesthetic_style: str = "dark cinematic") -> list:
    prompt = (
        "You are a professional video director and visual storyteller. Analyze the following vertical short video script and generate exactly 4 highly relevant, visually rich, and contextually precise English search terms for Pexels videos.\n\n"
        "CRITICAL GUIDELINES:\n"
        f"1. MATCH THE AESTHETIC & CONTEXT: Make sure the visuals perfectly match this specific channel's aesthetic: '{aesthetic_style}'. If the aesthetic is stoicism (e.g. roman statue, calm), DO NOT use dark psychology metaphors like 'tense face' or 'puppet strings'. If it is dark psychology, use psychological representations. ALWAYS adhere strictly to the '{aesthetic_style}' vibe.\n"
        f"2. VISUALLY GRAPPLING: Focus on high-contrast, moody, or cinematic concepts that align with '{aesthetic_style}'.\n"
        "3. PEXELS FRIENDLY: Keep terms to 2-3 words, descriptive but concrete (avoid terms Pexels won't have like 'subconscious mind'). Use tangible objects/actions (e.g., 'brain model neon', 'hour glass sand', 'locked door key').\n"
        "4. MOOD CONSISTENCY: Ensure all 4 terms align with the overall tense/mysterious/educational mood of the script.\n\n"
        f"SCRIPT:\n\"{script_text}\"\n\n"
        "OUTPUT FORMAT: Return only a JSON array of strings containing exactly 4 search terms.\n"
        "Example: [\"whispering shadow\", \"puppeteer strings\", \"anxious expression\", \"neon abstract brain\"].\n"
        "No additional text outside the JSON."
    )
    try:
        res = await call_gemini_with_retry(prompt, is_json=True)
        res_data = clean_and_parse_json(res)
        if isinstance(res_data, dict):
            for val in res_data.values():
                if isinstance(val, list): return val
        if isinstance(res_data, list): return res_data
    except Exception as e:
        logger.warning("[%s] Keyword extraction gagal, memakai default: %s", EV_GEMINI_CRASH, e)
    return ["dark abstract", "minimalist", "dark aesthetic", "space galaxy"]


# Daftar voice cadangan Bahasa Indonesia — dirotasi jika voice sebelumnya gagal WordBoundary
VOICE_ROTATION = [
    "id-ID-ArdiNeural",    # Pria utama
    "id-ID-GadisNeural",   # Wanita cadangan 1
]

async def generate_voiceover_resilient(hook: str, story: str, cta: str, path: str, voice_id: str = "id-ID-ArdiNeural", voice_rate: str = "+0%", voice_pitch: str = "+0Hz", attempts: int = 3):
    """Mencoba menghasilkan voiceover dengan rotasi voice jika gagal atau WordBoundary kosong."""
    import random
    last_exception = None
    
    # Salin dan prioritaskan voice yang dipilih, sisanya diacak
    voices = VOICE_ROTATION.copy()
    if voice_id in voices:
        voices.remove(voice_id)
        random.shuffle(voices)
        voices.insert(0, voice_id)
    else:
        random.shuffle(voices)
        if voice_id:
            voices.insert(0, voice_id)
    
    for voice_idx, voice in enumerate(voices):
        for i in range(attempts):
            try:
                result = await generate_voiceover_with_timestamps(hook, story, cta, path, voice=voice, rate=voice_rate, pitch=voice_pitch)
                timestamps, meta = result
                # Jika WordBoundary kosong (akurasi 0), coba voice berikutnya
                if meta.accuracy == 0.0 and voice_idx < len(voices) - 1:
                    logger.warning(
                        " Voice '%s' tidak menghasilkan WordBoundary. Mencoba voice cadangan '%s'...",
                        voice, voices[voice_idx + 1]
                    )
                    break  # Keluar dari loop percobaan, coba voice berikutnya
                return result
            except Exception as e:
                last_exception = e
                logger.warning(" Kegagalan Edge-TTS (voice=%s) percobaan %d/%d: %s", voice, i + 1, attempts, e)
                if i < attempts - 1:
                    await asyncio.sleep(1.5 + i)
        else:
            # Semua percobaan untuk voice ini gagal, lanjut ke voice berikutnya
            if voice_idx < len(voices) - 1:
                logger.warning(" Voice '%s' gagal semua percobaan. Beralih ke voice cadangan...", voice)
                continue
    # Semua voice sudah dicoba
    if last_exception:
        raise last_exception
    raise RuntimeError("Semua voice Edge-TTS gagal menghasilkan voiceover.")



async def run_retention_download(loop, keyword: str) -> list:
    """Mengunduh video retention via yt-dlp secara asinkron (blocking wrapper)."""
    try:
        filename = await loop.run_in_executor(None, download_youtube_retention_video, keyword)
        if filename:
            return [filename]
    except Exception as e:
        logger.warning("⚠️ Gagal mengunduh retention video: %s", e)
    return []

async def run_download_with_retry(loop, keywords: list, target_count: int = 4, aesthetic_style: str = "dark cinematic cold moody tone", max_retry: int = 3) -> list:
    """Poin 4: Mengaktifkan mekanisme Retry internal untuk menangani network glitch download dengan target_count dinamis."""
    for attempt in range(max_retry):
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, download_video_clips, keywords, target_count, aesthetic_style), 
                timeout=DOWNLOAD_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning("[%s] Timeout unduhan terjadi pada percobaan %d/%d.", EV_DOWNLOAD_TIMEOUT, attempt + 1, max_retry)
        except Exception as e:
            logger.warning("[%s] Gangguan jaringan unduhan pada percobaan %d/%d: %s", EV_DOWNLOAD_FAIL, attempt + 1, max_retry, e)
        if attempt < max_retry - 1:
            await asyncio.sleep(2.0 * (attempt + 1))
    return []

async def run_retention_with_fallback(loop, retention_keyword: str, keywords: list, target_count: int, aesthetic_style: str) -> tuple:
    """Mencoba download dari YouTube, jika gagal (misal: bot protection), fallback ke Pexels.
    Return: (results_list, is_fallback_boolean)"""
    results = await run_retention_download(loop, retention_keyword)
    if not results:
        logger.warning("⚠️ YouTube-DL gagal (kemungkinan IP diblokir). Mengaktifkan fallback otomatis ke Pexels/Pixabay...")
        results = await run_download_with_retry(loop, keywords, target_count, aesthetic_style, max_retry=3)
        return results, True
    return results, False


def safe_close_resources(resources: dict, files_to_delete: list):
    logger.info("🧹 Memulai pembersihan resource secara aman...")
    for name, obj in resources.items():
        if obj is not None:
            try:
                obj.close()
            except Exception as ce:
                logger.error(" Gagal menutup resource '%s': %s", name, ce)

    for file_path in files_to_delete:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as fe:
                logger.error(" Gagal menghapus berkas %s: %s", file_path, fe)

async def kill_zombie_ffmpeg_processes(target_file: str):
    """Poin 1: Watchdog OS Tingkat Rendah untuk membunuh proses zombie FFmpeg MoviePy."""
    if psutil is None: return
    logger.warning("[%s] Watchdog mendeteksi hang. Mencari proses FFmpeg terkait handle file...", EV_RENDER_TIMEOUT)
    await asyncio.sleep(0.5)
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'ffmpeg' in proc.info['name'].lower():
                for open_file in proc.open_files():
                    if target_file in open_file.path:
                        logger.error(" Membunuh proses zombie FFmpeg PID %d yang mengunci berkas.", proc.pid)
                        proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

async def create_video(channel_id: str = "ruangpikir") -> bool:
    start_total = time.time()
    moviepy_resources = {"audio_clip": None, "processed_clips": [], "raw_combined_bg": None, "looped_bg": None, "combined_bg": None, "final_video": None}
    video_files = []
    timestamp_suffix = int(time.time())
    vo_file_path = os.path.join(DIR_TEMP, f"vo_{timestamp_suffix}.mp3")
    draft_script_path = os.path.join(DIR_TEMP, "draft_script.json")
    draft_audio_path = os.path.join(DIR_TEMP, "draft_audio.mp3")
    draft_timestamps_path = os.path.join(DIR_TEMP, "draft_timestamps.json")
    
    # Load channel configuration dynamically
    from config import get_channel_config
    channel_cfg = get_channel_config(channel_id)
    niche_description = channel_cfg.get("niche", "dark psychology and human behavior secrets")
    aesthetic_style = channel_cfg.get("aesthetic_query", "dark cinematic cold moody tone")
    voice_id = channel_cfg.get("voice_id", "id-ID-ArdiNeural")
    voice_rate = channel_cfg.get("voice_rate", "+0%")
    voice_pitch = channel_cfg.get("voice_pitch", "+0Hz")
    watermark_name = channel_cfg.get("watermark", "@RuangPikir")
    
    logger.info("🎯 Channel terpilih: %s (Niche: %s)", channel_id, niche_description)

    
    try:
        os.makedirs(DIR_TEMP, exist_ok=True)
        
        # 1. Cek naskah di cache
        script_data = None
        if os.path.exists(draft_script_path):
            try:
                with open(draft_script_path, "r", encoding="utf-8") as f:
                    script_data = json.load(f)
                logger.info("♻️ Menggunakan draf naskah dari cache (%s)", draft_script_path)
            except Exception as e:
                logger.warning(" Gagal memuat draf naskah: %s", e)
                
        if not script_data:
            script_data = await generate_structured_script(channel_cfg)
            with open(draft_script_path, "w", encoding="utf-8") as f:
                json.dump(script_data, f, indent=4, ensure_ascii=False)
            logger.info(" Draf naskah disimpan ke cache (%s)", draft_script_path)
            
        hook = script_data.get("hook", "FAKTA MENARIK").strip()
        story = script_data.get("story", "").strip()
        cta = script_data.get("cta", "Follow untuk info lainnya").strip()
        caption = script_data.get("caption", "Fakta Menarik Hari Ini... #faktapsikologi #ruangpikir #fyp").strip()
        
        keywords = await extract_keywords_from_script(story, aesthetic_style)
        
        # Memilih tema visual secara acak untuk A/B testing
        from subtitle_engine.styles import SubtitleStyles
        import random
        chosen_visual_theme = random.choice(list(SubtitleStyles.THEMES.keys()))
        SubtitleStyles.CHOSEN_THEME = chosen_visual_theme
        logger.info("🎨 A/B Testing: Tema visual terpilih untuk video ini: %s", chosen_visual_theme)

        # Simpan metadata dinamis untuk dibaca uploader di app.py
        tags = script_data.get("tags", ["faktapsikologi", "mindset", "stoikisme", "ruangpikir"])
        category_id = script_data.get("category_id", "22")
        interactive_comment = script_data.get("interactive_comment", "")
        with open(os.path.join(DIR_TEMP, "video_metadata.json"), "w", encoding="utf-8") as f:
            json.dump({
                "caption": caption,
                "tags": tags,
                "category_id": category_id,
                "interactive_comment": interactive_comment,
                "theme": chosen_visual_theme,
                "niche": channel_id,
                "hook": hook
            }, f, indent=4, ensure_ascii=False)
            
        # Simpan ke riwayat untuk mencegah duplikasi/repetisi konten (lewat Firebase / cadangan Lokal)
        try:
            import firebase_connector
            # Cek apakah hook ini sudah terdaftar di riwayat terakhir agar tidak mencatat ganda saat memuat cache
            recent_entries = firebase_connector.get_recent_history(10)
            if not any(item.get("hook") == hook for item in recent_entries):
                firebase_connector.save_to_history(hook, story, cta, caption)
        except Exception as hist_err:
            logger.warning(" Gagal mencatat riwayat naskah: %s", hist_err)
        
        # Estimasi durasi untuk menentukan target count background clip (1 clip = 4 detik)
        total_words = len(hook.split()) + len(story.split()) + len(cta.split())
        estimated_duration = max(10, total_words / 2.2) # Asumsi kecepatan berbicara 2.2 kata per detik
        needed_clips = max(4, int(estimated_duration / 4.0) + 1)
        logger.info(" Menghitung target background clip: estimasi %.1fs -> %d clip (4s/clip)", estimated_duration, needed_clips)
        
        loop = asyncio.get_running_loop()
        
        # 2. Cek audio & timestamps di cache
        reused_audio_and_timestamps = False
        all_timestamps_dataclass = None
        meta = None
        
        if os.path.exists(draft_audio_path) and os.path.exists(draft_timestamps_path):
            try:
                import shutil
                shutil.copy2(draft_audio_path, vo_file_path)
                with open(draft_timestamps_path, "r", encoding="utf-8") as f:
                    ts_data = json.load(f)
                all_timestamps_dataclass = _to_wordtimestamp_list(ts_data["timestamps"])
                from audio import SyncMetadata
                meta = SyncMetadata(
                    matched=ts_data["meta"]["matched"],
                    total=ts_data["meta"]["total"],
                    accuracy=ts_data["meta"]["accuracy"],
                    missed=ts_data["meta"]["missed"],
                    failed_tokens=ts_data["meta"]["failed_tokens"]
                )
                reused_audio_and_timestamps = True
                logger.info("♻️ Menggunakan draf audio & timestamps dari cache")
            except Exception as e:
                logger.warning(" Gagal memuat cache audio & timestamps: %s. Mengulang proses sintesis.", e)
                
        bg_type = channel_cfg.get("background_type", "pexels")
        retention_keyword = channel_cfg.get("retention_keyword", "")
        
        if reused_audio_and_timestamps:
            logger.info(" Menjalankan download background secara mandiri (menggunakan audio cache)...")
            if bg_type == "retention":
                results, is_fallback = await run_retention_with_fallback(loop, retention_keyword, keywords, needed_clips, aesthetic_style)
                if is_fallback:
                    bg_type = "pexels"
            else:
                results = await run_download_with_retry(loop, keywords, target_count=needed_clips, aesthetic_style=aesthetic_style, max_retry=3)
                
            if not results:
                logger.error("[%s] Proses unduh gagal total setelah rentetan retry. Menggunakan fallback.", EV_DOWNLOAD_FAIL)
                video_files = []
            else:
                video_files = results
        else:
            logger.info("⚡ Menjalankan download background dan TTS secara bersamaan...")
            if bg_type == "retention":
                download_task = run_retention_with_fallback(loop, retention_keyword, keywords, needed_clips, aesthetic_style)
            else:
                download_task = run_download_with_retry(loop, keywords, target_count=needed_clips, aesthetic_style=aesthetic_style, max_retry=3)
                
            audio_task = generate_voiceover_resilient(hook, story, cta, vo_file_path, voice_id=voice_id, voice_rate=voice_rate, voice_pitch=voice_pitch, attempts=3)
            
            results = await asyncio.gather(download_task, audio_task, return_exceptions=True)
            
            if isinstance(results[0], Exception) or not results[0]:
                logger.error("[%s] Proses unduh gagal total setelah rentetan retry. Menggunakan fallback.", EV_DOWNLOAD_FAIL)
                video_files = []
            else:
                if bg_type == "retention":
                    video_files, is_fallback = results[0]
                    if is_fallback:
                        bg_type = "pexels"
                else:
                    video_files = results[0]
                
            if isinstance(results[1], Exception):
                raise RuntimeError(f"Gagal menghasilkan audio dari Edge-TTS: {results[1]}") from results[1]
                
            _, (all_timestamps_dataclass, meta) = results
            
            # Simpan hasil baru ke cache
            try:
                import shutil
                shutil.copy2(vo_file_path, draft_audio_path)
                with open(draft_timestamps_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "meta": {
                            "matched": meta.matched,
                            "total": meta.total,
                            "accuracy": meta.accuracy,
                            "missed": meta.missed,
                            "failed_tokens": meta.failed_tokens
                        },
                        "timestamps": _to_dict_list(all_timestamps_dataclass)
                    }, f, indent=4, ensure_ascii=False)
                logger.info(" Audio & timestamps disimpan ke cache")
            except Exception as cache_save_err:
                logger.warning(" Gagal menyimpan cache audio/timestamps: %s", cache_save_err)

        if meta.accuracy < SUBTITLE_MIN_ACCURACY:
            logger.warning(
                "[%s] Akurasi sinkronisasi rendah (%.1f%%). "
                "Pipeline tetap dilanjutkan menggunakan interpolasi timestamp.",
                EV_SUBTITLE_WARN, meta.accuracy * 100
            )
        elif meta.accuracy < 0.90:
            logger.warning("[%s] Peringatan: Akurasi subtitle berada di zona rendah (%.1f%%)", EV_SUBTITLE_WARN, meta.accuracy * 100)

        # ================= POIN 8: OPTIMASI SUBTITLE TIMING PRESISI CAPCUT =================
        logger.info("[%s] Mengoptimalkan timing subtitle dengan Voice Activity Detection...", EV_SUBTITLE_OPTIMIZED)
        try:
            all_timestamps_dataclass = await optimize_subtitle_timing(
                timestamps=all_timestamps_dataclass,
                audio_file_path=vo_file_path,
                target_tokens=[
                    {"word": item["word"], "token": item["display"], "section": item["section"]}
                    for item in [asdict(ts) for ts in all_timestamps_dataclass]
                ],
                enable_vad=True,
                enable_smoothing=True
            )
            logger.info("[%s] Subtitle timing berhasil dioptimalkan untuk sinkronisasi akurat", EV_SUBTITLE_OPTIMIZED)
        except Exception as opt_error:
            logger.warning("[%s] Optimasi timing gagal, melanjutkan dengan timing original: %s", EV_SUBTITLE_OPTIMIZED, opt_error)
        # ==================================================================================

        # ================= GERBANG VALIDASI INVARIANT TIMELINE (FINAL) =================
        # Satu-satunya titik terakhir yang menegakkan aturan timing sebelum dipakai render,
        # terlepas dari apakah optimize_subtitle_timing() di atas berhasil atau gagal (fallback).
        try:
            audio_duration_for_validation = librosa.get_duration(path=vo_file_path)
            all_timestamps_dataclass = validate_timeline_invariants(
                all_timestamps_dataclass, audio_duration_for_validation
            )
            logger.info("[%s] Timeline lolos gerbang validasi invariant.", EV_TIMELINE_VALIDATED)
        except Exception as validate_error:
            logger.warning(
                "[%s] Validasi invariant timeline gagal dieksekusi, melanjutkan tanpa validasi tambahan: %s",
                EV_TIMELINE_VALIDATED, validate_error
            )
        # ==================================================================================

        if not video_files:
            fallback_dir = "assets/fallback"
            if os.path.exists(fallback_dir):
                video_files = [os.path.join(fallback_dir, f) for f in os.listdir(fallback_dir) if f.endswith('.mp4') and os.path.getsize(os.path.join(fallback_dir, f)) > 0]
            if not video_files:
                if os.path.exists("assets/default_portrait.mp4") and os.path.getsize("assets/default_portrait.mp4") > 0:
                    video_files = ["assets/default_portrait.mp4"]
                else:
                    raise RuntimeError(" Tidak ada aset latar belakang yang valid dan lolos inspeksi 0-byte.")
            
        all_timestamps = [asdict(ts) for ts in all_timestamps_dataclass]
            
        from moviepy import AudioFileClip, concatenate_videoclips, CompositeVideoClip, CompositeAudioClip, ColorClip
        try:
            from moviepy.video.fx.loop import Loop
        except ImportError:
            from moviepy.video.fx import Loop
        
        moviepy_resources["audio_clip"] = AudioFileClip(vo_file_path)
        total_duration = moviepy_resources["audio_clip"].duration
        
        # PADDING 0.5 DETIK DI AKHIR VIDEO
        # Agar kalimat / teks terakhir punya "ruang napas" dan tidak terpotong mentah-mentah
        total_duration += 0.5

        # Hitung durasi Hook dari timestamps untuk menentukan pacing
        hook_end = 3.0
        hook_ts = [ts for ts in all_timestamps_dataclass if ts.section == "hook"]
        if hook_ts:
            hook_end = max(ts.end for ts in hook_ts)

        segment_durations = []
        current_time = 0.0
        while current_time < total_duration:
            if current_time < hook_end:
                dur = min(1.2, hook_end - current_time)
                # Jika segmen terakhir di hook terlalu pendek, gabungkan saja
                if segment_durations and current_time < hook_end and (hook_end - current_time) < 0.5:
                    segment_durations[-1] += (hook_end - current_time)
                    current_time = hook_end
                    continue
            else:
                # FAST PACING: Maksimal 2.5 detik per visual klip agar penonton tidak bosan
                dur = min(2.5, total_duration - current_time)
                # Jika segmen terakhir terlalu pendek, gabungkan dengan sebelumnya
                if segment_durations and (total_duration - current_time) < 1.0:
                    segment_durations[-1] += (total_duration - current_time)
                    break
            segment_durations.append(dur)
            current_time += dur

        logger.info("📊 Segmentasi durasi latar belakang: %s", segment_durations)

        if bg_type == "retention" and video_files:
            # Mode Layar Penuh (ASMR/Gameplay)
            import random
            from moviepy import VideoFileClip
            from moviepy.video.fx.colorx import Colorx
            
            file = video_files[0]
            try:
                retention_clip = VideoFileClip(file).with_audio(None)
                max_start = max(0, retention_clip.duration - total_duration)
                start_time = random.uniform(0, max_start)
                
                # Potong klip
                sliced_clip = retention_clip.subclipped(start_time, start_time + total_duration)
                
                # Crop to fit portrait (1080x1920)
                from effects import find_smart_crop_offset, find_smart_crop_offset_vertical
                w, h = sliced_clip.size
                target_ratio = WIDTH / HEIGHT
                current_ratio = w / h
                x1, y1, x2, y2 = 0, 0, w, h
                
                if current_ratio > target_ratio:
                    new_w = int(h * target_ratio)
                    x_offset = find_smart_crop_offset(sliced_clip, new_w)
                    x1 = x_offset
                    x2 = x_offset + new_w
                elif current_ratio < target_ratio:
                    new_h = int(w / target_ratio)
                    y_offset = find_smart_crop_offset_vertical(sliced_clip, new_h)
                    y1 = y_offset
                    y2 = y_offset + new_h
                    
                cropped = sliced_clip.cropped(x1=x1, y1=y1, x2=x2, y2=y2).resized((WIDTH, HEIGHT))
                
                # Gelapkan (dark overlay) sebesar 30% agar teks terbaca jelas
                darkened = cropped.with_effects([Colorx(0.7)])
                
                moviepy_resources["combined_bg"] = darkened
                moviepy_resources["processed_clips"].append(darkened) # for resource tracking
                logger.info("🎬 Menggunakan Full-Screen Retention Background (Start: %.1fs)", start_time)
            except Exception as e:
                logger.error("❌ Gagal memproses retention background: %s", e)
                moviepy_resources["combined_bg"] = ColorClip(size=(WIDTH, HEIGHT), color=(20, 20, 20), duration=total_duration)
        else:
            # Mode Klasik (Pexels / Pixabay)
            for i, dur in enumerate(segment_durations):
                file = video_files[i % len(video_files)]
                try:
                    processed_clip = process_background_clip(file, dur)
                    moviepy_resources["processed_clips"].append(processed_clip)
                except Exception as ce:
                    logger.error(" Kebocoran sub-resource dicegah: %s", ce)
                    if 'processed_clip' in locals() and processed_clip is not None:
                        try: processed_clip.close()
                        except: pass
                    continue
    
            if not moviepy_resources["processed_clips"]:
                logger.warning(" Tidak ada klip video latar belakang yang valid. Menggunakan background warna solid gelap.")
                # Lebar 1080, tinggi 1920 (portrait) sesuai setelan video
                moviepy_resources["combined_bg"] = ColorClip(
                    size=(WIDTH, HEIGHT), color=(20, 20, 20), duration=total_duration
                )
            else:
                moviepy_resources["raw_combined_bg"] = concatenate_videoclips(moviepy_resources["processed_clips"], method="compose")
                bg_duration = moviepy_resources["raw_combined_bg"].duration
                
                if bg_duration < total_duration:
                    loop_factor = int(total_duration / bg_duration) + 1
                    moviepy_resources["looped_bg"] = moviepy_resources["raw_combined_bg"].with_effects([Loop(n=loop_factor)])
                    moviepy_resources["combined_bg"] = moviepy_resources["looped_bg"].subclipped(0, total_duration)
                else:
                    moviepy_resources["combined_bg"] = moviepy_resources["raw_combined_bg"].subclipped(0, total_duration)

        # Poin 5: Konsep Smoothing/Interpolasi Teks.
        valid_words = []
        for x in all_timestamps:
            sec = x["section"]
            thresh = CONFIDENCE_THRESHOLD_HOOK if sec == "hook" else (CONFIDENCE_THRESHOLD_BODY if sec == "story" else CONFIDENCE_THRESHOLD_CTA)
            
            x["is_blurred_fallback"] = x["confidence"] < thresh
            valid_words.append(x)
        
        hook_words = [x for x in valid_words if x["section"] == "hook"]
        story_words = [x for x in valid_words if x["section"] == "story"]
        cta_words = [x for x in valid_words if x["section"] == "cta"]

        engine_v3 = SubtitleEngineV2()
        all_text_clips = []

        # Pastikan subtitle tidak melampaui durasi final (hindari trailing frames)
        all_text_clips.extend(engine_v3.generate_subtitle_clips(hook_words, font_size=FONT_SIZE_HOOK, style_type="hook", max_total_duration=total_duration))
        all_text_clips.extend(engine_v3.generate_subtitle_clips(story_words, font_size=FONT_SIZE_BODY, style_type="body", max_total_duration=total_duration))
        all_text_clips.extend(engine_v3.generate_subtitle_clips(cta_words, font_size=FONT_SIZE_BODY, style_type="cta", max_total_duration=total_duration))

        moviepy_resources["final_video"] = CompositeVideoClip([moviepy_resources["combined_bg"]] + all_text_clips, use_bgclip=True)

        # ================= MUSIK LATAR OTOMATIS =================
        bg_music_clip = None
        music_dir = os.path.join(os.path.dirname(__file__), "assets", "music")
        music_extensions = (".mp3", ".wav", ".ogg", ".m4a")
        sfx_names = {"whoosh.wav", "pop.wav", "glitch.wav", "sub_drop.wav", "heartbeat.wav", "rain_noise.wav", "soft_swish.wav", "soft_tick.wav"}
        
        os.makedirs(music_dir, exist_ok=True)
        music_files = [f for f in os.listdir(music_dir) if f.lower().endswith(music_extensions) and f not in sfx_names]
        
        if not music_files:
            logger.info(" Folder assets/music/ kosong. Mengunduh backsound gratis bebas hak cipta secara otomatis...")
            import urllib.request
            import random
            
            # List lagu dark/cinematic stoic dari Incompetech (Kevin MacLeod)
            free_tracks = [
                ("Dark_Times.mp3", "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Dark%20Times.mp3"),
                ("Dark_Fog.mp3", "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Dark%20Fog.mp3"),
                ("Echoes_of_Time.mp3", "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Echoes%20of%20Time.mp3"),
                ("Anxiety.mp3", "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Anxiety.mp3"),
                ("Distant_Tension.mp3", "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Distant%20Tension.mp3")
            ]
            chosen_track_name, chosen_track_url = random.choice(free_tracks)
            download_dest = os.path.join(music_dir, chosen_track_name)
            try:
                # Unduh file BGM dengan user agent agar tidak diblokir
                req = urllib.request.Request(
                    chosen_track_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req, timeout=30) as response:
                    with open(download_dest, "wb") as out_file:
                        out_file.write(response.read())
                logger.info(" Berhasil mengunduh backsound otomatis: %s", chosen_track_name)
                music_files = [chosen_track_name]
            except Exception as dl_err:
                logger.warning(" Gagal mengunduh backsound otomatis dari Incompetech: %s. Melanjutkan tanpa musik.", dl_err)
                
        if music_files:
            import random
            chosen_music = os.path.join(music_dir, random.choice(music_files))
            try:
                bg_music_raw = AudioFileClip(chosen_music)
                moviepy_resources["bg_music_clip"] = bg_music_raw
                # Potong atau loop musik agar sesuai durasi video
                if bg_music_raw.duration < total_duration:
                    loops_needed = int(total_duration / bg_music_raw.duration) + 1
                    import itertools
                    music_clips = [bg_music_raw] * loops_needed
                    from moviepy import concatenate_audioclips
                    bg_music_clip = concatenate_audioclips(music_clips).subclipped(0, total_duration)
                else:
                    bg_music_clip = bg_music_raw.subclipped(0, total_duration)
                # Volume musik latar -20dB (sekitar 10% dari suara utama)
                from moviepy.audio.fx import MultiplyVolume
                bg_music_clip = bg_music_clip.with_effects([MultiplyVolume(0.10)])
                logger.info("🎵 Musik latar berhasil dimuat: %s", chosen_music)
            except Exception as me:
                logger.warning(" Gagal memuat musik latar: %s. Melanjutkan tanpa musik.", me)
                bg_music_clip = None
        # ================= TRANSISI SOUND EFFECTS (SFX) & ADVANCED AUDIO DESIGN =================
        sfx_clips = []
        music_dir = os.path.join(os.path.dirname(__file__), "assets", "music")
        
        # Helper untuk memuat SFX pendek ke memori tanpa bug FFMPEG_AudioReader MoviePy
        def load_sfx(filepath):
            import scipy.io.wavfile as wav
            import numpy as np
            from moviepy.audio.AudioClip import AudioArrayClip
            fps, data = wav.read(filepath)
            if data.dtype == np.int16:
                data = data.astype(np.float32) / 32768.0
            if len(data.shape) == 1:
                data = np.vstack((data, data)).T
            return AudioArrayClip(data, fps=fps)

        # 1. Soft Swish / Glitch untuk transisi visual
        trans_path = os.path.join(music_dir, "glitch.wav" if channel_id == "ruangpikir" else "soft_swish.wav")
        if os.path.exists(trans_path):
            try:
                trans_base = load_sfx(trans_path)
                moviepy_resources["trans_base"] = trans_base
                t_transition = 0.0
                for dur in segment_durations[:-1]:
                    t_transition += dur
                    if t_transition < total_duration - 1.0:
                        clip_len = min(trans_base.duration, 0.8)
                        # Terapkan efek DULU, baru set start dan end agar tidak tertimpa wrapper
                        from moviepy.audio.fx import MultiplyVolume
                        sfx_item = trans_base.subclipped(0, clip_len).with_effects([MultiplyVolume(0.12)])
                        s_time = t_transition - (0.05 if channel_id == "ruangpikir" else 0.2)
                        sfx_item = sfx_item.with_start(s_time).with_end(s_time + clip_len)
                        
                        # Probabilitas 60% agar tidak selalu muncul
                        if random.random() < 0.6:
                            sfx_clips.append(sfx_item)
                logger.info(" SFX Transisi berhasil dimuat.")
            except Exception as e:
                logger.warning(" Gagal memuat SFX transisi: %s", e)
                
        # 2. Sub Drop (Hanya 1x di detik 0.0 untuk efek kejut subliminal)
        sub_path = os.path.join(music_dir, "sub_drop.wav")
        if os.path.exists(sub_path):
            try:
                sub_base = load_sfx(sub_path)
                moviepy_resources["sub_base"] = sub_base
                from moviepy.audio.fx import MultiplyVolume
                clip_len = min(sub_base.duration, 2.0)
                sfx_item = sub_base.subclipped(0, clip_len).with_effects([MultiplyVolume(0.20)])
                sfx_item = sfx_item.with_start(0.0).with_end(clip_len)
                sfx_clips.append(sfx_item)
            except Exception as e:
                logger.warning(" Gagal memuat Sub Drop: %s", e)

        # 3. Heartbeat (Hanya untuk channel psikologi/stoik)
        heartbeat_path = os.path.join(music_dir, "heartbeat.wav")
        if os.path.exists(heartbeat_path) and channel_id == "ruangpikir":
            try:
                hb_base = load_sfx(heartbeat_path)
                moviepy_resources["hb_base"] = hb_base
                hb_len = hb_base.duration
                # Mainkan setiap 4 detik
                import numpy as np
                for t in np.arange(2.0, total_duration - 2.0, 4.0):
                    from moviepy.audio.fx import MultiplyVolume
                    sfx_item = hb_base.with_effects([MultiplyVolume(0.15)])
                    sfx_item = sfx_item.with_start(float(t)).with_end(float(t) + hb_len)
                    sfx_clips.append(sfx_item)
            except Exception as e:
                logger.warning(" Gagal memuat Heartbeat: %s", e)
                
        # 4. Soft Tick (Untuk setiap kata yang muncul, volume sangat pelan 8%)
        tick_path = os.path.join(music_dir, "soft_tick.wav")
        if os.path.exists(tick_path) and all_timestamps:
            try:
                tick_base = load_sfx(tick_path)
                moviepy_resources["tick_base"] = tick_base
                tick_len = tick_base.duration
                for ts in all_timestamps:
                    start_t = ts["start"]
                    if start_t < total_duration:
                        from moviepy.audio.fx import MultiplyVolume
                        sfx_item = tick_base.with_effects([MultiplyVolume(0.08)])
                        sfx_item = sfx_item.with_start(start_t).with_end(start_t + tick_len)
                        sfx_clips.append(sfx_item)
                logger.info(" SFX Ticks berhasil ditambahkan untuk %d kata.", len(all_timestamps))
            except Exception as e:
                logger.warning(" Gagal memuat Soft Tick: %s", e)

        # 5. Rain Noise (Ambience pad)
        rain_path = os.path.join(music_dir, "rain_noise.wav")
        if os.path.exists(rain_path):
            try:
                rain_base = AudioFileClip(rain_path)
                moviepy_resources["rain_base"] = rain_base
                # loop rain
                if rain_base.duration < total_duration:
                    loops_needed = int(total_duration / rain_base.duration) + 1
                    rain_clips = [rain_base] * loops_needed
                    from moviepy import concatenate_audioclips
                    rain_clip = concatenate_audioclips(rain_clips).subclipped(0, total_duration)
                else:
                    rain_clip = rain_base.subclipped(0, total_duration)
                from moviepy.audio.fx import MultiplyVolume
                rain_clip = rain_clip.with_effects([MultiplyVolume(0.10)]) # 10%
                sfx_clips.append(rain_clip)
            except Exception as e:
                logger.warning(" Gagal memuat Rain Ambience: %s", e)
                
        # Gabungkan audio TTS + musik latar + SFX
        audio_sources = [moviepy_resources["audio_clip"]]
        if bg_music_clip is not None:
            audio_sources.append(bg_music_clip)
        if sfx_clips:
            audio_sources.extend(sfx_clips)
            
        try:
            final_audio = CompositeAudioClip(audio_sources)
            moviepy_resources["final_video"] = moviepy_resources["final_video"].with_audio(final_audio)
            logger.info(" Audio final: TTS + Musik Latar + %d SFX Transisi digabungkan.", len(sfx_clips))
        except Exception as mix_err:
            logger.error(" Gagal menggabungkan audio composite: %s. Melanjutkan dengan audio utama.", mix_err)
            moviepy_resources["final_video"] = moviepy_resources["final_video"].with_audio(moviepy_resources["audio_clip"])
        # =========================================================


        output_file_name = f"final_output_{timestamp_suffix}.mp4"
        output_file_path = os.path.join(DIR_OUTPUT, output_file_name)
        temp_output_path = f"{output_file_path}.tmp.mp4"

        # ================= WATERMARK & VISUAL CTA =================
        try:
            from overlay import apply_text_watermark, apply_visual_cta
            import config as _config

            moviepy_resources["final_video"] = apply_text_watermark(
                moviepy_resources["final_video"], channel_name=watermark_name
            )
            logger.info(" Watermark channel berhasil ditambahkan.")

            # Hanya tampilkan visual CTA jika diizinkan oleh konfigurasi
            if getattr(_config, "ENABLE_VISUAL_CTA", True):
                moviepy_resources["final_video"] = apply_visual_cta(moviepy_resources["final_video"])
                logger.info(" Visual CTA berhasil ditambahkan di 3 detik terakhir video.")
            else:
                logger.info(" Visual CTA dinonaktifkan oleh konfigurasi.")
        except Exception as wm_err:
            logger.warning(" Watermark/CTA dilewati: %s", wm_err)
        # Pastikan durasi final video persis sama dengan durasi audio (hindari padding/freep frames)
        try:
            moviepy_resources["final_video"] = moviepy_resources["final_video"].with_duration(total_duration)
        except Exception as e:
            # Jika with_duration gagal, lanjutkan tanpa crash
            logger.debug(f"Tidak bisa memaksa with_duration pada final_video: {e}, melanjutkan.")
        # ======================================================

        os.makedirs(DIR_OUTPUT, exist_ok=True)
        cpu_threads = min(THREADS_MAX, os.cpu_count() or 2)

        
        def execute_ffmpeg_render(target_path: str):
            moviepy_resources["final_video"].write_videofile(
                target_path, fps=30, codec="libx264", preset="veryfast", # OPTIMASI: Kecepatan & kompresi seimbang
                audio_codec="aac", threads=cpu_threads, logger=None,
                ffmpeg_params=["-crf", "30", "-pix_fmt", "yuv420p"]      # OPTIMASI: Kompresi optimal untuk batas 50MB Telegram
            )

        render_timeout = total_duration * RENDER_TIMEOUT_FACTOR
        logger.info("[%s] Memulai proses kompilasi ffmpeg dengan %d utas core...", EV_RENDER_START, cpu_threads)
        
        try:
            await asyncio.wait_for(loop.run_in_executor(None, execute_ffmpeg_render, temp_output_path), timeout=render_timeout)
        except asyncio.TimeoutError:
            logger.error("[%s] Batas rendering terlampaui. Memicu pembunuhan paksa subproses OS FFmpeg.", EV_RENDER_TIMEOUT)
            await kill_zombie_ffmpeg_processes(temp_output_path)
            if os.path.exists(temp_output_path):
                try: os.remove(temp_output_path)
                except OSError: pass
            return False
        except Exception as render_error:
            logger.warning("[%s] Gangguan rendering FFmpeg pertama: %s. Melakukan upaya darurat...", EV_RENDER_FAIL, render_error)
            await kill_zombie_ffmpeg_processes(temp_output_path)
            if os.path.exists(temp_output_path):
                try: os.remove(temp_output_path)
                except OSError: pass
            await asyncio.sleep(2)
            try:
                await asyncio.wait_for(loop.run_in_executor(None, execute_ffmpeg_render, temp_output_path), timeout=render_timeout)
            except Exception:
                logger.error("[%s] Upaya render darurat kedua gagal total.", EV_RENDER_FAIL)
                await kill_zombie_ffmpeg_processes(temp_output_path)
                return False
            
        if not os.path.exists(temp_output_path) or os.path.getsize(temp_output_path) == 0:
            logger.error("[%s] File hasil render rusak/0-byte. Menggagalkan transaksi berkas.", EV_RENDER_FAIL)
            if os.path.exists(temp_output_path): os.remove(temp_output_path)
            return False
            
        os.replace(temp_output_path, output_file_path)
        
        ram_mb = 0.0
        if psutil is not None:
            try: ram_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
            except: pass
        
        # Bersihkan cache draf naskah & audio karena rendering berhasil sempurna
        for cp in [draft_script_path, draft_audio_path, draft_timestamps_path]:
            if os.path.exists(cp):
                try: os.remove(cp)
                except OSError: pass

        logger.info("[%s] Autopilot Berhasil. Total Waktu: %.2fs | RAM: %.2f MB | Output: %s", EV_PIPELINE_SUCCESS, time.time() - start_total, ram_mb, output_file_name)
        return True
        
    except Exception:
        logger.exception("[%s] Malfungsi sistem pada alur pipa eksekusi", EV_RENDER_FAIL)
        return False
        
    finally:
        if 'temp_output_path' in locals() and os.path.exists(temp_output_path):
            try: os.remove(temp_output_path)
            except OSError: pass
            
        clips_to_close = {
            "audio_clip": moviepy_resources["audio_clip"], "raw_combined_bg": moviepy_resources["raw_combined_bg"],
            "looped_bg": moviepy_resources["looped_bg"], "combined_bg": moviepy_resources["combined_bg"], "final_video": moviepy_resources["final_video"]
        }
        for idx, cp in enumerate(moviepy_resources["processed_clips"]):
            clips_to_close[f"processed_clip_{idx}"] = cp

        clean_video_files = video_files if isinstance(video_files, list) else []
        safe_close_resources(clips_to_close, clean_video_files + [vo_file_path])
