import os
from moviepy.editor import ImageClip, VideoFileClip
from config import WIDTH, HEIGHT

def apply_watermark(video_clip, watermark_path: str = "assets/overlays/watermark.png"):
    """Menambahkan watermark atau logo transparan di pojok atas video."""
    if not os.path.exists(watermark_path):
        return video_clip
        
    watermark = (ImageClip(watermark_path)
                 .set_duration(video_clip.duration)
                 .resize(width=150) # Menyesuaikan ukuran logo
                 .set_position(("center", HEIGHT * 0.1)) # Letakkan di area atas aman
                 .set_opacity(0.6))
                 
    return watermark
