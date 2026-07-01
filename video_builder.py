import os
import json
import time
import asyncio
from google import genai
from google.genai import types

# Import konfigurasi global dan modul pendukung terpisah
from config import GEMINI_KEYS, DIR_OUTPUT, FONT_SIZE_HOOK, FONT_SIZE_BODY
from downloader import download_video_clips
from effects import process_background_clip
from subtitle_engine.orchestrator import SubtitleEngineV2
from audio import generate_voiceover_edge

# Indeks global untuk melacak API Key yang sedang aktif
current_key_index = 0

def get_next_client():
    """Mengambil Google GenAI Client berikutnya dari daftar rotasi jika terjadi limit kuota."""
    global current_key_index
    if not GEMINI_KEYS:
        raise ValueError("❌ Tidak ada GEMINI_API_KEY yang ditemukan di GitHub Secrets.")
        
    if current_key_index >= len(GEMINI_KEYS):
        print("🔄 Semua API Key di dalam daftar sudah dicoba. Mengulang kembali dari kunci pertama...")
        current_key_index = 0
        
    active_key = GEMINI_KEYS[current_key_index]
    masked_key = f"{active_key[:8]}...{active_key[-4:]}" if len(active_key) > 12 else "INVALID_KEY"
    print(f"🔑 Menggunakan API Key Slot-{current_key_index + 1} ({masked_key})")
    
    return genai.Client(api_key=active_key)

def generate_structured_script():
    """Fungsi Tahap 1: Meminta Gemini membuat naskah JSON dengan proteksi failover ketat (429 & 503)."""
    global current_key_index
    print("🧠 Gemini sedang merancang naskah berstruktur dengan variasi topik otomatis...")
    
    prompt = (
        "Buat satu konten edukasi pendek yang siap pakai untuk TikTok Shorts.\n"
        "Pilih secara acak SALAH SATU dari tema besar berikut untuk setiap kali generate:\n"
        "1. Fakta Psikologi Manusia (Unik, jarang diketahui, atau mind-blowing).\n"
        "2. Filosofi Stoikisme / Trik Mental (Cara mengatasi stres, tetap tenang, seni tidak peduli).\n"
        "3. Dark Psychology / Bahasa Tubuh (Cara membaca pikiran orang, tanda orang bohong, proteksi manipulasi).\n"
        "4. Produktivitas & Mindset Orang Sukses (Trik berhenti menunda/prokrastinasi, kebiasaan fokus pagi hari).\n\n"
        "Konten harus terbagi menjadi 3 bagian utuh dalam format JSON:\n"
        "1. 'hook': Kalimat pembuka singkat penarik perhatian di 3 detik pertama (Gunakan huruf kapital, contoh: 'RAHASIA MENTAL YANG JARANG ORANG TAHU...').\n"
        "2. 'story': Isi materi/penjelasannya (Bahasa Indonesia, 2-3 kalimat, padat, jelas, dan tuntas).\n"
        "3. 'cta': Kalimat ajakan di akhir video untuk memicu komentar/follow (Contoh: 'Komen jika kamu butuh trik seperti ini lagi').\n\n"
        "ATURAN PENTING UNTUK INTERPRETASI SUARA (TEXT-TO-SPEECH):\n"
        "- Wajib gunakan tanda koma (,) di tengah kalimat jika ada pergantian ide agar robot TTS mengambil jeda napas pendek.\n"
        "- Wajib gunakan tanda titik (.) di akhir kalimat agar robot TTS berhenti sejenak sebelum masuk ke kalimat berikutnya.\n"
        "- Jangan buat kalimat yang terlalu panjang tanpa jeda tanda baca agar suara tidak terdengar terburu-buru.\n\n"
        "Format JSON harus valid, bersih, tanpa markdown."
    )
    
    max_attempts = max(5, len(GEMINI_KEYS) * 2)
    for attempt in range(max_attempts):
        try:
            client = get_next_client()
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(response.text.strip())
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "503" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "UNAVAILABLE" in err_msg:
                print(f"⚠️ Slot-{current_key_index + 1} bermasalah ({err_msg[:80]}).")
                current_key_index += 1
                if attempt < max_attempts - 1:
                    print("🔄 Otomatis beralih ke API Key cadangan berikutnya tanpa mematikan sistem...")
                    time.sleep(1)
                    continue
            raise e

def extract_keywords_from_script(script_text: str) -> list:
    """Fungsi Tahap 2: AI mengekstrak kata kunci visual dengan sistem proteksi failover."""
    global current_key_index
    print("🧠 AI sedang menganalisis isi cerita untuk mengekstrak keyword visual...")
    
    prompt = (
        f"Baca naskah video berikut dan berikan 4 kata kunci (keyword) dalam bahasa Inggris "
        f"yang paling cocok untuk mencari video latar belakang yang estetis di Pexels.\n"
        f"Naskah: \"{script_text}\"\n"
        f"Berikan hasil dalam format JSON array bertipe string. Contoh: [\"mind\", \"thinking\", \"human\", \"dark\"]"
    )
    
    max_attempts = max(5, len(GEMINI_KEYS) * 2)
    for attempt in range(max_attempts):
        try:
            client = get_next_client()
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(response.text.strip())
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "503" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "UNAVAILABLE" in err_msg:
                print(f"⚠️ Slot-{current_key_index + 1} bermasalah saat ekstraksi keyword.")
                current_key_index += 1
                if attempt < max_attempts - 1:
                    print("🔄 Otomatis beralih ke API Key cadangan berikutnya...")
                    time.sleep(1)
                    continue
            print(f"⚠️ Gagal mengekstrak keyword kustom: {e}. Menggunakan keyword fallback.")
            return ["mind", "abstract", "human", "moody"]

async def create_video() -> bool:
    """Orchestrator Utama Pipeline Perakitan Video TikTok Shorts."""
    processed_clips = []
    audio_clip = None
    combined_bg = None
    final_video = None
    
    try:
        # 1. Pembuatan Naskah Teks Konten Bervariasi
        script_data = generate_structured_script()
        hook = script_data.get("hook", "FAKTA MENARIK").strip()
        story = script_data.get("story", "").strip()
        cta = script_data.get("cta", "Follow untuk info lainnya").strip()
        
        full_text = f"{hook}. {story} {cta}"
        
        # 2. Ekstraksi Kata Kunci Kontekstual Berbasis AI
        keywords = extract_keywords_from_script(story)
        
        # 3. Pengunduhan Klip Video yang Relevan via downloader.py
        video_files = download_video_clips(keywords, target_count=4)
        
        # 4. Pembuatan Audio Narasi via audio.py
        vo_file_path = "temp/vo.mp3"
        os.makedirs("temp", exist_ok=True)
        await generate_voiceover_edge(full_text, vo_file_path)
        
        from moviepy import AudioFileClip, concatenate_videoclips, CompositeVideoClip
        
        audio_clip = AudioFileClip(vo_file_path)
        total_duration = audio_clip.duration

        # 5. Pemrosesan Efek Visual dan Transisi Background via effects.py
        clip_count = len(video_files)
        duration_per_clip = total_duration / clip_count
        
        print("🎬 Memotong klip dan menyuntikkan efek Zoom In dinamis...")
        for file in video_files:
            processed_clip = process_background_clip(file, duration_per_clip)
            processed_clips.append(processed_clip)
            
        combined_bg = concatenate_videoclips(processed_clips, method="compose").with_duration(total_duration)

        # 6. PERBAIKAN SINKRONISASI: Hitung bobot durasi segmen berdasarkan jumlah karakter teks (Proporsional)
        len_hook = len(hook)
        len_story = len(story)
        len_cta = len(cta)
        total_len = len_hook + len_story + len_cta

        # Distribusikan total duration secara adil sesuai panjang teks asli
        hook_duration = (len_hook / total_len) * total_duration
        story_duration = (len_story / total_len) * total_duration
        cta_duration = (len_cta / total_len) * total_duration

        engine_v3 = SubtitleEngineV2()
        all_text_clips = []

        # Render Teks Hook dengan start_time linear terhitung
        all_text_clips.extend(engine_v3.generate_subtitle_clips(hook, 0, hook_duration, font_size=FONT_SIZE_HOOK, style_type="hook"))
        
        # Render Teks Story tepat setelah Hook selesai
        all_text_clips.extend(engine_v3.generate_subtitle_clips(story, hook_duration, story_duration, font_size=FONT_SIZE_BODY, style_type="body"))
        
        # Render Teks CTA tepat setelah Story selesai
        all_text_clips.extend(engine_v3.generate_subtitle_clips(cta, hook_duration + story_duration, cta_duration, font_size=FONT_SIZE_BODY, style_type="cta"))

        # 7. Komposisi Akhir dan Ekspor Render Video
        final_video = CompositeVideoClip([combined_bg] + all_text_clips, use_bgclip=True)
        final_video = final_video.with_audio(audio_clip)

        output_file_path = os.path.join(DIR_OUTPUT, "final_output.mp4")
        os.makedirs(DIR_OUTPUT, exist_ok=True)
        
        print("🔄 Memulai proses ekspor video kualitas tinggi (output/final_output.mp4)...")
        final_video.write_videofile(
            output_file_path, 
            fps=30, 
            codec="libx264", 
            audio_codec="aac",
            threads=4
        )
        
        # 8. Pembersihan Memori & Objek
        audio_clip.close()
        final_video.close()
        combined_bg.close()
        for clip in processed_clips:
            clip.close()
            
        for file in video_files:
            if os.path.exists(file):
                os.remove(file)
        if os.path.exists(vo_file_path):
            os.remove(vo_file_path)
            
        print("🎉 Sukses Besar! Perakitan video sinkron selesai.")
        return True
        
    except Exception as e:
        print(f"❌ Gagal mengeksekusi pipeline di video_builder: {e}")
        if audio_clip: audio_clip.close()
        if final_video: final_video.close()
        if combined_bg: combined_bg.close()
        for clip in processed_clips: clip.close()
        return False
