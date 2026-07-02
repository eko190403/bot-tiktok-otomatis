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
        
        self.measure_img = Image.new("RGBA", (1, 1))
        self.measure_draw = ImageDraw.Draw(self.measure_img)

    def clear_cache(self):
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

    def _render_static_layer(self, words_tuple: tuple, font, style_cfg) -> Image.Image:
        """
        Merender Lapisan Dasar Kotak Latar Belakang.
        PERBAIKAN: Dihitung dengan font normal agar spacing tidak terlalu longgar (Poin 2 Fix).
        """
        static_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        word_positions = []
        current_x = 0
        space_w = self.measure_draw.textbbox((0, 0), " ", font=font)[2] + 10

        for item_word in words_tuple:
            # Bersihkan tanda baca khusus untuk visual render
            clean_text = item_word.upper().replace(".", "").replace(",", "").replace("!", "").replace("?", "")
            bbox = self.measure_draw.textbbox((0, 0), clean_text, font=font)
            w_width = bbox[2] - bbox[0]
            w_height = bbox[3] - bbox[1]
            
            word_positions.append({
                "text": clean_text,
                "width": w_width,
                "height": w_height,
                "local_x": current_x
            })
            current_x += w_width + space_w

        total_sentence_width = current_x - space_w if word_positions else 0
        max_word_height = max(w["height"] for w in word_positions) if word_positions else 40

        start_x = (self.width - total_sentence_width) // 2
        start_y = int(self.height * 0.58) - (max_word_height // 2)

        box_x0 = start_x - self.styles.BOX_PADDING_X
        box_y0 = start_y - self.styles.BOX_PADDING_Y
        box_x1 = start_x + total_sentence_width + self.styles.BOX_PADDING_X
        box_y1 = start_y + max_word_height + self.styles.BOX_PADDING_Y + 12

        static_draw = ImageDraw.Draw(static_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 130)
        static_draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=self.styles.BOX_ROUNDED_RADIUS], fill=box_fill)
        
        return static_canvas, word_positions, start_x, start_y

    def create_progressive_frame(self, words_list: list, active_index: int, font_path: str, font_size: int, scale_factor: float = 1.0, style_type: str = "body") -> Image.Image:
        """
        Subtitle Engine V5.2 (Premium Karaoke Easing Layout):
        Menyeimbangkan pembesaran teks & bayangan drop shadow secara sinkron penuh tanpa getaran.
        """
        words_tuple = tuple(w["word"] for w in words_list)
        
        # PERBAIKAN POIN 6 CACHE KEY: Masukkan properti warna aktif agar aman dari leak perubahan gaya
        active_color = getattr(self.styles, 'ACTIVE_WORD_COLOR', "#FFCC00")
        cache_key = (active_index, words_tuple, font_size, scale_factor, active_color, style_type)
        if cache_key in self.render_cache:
            return self.render_cache[cache_key]

        font_normal = self._get_cached_font(font_path, font_size)
        style_cfg = self.styles.get_style_config(style_type)

        static_key = (words_tuple, font_size, style_type)
        if static_key not in self.static_layer_cache:
            self.static_layer_cache[static_key] = self._render_static_layer(words_tuple, font_normal, style_cfg)
        
        static_layer_img, word_positions, start_x, start_y = self.static_layer_cache[static_key]
        
        base_canvas = static_layer_img.copy()
        
        # Lapisan Terpisah Shadow (Poin 1 Fix: Ikut membesar sinkron bersama font aktif)
        shadow_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_canvas)
        off_x, off_y = self.styles.SHADOW_OFFSET

        # Tahap 1: Render Bayangan Drop Shadow Dinamis Berbasis Skala Zoom Terhitung
        for idx, w in enumerate(word_positions):
            is_active = (idx == active_index)
            current_scale = scale_factor if is_active else 1.0
            current_font = self._get_cached_font(font_path, int(font_size * current_scale))
            
            word_center_x = start_x + w["local_x"] + (w["width"] // 2)
            bbox_curr = shadow_draw.textbbox((0, 0), w["text"], font=current_font)
            curr_w = bbox_curr[2] - bbox_curr[0]
            curr_h = bbox_curr[3] - bbox_curr[1]
            
            render_x = word_center_x - (curr_w // 2)
            render_y = start_y + (w["height"] // 2) - (curr_h // 2)

            shadow_draw.text(
                (render_x + off_x, render_y + off_y), w["text"], font=current_font,
                fill=self.styles.SHADOW_COLOR,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.SHADOW_COLOR
            )
            
        shadow_blurred = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=self.styles.SHADOW_BLUR_RADIUS))
        base_canvas = Image.alpha_composite(base_canvas, shadow_blurred)

        # Tahap 2: Render Lapisan Utama Teks
        main_draw = ImageDraw.Draw(base_canvas)
        for idx, w in enumerate(word_positions):
            is_active = (idx == active_index)
            current_scale = scale_factor if is_active else 1.0
            current_font = self._get_cached_font(font_path, int(font_size * current_scale))
            
            # Poin 5 Alpha Brightness: Kecerahan adaptif (Putih normal agak redup 85% kecerahan, Aktif 100% glow)
            if is_active:
                text_color = active_color
            else:
                text_color = "#E0E0E0" # Putih redup premium (Brightness 85%)

            word_center_x = start_x + w["local_x"] + (w["width"] // 2)
            bbox_curr = main_draw.textbbox((0, 0), w["text"], font=current_font)
            curr_w = bbox_curr[2] - bbox_curr[0]
            curr_h = bbox_curr[3] - bbox_curr[1]
            
            render_x = word_center_x - (curr_w // 2)
            render_y = start_y + (w["height"] // 2) - (curr_h // 2)

            main_draw.text(
                (render_x, render_y), w["text"], font=current_font,
                fill=text_color,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
            )

        self.render_cache[cache_key] = base_canvas
        return base_canvas
