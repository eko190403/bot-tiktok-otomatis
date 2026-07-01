import edge_tts
from moviepy.editor import AudioFileClip

async def generate_voiceover_edge(text: str, output_path: str = "temp/vo.mp3"):
    """Mengonversi teks menjadi audio menggunakan Edge-TTS (Suara Pria Ardi)."""
    print("🎙️ Mengonversi script menjadi suara Edge-TTS (id-ID-ArdiNeural)...")
    voice = "id-ID-ArdiNeural"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)
    print("✅ File audio Voice Over berhasil disimpan.")

def mix_background_music(vo_path: str, bgm_path: str = None, volume_bgm: float = 0.1) -> AudioFileClip:
    """Menggabungkan VO dengan BGM dan mengatur level volume audio."""
    vo_clip = AudioFileClip(vo_path)
    
    if bgm_path and os.path.exists(bgm_path):
        # Logika pencampuran audio jika file BGM tersedia di assets/bgm/
        pass
        
    return vo_clip
