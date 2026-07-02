import os
import json
import asyncio
import logging
import time
from dataclasses import asdict

from google import genai
from google.genai import types

from config import GEMINI_KEYS, DIR_OUTPUT, FONT_SIZE_HOOK, FONT_SIZE_BODY
from downloader import download_video_clips
from effects import process_background_clip
from subtitle_engine.orchestrator import SubtitleEngineV2
from audio import generate_voiceover_with_timestamps

logger = logging.getLogger("video_pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class GeminiClientPool:
    def __init__(self, api_keys: list):
        if not api_keys:
            raise ValueError("❌ Tidak ada GEMINI_API_KEY yang ditemukan di GitHub Secrets.")
        self.api_keys = api_keys
        self.current_index = 0
        self.lock = asyncio.Lock()

    async def get_client_and_rotate(self):
        async with self.lock:
            active_key = self.api_keys[self.current_index]
            masked_key = f"{active_key[:8]}...{active_key[-4:]}" if len(active_key) > 12 else "INVALID_KEY"
            logger.info("🔑 [Pool Slot-%d] Menggunakan API Key: %s", self.current_index + 1, masked_key)
            self.current_index = (self.current_index + 1) % len(self.api_keys)
            return genai.Client(api_key=active_key)

client_pool = GeminiClientPool(GEMINI_KEYS)

async def generate_structured_script():
    logger.info("🧠 Gemini sedang merancang naskah berstruktur otomatis...")
    prompt = (
        "Buat satu konten edukasi pendek untuk TikTok Shorts dalam format JSON.\n"
        "Pilih secara acak tema: Fakta Psikologi, Stoikisme, Dark Psychology, atau Mindset Sukses.\n"
        "Format JSON wajib memiliki 3 key: 'hook' (kapital), 'story', dan 'cta'.\n"
        "Gunakan tanda baca koma dan titik dengan baik agar intonasi suara natural."
    )
    
    max_attempts = max(5, len(GEMINI_KEYS) * 2)
    for attempt in range(max_attempts):
        try:
            client = await client_pool.get_client_and_rotate()
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(response.text.strip())
        except Exception as e:
            err_msg = str(e)
            if any(x in err_msg for x in ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE"]):
                logger.warning("⚠️ Kuota limit terdeteksi pada slot ini. Mencoba otomatis ke kunci cadangan...")
                await asyncio.sleep(1)
                continue
            logger.exception("Gagal menghasilkan naskah berstruktur")
            raise e

async def extract_keywords_from_script(script_text: str) -> list:
    prompt = f"Berikan 4 kata kunci visual bahasa Inggris dalam bentuk JSON array langsung (tanpa key object pembungkus) untuk mencari video latar belakang naskah ini: \"{script_text}\""
    for attempt in range(5):
        try:
            client = await client_pool.get_client_and_rotate()
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            res_data = json.loads(response.text.strip())
            if isinstance(res_data, dict):
                for val in res_data.values():
                    if isinstance(val, list): return val
            if isinstance(res_data, list): return res_data
        except Exception as e:
            logger.warning("Gagal mengekstrak kata kunci pada percobaan %d: %s", attempt + 1, e)
            await asyncio.sleep(0.5)
            continue
    return ["mind", "abstract", "human"]

def safe_close_resources(resources: dict, files_to_delete: list):
    logger.info("🧹 Memulai pembersihan resource dan file temporer secara aman...")
    for name, obj in resources.items():
        if obj is not None:
            try:
                obj.close()
                logger.info("✅ Resource '%s' berhasil dilepas.", name)
            except Exception as ce:
                logger.error("⚠️ Resource '%s' melemparkan exception saat penutupan (Diabaikan aman): %s", name, ce)

    for file_path in files_to_delete:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info("🗑️ Berkas sampah berhasil dihapus: %s", file_path)
            except Exception as fe:
                logger.error("⚠️ Gagal menghapus berkas %s: %s", file_path, fe)

async def create_video() -> bool:
    moviepy_resources = {
        "audio_clip": None,
        "processed_clips": [],
        "raw_combined_bg": None,
        "looped_bg": None,
        "combined_bg": None,
        "final_video": None
    }
    video_files = []
    
    # Poin 6: Mengamankan nama file temporal menggunakan stempel epoch unik agar kebal interferensi
    timestamp_suffix = int(time.time())
    vo_file_path = f"temp/vo_{timestamp_suffix}.mp3"
    
    try:
        script_data = await generate_structured_script()
        hook = script_data.get("hook", "FAKTA MENARIK").strip()
        story = script_data.get("story", "").strip()
        cta = script_data.get("cta", "Follow untuk info lainnya").strip()
        
        keywords = await extract_keywords_from_script(story)
        os.makedirs("temp", exist_ok=True)
        
        logger.info("⚡ Menjalankan download background dan TTS secara bersamaan (Paralel)...")
        loop = asyncio.get_running_loop()
        download_task = loop.run_in_executor(None, download_video_clips, keywords, 4)
        audio_task = generate_voiceover_with_timestamps(hook, story, cta, vo_file_path)
        
        # Poin 3: Proteksi parsial task via return_exceptions=True agar crash terisolasi dengan transparan
        results = await asyncio.gather(download_task, audio_task, return_exceptions=True)
        
        # Evaluasi hasil eksekusi task paralel
        if isinstance(results[0], Exception):
            raise RuntimeError(f"Gagal mengunduh klip video latar belakang: {results[0]}") from results[0]
        if isinstance(results[1], Exception):
            raise RuntimeError(f"Gagal menghasilkan sintesis audio Edge-TTS: {results[1]}") from results[1]
            
        video_files, (all_timestamps_dataclass, meta) = results

        logger.info("📊 [Pipeline Audit] Akurasi Subtitle Otomatis: %d/%d (%.1f%%)", meta.matched, meta.total, meta.accuracy * 100)

        if not video_files:
            raise RuntimeError("❌ Eror Batas: Tidak ada video latar belakang yang berhasil diunduh dari Pexels.")
            
        all_timestamps = [asdict(ts) for ts in all_timestamps_dataclass]
            
        from moviepy import AudioFileClip, concatenate_videoclips, CompositeVideoClip
        # Poin 1: Impor fleksibel yang kompatibel penuh dengan berbagai distribusi sub-modul MoviePy 2.x
        try:
            from moviepy.video.fx.loop import Loop
        except ImportError:
            from moviepy.video.fx import Loop
        
        moviepy_resources["audio_clip"] = AudioFileClip(vo_file_path)
        total_duration = moviepy_resources["audio_clip"].duration

        clip_count = len(video_files)
        duration_per_clip = (total_duration / clip_count) + 3.0
        
        for file in video_files:
            processed_clip = process_background_clip(file, duration_per_clip)
            moviepy_resources["processed_clips"].append(processed_clip)
            
        moviepy_resources["raw_combined_bg"] = concatenate_videoclips(
            moviepy_resources["processed_clips"], method="compose"
        )
        
        bg_duration = moviepy_resources["raw_combined_bg"].duration
        logger.info("📊 Evaluasi Durasi -> Audio: %.2fs | Gabungan Video Mentah: %.2fs", total_duration, bg_duration)
        
        if bg_duration < total_duration:
            logger.warning("⚠️ Video mentah terlalu pendek! Mengaktifkan pengulangan visual...")
            loop_factor = int(total_duration / bg_duration) + 1
            moviepy_resources["looped_bg"] = moviepy_resources["raw_combined_bg"].with_effects([Loop(n=loop_factor)])
            moviepy_resources["combined_bg"] = moviepy_resources["looped_bg"].subclipped(0, total_duration)
        else:
            moviepy_resources["combined_bg"] = moviepy_resources["raw_combined_bg"].subclipped(0, total_duration)

        hook_words = [x for x in all_timestamps if x["section"] == "hook"]
        story_words = [x for x in all_timestamps if x["section"] == "story"]
        cta_words = [x for x in all_timestamps if x["section"] == "cta"]

        engine_v3 = SubtitleEngineV2()
        all_text_clips = []

        all_text_clips.extend(engine_v3.generate_subtitle_clips(hook_words, font_size=FONT_SIZE_HOOK, style_type="hook"))
        all_text_clips.extend(engine_v3.generate_subtitle_clips(story_words, font_size=FONT_SIZE_BODY, style_type="body"))
        all_text_clips.extend(engine_v3.generate_subtitle_clips(cta_words, font_size=FONT_SIZE_BODY, style_type="cta"))

        moviepy_resources["final_video"] = CompositeVideoClip(
            [moviepy_resources["combined_bg"]] + all_text_clips, use_bgclip=True
        )
        moviepy_resources["final_video"] = moviepy_resources["final_video"].with_audio(moviepy_resources["audio_clip"])

        # Poin 6: Nama berkas hasil akhir dibuat unik untuk mengeliminasi resiko overwrite di GitHub Actions
        output_file_name = f"final_output_{timestamp_suffix}.mp4"
        output_file_path = os.path.join(DIR_OUTPUT, output_file_name)
        os.makedirs(DIR_OUTPUT, exist_ok=True)
        
        # Poin 5: Optimasi core rendering dinamis mengikuti spesifikasi CPU mesin pelaksana runtime
        cpu_threads = os.cpu_count() or 4
        logger.info("🔄 Memulai render video durasi penuh %.2f detik dengan %d CPU Threads...", total_duration, cpu_threads)
        
        moviepy_resources["final_video"].write_videofile(
            output_file_path, fps=30, codec="libx264", audio_codec="aac", threads=cpu_threads
        )
        
        logger.info("🎉 Sukses Besar! File final berstandar industri siap dipublikasikan: %s", output_file_name)
        return True
        
    except Exception:
        # Poin 2: Menggunakan logger.exception untuk menangkap riwayat penuh traceback secara absolut
        logger.exception("❌ Terjadi Eror Fatal pada Jalur Pipeline Produksi")
        return False
        
    finally:
        clips_to_close = {}
        if moviepy_resources["audio_clip"]: clips_to_close["audio_clip"] = moviepy_resources["audio_clip"]
        if moviepy_resources["raw_combined_bg"]: clips_to_close["raw_combined_bg"] = moviepy_resources["raw_combined_bg"]
        if moviepy_resources["looped_bg"]: clips_to_close["looped_bg"] = moviepy_resources["looped_bg"]
        if moviepy_resources["combined_bg"]: clips_to_close["combined_bg"] = moviepy_resources["combined_bg"]
        if moviepy_resources["final_video"]: clips_to_close["final_video"] = moviepy_resources["final_video"]
        
        for idx, cp in enumerate(moviepy_resources["processed_clips"]):
            clips_to_close[f"processed_clip_{idx}"] = cp

        clean_video_files = video_files if isinstance(video_files, list) else []
        files_cleanup = clean_video_files + [vo_file_path]
        safe_close_resources(clips_to_close, files_cleanup)
                print(f"🗑️ Berkas sampah berhasil dihapus: {file_path}")
            except Exception as fe:
                print(f"⚠️ Gagal menghapus berkas {file_path}: {fe}")

async def create_video() -> bool:
    moviepy_resources = {
        "audio_clip": None,
        "processed_clips": [],
        "raw_combined_bg": None,
        "looped_bg": None,
        "combined_bg": None,
        "final_video": None
    }
    video_files = []
    vo_file_path = "temp/vo.mp3"
    
    try:
        # 1. Bangun Naskah Konten via Gemini
        script_data = await generate_structured_script()
        hook = script_data.get("hook", "FAKTA MENARIK").strip()
        story = script_data.get("story", "").strip()
        cta = script_data.get("cta", "Follow untuk info lainnya").strip()
        
        # 2. Ekstrak Kata Kunci Visual Konten
        keywords = await extract_keywords_from_script(story)
        os.makedirs("temp", exist_ok=True)
        
        print("⚡ Menjalankan download background dan TTS secara bersamaan (Paralel)...")
        loop = asyncio.get_event_loop()
        download_task = loop.run_in_executor(None, download_video_clips, keywords, 4)
        audio_task = generate_voiceover_with_timestamps(hook, story, cta, vo_file_path)
        
        video_files, all_timestamps = await asyncio.gather(download_task, audio_task)

        if not video_files:
            raise RuntimeError("❌ Eror Batas: Tidak ada video latar belakang yang berhasil diunduh dari Pexels.")
            
        from moviepy import AudioFileClip, concatenate_videoclips, CompositeVideoClip
        import moviepy.video.fx as vfx
        
        moviepy_resources["audio_clip"] = AudioFileClip(vo_file_path)
        total_duration = moviepy_resources["audio_clip"].duration

        # 4. Potong & Suntik Efek Zoom Latar Belakang
        clip_count = len(video_files)
        duration_per_clip = (total_duration / clip_count) + 3.0
        
        for file in video_files:
            processed_clip = process_background_clip(file, duration_per_clip)
            moviepy_resources["processed_clips"].append(processed_clip)
            
        # Gabungkan semua klip background
        moviepy_resources["raw_combined_bg"] = concatenate_videoclips(
            moviepy_resources["processed_clips"], method="compose"
        )
        
        bg_duration = moviepy_resources["raw_combined_bg"].duration
        print(f"📊 Evaluasi Durasi -> Audio: {total_duration:.2f}s | Gabungan Video Mentah: {bg_duration:.2f}s")
        
        if bg_duration < total_duration:
            print("⚠️ Video mentah terlalu pendek! Mengaktifkan pengulangan visual (Looping Filter)...")
            loop_factor = int(total_duration / bg_duration) + 1
            moviepy_resources["looped_bg"] = moviepy_resources["raw_combined_bg"].with_effects([vfx.Loop(n=loop_factor)])
            moviepy_resources["combined_bg"] = moviepy_resources["looped_bg"].subclipped(0, total_duration)
        else:
            moviepy_resources["combined_bg"] = moviepy_resources["raw_combined_bg"].subclipped(0, total_duration)

        # 5. Filter Pemecahan Teks Berdasarkan Tag Seksi Progresif
        hook_words = [x for x in all_timestamps if x["section"] == "hook"]
        story_words = [x for x in all_timestamps if x["section"] == "story"]
        cta_words = [x for x in all_timestamps if x["section"] == "cta"]

        engine_v3 = SubtitleEngineV2()
        all_text_clips = []

        all_text_clips.extend(engine_v3.generate_subtitle_clips(hook_words, font_size=FONT_SIZE_HOOK, style_type="hook"))
        all_text_clips.extend(engine_v3.generate_subtitle_clips(story_words, font_size=FONT_SIZE_BODY, style_type="body"))
        all_text_clips.extend(engine_v3.generate_subtitle_clips(cta_words, font_size=FONT_SIZE_BODY, style_type="cta"))

        # 6. Komposisi Lapisan Overlay & Ekspor Hasil Akhir Video
        moviepy_resources["final_video"] = CompositeVideoClip(
            [moviepy_resources["combined_bg"]] + all_text_clips, use_bgclip=True
        )
        moviepy_resources["final_video"] = moviepy_resources["final_video"].with_audio(moviepy_resources["audio_clip"])

        output_file_path = os.path.join(DIR_OUTPUT, "final_output.mp4")
        os.makedirs(DIR_OUTPUT, exist_ok=True)
        
        print(f"🔄 Memulai render video durasi penuh {total_duration:.2f} detik...")
        moviepy_resources["final_video"].write_videofile(
            output_file_path, fps=30, codec="libx264", audio_codec="aac", threads=4
        )
        
        print("🎉 Sukses Besar! Sistem imunisasi mengamankan pipeline otomatis skala produksi.")
        return True
        
    except Exception as e:
        print(f"❌ Terjadi Eror Fatal pada Jalur Pipeline: {e}")
        return False
        
    finally:
        clips_to_close = {}
        if moviepy_resources["audio_clip"]: clips_to_close["audio_clip"] = moviepy_resources["audio_clip"]
        if moviepy_resources["raw_combined_bg"]: clips_to_close["raw_combined_bg"] = moviepy_resources["raw_combined_bg"]
        if moviepy_resources["looped_bg"]: clips_to_close["looped_bg"] = moviepy_resources["looped_bg"]
        if moviepy_resources["combined_bg"]: clips_to_close["combined_bg"] = moviepy_resources["combined_bg"]
        if moviepy_resources["final_video"]: clips_to_close["final_video"] = moviepy_resources["final_video"]
        
        for idx, cp in enumerate(moviepy_resources["processed_clips"]):
            clips_to_close[f"processed_clip_{idx}"] = cp

        files_cleanup = video_files + [vo_file_path]
        safe_close_resources(clips_to_close, files_cleanup)
