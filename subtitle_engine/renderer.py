import os
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from subtitle_engine.styles import SubtitleStyles

MAX_STATIC_CACHE = 40
MAX_FONT_CACHE = 20

class SubtitleRenderer:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height
        self.styles = SubtitleStyles()
        
        self.static_layer_cache = OrderedDict()
        self.font_cache = OrderedDict()
        
        # Objek pengukur geometry sekali pakai
        self.measure_img = Image.new("RGBA", (1, 1))
        self.measure_draw = ImageDraw.Draw(self.measure_img)
        
        # Canvas reuse untuk memproses shadow tanpa alokasi baru
        self.shadow_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

    def clear_cache(self):
        self.static_layer_cache.clear()
        self.font_cache.clear()

    def _get_cached_font(self, font_path: str, font_size: int):
        safe_font_size = int(font_size)
        font_key = (font_path, safe_font_size)
        
        if font_key in self.font_cache:
            self.font_cache.move_to_end(font_key)
            return self.font_cache[font_key]
            
        try:
            font_obj = ImageFont.truetype(font_path, safe_font_size)
        except IOError:
            font_obj = ImageFont.load_default()
            
        self.font_cache[font_key] = font_obj
        if len(self.font_cache) > MAX_FONT_CACHE:
            self.font_cache.popitem(last=False)
            
        return font_obj

    def _render_static_base(self, words_list: list, font) -> tuple:
        """
        Dihitung SEKALI per frasa. Mengunci posisi geometry X & Y, menggambar Box,
        serta menggambar Drop Shadow yang sudah di-blur murni.
        """
        static_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        word_positions = []
        current_x = 0
        
        space_w = self.measure_draw.textbbox((0, 0), " ", font=font)[2] + 14

        # GEOMETRY PRE-CALCULATION (Poin 3 Fix): Hitung textbbox sekali saja di sini
        for item in words_list:
            clean_text = item["display"] # Menggunakan teks yang sudah bersih dari audio.py
            
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

        # 1. Gambar Background Box
        static_draw = ImageDraw.Draw(static_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 130)
        static_draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=self.styles.BOX_ROUNDED_RADIUS, fill=box_fill)

        # 2. Gambar Lapisan Drop Shadow
        self.shadow_canvas.paste((0, 0, 0, 0), [0, 0, self.width, self.height])
        shadow_draw = ImageDraw.Draw(self.shadow_canvas)
        off_x, off_y = self.styles.SHADOW_OFFSET

        for w in word_positions:
            word_x = start_x + w["local_x"]
            shadow_draw.text(
                (word_x + off_x, start_y + off_y), w["text"], font=font,
                fill=self.styles.SHADOW_COLOR,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.SHADOW_COLOR
            )
        
        shadow_blurred = self.shadow_canvas.filter(ImageFilter.GaussianBlur(radius=self.styles.SHADOW_BLUR_RADIUS))
        static_canvas = Image.alpha_composite(static_canvas, shadow_blurred)
        
        return static_canvas, word_positions, start_x, start_y

    def create_progressive_frame(self, words_list: list, active_index: int, font_path: str, font_size: int, scale_factor: float = 1.0, style_type: str = "body") -> Image.Image:
        """
        Subtitle Engine V6.0 (Zero-Composition Architecture):
        Menghapus total operasi Image.alpha_composite per frame dengan langsung menimpa teks utama dinamis
        di atas salinan instan dari basis kanvas statis.
        """
        words_tuple = tuple(w["display"] for w in words_list)
        active_color = getattr(self.styles, 'ACTIVE_WORD_COLOR', "#FFCC00")
        
        safe_scale = round(min(scale_factor, 1.05), 2)
        font_normal = self._get_cached_font(font_path, font_size)
        font_active = self._get_cached_font(font_path, int(font_size * safe_scale))
        style_cfg = self.styles.get_style_config(style_type)

        # Manajemen Cache Lapisan Statis (Background + Shadow)
        static_key = (words_tuple, font_size, style_type)
        if static_key in self.static_layer_cache:
            self.static_layer_cache.move_to_end(static_key)
        else:
            self.static_layer_cache[static_key] = self._render_static_base(words_list, font_normal)
            if len(self.static_layer_cache) > MAX_STATIC_CACHE:
                self.static_layer_cache.popitem(last=False)
        
        static_layer_img, word_positions, start_x, start_y = self.static_layer_cache[static_key]
        
        # PERBAIKAN RADIKAL (Poin 1 Fix): Gunakan .copy() langsung dari kanvas statis matang,
        # lalu timpa teks utama di atasnya. Menghapus 100% operasi Image.alpha_composite() per frame!
        final_frame = static_layer_img.copy()
        frame_draw = ImageDraw.Draw(final_frame) # ImageDraw dibuat per frame (Aman & Sesuai Evaluasi Poin 5)

        # 3. Gambar Teks Utama Lapisan Teratas
        for idx, w in enumerate(word_positions):
            is_word_active = (idx == active_index)
            current_font = font_active if is_word_active else font_normal
            text_color = active_color if is_word_active else style_cfg.get("default_color", "#E0E0E0")

            word_center_x = start_x + w["local_x"] + (w["width"] // 2)
            
            # Ambil dimensi geometry kata yang SUDAH DIHITUNG di awal seksi (Poin 3 Fix)
            # Tanpa memanggil textbbox() berulang kali!
            if is_word_active:
                # Hanya hitung textbbox jika ada scale zoom aktif pada kata tersebut
                bbox_curr = frame_draw.textbbox((0, 0), w["text"], font=current_font)
                curr_w = bbox_curr[2] - bbox_curr[0]
                curr_h = bbox_curr[3] - bbox_curr[1]
            else:
                curr_w = w["width"]
                curr_h = w["height"]
            
            render_x = word_center_x - (curr_w // 2)
            render_y = start_y + (w["height"] // 2) - (curr_h // 2)

            frame_draw.text(
                (render_x, render_y), w["text"], font=current_font,
                fill=text_color,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
            )

        return final_frame
