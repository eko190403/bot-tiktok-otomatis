import os
import edge_tts
from moviepy import AudioFileClip

async def generate_voiceover_edge(text: str, output_path: str = "temp/vo.mp3"):
    """Mengonversi teks menjadi audio menggunakan Edge-TTS (Suara Pria Ardi)."""
    print("🎙️ Mengonversi script menjadi suara Edge-TTS (id-ID-ArdiNeural)...")
    voice = "id-ID-ArdiNeural"
    
    # Pastikan folder temp tersedia
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)
    print("✅ File audio Voice Over berhasil disimpan.")

def mix_background_music(vo_path: str, bgm_path: str = None, volume_bgm: float = 0.1) -> AudioFileClip:
    """Menggabungkan VO dengan BGM dan mengatur level volume audio."""
    if not os.path.exists(vo_path):
        raise FileNotFoundError(f"❌ File VO tidak ditemukan di: {vo_path}")
        
    vo_clip = AudioFileClip(vo_path)
    
    if bgm_path and os.path.exists(bgm_path):
        # Logika pencampuran audio jika file BGM tersedia di masa mendatang
        pass
        
    return vo_clip
