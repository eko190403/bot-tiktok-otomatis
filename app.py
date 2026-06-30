import os
import asyncio
import json
from google import genai
from google.genai import types
import requests
from video_builder import create_tiktok_video

# 1. Fungsi Membuat Konten Lengkap Berstruktur via Gemini
def generate_content():
    print("🧠 Meminta Gemini membuat konten TikTok berstruktur...")
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
    
    full_script = f"{hook}. {story} {cta}"
    
    print(f"🪝 Hook: {hook}")
    print(f"📄 Story: {story}")
    print(f"🚀 CTA: {cta}")
    return hook, story, cta, full_script

# 2. Fungsi Mengubah Teks Menjadi Suara Otomatis Deteksi Voice ID yang Aktif
def generate_voiceover_elevenlabs(text, output_audio="vo.mp3"):
    print("🎙️ Menghubungkan ke ElevenLabs...")
    el_api_key = os.getenv("ELEVENLABS_API_KEY")
    if not el_api_key:
        raise ValueError("❌ Eror: ELEVENLABS_API_KEY tidak ditemukan di Secrets GitHub!")

    headers = {
        "xi-api-key": el_api_key
    }
    
    # Ambil daftar suara yang tersedia di akunmu secara real-time
    print("🔍 Mengambil daftar Voice ID yang aktif di akun kamu...")
    voices_response = requests.get("https://api.elevenlabs.io/v1/voices", headers=headers)
    if voices_response.status_code != 200:
        raise RuntimeError(f"❌ Gagal mengambil daftar suara: {voices_response.text}")
        
    voices_data = voices_response.json()
    available_voices = voices_data.get("voices", [])
    
    if not available_voices:
        raise ValueError("❌ Tidak ada suara yang tersedia di akun ElevenLabs kamu!")
    
    # Pilih suara pertama yang ditemukan di akun (Pasti valid & tidak akan 404)
    selected_voice = available_voices[0]
    voice_id = selected_voice.get("voice_id")
    voice_name = selected_voice.get("name")
    print(f"🎤 Menggunakan suara yang aktif: '{voice_name}' (ID: {voice_id})")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers["Accept"] = "audio/mpeg"
    headers["Content-Type"] = "application/json"
    
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
        }
    }
    
    response = requests.post(url, json=data, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"❌ Eror ElevenLabs API saat TTS: {response.text}")
        
    with open(output_audio, "wb") as f:
        f.write(response.content)
    print("✅ File audio premium vo.mp3 berhasil disimpan.")

# Alur Kerja Utama
async def main():
    try:
        hook, story, cta, full_script = generate_content()
        
        meta_data = {"hook": hook, "story": story, "cta": cta}
        with open("script.json", "w", encoding="utf-8") as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=4)
            
        generate_voiceover_elevenlabs(full_script)
        
        print("🎬 Memulai proses perakitan video...")
        create_tiktok_video(keyword=hook.split()[0] if len(hook.split()) > 0 else "human")
        
        if os.path.exists("script.json"):
            os.remove("script.json")
            
        print("🎉 Selesai! Video dengan suara premium otomatis berhasil dirakit.")
    except Exception as e:
        print(f"❌ Terjadi kesalahan sistem: {e}")
        raise e

if __name__ == "__main__":
    asyncio.run(main())
