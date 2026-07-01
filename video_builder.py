import os
import json
import time
import asyncio
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from moviepy.editor import AudioFileClip, CompositeVideoClip, concatenate_videoclips

# Import konfigurasi global dan modul pendukung terpisah
from config import GEMINI_API_KEY, DIR_OUTPUT
from downloader import download_video_clips
from effects import process_background_clip
from subtitle import render_subtitles_for_section
from audio import generate_voiceover_edge

# Inisialisasi Google GenAI Client
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def generate_structured_script():
    """Fungsi Tahap 1: Meminta Gemini membuat naskah JSON berstruktur untuk TikTok."""
    if not client:
        raise ValueError("❌ GEMINI_API_KEY belum dikonfigurasi di variabel lingkungan.")
        
    print("🧠 Gemini sedang merancang naskah berstruktur (Hook, Story, CTA)...")
    prompt = (
        "Buat satu konten fakta psikologi manusia yang siap pakai untuk TikTok Shorts.\n"
        "Konten harus terbagi menjadi 3 bagian utuh dalam format JSON:\n"
        "1. 'hook': Kalimat pembuka singkat penarik perhatian di 3 detik pertama (Contoh: 'FAKTA PSIKOLOGI YANG HARUS KAMU TAHU...').\n"
        "2. 'story': Isi fakta psikologinya (Bahasa Indonesia, 2-3 kalimat, padat, jelas, dan tuntas).\n"
        "3. 'cta': Kalimat ajakan di akhir video untuk memicu komentar/follow (Contoh: 'Komen jika kamu pernah merasakannya').\n\n"
        "Format JSON harus valid, bersih, tanpa markdown."
    )
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(response.text.strip())
        except ClientError as ce:
            if "429" in str(ce) and attempt < max_retries - 1:
                print(f"⚠️ Kuota Gemini penuh (429). Menunggu 10 detik sebelum coba lagi...")
                time.sleep(10)
            else:
                raise ce

def extract_keywords_from_script(script_text: str) -> list:
    """Fungsi Tahap 2: AI membaca isi skrip cerita dan mengekstrak kata kunci pencarian video."""
    if not client:
        return ["human", "thinking", "mind"]
        
    print("🧠 AI sedang menganalisis isi cerita untuk mengekstrak keyword visual...")
    prompt = (
        f"Baca naskah video berikut dan berikan 4 kata kunci (keyword) dalam bahasa Inggris "
        f"yang paling cocok untuk mencari video latar belakang yang estetis di Pexels.\n"
        f"Naskah: \"{script_text}\"\n"
        f"Berikan hasil dalam format JSON array bertipe string. Contoh: [\"mind\", \"thinking\", \"human\", \"dark\"]"
    )
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text.strip())
    except Exception as e:
        print(f"⚠️ Gagal mengekstrak keyword kustom: {e}. Menggunakan keyword fallback.")
        return ["mind", "abstract", "human", "moody"]

def create_video() -> bool:
    """Orchestrator Utama Pipeline Perakitan Video TikTok."""
    processed_clips = []
    audio_clip = None
    combined_bg = None
    final_video = None
    
    try:
        # 1. Pembuatan Naskah Teks Konten
        script_data = generate_structured_script()
        hook = script_data.get("hook", "FAKTA PSIKOLOGI").strip()
        story = script_data.get("story", "").strip()
        cta = script_data.get("cta", "Follow untuk info lainnya").strip()
        full_text = f"{hook}. {story} {cta}"
        
        # 2. Ekstraksi Kata Kunci Kontekstual Berbasis AI
        keywords = extract_keywords_from_script(story)
        
        # 3. Pengunduhan Klip Video yang Relevan via downloader.py
        video_files = download_video_clips(keywords, target_count=4)
        
        # 4. Pembuatan Audio Narasi Sempurna via audio.py (Edge-TTS Async)
        vo_file_path = "temp/vo.mp3"
        os.makedirs("temp", exist_ok=True)
        asyncio.run(generate_voiceover_edge(full_text, vo_file_path))
        
        audio_clip = AudioFileClip(vo_file_path)
        total_duration = audio_clip.duration

        # 5. Pemrosesan Efek Visual dan Transisi Background via effects.py
        clip_count = len(video_files)
        duration_per_clip = total_duration / clip_count
        
        print("🎬 Memotong klip dan menyuntikkan efek Zoom In dinamis (MoviePy 2.x)...")
        for file in video_files:
            processed_clip = process_background_clip(file, duration_per_clip)
            processed_clips.append(processed_clip)
            
        combined_bg = concatenate_videoclips(processed_clips, method="compose").set_duration(total_duration)

        # 6. Pembuatan dan Penataan Subtitle Otomatis via subtitle.py
        # Alokasi waktu: Hook awal (15%), CTA akhir (15%), Story tengah (70%)
        hook_duration = total_duration * 0.15
        cta_duration = total_duration * 0.15
        story_duration = total_duration - hook_duration - cta_duration

        all_text_clips = []
        # Render Teks Hook (Oranye)
        all_text_clips.extend(render_subtitles_for_section(hook, 0, hook_duration, style="hook"))
        # Render Teks Story (Selang-seling Kuning/Putih)
        all_text_clips.extend(render_subtitles_for_section(story, hook_duration, story_duration, style="body"))
        # Render Teks CTA (Cyan)
        all_text_clips.extend(render_subtitles_for_section(cta, hook_duration + story_duration, cta_duration, style="cta"))

        # 7. Komposisi Akhir Semua Lapasan Video dan Ekspor Render
        final_video = CompositeVideoClip([combined_bg] + all_text_clips)
        final_video = final_video.set_audio(audio_clip)

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
        
        # 8. Penutupan Object untuk Menghindari Memory Leak di Server
        audio_clip.close()
        final_video.close()
        combined_bg.close()
        for clip in processed_clips:
            clip.close()
            
        # Bersihkan file mentahan pasca render sukses
        for file in video_files:
            if os.path.exists(file):
                os.remove(file)
        if os.path.exists(vo_file_path):
            os.remove(vo_file_path)
            
        print("🎉 Sukses Besar! Perakitan video modular tingkat tinggi selesai.")
        return True
        
    except Exception as e:
        print(f"❌ Gagal mengeksekusi pipeline di video_builder: {e}")
        # Safeguard penutupan resource jika terjadi crash di tengah jalan
        if audio_clip: audio_clip.close()
        if final_video: final_video.close()
        if combined_bg: combined_bg.close()
        for clip in processed_clips: clip.close()
        return False
