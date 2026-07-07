"""
overlay.py — Watermark dan branding channel untuk video TikTok.
Mendukung watermark PNG maupun watermark teks (fallback jika tidak ada file gambar).
"""
import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np


def create_text_watermark_frame(text: str, video_width: int, video_height: int) -> np.ndarray:
    """
    Membuat frame RGBA transparan berisi teks watermark untuk di-overlay ke video.
    Digunakan sebagai ImageClip oleh MoviePy.
    """
    img = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Coba muat font custom, fallback ke default
    # Coba muat font custom, fallback ke default
    font_paths = [
        os.path.join(os.path.dirname(__file__), "assets", "fonts", "font.ttf"),
        os.path.join(os.path.dirname(__file__), "assets", "fonts", "Oswald-Bold.ttf")
    ]
    font = None
    for path in font_paths:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size=28)
                break
            except (IOError, OSError):
                continue
    if font is None:
        font = ImageFont.load_default()

    # Ukur dimensi teks
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Posisi: pojok kanan bawah dengan padding 20px
    padding = 20
    x = video_width - text_w - padding
    y = video_height - text_h - padding

    # Bayangan teks (shadow) agar terbaca di atas background apapun
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 160))
    # Teks utama putih semi-transparan
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 200))

    return np.array(img)


def apply_text_watermark(video_clip, channel_name: str = "@RuangPikir"):
    """
    Menambahkan watermark teks channel di pojok kanan bawah video.
    Kompatibel dengan MoviePy versi baru (tidak memakai moviepy.editor).
    """
    try:
        from moviepy import ImageClip, CompositeVideoClip

        w = int(video_clip.w)
        h = int(video_clip.h)

        wm_frame = create_text_watermark_frame(channel_name, w, h)
        watermark_clip = (
            ImageClip(wm_frame)
            .with_duration(video_clip.duration)
            .with_opacity(0.75)
        )
        return CompositeVideoClip([video_clip, watermark_clip])
    except Exception as e:
        import logging
        logging.getLogger("video_pipeline").warning(
            "⚠️ Watermark gagal ditambahkan: %s. Melanjutkan tanpa watermark.", e
        )
        return video_clip

def create_visual_cta_frame(video_width: int, video_height: int) -> np.ndarray:
    """Membuat frame visual CTA premium (tombol & info share/save) di tengah bawah."""
    img = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Target box di tengah bawah — dibuat sedikit lebih kecil dan diangkat
    # supaya tidak menutupi UI platform (like/comment/share) pada beberapa aplikasi.
    box_w = min(640, video_width - 120)
    box_h = 180
    start_x = (video_width - box_w) // 2
    # Angkat sedikit dari bottom agar area action/platform UI tetap terlihat
    start_y = int(video_height * 0.48)
    
    # 1. Background Box semi transparan
    draw.rounded_rectangle(
        [start_x, start_y, start_x + box_w, start_y + box_h],
        radius=25,
        fill=(0, 0, 0, 215),
        outline=(255, 204, 0, 255),
        width=4
    )
    
    # 2. Cari font tebal
    font_paths = [
        "assets/fonts/Oswald-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "arialbd.ttf"
    ]
    font_title = None
    for path in font_paths:
        try:
            font_title = ImageFont.truetype(path, size=38)
            break
        except Exception:
            continue
    if font_title is None:
        font_title = ImageFont.load_default()
        
    font_desc = None
    for path in font_paths:
        try:
            font_desc = ImageFont.truetype(path, size=26)
            break
        except Exception:
            continue
    if font_desc is None:
        font_desc = ImageFont.load_default()
        
    # 3. Tulis teks CTA (singkat) — jangan tutupi area interaksi platform
    title_text = "SIMPAN & BAGIKAN VIDEO INI!"
    desc_text = "Tap 2x jika info ini berguna"
    
    try:
        t_bbox = draw.textbbox((0, 0), title_text, font=font_title)
        t_w = t_bbox[2] - t_bbox[0]
        tx = start_x + (box_w - t_w) // 2
        ty = start_y + 45
        draw.text((tx, ty), title_text, font=font_title, fill=(255, 204, 0, 255))
        
        d_bbox = draw.textbbox((0, 0), desc_text, font=font_desc)
        d_w = d_bbox[2] - d_bbox[0]
        dx = start_x + (box_w - d_w) // 2
        dy = start_y + 135
        draw.text((dx, dy), desc_text, font=font_desc, fill=(240, 240, 240, 255))
    except Exception:
        draw.text((start_x + 50, start_y + 40), title_text, font=font_title, fill=(255, 204, 0))
        draw.text((start_x + 50, start_y + 120), desc_text, font=font_desc, fill=(255, 255, 255))
        
    return np.array(img)

def apply_visual_cta(video_clip):
    """Menampilkan overlay CTA visual di 3 detik terakhir video."""
    try:
        from moviepy import ImageClip, CompositeVideoClip
        w = int(video_clip.w)
        h = int(video_clip.h)
        duration = video_clip.duration
        
        # Buat cta clip muncul di 3 detik terakhir
        cta_duration = 3.0
        if duration < cta_duration:
            cta_duration = duration
            
        start_time = duration - cta_duration
        
        cta_frame = create_visual_cta_frame(w, h)
        cta_clip = (
            ImageClip(cta_frame)
            .with_start(start_time)
            .with_duration(cta_duration)
            .with_opacity(0.95)
        )
        return CompositeVideoClip([video_clip, cta_clip])
    except Exception as e:
        import logging
        logging.getLogger("video_pipeline").warning("⚠️ Visual CTA gagal: %s", e)
        return video_clip

def apply_cinematic_overlay(video_clip):
    """
    Mengatasi Stock Footage Syndrome dengan menyatukan seluruh klip (Pexels)
    ke dalam satu "Cinematic Universe" menggunakan Vignette & Film Grain noise tipis.
    """
    try:
        from moviepy import ImageClip, CompositeVideoClip
        w, h = int(video_clip.w), int(video_clip.h)
        duration = video_clip.duration
        
        # 1. Buat frame transparan untuk overlay
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        
        # 2. Gambar Vignette (gelap di ujung-ujung)
        import math
        pixels = overlay.load()
        cx, cy = w / 2, h / 2
        max_dist = math.hypot(cx, cy)
        
        # 3. Tambahkan efek Film Grain Statis yang sangat halus
        # Kita menggunakan satu frame grain statis dengan alpha sangat rendah
        # untuk menghindari frame-by-frame processing python yang sangat lambat di MoviePy
        import random
        for y in range(0, h, 2): # Lewati tiap 2 pixel agar lebih cepat dan terlihat seperti butiran besar
            for x in range(0, w, 2):
                dist = math.hypot(x - cx, y - cy)
                vignette_intensity = int(255 * (dist / max_dist)**2)
                vignette_intensity = min(220, max(0, vignette_intensity - 50))
                
                # Film grain noise
                noise = random.randint(-15, 15)
                
                alpha = vignette_intensity
                if alpha > 0:
                    r, g, b = max(0, 15+noise), max(0, 10+noise), max(0, 20+noise) # Sedikit kebiruan/gelap
                    pixels[x, y] = (r, g, b, alpha)
                    if x+1 < w: pixels[x+1, y] = (r, g, b, alpha)
                    if y+1 < h: pixels[x, y+1] = (r, g, b, alpha)
                    if x+1 < w and y+1 < h: pixels[x+1, y+1] = (r, g, b, alpha)

        # Blur sedikit agar menyatu (Gaussian Blur lambat, resize hack lebih cepat)
        overlay = overlay.resize((w//2, h//2), Image.Resampling.NEAREST).resize((w, h), Image.Resampling.BILINEAR)

        overlay_clip = (
            ImageClip(np.array(overlay))
            .with_duration(duration)
        )
        
        return CompositeVideoClip([video_clip, overlay_clip])
    except Exception as e:
        import logging
        logging.getLogger("video_pipeline").warning("⚠️ Cinematic Overlay gagal: %s", e)
        return video_clip
