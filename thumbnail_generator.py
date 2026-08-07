import os
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

def extract_frame_from_video(video_path: str, output_image_path: str, timestamp_sec: float = 1.0) -> bool:
    """Ekstrak satu frame dari video di detik tertentu menggunakan subprocess ffmpeg."""
    import subprocess
    try:
        os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
        # Panggil ffmpeg untuk mengekstrak 1 frame
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(timestamp_sec),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            output_image_path
        ]
        # Sembunyikan output banner/log agar bersih
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception as e:
        logger.error(f" Gagal mengekstrak frame dari video: {e}")
        return False

# Peta warna tema ke RGB untuk thumbnail
THUMBNAIL_THEME_COLORS = {
    "classic_yellow": (255, 204, 0),
    "neon_green": (52, 199, 89),
    "cyberpunk_pink": (255, 45, 85)
}

def generate_thumbnail(hook_text: str, background_path: str, output_path: str = "output/thumbnail.jpg", brand_name: str = "Ruang Pikir", theme_color: str = "classic_yellow") -> bool:
    """
    Menghasilkan gambar thumbnail 1280x720 (16:9) dengan overlay teks hook.
    """
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if not os.path.exists(background_path):
            logger.warning(f" Background thumbnail tidak ditemukan: {background_path}")
            return False

        # 1. Buka background dan posisikan di tengah (1280x720)
        img_bg = Image.open(background_path)
        bg_w, bg_h = img_bg.size
        
        # Target rasio 16:9
        target_w, target_h = 1280, 720
        
        # Crop center ke rasio 16:9
        src_aspect = bg_w / bg_h
        target_aspect = target_w / target_h
        
        if src_aspect > target_aspect:
            # Source lebih lebar, crop kiri-kanan
            new_w = int(bg_h * target_aspect)
            offset_x = (bg_w - new_w) // 2
            img_cropped = img_bg.crop((offset_x, 0, offset_x + new_w, bg_h))
        else:
            # Source lebih tinggi (vertical), crop atas-bawah
            new_h = int(bg_w / target_aspect)
            offset_y = (bg_h - new_h) // 2
            img_cropped = img_bg.crop((0, offset_y, bg_w, offset_y + new_h))
            
        img_resized = img_cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        # 2. Buat draw layer & overlay gradien gelap (meningkatkan keterbacaan teks)
        overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        # Gradient dari atas (transparan) ke bawah (gelap) untuk efek premium
        for y_pos in range(target_h):
            opacity = int(60 + (180 * (y_pos / target_h)))  # 60 di atas, 240 di bawah
            overlay_draw.line([(0, y_pos), (target_w, y_pos)], fill=(0, 0, 0, opacity))
        img_resized = img_resized.convert("RGBA")
        img_combined = Image.alpha_composite(img_resized, overlay).convert("RGB")
        
        draw = ImageDraw.Draw(img_combined)
        
        # 3. Cari font (Bebas Neue / Arial / Sans-serif)
        # Mencoba memuat font sistem tebal
        font_paths = [
            "arialbd.ttf",       # Windows Bold
            "HelveticaNeue-Bold.otf", # macOS Bold
            "DejaVuSans-Bold.ttf", # Linux Bold
            "Arial.ttf"
        ]
        
        font = None
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, 72)
                break
            except Exception:
                continue
                
        if font is None:
            font = ImageFont.load_default()
            logger.info(" Menggunakan default font PIL karena font sistem tebal tidak ditemukan.")
            
        # 4. Bungkus teks agar muat di layar
        text = hook_text.upper()
        words = text.split()
        lines = []
        current_line = []
        
        # Limit lebar teks (80% dari lebar layar)
        max_width = int(target_w * 0.8)
        
        for word in words:
            current_line.append(word)
            # Dapatkan ukuran teks untuk baris saat ini
            test_line = " ".join(current_line)
            try:
                line_w = draw.textlength(test_line, font=font)
            except AttributeError:
                # Fallback untuk PIL versi lama
                line_w = draw.textsize(test_line, font=font)[0]
                
            if line_w > max_width:
                if len(current_line) > 1:
                    current_line.pop()
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(" ".join(current_line))
                    current_line = []
                    
        if current_line:
            lines.append(" ".join(current_line))
            
        # Batasi maksimal 3 baris
        lines = lines[:3]
        
        # 5. Gambar Badge High-CTR di pojok kiri atas
        badges = ["🔥 VIRAL", "🧠 RAHASIA", "💡 FAKTA GELAP", "⚡ MUST WATCH", "👁️ TAHUKAH KAMU"]
        import random
        badge_text = random.choice(badges)
        
        try:
            badge_font = ImageFont.truetype("arialbd.ttf", 30)
        except Exception:
            badge_font = font
            
        try:
            bw = draw.textlength(badge_text, font=badge_font)
        except AttributeError:
            bw = draw.textsize(badge_text, font=badge_font)[0]
            
        # Draw pill box untuk badge
        bx1, by1 = 40, 40
        bx2, by2 = int(bx1 + bw + 40), by1 + 55
        badge_color = THUMBNAIL_THEME_COLORS.get(theme_color, (255, 204, 0))
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=15, fill=badge_color)
        draw.text((bx1 + 20, by1 + 10), badge_text, fill=(0, 0, 0), font=badge_font)

        # 6. Gambar teks hook di tengah vertikal dan horizontal dengan drop shadow ganda
        line_height = 85
        total_text_height = len(lines) * line_height
        start_y = (target_h - total_text_height) // 2 + 20
        
        text_color = THUMBNAIL_THEME_COLORS.get(theme_color, (255, 204, 0))
        for i, line in enumerate(lines):
            try:
                line_w = draw.textlength(line, font=font)
            except AttributeError:
                line_w = draw.textsize(line, font=font)[0]
                
            x = (target_w - line_w) // 2
            y = start_y + (i * line_height)
            
            # Shadow tebal multi-layer untuk kontras tinggi di latar apapun
            for off_x, off_y in [(-3,-3), (3,-3), (-3,3), (3,3), (0,4), (4,0), (-4,0), (0,-4)]:
                draw.text((x + off_x, y + off_y), line, fill=(0, 0, 0), font=font)

            draw.text((x, y), line, fill=text_color, font=font)

        # 7. Brand watermark di bawah
        try:
            brand_font = ImageFont.truetype("arialbd.ttf", 28)
        except Exception:
            brand_font = font
            
        brand_text = f"// {brand_name.upper()}"
        try:
            brand_w = draw.textlength(brand_text, font=brand_font)
        except AttributeError:
            brand_w = draw.textsize(brand_text, font=brand_font)[0]
            
        brand_x = (target_w - brand_w) // 2
        brand_y = target_h - 60
        
        # Background box kecil brand
        draw.rounded_rectangle([brand_x - 15, brand_y - 5, brand_x + brand_w + 15, brand_y + 35], radius=8, fill=(0, 0, 0, 180))
        draw.text((brand_x, brand_y), brand_text, fill=(255, 255, 255), font=brand_font)
        
        img_combined.save(output_path, quality=95)
        logger.info(f" Thumbnail High-CTR V2 berhasil dibuat: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f" Gagal membuat thumbnail: {e}")
        return False
