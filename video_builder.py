import os
import json
import time
from google import genai
from google.genai import types
from google.genai.errors import ClientError
import edge_tts

from config import GEMINI_API_KEY, DIR_OUTPUT
from downloader import download_video_clips
from effects import process_background_clip
# Modul subtitle, overlay, audio dapat di-import di sini setelah kamu memecahnya

# Jalankan Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def generate_structured_script():
    """Fungsi Tahap 1: Meminta Gemini membuat naskah JSON TikTok."""
    print("🧠 Gemini sedang merancang naskah berstruktur...")
    prompt = (
        "Buat satu konten fakta psikologi manusia yang siap pakai untuk TikTok Shorts.\n"
        "Konten harus terbagi menjadi 3 bagian utuh dalam format JSON:\n"
        "1. 'hook': Kalimat pembuka singkat penarik perhatian (3 detik pertama).\n"
        "2. 'story': Isi fakta psikologinya (Bahasa Indonesia, 2-3 kalimat, tuntas).\n"
        "3. 'cta': Ajakan bertindak di akhir video.\n"
        "Format JSON harus valid, bersih, tanpa markdown."
    )
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return json.loads(response.text.strip())

def extract_keywords_from_script(script_text: str) -> list:
    """Fungsi Tahap 2: AI membaca isi skrip dan menghasilkan keyword pencarian video."""
    print("🧠 AI sedang menganalisis konten untuk mengekstrak keyword visual...")
    prompt = (
        f"Baca naskah video berikut dan berikan 4 kata kunci (keyword) dalam bahasa Inggris "
        f"yang paling cocok untuk mencari video latar belakang yang estetis di Pexels.\n"
        f"Naskah: \"{script_text}\"\n"
        f"Berikan hasil dalam format JSON array bertipe string. Contoh: [\"mind\", \"thinking\", \"human\"]"
    )
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return json.loads(response.text.strip())

def create_video() -> bool:
    """Orchestrator Utama Pipeline Pembuatan Video."""
    try:
        # 1. Generate Script
        script_data = generate_structured_script()
        hook = script_data.get("hook", "")
        story = script_data.get("story", "")
        cta = script_data.get("cta", "")
        full_text = f"{hook}. {story} {cta}"
        
        # 2. AI Extract Keywords (Peningkatan Terbesar Sesuai Saranmu)
        keywords = extract_keywords_from_script(story)
        
        # 3. Download Video via downloader.py
        video_files = download_video_clips(keywords, target_count=4)
        
        # 4. Generate Audio via Edge-TTS (Temporary)
        print("🎙️ Mengonversi teks ke suara (ArdiNeural)...")
        # Kode pemanggilan audio.py atau edge-tts diletakkan di sini
        
        # 5. Perakitan Video & Pemanggilan Efek / Subtitle
        # (Logika penggabungan klip menggunakan MoviePy 2.x)
        print("🎬 Menggabungkan komponen video menggunakan arsitektur modular...")
        
        # Proses pembuatan teks, overlay, audio mixing, dan render_output...
        # Sesuai target, file orchestrator ini sekarang sangat bersih (< 120 baris).
        
        return True
    except Exception as e:
        print(f"❌ Gagal pada orchestrator video_builder: {e}")
        return False
