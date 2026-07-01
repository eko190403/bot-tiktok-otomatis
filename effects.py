import moviepy.video.fx as vfx
from moviepy import VideoFileClip
from config import WIDTH, HEIGHT

def crop_vertical(clip):
    """Memastikan video terpotong pas di tengah dengan aspek rasio 9:16."""
    # PERBAIKAN MoviePy 2.x: Panggil fungsi fx secara langsung
    return vfx.Crop(clip, x_center=clip.w/2, y_center=clip.h/2, width=WIDTH, height=HEIGHT)

def apply_slow_zoom(clip, speed=0.04):
    """Efek Ken Burns (Slow Zoom In) khas TikTok menggunakan MoviePy 2.x."""
    # PERBAIKAN MoviePy 2.x: Panggil fungsi fx secara langsung
    return vfx.Resize(clip, lambda t: 1.0 + (speed * t))

def process_background_clip(file_path: str, duration: float) -> VideoFileClip:
    """Memotong, meresize, dan menerapkan efek visual pada satu klip."""
    # Memotong durasi klip video
    clip = VideoFileClip(file_path).subclipped(0, duration).with_audio(None)
    
    # PERBAIKAN MoviePy 2.x: Mengubah pemanggilan .fx() menjadi fungsi biasa
    clip = vfx.Resize(clip, width=WIDTH, height=HEIGHT)
    clip = apply_slow_zoom(clip)
    
    return clip
