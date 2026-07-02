import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from subtitle_engine.styles import SubtitleStyles

class SubtitleRenderer:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height
        self.styles = SubtitleStyles()
        
        # Inisialisasi sistem Cache Terkendali
        self.render_cache = {}
        self.font_cache = {}       # Optimasi 1: Cache Font khusus agar tidak re-load file (EVALUASI 1)
        self.static_layer_cache = {}  # Optimasi 2: Cache Lapisan Statis (Background Box + Blur Shadow)
        
        # Objek pengukur geometry sekali pakai
        self.measure_img = Image.new("RGBA", (1, 1))
        self.measure_draw = ImageDraw.Draw(self.measure_img)

    def clear_cache(self):
        """Mematikan potensi memory leak dengan mengosongkan seluruh cache setelah seksi selesai."""
        self.render_cache.clear()
        self.static_layer_cache.clear()

    def _get_cached_font(self, font_path: str, font_size: int):
        """Mengambil atau menyimpan instans font dari cache memori internal."""
        font_key = (font_path, font_size)
        if font_key not in self.font_cache:
            try:
                self.font_cache[font_key] = ImageFont.truetype(font_path, font_size)
            except IOError:
                self.font_cache[font_key] = ImageFont.load_default()
        return self.font_cache[font_key]

    def _render_static_layer(self, words_tuple: tuple, font, style_cfg) -> Image.Image:
        """
        Merender Lapisan Statis (Background + Shadow Teks Putih).
        Hanya dipanggil SEKALI per kelompok frasa baru (Menghemat waktu hitung CPU).
        """
        static_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        
        # Hitung geometri kata secara presisi
        word_positions = []
        current_x = 0
        space_w = self.measure_draw.textbbox((0, 0), " ", font=font)[2] + 8

        for item_word in words_tuple:
            w_text = item_word.upper()
            bbox = self.measure_draw.textbbox((0, 0), w_text, font=font)
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

        start_x = (self.width - total_sentence_width) // 2
        start_y = int(self.height * 0.58) - (max_word_height // 2)

        # Bounding box koordinat box
        box_x0 = start_x - self.styles.BOX_PADDING_X
        box_y0 = start_y - self.styles.BOX_PADDING_Y
        box_x1 = start_x + total_sentence_width + self.styles.BOX_PADDING_X
        box_y1 = start_y + max_word_height + self.styles.BOX_PADDING_Y + 10

        # Optimasi Poin 4: Gambar langsung rounded box ke canvas utama tanpa composite tambahan
        static_draw = ImageDraw.Draw(static_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 130)
        static_draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=self.styles.BOX_ROUNDED_RADIUS, fill=box_fill)

        # Gambar lapisan Drop Shadow Blur Terpisah
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
        
        # Optimasi Poin 5: SubtitleStyles dijamin memiliki properti SHADOW_BLUR_RADIUS secara mutlak
        blur_radius = self.styles.SHADOW_BLUR_RADIUS
        shadow_blurred = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        
        # Satukan background dan bayangan kabur menjadi satu lapisan statis tunggal
        static_canvas = Image.alpha_composite(static_canvas, shadow_blurred)
        
        return static_canvas, word_positions, start_x, start_y

    def create_progressive_frame(self, words_list: list, active_index: int, font_path: str, font_size: int, style_type: str = "body") -> Image.Image:
        """
        Subtitle Engine V4.8 (Ultimate Phrase Hybrid Layer):
        Menggabungkan Static Cache Layer (Blur hanya sekali) dengan Dynamic Highlight Teks Utama.
        """
        words_tuple = tuple(w["word"] for w in words_list)
        cache_key = (active_index, words_tuple, font_size, style_type)
        if cache_key in self.render_cache:
            return self.render_cache[cache_key]

        font = self._get_cached_font(font_path, font_size)
        style_cfg = self.styles.get_style_config(style_type)

        # OPTIMASI DUA TAHAP (EVALUASI 2 & TAHAP LANJUT #169): 
        # Cek apakah Lapisan Statis (Background + Shadow) untuk frasa kata ini sudah ada di cache
        static_key = (words_tuple, font_size, style_type)
        if static_key not in self.static_layer_cache:
            self.static_layer_cache[static_key] = self._render_static_layer(words_tuple, font, style_cfg)
        
        # Panggil lapisan dasar hasil pengerjaan cache (Instan, Hemat Beban Kerja Gaussian Blur!)
        static_layer_img, word_positions, start_x, start_y = self.static_layer_cache[static_key]
        
        # Buat salinan lapisan statis untuk disuntikkan teks dinamis aktif diatasnya
        base_canvas = static_layer_img.copy()
        main_draw = ImageDraw.Draw(base_canvas)

        # Gambar Teks Utama (Kata tidak aktif = Putih, Kata aktif = Kuning Murni)
        for idx, w in enumerate(word_positions):
            word_x = start_x + w["local_x"]
            
            highlight_color = self.styles.ACTIVE_WORD_COLOR
            text_color = highlight_color if idx == active_index else style_cfg["default_color"]

            main_draw.text(
                (word_x, start_y), w["text"], font=font,
                fill=text_color,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
            )

        self.render_cache[cache_key] = base_canvas
        return base_canvas
