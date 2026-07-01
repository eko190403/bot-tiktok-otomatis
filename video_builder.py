import os
import json
import time
import asyncio
from google import genai
from google.genai import types

# Import konfigurasi global dan modul pendukung terpisah
from config import GEMINI_KEYS, DIR_OUTPUT
from downloader import download_video_clips
from effects import process_background_clip
from subtitle import render_subtitles_for_section
from audio import generate_voiceover_edge

# Indeks global untuk melacak API Key yang sedang aktif
current_key_index = 0

def get_next_client():
    """Mengambil Google GenAI Client berikutnya dari daftar rotasi jika terjadi limit kuota."""
    global current_key_index
    if not GEMINI_KEYS:
        raise ValueError("❌ Tidak ada GEMINI_API_KEY yang ditemukan di GitHub Secrets.")
        
    # Pastikan indeks tidak overflow
    if current_key_index >= len(GEMINI_KEYS):
        print("🔄 Semua API Key di dalam daftar sudah dicoba. Mengulang kembali dari kunci pertama...")
        current_key_index = 0
        
    active_key = GEMINI_KEYS[current_key_index]
    # Sembunyikan sebagian karakter token di log demi keamanan
    masked_key = f"{active_key[:8]}...{active_key[-4:]}" if len(active_key) > 12 else "INVALID_KEY"
    print(f"🔑 Menggunakan API Key Slot-{current_key_index + 1} ({masked_key})")
    
    return genai.Client(api_key=active_key)

def generate_structured_script():
    """Fungsi Tahap 1: Meminta Gemini membuat naskah JSON dengan instruksi intonasi tanda baca ketat."""
    global current_key_index
    print("🧠 Gemini sedang merancang naskah berstruktur dengan optimasi tanda baca...")
    
    # PERBAIKAN PROMPT: Menambahkan aturan tanda baca yang ketat agar suara tidak terlalu cepat
    prompt = (
        "Buat satu konten fakta psikologi manusia yang siap pakai untuk TikTok Shorts.\n"
        "Konten harus terbagi menjadi 3 bagian utuh dalam format JSON:\n"
        "1. 'hook': Kalimat pembuka singkat penarik perhatian di 3 detik pertama (Contoh: 'FAKTA PSIKOLOGI YANG HARUS KAMU TAHU...').\n"
        "2. 'story': Isi fakta psikologinya (Bahasa Indonesia, 2-3 kalimat, padat, jelas, dan tuntas).\n"
        "3. 'cta': Kalimat ajakan di akhir video untuk memicu komentar/follow (Contoh: 'Komen jika kamu pernah merasakannya').\n\n"
        "ATURAN ATURAN PENTING UNTUK INTERPRETASI SUARA (TEXT-TO-SPEECH):\n"
        "- Wajib gunakan tanda koma (,) di tengah kalimat jika ada pergantian ide agar robot TTS mengambil jeda napas pendek.\n"
        "- Wajib gunakan tanda titik (.) di akhir kalimat agar robot TTS berhenti sejenak sebelum masuk ke kalimat berikutnya.\n"
        "- Jangan buat kalimat yang terlalu panjang tanpa jeda tanda baca agar suara tidak terdengar terburu-buru atau kehabisan napas.\n\n"
        "Format JSON harus valid, bersih, tanpa markdown."
    )
    
    max_attempts = max(3, len(GEMINI_KEYS))
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
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"⚠️ Slot-{current_key_index + 1} terkena limit kuota (429).")
                current_key_index += 1
                if attempt < max_attempts - 1:
                    print("🔄 Otomatis beralih ke API Key cadangan berikutnya tanpa jeda waktu...")
                    continue
            raise e

def extract_keywords_from_script(script_text: str) -> list:
    """Fungsi Tahap 2: AI mengekstrak kata kunci visual dengan sistem Auto-Rotasi Kunci."""
    global current_key_index
    print("🧠 AI sedang menganalisis isi cerita untuk mengekstrak keyword visual...")
    
    prompt = (
        f"Baca naskah video berikut dan berikan 4 kata kunci (keyword) dalam bahasa Inggris "
        f"yang paling cocok untuk mencari video latar belakang yang estetis di Pexels.\n"
        f"Naskah: \"{script_text}\"\n"
        f"Berikan hasil dalam format JSON array bertipe string. Contoh: [\"mind\", \"thinking\", \"human\", \"dark\"]"
    )
    
    max_attempts = max(3, len(GEMINI_KEYS))
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
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"⚠️ Slot-{current_key_index + 1} terkena limit saat ekstraksi keyword.")
                current_key_index += 1
                if attempt < max_attempts - 1:
                    print("🔄 Otomatis beralih ke API Key cadangan berikutnya tanpa jeda waktu...")
                    continue
            print(f"⚠️ Gagal mengekstrak keyword kustom: {e}. Menggunakan keyword fallback.")
            return ["mind", "abstract", "human", "moody"]

async def create_video() -> bool:
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
        
        # Penggabungan teks dengan memastikan ada jeda spasi dan tanda baca yang jelas antarsegmen
        full_text = f"{hook}. {story} {cta}"
        
        # 2. Ekstraksi Kata Kunci Kontekstual Berbasis AI
        keywords = extract_keywords_from_script(story)
        
        # 3. Pengunduhan Klip Video yang Relevan via downloader.py
        video_files = download_video_clips(keywords, target_count=4)
        
        # 4. Pembuatan Audio Narasi Sempurna via audio.py
        vo_file_path = "temp/vo.mp3"
        os.makedirs("temp", exist_ok=True)
        await generate_voiceover_edge(full_text, vo_file_path)
        
        # Mengimpor kelas video editor secara aman di dalam fungsi runtime
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

        # 6. Pembuatan dan Penataan Subtitle Otomatis via subtitle.py
        hook_duration = total_duration * 0.15
        cta_duration = total_duration * 0.15
        story_duration = total_duration - hook_duration - cta_duration

        all_text_clips = []
        # Render Teks Hook
        all_text_clips.extend(render_subtitles_for_section(hook, 0, hook_duration, style="hook"))
        # Render Teks Story
        all_text_clips.extend(render_subtitles_for_section(story, hook_duration, story_duration, style="body"))
        # Render Teks CTA
        all_text_clips.extend(render_subtitles_for_section(cta, hook_duration + story_duration, cta_duration, style="cta"))

        # 7. Komposisi Akhir Semua Lapisan Video dan Ekspor Render
        final_video = CompositeVideoClip([combined_bg] + all_text_clips)
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
        
        # 8. Penutupan Object untuk Menghindari Memory Leak
        audio_clip.close()
        final_video.close()
        combined_bg.close()
        for clip in processed_clips:
            clip.close()
            
        # Bersihkan file mentahan
        for file in video_files:
            if os.path.exists(file):
                os.remove(file)
        if os.path.exists(vo_file_path):
            os.remove(vo_file_path)
            
        print("🎉 Sukses Besar! Perakitan video modular selesai.")
        return True
        
    except Exception as e:
        print(f"❌ Gagal mengeksekusi pipeline di video_builder: {e}")
        if audio_clip: audio_clip.close()
        if final_video: final_video.close()
        if combined_bg: combined_bg.close()
        for clip in processed_clips: clip.close()
        return False
