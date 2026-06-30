import os
import asyncio
from google import genai
from google.genai import types
import edge_tts
from video_builder import create_tiktok_video

# 1. Fungsi Membuat Script Menggunakan Gemini
def generate_script():
    print("🧠 Meminta Gemini membuat script fakta psikologi...")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("❌ Eror: GEMINI_API_KEY tidak ditemukan di environment!")
        
    client = genai.Client(api_key=api_key)
    
    prompt = (
        "Buat satu fakta psikologi singkat, menarik, dan mengejutkan tentang manusia. "
        "Langsung berikan isi faktanya tanpa pembukaan atau penutup. "
        "Maksimal 2 kalimat saja agar durasi video pendek."
    )
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    script_text = response.text.strip()
    print(f"📄 Script Berhasil Dibuat: {script_text}")
    return script_text

# 2. Fungsi Mengubah Teks Menjadi Suara (Voiceover)
async def generate_voiceover(text, output_audio="vo.mp3"):
    print("🎙️ Mengonversi script menjadi suara (Edge-TTS)...")
    voice = "id-ID-GadisNeural" 
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_audio)
    print("✅ File audio vo.mp3 berhasil disimpan.")

# Alur Kerja Utama Tanpa Upload
async def main():
    try:
        # Tahap 1: Bikin Script & Audio
        script = generate_script()
        await generate_voiceover(script)
        
        # Tahap 2: Potong Video & Tempel Subtitle
        print("🎬 Memulai proses perakitan video...")
        create_tiktok_video()
        
        print("🎉 Selesai! Video berhasil dirakit dan siap diunduh.")
    except Exception as e:
        print(f"❌ Terjadi kesalahan sistem: {e}")

if __name__ == "__main__":
    asyncio.run(main())
