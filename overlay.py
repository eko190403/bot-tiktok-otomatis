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
