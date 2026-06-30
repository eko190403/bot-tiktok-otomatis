import os
import asyncio
import json
from google import genai
from google.genai import types
import edge_tts
from video_builder import create_tiktok_video

# 1. Fungsi Membuat Script & Keyword Video Menggunakan Gemini (Tuntas & Jelas)
def generate_content():
    print("🧠 Meminta Gemini membuat script fakta psikologi yang tuntas dan mencari keyword...")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("❌ Eror: GEMINI_API_KEY tidak ditemukan!")
        
    client = genai.Client(api_key=api_key)
    
    # Prompt diperketat agar pembahasan bulat, tuntas, dan logis
    prompt = (
        "Buat satu fakta psikologi tentang perilaku atau otak manusia.\n"
        "Ketentuan Script:\n"
        "1. Harus padat, jelas, dan tuntas (tidak boleh menggantung atau terpotong di tengah kalimat).\n"
        "2. Berikan struktur: sebutkan faktanya, lalu jelaskan alasan ilmiah singkatnya dalam maksimal 3 kalimat.\n"
        "3. Langsung berikan isi materi tanpa salam pembuka atau penutup.\n"
        "4. Gunakan Bahasa Indonesia yang mudah dipahami.\n\n"
        "Berikan output dalam bentuk JSON dengan dua key:\n"
        "1. 'script': Isi fakta psikologi yang utuh dan tuntas.\n"
        "2. 'keyword': Satu atau dua kata kunci dalam Bahasa Inggris yang paling menggambarkan suasana skrip tersebut untuk dicari di Pexels video API (contoh: 'confused person', 'sleeping dawn', 'crowded street').\n\n"
        "Format JSON harus valid dan bersih."
    )
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    
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
        script, keyword = generate_content()
        
        with open("script.txt", "w", encoding="utf-8") as f:
            f.write(script)
        print("💾 File script.txt berhasil disimpan untuk subtitle.")
            
        await generate_voiceover(script)
        
        print("🎬 Memulai proses perakitan video...")
        create_tiktok_video(keyword=keyword)
        
        if os.path.exists("script.txt"):
            os.remove("script.txt")
            
        print("🎉 Selesai! Video dengan pembahasan tuntas berhasil dirakit.")
    except Exception as e:
        print(f"❌ Terjadi kesalahan sistem: {e}")
        raise e

if __name__ == "__main__":
    asyncio.run(main())
