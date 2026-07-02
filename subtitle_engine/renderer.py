import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from subtitle_engine.styles import SubtitleStyles

class SubtitleRenderer:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height
        self.styles = SubtitleStyles()
        
        self.render_cache = {}
        self.font_cache = {}
        self.static_layer_cache = {}
        
        # Objek pengukur geometry sekali pakai
        self.measure_img = Image.new("RGBA", (1, 1))
        self.measure_draw = ImageDraw.Draw(self.measure_img)

    def clear_cache(self):
        """Mematikan potensi memory leak dengan mengosongkan seluruh cache."""
        self.render_cache.clear()
        self.static_layer_cache.clear()

    def _get_cached_font(self, font_path: str, font_size: int):
        font_key = (font_path, font_size)
        if font_key not in self.font_cache:
            try:
                self.font_cache[font_key] = ImageFont.truetype(font_path, font_size)
            except IOError:
                self.font_cache[font_key] = ImageFont.load_default()
        return self.font_cache[font_key]

    def _render_static_layer(self, words_tuple: tuple, font, font_active, style_cfg) -> Image.Image:
        """
        Merender Lapisan Statis (Background Box + Drop Shadow Teks).
        Dihitung menggunakan basis geometri font_active terbesar agar layout
        ruang box terkunci diam sejak awal dan tidak berkedip.
        """
        static_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        word_positions = []
        current_x = 0
        
        # Ambil lebar spasi longgar dinamis
        space_w = self.measure_draw.textbbox((0, 0), " ", font=font_active)[2] + 12

        # Hitung titik koordinat X absolut untuk tiap kata berdasarkan porsi ruang maksimalnya
        for item_word in words_tuple:
            w_text = item_word.upper()
            # Gunakan font_active untuk pengukuran ruang agar tidak terjadi layout shifting (goyang)
            bbox = self.measure_draw.textbbox((0, 0), w_text, font=font_active)
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
        max_word_height = max(w["height"] for w in word_positions) if word_positions else 40

        # Kunci posisi sumbu koordinat di area emas 58% tinggi layar
        start_x = (self.width - total_sentence_width) // 2
        start_y = int(self.height * 0.58) - (max_word_height // 2)

        # Hitung batas luar rounded rectangle box background
        box_x0 = start_x - self.styles.BOX_PADDING_X
        box_y0 = start_y - self.styles.BOX_PADDING_Y
        box_x1 = start_x + total_sentence_width + self.styles.BOX_PADDING_X
        box_y1 = start_y + max_word_height + self.styles.BOX_PADDING_Y + 12

        # 1. Gambar Background Rounded Box langsung ke canvas statis
        static_draw = ImageDraw.Draw(static_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 135)
        static_draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=self.styles.BOX_ROUNDED_RADIUS, fill=box_fill)

        # 2. Gambar Lapisan Drop Shadow Blur Terpisah
        shadow_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_canvas)
        off_x, off_y = self.styles.SHADOW_OFFSET

        for w in word_positions:
            word_x = start_x + w["local_x"]
            shadow_draw.text(
                (word_x + off_x, start_y + off_y), w["text"], font=font,
                fill=self.styles.SHADOW_COLOR,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.SHADOW_COLOR
            )
        
        blur_radius = self.styles.SHADOW_BLUR_RADIUS
        shadow_blurred = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        
        # Satukan background box dan drop shadow menjadi satu lapisan statis tunggal
        static_canvas = Image.alpha_composite(static_canvas, shadow_blurred)
        
        return static_canvas, word_positions, start_x, start_y

    def create_progressive_frame(self, words_list: list, active_index: int, font_path: str, font_size: int, style_type: str = "body") -> Image.Image:
        """
        Subtitle Engine V5.0 (Active Scale Zoom & Zero-Shaking):
        Kalimat diam kokoh di tempat, hanya kata aktif yang membesar 106% dan berubah kuning.
        """
        words_tuple = tuple(w["word"] for w in words_list)
        cache_key = (active_index, words_tuple, font_size, style_type)
        if cache_key in self.render_cache:
            return self.render_cache[cache_key]

        font_normal = self._get_cached_font(font_path, font_size)
        # PERBAIKAN POIN PRIORITAS 5: Naikkan skala ukuran font kata aktif sebesar 106% (TikTok Style!)
        font_active = self._get_cached_font(font_path, int(font_size * 1.06))
        
        style_cfg = self.styles.get_style_config(style_type)

        # Cek memori cache untuk lapisan dasar statis
        static_key = (words_tuple, font_size, style_type)
        if static_key not in self.static_layer_cache:
            self.static_layer_cache[static_key] = self._render_static_layer(words_tuple, font_normal, font_active, style_cfg)
        
        static_layer_img, word_positions, start_x, start_y = self.static_layer_cache[static_key]
        
        # Salin lapisan dasar untuk ditimpa lapisan teks utama dinamis
        base_canvas = static_layer_img.copy()
        main_draw = ImageDraw.Draw(base_canvas)

        # Gambar teks utama di atas bayangan box
        for idx, w in enumerate(word_positions):
            is_word_active = (idx == active_index)
            
            # Tentukan font dan warna berdasarkan status keaktifan kata
            current_font = font_active if is_word_active else font_normal
            highlight_color = self.styles.ACTIVE_WORD_COLOR
            text_color = highlight_color if is_word_active else style_cfg["default_color"]

            # Cari titik tengah X dan Y per kata agar saat membesar tetap presisi di jangkar tengahnya
            word_center_x = start_x + w["local_x"] + (w["width"] // 2)
            
            # Ukur geometry teks saat ini untuk penyeimbang koordinat render
            bbox_curr = main_draw.textbbox((0, 0), w["text"], font=current_font)
            curr_w = bbox_curr[2] - bbox_curr[0]
            curr_h = bbox_curr[3] - bbox_curr[1]
            
            # Hitung pergeseran offset agar penulisan text tepat berada di pusat ruang aslinya
            render_x = word_center_x - (curr_w // 2)
            render_y = start_y + (w["height"] // 2) - (curr_h // 2)

            main_draw.text(
                (render_x, render_y), w["text"], font=current_font,
                fill=text_color,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
            )

        self.render_cache[cache_key] = base_canvas
        return base_canvas
