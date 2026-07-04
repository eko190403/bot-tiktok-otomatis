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
    """Memotong, melakukan crop-to-fit (agar tidak gepeng/distorsi), dan meresize video."""
    # 1. Buka klip video mentah dan matikan audionya
    clip = VideoFileClip(file_path).with_audio(None)
    
    # PROTEKSI: Jika durasi asli video lebih pendek dari target potong, gunakan durasi asli maksimumnya
    actual_duration = clip.duration
    target_duration = min(duration, actual_duration)
    
    # 2. Potong dengan aman tanpa melampaui batas maksimum video asli
    clip = clip.subclipped(0, target_duration)
    
    # 3. Crop-to-fit untuk menghindari video gepeng jika inputnya landscape atau bukan 9:16
    w, h = clip.size
    target_ratio = WIDTH / HEIGHT
    current_ratio = w / h
    
    x1, y1, x2, y2 = 0, 0, w, h
    if current_ratio > target_ratio:
        # Video terlalu lebar (landscape), potong sisi kiri dan kanan secara simetris
        new_w = int(h * target_ratio)
        x_offset = (w - new_w) // 2
        x1 = x_offset
        x2 = x_offset + new_w
    elif current_ratio < target_ratio:
        # Video terlalu tinggi, potong sisi atas dan bawah secara simetris
        new_h = int(w / target_ratio)
        y_offset = (h - new_h) // 2
        y1 = y_offset
        y2 = y_offset + new_h
        
    clip = clip.cropped(x1=x1, y1=y1, x2=x2, y2=y2)
    
    # 4. Lakukan resize dimensi dasar video ke tepat (WIDTH, HEIGHT)
    resized_clip = clip.resized((WIDTH, HEIGHT))
    
    # 5. Terapkan efek slow zoom
    final_clip = apply_slow_zoom(resized_clip)
    
    return final_clip
