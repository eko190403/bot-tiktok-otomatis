import moviepy.video.fx as vfx
from moviepy import VideoFileClip
from config import WIDTH, HEIGHT

def crop_vertical(clip):
    """Memastikan video terpotong pas di tengah dengan aspek rasio 9:16."""
    # Menjalankan fungsi Crop langsung pada objek klip
    return vfx.Crop(clip, x_center=clip.w/2, y_center=clip.h/2, width=WIDTH, height=HEIGHT)

def apply_slow_zoom(clip, speed=0.04):
    """Efek Ken Burns (Slow Zoom In) khas TikTok menggunakan MoviePy 2.x."""
    # Menjalankan fungsi Resize langsung pada objek klip dengan fungsi lambda
    return vfx.Resize(clip, lambda t: 1.0 + (speed * t))

def process_background_clip(file_path: str, duration: float) -> VideoFileClip:
    """Memotong, meresize, dan menerapkan efek visual pada satu klip."""
    # 1. Buka klip video mentah dan potong durasinya
    clip = VideoFileClip(file_path).subclipped(0, duration).with_audio(None)
    
    # 2. Lakukan resize dimensi dasar video agar sesuai ukuran target config
    resized_clip = vfx.Resize(clip, width=WIDTH, height=HEIGHT)
    
    # 3. Terapkan efek slow zoom pada video yang sudah di-resize
    final_clip = apply_slow_zoom(resized_clip)
    
    # PERBAIKAN: Berikan informasi durasi asli klip ke objek efek agar tidak hilang saat concatenate
    final_clip.duration = duration
    
    return final_clip
