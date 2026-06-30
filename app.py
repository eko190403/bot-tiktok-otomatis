import os
import asyncio
import json
from google import genai
from google.genai import types
import edge_tts
from video_builder import create_tiktok_video

# 1. Fungsi Membuat Script & Keyword Video Menggunakan Gemini
def generate_content():
    print("🧠 Meminta Gemini membuat script fakta psikologi dan mencari keyword video...")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("❌ Eror: GEMINI_API_KEY tidak ditemukan!")
        
    client = genai.Client(api_key=api_key)
    
    # Kita paksa Gemini mengeluarkan output format JSON yang rapi
    prompt = (
        "Buat satu fakta psikologi singkat, menarik, dan mengejutkan tentang manusia.\n"
        "Berikan output dalam bentuk JSON dengan dua key:\n"
        "1. 'script': Isi fakta psikologinya (Bahasa Indonesia, maksimal 2 kalimat langsung ke inti).\n"
        "2. 'keyword': Satu atau dua kata kunci dalam Bahasa Inggris yang paling menggambarkan suasana atau objek dari skrip tersebut untuk dicari di Pexels video API (contoh: 'sad person', 'thinking', 'running man', 'night city').\n\n"
        "Format JSON harus valid dan bersih."
    )
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    
    # Parse hasil JSON dari Gemini
    data = json.loads(response.text.strip())
    script_text = data.get("script", "").strip()
    keyword_video = data.get("keyword", "urban").strip()
    
    print(f"📄 Script Berhasil Dibuat: {script_text}")
    print(f"🔍 Keyword Video Terpilih: {keyword_video}")
    return script_text, keyword_video

# 2. Fungsi Mengubah Teks Menjadi Suara
async def generate_voiceover(text, output_audio="vo.mp3"):
    print("🎙️ Mengonversi script menjadi suara (Edge-TTS)...")
    voice = "id-ID-GadisNeural" 
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_audio)
    print("✅ File audio vo.mp3 berhasil disimpan.")

# Alur Kerja Utama
async def main():
    try:
        # Mengambil skrip dan keyword sekaligus
        script, keyword = generate_content()
        await generate_voiceover(script)
        
        print("🎬 Memulai proses perakitan video...")
        # Kita oper keyword-nya ke fungsi pembuat video
        create_tiktok_video(keyword=keyword)
        
        print("🎉 Selesai! Video dengan latar belakang relevan berhasil dirakit.")
    except Exception as e:
        print(f"❌ Terjadi kesalahan sistem: {e}")
        raise e

if __name__ == "__main__":
    asyncio.run(main())
