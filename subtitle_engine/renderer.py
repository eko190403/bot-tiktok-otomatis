import os
import string
import unicodedata
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from subtitle_engine.styles import SubtitleStyles

MAX_STATIC_CACHE = 40
MAX_FONT_CACHE = 20

class PhraseCache:
    def __init__(self, base_image: Image.Image, word_positions: list, start_x: int, start_y: int, max_h: int):
        self.base_image = base_image       
        self.word_positions = word_positions 
        self.start_x = start_x
        self.start_y = start_y
        self.max_h = max_h

class SubtitleRenderer:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height
        self.styles = SubtitleStyles()
        
        self.static_layer_cache = OrderedDict()
        self.font_cache = OrderedDict()
        
        self.measure_img = Image.new("RGBA", (1, 1))
        self.measure_draw = ImageDraw.Draw(self.measure_img)
        self.shadow_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

    def clear_cache(self):
        """Mematikan potensi memory leak dengan mengosongkan seluruh cache memori."""
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

    def _clean_unicode_text(self, text: str) -> str:
        """Menyaring emoji dan karakter non-huruf secara universal."""
        cleaned_chars = []
        for ch in text:
            category = unicodedata.category(ch)
            if category.startswith('L') or category.startswith('N') or category == 'Zs':
                cleaned_chars.append(ch)
        return "".join(cleaned_chars).upper().strip()

    def _render_static_base(self, words_list: list, font_normal, font_active_base) -> tuple:
        """
        DIHITUNG HANYA SEKALI PER FRASA.
        FIXED: Menggunakan default=40 pada max() untuk menghalau eror empty sequence secara mutlak.
        """
        static_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        word_positions = []
        current_x = 0
        
        stroke_w = getattr(self.styles, 'STROKE_WIDTH', 0)
        space_w = self.measure_draw.textbbox((0, 0), " ", font=font_normal)[2] + 14

        for item in words_list:
            # Gunakan text visual bersih yang sudah disediakan oleh audio.py
            clean_text = item.get("display", "").strip()
            if not clean_text:
                clean_text = self._clean_unicode_text(item.get("word", ""))
                
            # Fallback jika kata benar-benar kosong setelah dibersihkan agar tidak crash
            if not clean_text:
                continue

            bbox_n = self.measure_draw.textbbox((0, 0), clean_text, font=font_normal, stroke_width=stroke_w)
            w_norm = bbox_n[2] - bbox_n[0]
            h_norm = bbox_n[3] - bbox_n[1]
            
            bbox_a = self.measure_draw.textbbox((0, 0), clean_text, font=font_active_base, stroke_width=stroke_w)
            w_act = bbox_a[2] - bbox_a[0]
            h_act = bbox_a[3] - bbox_a[1]
            
            word_positions.append({
                "text": clean_text,
                "w_normal": w_norm,
                "h_normal": h_norm,
                "w_active_max": w_act,
                "h_active_max": h_act,
                "local_x": current_x
            })
            current_x += w_norm + space_w

        # SUNTIKAN PROTEKSI JIKA SATU BARIS FRASA KOSONG TOTAL
        if not word_positions:
            word_positions.append({
                "text": "...", "w_normal": 20, "h_normal": 30,
                "w_active_max": 22, "h_active_max": 32, "local_x": 0
            })
            current_x = 20 + space_w

        total_sentence_width = current_x - space_w
        
        # PERBAIKAN BUG UTAMA: Menambahkan parameter default agar max() tidak meledak saat sequence kosong
        max_word_height = max((w["h_normal"] for w in word_positions), default=40)

        start_x = (self.width - total_sentence_width) // 2
        start_y = int(self.height * 0.58) - (max_word_height // 2)

        box_x0 = start_x - self.styles.BOX_PADDING_X
        box_y0 = start_y - self.styles.BOX_PADDING_Y
        box_x1 = start_x + total_sentence_width + self.styles.BOX_PADDING_X
        box_y1 = start_y + max_word_height + self.styles.BOX_PADDING_Y + 12

        static_draw = ImageDraw.Draw(static_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 130)
        static_draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=self.styles.BOX_ROUNDED_RADIUS, fill=box_fill)

        self.shadow_canvas.paste((0, 0, 0, 0), [0, 0, self.width, self.height])
        shadow_draw = ImageDraw.Draw(self.shadow_canvas)
        off_x, off_y = self.styles.SHADOW_OFFSET

        for w in word_positions:
            word_x = start_x + w["local_x"]
            shadow_draw.text(
                (word_x + off_x, start_y + off_y), w["text"], font=font_normal,
                fill=self.styles.SHADOW_COLOR,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.SHADOW_COLOR
            )
        shadow_blurred = self.shadow_canvas.filter(ImageFilter.GaussianBlur(radius=self.styles.SHADOW_BLUR_RADIUS))
        static_canvas = Image.alpha_composite(static_canvas, shadow_blurred)

        main_static_draw = ImageDraw.Draw(static_canvas)
        for w in word_positions:
            word_x = start_x + w["local_x"]
            main_static_draw.text(
                (word_x, start_y), w["text"], font=font_normal,
                fill="#E0E0E0",
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
            )
        
        return PhraseCache(static_canvas, word_positions, start_x, start_y, max_word_height)

    def create_progressive_frame(self, words_list: list, active_index: int, font_path: str, font_size: int, scale_factor: float = 1.0, style_type: str = "body") -> Image.Image:
        """Subtitle Engine V7.0 (Safe Static Base Patching)."""
        words_tuple = tuple(w.get("display", w.get("word", "")) for w in words_list)
        active_color = getattr(self.styles, 'ACTIVE_WORD_COLOR', "#FFCC00")
        
        safe_scale = round(min(scale_factor, 1.05), 1)
        font_normal = self._get_cached_font(font_path, font_size)
        font_active_current = font_normal if safe_scale == 1.0 else self._get_cached_font(font_path, int(font_size * safe_scale))
        font_active_max = self._get_cached_font(font_path, int(font_size * 1.05))

        static_key = (words_tuple, font_size, style_type)
        if static_key in self.static_layer_cache:
            self.static_layer_cache.move_to_end(static_key)
        else:
            self.static_layer_cache[static_key] = self._render_static_base(words_list, font_normal, font_active_max)
            if len(self.static_layer_cache) > MAX_STATIC_CACHE:
                self.static_layer_cache.popitem(last=False)
        
        phrase_storage = self.static_layer_cache[static_key]
        
        final_frame = phrase_storage.base_image.copy()
        frame_draw = ImageDraw.Draw(final_frame)

        if 0 <= active_index < len(phrase_storage.word_positions):
            w = phrase_storage.word_positions[active_index]
            
            if safe_scale == 1.0:
                curr_w, curr_h = w["w_normal"], w["h_normal"]
            elif safe_scale == 1.05:
                curr_w, curr_h = w["w_active_max"], w["h_active_max"]
            else:
                ratio = (safe_scale - 1.0) / 0.05
                curr_w = int(w["w_normal"] + (w["w_active_max"] - w["w_normal"]) * ratio)
                curr_h = int(w["h_normal"] + (w["h_active_max"] - w["h_normal"]) * ratio)

            word_center_x = phrase_storage.start_x + w["local_x"] + (w["w_normal"] // 2)
            render_x = word_center_x - (curr_w // 2)
            render_y = phrase_storage.start_y + (w["h_normal"] // 2) - (curr_h // 2)

            frame_draw.text(
                (render_x, render_y), w["text"], font=font_active_current,
                fill=active_color,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
            )

        return final_frame
