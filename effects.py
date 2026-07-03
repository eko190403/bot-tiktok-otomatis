from moviepy import VideoFileClip
from config import WIDTH, HEIGHT
from PIL import Image
import numpy as np

def apply_slow_zoom(clip, speed=0.04):
    """Efek Ken Burns (Slow Zoom In) khas TikTok menggunakan PIL & transform untuk menjaga resolusi tetap."""
    def zoom_effect(get_frame, t):
        frame = get_frame(t) # Numpy array (H, W, C)
        h, w, c = frame.shape
        factor = 1.0 + (speed * t)
        
        # Hitung ukuran baru hasil zoom
        w_new = int(round(w * factor))
        h_new = int(round(h * factor))
        
        # Konversi ke PIL Image, resize, lalu crop bagian tengah kembali ke (w, h)
        img = Image.fromarray(frame)
        img_resized = img.resize((w_new, h_new), Image.Resampling.BILINEAR)
        
        left = (w_new - w) // 2
        top = (h_new - h) // 2
        right = left + w
        bottom = top + h
        
        img_cropped = img_resized.crop((left, top, right, bottom))
        
        # Pastikan ukuran hasil cropping tepat sesuai dengan dimensi asli (w, h)
        if img_cropped.size != (w, h):
            img_cropped = img_cropped.resize((w, h), Image.Resampling.BILINEAR)
            
        return np.array(img_cropped)
        
    return clip.transform(zoom_effect, keep_duration=True)

def process_background_clip(file_path: str, duration: float) -> VideoFileClip:
    """Memotong, meresize, dan menerapkan efek visual pada satu klip dengan proteksi durasi."""
    # 1. Buka klip video mentah dan matikan audionya
    clip = VideoFileClip(file_path).with_audio(None)
    
    # PROTEKSI: Jika durasi asli video lebih pendek dari target potong, gunakan durasi asli maksimumnya
    actual_duration = clip.duration
    target_duration = min(duration, actual_duration)
    
    # 2. Potong dengan aman tanpa melampaui batas maksimum video asli
    clip = clip.subclipped(0, target_duration)
    
    # 3. Lakukan resize dimensi dasar video ke tepat (WIDTH, HEIGHT)
    resized_clip = clip.resized((WIDTH, HEIGHT))
    
    # 4. Terapkan efek slow zoom
    final_clip = apply_slow_zoom(resized_clip)
    
    return final_clip
