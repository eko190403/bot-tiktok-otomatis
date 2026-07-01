from moviepy import VideoFileClip
from config import WIDTH, HEIGHT

def apply_slow_zoom(clip, speed=0.04):
    """Efek Ken Burns (Slow Zoom In) khas TikTok menggunakan MoviePy 2.x."""
    return clip.resized(lambda t: 1.0 + (speed * t))

def process_background_clip(file_path: str, duration: float) -> VideoFileClip:
    """Memotong, meresize, dan menerapkan efek visual pada satu klip dengan proteksi durasi."""
    # 1. Buka klip video mentah dan matikan audionya
    clip = VideoFileClip(file_path).with_audio(None)
    
    # PROTEKSI: Jika durasi asli video lebih pendek dari target potong, gunakan durasi asli maksimumnya
    actual_duration = clip.duration
    target_duration = min(duration, actual_duration)
    
    # 2. Potong dengan aman tanpa melampaui batas maksimum video asli
    clip = clip.subclipped(0, target_duration)
    
    # 3. Lakukan resize dimensi dasar video
    resized_clip = clip.resized(width=WIDTH, height=HEIGHT)
    
    # 4. Terapkan efek slow zoom
    final_clip = apply_slow_zoom(resized_clip)
    
    return final_clip
