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
        self.static_layer_cache.clear()
        self.font_cache.clear()

    def _get_cached_font(self, font_path: str, font_size: int):
        safe_font_size = int(font_size)
        font_key = (font_path, safe_font_size)
        
        if font_key in self.font_cache:
            self.font_cache.move_to_end(font_key)
            return self.font_cache[font_key]
            
        # PERBAIKAN SYSTEM FALLBACK: Paksa cari font sistem Linux jika font proyek gagal dimuat
        font_obj = None
        paths_to_try = [
            font_path,
            "assets/fonts/Oswald-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        ]
        
        for path in paths_to_try:
            if path and os.path.exists(path):
                try:
                    font_obj = ImageFont.truetype(path, safe_font_size)
                    break
                except IOError:
                    continue
        
        if font_obj == None:
            try:
                font_obj = ImageFont.truetype(font_path, safe_font_size)
            except IOError:
                font_obj = ImageFont.load_default()
            
        self.font_cache[font_key] = font_obj
        if len(self.font_cache) > MAX_FONT_CACHE:
            self.font_cache.popitem(last=False)
            
        return font_obj

    def _clean_unicode_text(self, text: str) -> str:
        if not text:
            return ""
        # Disederhanakan agar tidak merusak string alfabet normal saat dibaca di cloud
        return str(text).strip().upper()

    def _render_static_base(self, words_list: list, font_normal, font_active_base) -> tuple:
        static_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        word_positions = []
        current_x = 0
        
        stroke_w = getattr(self.styles, 'STROKE_WIDTH', 0)
        
        # Penanganan fail-safe jika menggunakan load_default() yang tidak punya textbbox
        try:
            space_w = self.measure_draw.textbbox((0, 0), " ", font=font_normal)[2] + 14
        except Exception:
            space_w = 20

        for item in words_list:
            clean_text = item.get("display", "").strip()
            if not clean_text:
                clean_text = self._clean_unicode_text(item.get("word", ""))
            
            # Buang tanda baca di ujung kata untuk kalkulasi boks agar rapi
            clean_text = clean_text.translate(str.maketrans('', '', string.punctuation))
            if not clean_text:
                continue

            try:
                bbox_n = self.measure_draw.textbbox((0, 0), clean_text, font=font_normal, stroke_width=stroke_w)
                w_norm = max(10, bbox_n[2] - bbox_n[0])
                h_norm = max(10, bbox_n[3] - bbox_n[1])
                
                bbox_a = self.measure_draw.textbbox((0, 0), clean_text, font=font_active_base, stroke_width=stroke_w)
                w_act = max(10, bbox_a[2] - bbox_a[0])
                h_act = max(10, bbox_a[3] - bbox_a[1])
            except Exception:
                # Fallback ukuran manual jika textbbox gagal
                w_norm, h_norm = len(clean_text) * 25, 40
                w_act, h_act = len(clean_text) * 28, 44
            
            word_positions.append({
                "text": clean_text,
                "w_normal": w_norm,
                "h_normal": h_norm,
                "w_active_max": w_act,
                "h_active_max": h_act,
                "local_x": current_x
            })
            current_x += w_norm + space_w

        if not word_positions:
            word_positions.append({
                "text": "KONTEN", "w_normal": 100, "h_normal": 40,
                "w_active_max": 110, "h_active_max": 44, "local_x": 0
            })
            current_x = 100 + space_w

        total_sentence_width = current_x - space_w
        heights = [w["h_normal"] for w in word_positions]
        max_word_height = max(heights) if heights else 40

        start_x = (self.width - total_sentence_width) // 2
        start_y = int(self.height * 0.70) - (max_word_height // 2) # Diturunkan ke posisi posisi rasio 0.70 agar pas di mata viewer TikTok

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
            try:
                shadow_draw.text(
                    (word_x + off_x, start_y + off_y), w["text"], font=font_normal,
                    fill=self.styles.SHADOW_COLOR,
                    stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.SHADOW_COLOR
                )
            except Exception:
                shadow_draw.text((word_x + off_x, start_y + off_y), w["text"], font=font_normal, fill=self.styles.SHADOW_COLOR)
                
        try:
            shadow_blurred = self.shadow_canvas.filter(ImageFilter.GaussianBlur(radius=self.styles.SHADOW_BLUR_RADIUS))
            static_canvas = Image.alpha_composite(static_canvas, shadow_blurred)
        except Exception:
            pass

        main_static_draw = ImageDraw.Draw(static_canvas)
        for w in word_positions:
            word_x = start_x + w["local_x"]
            try:
                main_static_draw.text(
                    (word_x, start_y), w["text"], font=font_normal,
                    fill="#E0E0E0",
                    stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
                )
            except Exception:
                main_static_draw.text((word_x, start_y), w["text"], font=font_normal, fill="#E0E0E0")
        
        return PhraseCache(static_canvas, word_positions, start_x, start_y, max_word_height)

    def create_progressive_frame(self, words_list: list, active_index: int, font_path: str, font_size: int, scale_factor: float = 1.0, style_type: str = "body") -> Image.Image:
        if not words_list:
            words_list = [{"word": "KONTEN", "display": "KONTEN"}]

        words_tuple = tuple(w.get("display", w.get("word", "KONTEN")) for w in words_list)
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

            try:
                frame_draw.text(
                    (render_x, render_y), w["text"], font=font_active_current,
                    fill=active_color,
                    stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
                )
            except Exception:
                frame_draw.text((render_x, render_y), w["text"], font=font_active_current, fill=active_color)

        return final_frame
