import os
import json
import time
import asyncio
from google import genai
from google.genai import types

from config import GEMINI_KEYS, DIR_OUTPUT, FONT_SIZE_HOOK, FONT_SIZE_BODY
from downloader import download_video_clips
from effects import process_background_clip
from subtitle_engine.orchestrator import SubtitleEngineV2
from audio import generate_voiceover_with_timestamps

current_key_index = 0

def get_next_client():
    global current_key_index
    if not GEMINI_KEYS:
        raise ValueError("❌ Tidak ada GEMINI_API_KEY yang ditemukan di GitHub Secrets.")
    if current_key_index >= len(GEMINI_KEYS):
        current_key_index = 0
    active_key = GEMINI_KEYS[current_key_index]
    return genai.Client(api_key=active_key)

def generate_structured_script():
    global current_key_index
    print("🧠 Gemini sedang merancang naskah berstruktur otomatis...")
    prompt = (
        "Buat satu konten edukasi pendek untuk TikTok Shorts dalam format JSON.\n"
        "Pilih secara acak tema: Fakta Psikologi, Stoikisme, Dark Psychology, atau Mindset Sukses.\n"
        "Format JSON wajib memiliki 3 key: 'hook' (kapital), 'story', dan 'cta'.\n"
        "Gunakan tanda baca koma dan titik dengan baik agar intonasi suara natural."
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
                current_key_index += 1
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue
            raise e

def extract_keywords_from_script(script_text: str) -> list:
    global current_key_index
    prompt = f"Berikan 4 kata kunci visual bahasa Inggris dalam bentuk JSON array untuk mencari video latar belakang naskah ini: \"{script_text}\""
    for attempt in range(5):
        try:
            client = get_next_client()
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(response.text.strip())
        except Exception:
            current_key_index += 1
            continue
    return ["mind", "abstract", "human"]

async def create_video() -> bool:
    processed_clips = []
    audio_clip = None
    combined_bg = None
    final_video = None
    
    try:
        # 1. Bangun Naskah Konten
        script_data = generate_structured_script()
        hook = script_data.get("hook", "FAKTA MENARIK").strip()
        story = script_data.get("story", "").strip()
        cta = script_data.get("cta", "Follow untuk info lainnya").strip()
        
        # 2. Ekstrak Keyword & Ambil Background
        keywords = extract_keywords_from_script(story)
        video_files = download_video_clips(keywords, target_count=4)
        
        # 3. Generate Audio & Tangkap List Timestamp Terpadu Berbasis Seksi
        vo_file_path = "temp/vo.mp3"
        os.makedirs("temp", exist_ok=True)
        all_timestamps = await generate_voiceover_with_timestamps(hook, story, cta, vo_file_path)
        
        from moviepy import AudioFileClip, concatenate_videoclips, CompositeVideoClip
        
        audio_clip = AudioFileClip(vo_file_path)
        total_duration = audio_clip.duration

        # 4. Potong & Zoom Background
        clip_count = len(video_files)
        duration_per_clip = total_duration / clip_count
        for file in video_files:
            processed_clip = process_background_clip(file, duration_per_clip)
            processed_clips.append(processed_clip)
            
        combined_bg = concatenate_videoclips(processed_clips, method="compose").with_duration(total_duration)

        # 5. INTEGRASI FIX: Memecah list data absolut menggunakan filter penanda seksi rekomendasi kamu
        hook_words = [x for x in all_timestamps if x["section"] == "hook"]
        story_words = [x for x in all_timestamps if x["section"] == "story"]
        cta_words = [x for x in all_timestamps if x["section"] == "cta"]

        engine_v3 = SubtitleEngineV2()
        all_text_clips = []

        # Kirim potongan list kata langsung ke generator tanpa hitung durasi manual lagi
        all_text_clips.extend(engine_v3.generate_subtitle_clips(hook_words, font_size=FONT_SIZE_HOOK, style_type="hook"))
        all_text_clips.extend(engine_v3.generate_subtitle_clips(story_words, font_size=FONT_SIZE_BODY, style_type="body"))
        all_text_clips.extend(engine_v3.generate_subtitle_clips(cta_words, font_size=FONT_SIZE_BODY, style_type="cta"))

        # 6. Final Komposisi Lapisan Overlay
        final_video = CompositeVideoClip([combined_bg] + all_text_clips, use_bgclip=True)
        final_video = final_video.with_audio(audio_clip)

        output_file_path = os.path.join(DIR_OUTPUT, "final_output.mp4")
        os.makedirs(DIR_OUTPUT, exist_ok=True)
        
        print("🔄 Memulai proses ekspor video dengan sinkronisasi seksi absolut...")
        final_video.write_videofile(output_file_path, fps=30, codec="libx264", audio_codec="aac", threads=4)
        
        # Clean Up
        audio_clip.close()
        final_video.close()
        combined_bg.close()
        for clip in processed_clips: clip.close()
        for file in video_files: 
            if os.path.exists(file): os.remove(file)
        if os.path.exists(vo_file_path): os.remove(vo_file_path)
            
        print("🎉 Sukses Besar! Sinkronisasi video bermode seksi selesai.")
        return True
        
    except Exception as e:
        print(f"❌ Gagal mengeksekusi pipeline: {e}")
        if audio_clip: audio_clip.close()
        if final_video: final_video.close()
        if combined_bg: combined_bg.close()
        for clip in processed_clips: clip.close()
        return False
