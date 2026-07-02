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

from config import GEMINI_KEYS, DIR_OUTPUT, FONT_SIZE_HOOK, FONT_SIZE_BODY

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
    RENDER_TIMEOUT_FACTOR = 15.0 # OPTIMASI TINGKAT EKSTRIM: Memberikan kelonggaran waktu 15x durasi video
    CONFIDENCE_THRESHOLD_HOOK = 0.30
    CONFIDENCE_THRESHOLD_BODY = 0.45
    CONFIDENCE_THRESHOLD_CTA = 0.60

# Memastikan RENDER_TIMEOUT_FACTOR tetap tinggi jika ter-import dari config lama
RENDER_TIMEOUT_FACTOR = 15.0 

from downloader import download_video_clips
from effects import process_background_clip
from subtitle_engine.orchestrator import SubtitleEngineV2
from audio import generate_voiceover_with_timestamps, validate_timeline_invariants
from audio_sync_optimizer import optimize_subtitle_timing

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

async def call_gemini_with_retry(prompt: str, is_json: bool = True) -> str:
    max_attempts = max(5, len(GEMINI_KEYS) * 2)
    config = types.GenerateContentConfig(response_mime_type="application/json" if is_json else None)
    
    for attempt in range(max_attempts):
        client, idx = await client_pool.get_client_and_rotate()
        try:
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=config)
            return response.text.strip()
        except Exception as e:
            err_msg = str(e)
            if any(x.lower() in err_msg.lower() for x in RETRY_ERRORS):
                backoff_delay = 2 ** attempt
                logger.warning("[%s] Eror terdeteksi. Karantina Slot-%d. Backoff %d detik.", EV_GEMINI_ROTATION, idx + 1, backoff_delay)
                await client_pool.set_cooldown(idx, duration=60 + backoff_delay)
                await asyncio.sleep(backoff_delay)
                continue
            logger.exception("[%s] Gangguan fatal internal API Gemini", EV_GEMINI_CRASH)
            raise e
    raise RuntimeError("Batas maksimum percobaan API Gemini terlampaui.")

async def generate_structured_script() -> dict:
    logger.info("🧠 Gemini sedang merancang naskah berstruktur otomatis...")
    prompt = (
        "Buat satu konten edukasi pendek untuk TikTok Shorts dalam format JSON.\n"
        "Pilih secara acak tema: Fakta Psikologi, Stoikisme, Dark Psychology, atau Mindset Sukses.\n"
        "Format JSON wajib memiliki 3 key: 'hook' (kapital), 'story', dan 'cta'.\n"
        "Gunakan tanda baca koma dan titik dengan baik agar intonasi suara natural."
    )
    res = await call_gemini_with_retry(prompt, is_json=True)
    return clean_and_parse_json(res)

async def extract_keywords_from_script(script_text: str) -> list:
    prompt = f"Berikan 4 kata kunci visual bahasa Inggris dalam bentuk JSON array langsung untuk mencari video latar belakang naskah ini: \"{script_text}\""
    try:
        res = await call_gemini_with_retry(prompt, is_json=True)
        res_data = clean_and_parse_json(res)
        if isinstance(res_data, dict):
            for val in res_data.values():
                if isinstance(val, list): return val
        if isinstance(res_data, list): return res_data
    except Exception as e:
        logger.warning("[%s] Keyword extraction gagal, memakai default: %s", EV_GEMINI_CRASH, e)
    return ["mind", "abstract", "human"]

async def generate_voiceover_resilient(hook: str, story: str, cta: str, path: str, attempts: int = 3):
    for i in range(attempts):
        try:
            return await generate_voiceover_with_timestamps(hook, story, cta, path)
        except Exception as e:
            logger.warning("⚠️ Kegagalan Edge-TTS pada percobaan %d/%d: %s", i + 1, attempts, e)
            if i == attempts - 1: raise
            await asyncio.sleep(1.5 + i)

async def run_download_with_retry(loop, keywords: list, max_retry: int = 3) -> list:
    """Poin 4: Mengaktifkan mekanisme Retry internal untuk menangani network glitch download."""
    for attempt in range(max_retry):
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, download_video_clips, keywords, 4), 
                timeout=DOWNLOAD_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning("[%s] Timeout unduhan terjadi pada percobaan %d/%d.", EV_DOWNLOAD_TIMEOUT, attempt + 1, max_retry)
        except Exception as e:
            logger.warning("[%s] Gangguan jaringan unduhan pada percobaan %d/%d: %s", EV_DOWNLOAD_FAIL, attempt + 1, max_retry, e)
        if attempt < max_retry - 1:
            await asyncio.sleep(2.0 * (attempt + 1))
    return []

def safe_close_resources(resources: dict, files_to_delete: list):
    logger.info("🧹 Memulai pembersihan resource secara aman...")
    for name, obj in resources.items():
        if obj is not None:
            try:
                obj.close()
            except Exception as ce:
                logger.error("⚠️ Gagal menutup resource '%s': %s", name, ce)

    for file_path in files_to_delete:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as fe:
                logger.error("⚠️ Gagal menghapus berkas %s: %s", file_path, fe)

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
                        logger.error("💀 Membunuh proses zombie FFmpeg PID %d yang mengunci berkas.", proc.pid)
                        proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

async def create_video() -> bool:
    start_total = time.time()
    moviepy_resources = {"audio_clip": None, "processed_clips": [], "raw_combined_bg": None, "looped_bg": None, "combined_bg": None, "final_video": None}
    video_files = []
    timestamp_suffix = int(time.time())
    vo_file_path = f"temp/vo_{timestamp_suffix}.mp3"
    
    try:
        script_data = await generate_structured_script()
        hook = script_data.get("hook", "FAKTA MENARIK").strip()
        story = script_data.get("story", "").strip()
        cta = script_data.get("cta", "Follow untuk info lainnya").strip()
        
        keywords = await extract_keywords_from_script(story)
        os.makedirs("temp", exist_ok=True)
        
        logger.info("⚡ Menjalankan download background dan TTS secara bersamaan...")
        loop = asyncio.get_running_loop()
        
        download_task = run_download_with_retry(loop, keywords, max_retry=3)
        audio_task = generate_voiceover_resilient(hook, story, cta, vo_file_path, attempts=3)
        
        results = await asyncio.gather(download_task, audio_task, return_exceptions=True)
        
        if isinstance(results[0], Exception) or not results[0]:
            logger.error("[%s] Proses unduh gagal total setelah rentetan retry. Menggunakan fallback.", EV_DOWNLOAD_FAIL)
            video_files = []
        else:
            video_files = results[0]
            
        if isinstance(results[1], Exception):
            raise RuntimeError(f"Gagal menghasilkan audio dari Edge-TTS: {results[1]}") from results[1]
            
        _, (all_timestamps_dataclass, meta) = results

        if meta.accuracy < SUBTITLE_MIN_ACCURACY:
            raise RuntimeError(f"[{EV_SUBTITLE_REJECT}] Akurasi sinkronisasi subtitle di bawah batas toleransi produksi: {meta.accuracy*100:.1f}%")
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
                    raise RuntimeError("❌ Tidak ada aset latar belakang yang valid dan lolos inspeksi 0-byte.")
            
        all_timestamps = [asdict(ts) for ts in all_timestamps_dataclass]
            
        from moviepy import AudioFileClip, concatenate_videoclips, CompositeVideoClip
        try:
            from moviepy.video.fx.loop import Loop
        except ImportError:
            from moviepy.video.fx import Loop
        
        moviepy_resources["audio_clip"] = AudioFileClip(vo_file_path)
        total_duration = moviepy_resources["audio_clip"].duration

        clip_count = len(video_files)
        duration_per_clip = (total_duration / max(1, clip_count)) + 3.0
        
        for file in video_files:
            try:
                processed_clip = process_background_clip(file, duration_per_clip)
                moviepy_resources["processed_clips"].append(processed_clip)
            except Exception as ce:
                logger.error("⚠️ Kebocoran sub-resource dicegah. Melepas berkas korup [%s]: %s", file, ce)
                if 'processed_clip' in locals() and processed_clip is not None:
                    try: processed_clip.close()
                    except: pass
                continue

        if not moviepy_resources["processed_clips"]:
            raise RuntimeError("❌ Tidak ada klip video latar belakang yang valid.")
            
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

        all_text_clips.extend(engine_v3.generate_subtitle_clips(hook_words, font_size=FONT_SIZE_HOOK, style_type="hook"))
        all_text_clips.extend(engine_v3.generate_subtitle_clips(story_words, font_size=FONT_SIZE_BODY, style_type="body"))
        all_text_clips.extend(engine_v3.generate_subtitle_clips(cta_words, font_size=FONT_SIZE_BODY, style_type="cta"))

        moviepy_resources["final_video"] = CompositeVideoClip([moviepy_resources["combined_bg"]] + all_text_clips, use_bgclip=True)
        moviepy_resources["final_video"] = moviepy_resources["final_video"].with_audio(moviepy_resources["audio_clip"])

        output_file_name = f"final_output_{timestamp_suffix}.mp4"
        output_file_path = os.path.join(DIR_OUTPUT, output_file_name)
        temp_output_path = f"{output_file_path}.tmp.mp4"
        
        os.makedirs(DIR_OUTPUT, exist_ok=True)
        cpu_threads = min(THREADS_MAX, os.cpu_count() or 2)
        
        def execute_ffmpeg_render(target_path: str):
            moviepy_resources["final_video"].write_videofile(
                target_path, fps=30, codec="libx264", preset="ultrafast", # OPTIMASI: Kecepatan maksimal encoding
                audio_codec="aac", threads=cpu_threads, logger=None,
                ffmpeg_params=["-crf", "26", "-pix_fmt", "yuv420p"]      # OPTIMASI: Kompresi super ringan untuk GitHub Actions
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
