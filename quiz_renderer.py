import os
import logging
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

def compose_quiz_canvas(image_a_path: str, image_b_path: str, label_a: str = "A: PILIHAN 1", label_b: str = "B: PILIHAN 2", output_path: str = "temp/quiz_canvas.jpg", width: int = 1080, height: int = 1920) -> bool:
    """
    Menyusun 2 gambar AI (A dan B) secara Atas & Bawah di canvas 1080x1920.
    Menambahkan badge label A dan B dengan gaya visual yang kontras.
    """
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 1. Buat canvas dasar hitam
        canvas = Image.new("RGB", (width, height), (15, 15, 20))
        
        # Porsi gambar: Atas (y: 220 ke 920, h: 700), Bawah (y: 980 ke 1680, h: 700)
        box_h = 700
        box_w = width - 80 # 1000px
        
        # Helper crop & resize
        def fit_image(img_path, target_w, target_h):
            if not os.path.exists(img_path):
                # Buat placeholder jika file tidak ada
                img = Image.new("RGB", (target_w, target_h), (40, 40, 50))
                draw = ImageDraw.Draw(img)
                draw.text((target_w // 4, target_h // 2), "GAMBAR AI", fill=(200, 200, 200))
                return img
            img = Image.open(img_path)
            w, h = img.size
            aspect = w / h
            target_aspect = target_w / target_h
            if aspect > target_aspect:
                new_w = int(h * target_aspect)
                offset = (w - new_w) // 2
                img = img.crop((offset, 0, offset + new_w, h))
            else:
                new_h = int(w / target_aspect)
                offset = (h - new_h) // 2
                img = img.crop((0, offset, w, offset + new_h))
            return img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        img_a = fit_image(image_a_path, box_w, box_h)
        img_b = fit_image(image_b_path, box_w, box_h)
        
        # Paste gambar ke canvas
        x_pos = 40
        y_pos_a = 220
        y_pos_b = 980
        
        canvas.paste(img_a, (x_pos, y_pos_a))
        canvas.paste(img_b, (x_pos, y_pos_b))
        
        draw = ImageDraw.Draw(canvas)
        
        # Font setup
        font_paths = ["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial.ttf"]
        font_label = None
        for p in font_paths:
            try:
                font_label = ImageFont.truetype(p, 42)
                break
            except Exception:
                continue
        if font_label is None:
            font_label = ImageFont.load_default()
            
        # Draw Border & Badge Label Gambar A
        draw.rectangle([x_pos - 4, y_pos_a - 4, x_pos + box_w + 4, y_pos_a + box_h + 4], outline=(255, 45, 85), width=6)
        # Badge Label A
        try:
            lw_a = draw.textlength(label_a, font=font_label)
        except AttributeError:
            lw_a = draw.textsize(label_a, font=font_label)[0]
        draw.rounded_rectangle([x_pos + 20, y_pos_a + 20, x_pos + lw_a + 60, y_pos_a + 90], radius=15, fill=(255, 45, 85, 230))
        draw.text((x_pos + 40, y_pos_a + 30), label_a, fill=(255, 255, 255), font=font_label)
        
        # Draw Border & Badge Label Gambar B
        draw.rectangle([x_pos - 4, y_pos_b - 4, x_pos + box_w + 4, y_pos_b + box_h + 4], outline=(52, 199, 89), width=6)
        # Badge Label B
        try:
            lw_b = draw.textlength(label_b, font=font_label)
        except AttributeError:
            lw_b = draw.textsize(label_b, font=font_label)[0]
        draw.rounded_rectangle([x_pos + 20, y_pos_b + 20, x_pos + lw_b + 60, y_pos_b + 90], radius=15, fill=(52, 199, 89, 230))
        draw.text((x_pos + 40, y_pos_b + 30), label_b, fill=(0, 0, 0), font=font_label)
        
        canvas.save(output_path, quality=95)
        logger.info(f" Quiz Canvas berhasil disusun dan disimpan ke: {output_path}")
        return True
    except Exception as e:
        logger.error(f" Gagal menyusun quiz canvas: {e}")
        return False
