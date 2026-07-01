import moviepy.video.fx as vfx
from moviepy import VideoFileClip
from config import WIDTH, HEIGHT

def crop_vertical(clip):
    """Memastikan video terpotong pas di tengah dengan aspek rasio 9:16."""
    return clip.fx(vfx.Crop, x_center=clip.w/2, y_center=clip.h/2, width=WIDTH, height=HEIGHT)

def apply_slow_zoom(clip, speed=0.04):
    """Efek Ken Burns (Slow Zoom In) khas TikTok menggunakan MoviePy 2.x."""
    return clip.fx(vfx.Resize, lambda t: 1.0 + (speed * t))

def process_background_clip(file_path: str, duration: float) -> VideoFileClip:
    """Memotong, meresize, dan menerapkan efek visual pada satu klip."""
    # Perbaikan Final MoviePy 2.x: Menggunakan .sliced() untuk memotong durasi klip video
    clip = VideoFileClip(file_path).sliced(0, duration).with_audio(None)
    clip = clip.fx(vfx.Resize, width=WIDTH, height=HEIGHT)
    clip = apply_slow_zoom(clip)
    return clip
