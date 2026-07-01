from moviepy import VideoFileClip
from config import WIDTH, HEIGHT

def apply_slow_zoom(clip, speed=0.04):
    """Efek Ken Burns (Slow Zoom In) khas TikTok menggunakan MoviePy 2.x."""
    # PERBAIKAN: Menggunakan fungsi lambda langsung ke dalam metode .resized() bawaan klip
    return clip.resized(lambda t: 1.0 + (speed * t))

def process_background_clip(file_path: str, duration: float) -> VideoFileClip:
    """Memotong, meresize, dan menerapkan efek visual pada satu klip."""
    # 1. Buka klip video mentah, potong durasi, dan matikan audionya
    clip = VideoFileClip(file_path).subclipped(0, duration).with_audio(None)
    
    # 2. Lakukan resize dimensi dasar video langsung menggunakan metode .resized() bawaan objek
    resized_clip = clip.resized(width=WIDTH, height=HEIGHT)
    
    # 3. Terapkan efek slow zoom
    final_clip = apply_slow_zoom(resized_clip)
    
    return final_clip
