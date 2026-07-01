from moviepy.editor import VideoFileClip
import moviepy.video.fx.all as vfx
from config import WIDTH, HEIGHT

def crop_vertical(clip):
    """Memastikan video terpotong pas di tengah dengan aspek rasio 9:16."""
    return clip.fx(vfx.crop, x_center=clip.w/2, y_center=clip.h/2, width=WIDTH, height=HEIGHT)

def apply_slow_zoom(clip, speed=0.04):
    """Efek Ken Burns (Slow Zoom In) khas TikTok menggunakan MoviePy 2.x."""
    return clip.fx(vfx.resize, lambda t: 1.0 + (speed * t))

def process_background_clip(file_path: str, duration: float) -> VideoFileClip:
    """Memotong, meresize, dan menerapkan efek visual pada satu klip."""
    clip = VideoFileClip(file_path).subclip(0, duration).set_audio(None)
    # Gunakan vfx.Resize untuk MoviePy 2.x
    clip = clip.fx(vfx.resize, width=WIDTH, height=HEIGHT)
    clip = apply_slow_zoom(clip)
    return clip
