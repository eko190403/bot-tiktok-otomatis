import os
import asyncio
import json
from google import genai
from google.genai import types
import edge_tts
from video_builder import create_tiktok_video

# 1. Fungsi Membuat Konten Lengkap dengan Hook, Isi, dan CTA lewat Gemini
def generate_content():
    print("🧠 Meminta Gemini membuat konten TikTok yang berstruktur matang...")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("❌ Eror: GEMINI_API_KEY tidak ditemukan!")
        
    client = genai.Client(api_key=api_key)
    
    prompt = (
        "Buat satu konten fakta psikologi manusia yang siap pakai untuk TikTok Shorts.\n"
        "Konten harus terbagi menjadi 3 bagian utuh dalam format JSON:\n"
        "1. 'hook': Kalimat pembuka singkat yang sangat memancing rasa penasaran di 3 detik pertama (Contoh: 'FAKTA PSIKOLOGI YANG HARUS KAMU TAHU...').\n"
        "2. 'story': Isi fakta psikologinya (Bahasa Indonesia, 2-3 kalimat, padat, jelas, dan pembahasannya tuntas).\n"
        "3. 'cta': Kalimat ajakan di akhir video untuk meningkatkan interaksi (Contoh: 'Follow untuk fakta menarik lainnya!', 'Komen jika kamu pernah merasakannya').\n\n"
        "Format JSON harus valid, bersih, dan menggunakan Bahasa Indonesia yang santai tapi tegas."
    )
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    
    data = json.loads(response.text.strip())
    hook = data.get("hook", "FAKTA PSIKOLOGI").strip()
    story = data.get("story", "").strip()
    cta = data.get("cta", "Follow untuk info lainnya").strip()
    
    # Gabungkan menjadi satu teks utuh untuk disuarakan oleh AI
    full_script = f"{hook}. {story} {cta}"
    
    print(f"🪝 Hook: {hook}")
    print(f"📄 Story: {story}")
    print(f"🚀 CTA: {cta}")
    return hook, story, cta, full_script

# 2. Fungsi Mengubah Teks Menjadi Suara
async def generate_voiceover(text, output_audio="vo.mp3"):
    print("🎙️ Mengonversi script utuh menjadi suara (Edge-TTS)...")
    voice = "id-ID-GadisNeural" 
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_audio)
    print("✅ File audio vo.mp3 berhasil disimpan.")

# Alur Kerja Utama
async def main():
    try:
        hook, story, cta, full_script = generate_content()
        
        # Simpan komponen secara terpisah ke file JSON sementara agar bisa dibaca video_builder.py
        meta_data = {"hook": hook, "story": story, "cta": cta}
        with open("script.json", "w", encoding="utf-8") as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=4)
        print("💾 File script.json berhasil disimpan untuk pembuatan subtitle berstruktur.")
            
        await generate_voiceover(full_script)
        
        print("🎬 Memulai proses perakitan video...")
        # Gunakan keyword dari hook untuk mencari video background
        create_tiktok_video(keyword=hook.split()[0] if len(hook.split()) > 0 else "human")
        
        if os.path.exists("script.json"):
            os.remove("script.json")
            
        print("🎉 Selesai! Video dengan Hook dan CTA berhasil dirakit sempurna.")
    except Exception as e:
        print(f"❌ Terjadi kesalahan sistem: {e}")
        raise e

if __name__ == "__main__":
    asyncio.run(main())
