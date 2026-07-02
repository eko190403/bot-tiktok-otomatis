import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from subtitle_engine.styles import SubtitleStyles

class SubtitleRenderer:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height
        self.styles = SubtitleStyles()
        self.render_cache = {}  # Cache internal terkendali

    def clear_cache(self):
        """Mematikan potensi memory leak dengan mengosongkan cache setelah satu video selesai[cite: 123]."""
        self.render_cache.clear()

    def create_progressive_frame(self, words_list: list, active_index: int, font_path: str, font_size: int, style_type: str = "body") -> Image.Image:
        """
        Subtitle Engine V4.5 (Karaoke Style Teroptimasi):
        Layout tetap stabil tanpa pergeseran kata, anti-leak RAM, dan hemat CPU[cite: 77].
        """
        # EVALUASI 9: Gunakan text kata saja untuk key cache agar lebih ringkas [cite: 184, 185]
        words_tuple = tuple(w["word"] for w in words_list)
        cache_key = (active_index, words_tuple, font_size, style_type)
        if cache_key in self.render_cache:
            return self.render_cache[cache_key]

        base_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            font = ImageFont.load_default()

        style_cfg = self.styles.get_style_config(style_type)
        
        # EVALUASI 4: Buat satu canvas ukur sekali pakai untuk seluruh kata (Hemat CPU) [cite: 135, 137]
        measure_img = Image.new("RGBA", (1, 1))
        measure_draw = ImageDraw.Draw(measure_img)
        
        # Hitung geometri kata menggunakan ukuran font tunggal agar layout stabil (EVALUASI 6 & 7) [cite: 158, 172]
        word_positions = []
        current_x = 0
        space_w = measure_draw.textbbox((0, 0), " ", font=font)[2] + 8  # Spasi longgar dinamis [cite: 76]

        for idx, item in enumerate(words_list):
            w_text = item["word"].upper()
            bbox = measure_draw.textbbox((0, 0), w_text, font=font)
            w_width = bbox[2] - bbox[0]
            w_height = bbox[3] - bbox[1]
            
            word_positions.append({
                "text": w_text,
                "width": w_width,
                "height": w_height,
                "local_x": current_x
            })
            current_x += w_width + space_w

        total_sentence_width = current_x - space_w if word_positions else 0
        max_word_height = max([w["height"] for w in word_positions]) if word_positions else 40

        # EVALUASI 4 POSITION: Tempatkan teks stabil di area emas 58% tinggi layar [cite: 80]
        start_x = (self.width - total_sentence_width) // 2
        start_y = int(self.height * 0.58) - (max_word_height // 2)

        # Hitung bounding box latar belakang (Konsisten tidak berkedip) [cite: 172]
        box_x0 = start_x - self.styles.BOX_PADDING_X
        box_y0 = start_y - self.styles.BOX_PADDING_Y
        box_x1 = start_x + total_sentence_width + self.styles.BOX_PADDING_X
        box_y1 = start_y + max_word_height + self.styles.BOX_PADDING_Y + 10

        # 1. Gambar Background Rounded Box
        box_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        box_draw = ImageDraw.Draw(box_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 130)
        box_draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=self.styles.BOX_ROUNDED_RADIUS, fill=box_fill)
        base_canvas = Image.alpha_composite(base_canvas, box_canvas)

        # 2. Gambar Lapisan Drop Shadow Blur Terpisah (Saran Profesional #8) [cite: 173, 176]
        shadow_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_canvas)
        off_x, off_y = self.styles.SHADOW_OFFSET

        for idx, w in enumerate(word_positions):
            word_x = start_x + w["local_x"]
            shadow_draw.text(
                (word_x + off_x, start_y + off_y), w["text"], font=font,
                fill=self.styles.SHADOW_COLOR,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.SHADOW_COLOR
            )
        
        # Ambil radius blur dinamis dari configurasi styles [cite: 144, 145]
        blur_radius = getattr(self.styles, 'SHADOW_BLUR_RADIUS', 6)
        shadow_blurred = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        base_canvas = Image.alpha_composite(base_canvas, shadow_blurred)

        # 3. Gambar Teks Utama (Highlight Hanya Berubah Warna) [cite: 159]
        main_draw = ImageDraw.Draw(base_canvas)
        for idx, w in enumerate(word_positions):
            word_x = start_x + w["local_x"]
            text_color = "#FFCC00" if idx == active_index else style_cfg["default_color"]

            main_draw.text(
                (word_x, start_y), w["text"], font=font,
                fill=text_color,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
            )

        self.render_cache[cache_key] = base_canvas
        return base_canvas
