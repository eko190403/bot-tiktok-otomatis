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
        
        # Objek pengukur geometry sekali pakai di memori (Hemat CPU)
        self.measure_img = Image.new("RGBA", (1, 1))
        self.measure_draw = ImageDraw.Draw(self.measure_img)
        
        # Canvas reuse untuk memproses shadow tanpa alokasi baru
        self.shadow_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

    def clear_cache(self):
        """Mematikan potensi memory leak dengan mengosongkan seluruh cache memori."""
        self.static_layer_cache.clear()
        self.font_cache.clear()

    def _get_cached_font(self, font_path: str, font_size: int):
        """Mengambil instans font dari cache memori dengan limit LRU ketat."""
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

    def _render_static_base(self, words_list: list, font_normal, font_active) -> tuple:
        """
        EVALUASI V6.1 TAHAP 1: DIHITUNG HANYA SEKALI PER FRASA.
        Menghitung seluruh geometry koordinat normal & aktif secara absolut 
        dengan memperhitungkan stroke_width sejak awal agar tidak bergeser.
        """
        static_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        word_positions = []
        current_x = 0
        
        # Ambil konstanta stroke dari styles global
        stroke_w = getattr(self.styles, 'STROKE_WIDTH', 0)
        space_w = self.measure_draw.textbbox((0, 0), " ", font=font_normal)[2] + 14

        # 1. PRE-CALCULATE SEMUA METRIK GEOMETRI (Rekomendasi Poin 2 & V6.1)
        for item in words_list:
            clean_text = item["display"]
            
            # Hitung geometry ukuran normal (Termasuk Stroke Width)
            bbox_n = self.measure_draw.textbbox((0, 0), clean_text, font=font_normal, stroke_width=stroke_w)
            w_norm = bbox_n[2] - bbox_n[0]
            h_norm = bbox_n[3] - bbox_n[1]
            
            # Hitung geometry ukuran aktif/zoom (Termasuk Stroke Width)
            bbox_a = self.measure_draw.textbbox((0, 0), clean_text, font=font_active, stroke_width=stroke_w)
            w_act = bbox_a[2] - bbox_a[0]
            h_act = bbox_a[3] - bbox_a[1]
            
            word_positions.append({
                "text": clean_text,
                "w_normal": w_norm,
                "h_normal": h_norm,
                "w_active": w_act,
                "h_active": h_act,
                "local_x": current_x
            })
            # Gunakan base normal_width untuk pondasi baris kalimat agar tetap rapat alami
            current_x += w_norm + space_w

        total_sentence_width = current_x - space_w if word_positions else 0
        max_word_height = max(w["h_normal"] for w in word_positions) if word_positions else 40

        start_x = (self.width - total_sentence_width) // 2
        start_y = int(self.height * 0.58) - (max_word_height // 2)

        # Tentukan ukuran Bounding Box pembungkus latar belakang
        box_x0 = start_x - self.styles.BOX_PADDING_X
        box_y0 = start_y - self.styles.BOX_PADDING_Y
        box_x1 = start_x + total_sentence_width + self.styles.BOX_PADDING_X
        box_y1 = start_y + max_word_height + self.styles.BOX_PADDING_Y + 12

        # 2. Gambar Lapisan Background Box
        static_draw = ImageDraw.Draw(static_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 130)
        static_draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=self.styles.BOX_ROUNDED_RADIUS, fill=box_fill)

        # 3. Gambar Lapisan Drop Shadow Blur Statis
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
        
        return static_canvas, word_positions, start_x, start_y

    def create_progressive_frame(self, words_list: list, active_index: int, font_path: str, font_size: int, scale_factor: float = 1.0, style_type: str = "body") -> Image.Image:
        """
        Subtitle Engine V6.1 (Zero-TextBBox Architecture):
        Menghilangkan total fungsi textbbox() dan alpha_composite() dari jalur loop utama.
        Seluruh metrik dan koordinat scale zoom diambil langsung dari pre-calculated geometry cache.
        """
        words_tuple = tuple(w["display"] for w in words_list)
        active_color = getattr(self.styles, 'ACTIVE_WORD_COLOR', "#FFCC00")
        
        # Evaluasi Poin 5: Jika scale_factor bernilai 1.0, bypass font_active ke normal (Hemat memori)
        safe_scale = round(min(scale_factor, 1.05), 2)
        font_normal = self._get_cached_font(font_path, font_size)
        font_active = font_normal if safe_scale == 1.0 else self._get_cached_font(font_path, int(font_size * safe_scale))
        
        style_cfg = self.styles.get_style_config(style_type)

        # Manajemen Cache Lapisan Statis (Background + Shadow + Geometry Campuran)
        static_key = (words_tuple, font_size, style_type)
        if static_key in self.static_layer_cache:
            self.static_layer_cache.move_to_end(static_key)
        else:
            self.static_layer_cache[static_key] = self._render_static_base(words_list, font_normal, font_active)
            if len(self.static_layer_cache) > MAX_STATIC_CACHE:
                self.static_layer_cache.popitem(last=False)
        
        static_layer_img, word_positions, start_x, start_y = self.static_layer_cache[static_key]
        
        # Buat salinan kanvas dasar statis instan untuk ditimpa lapisan dinamis teks
        final_frame = static_layer_img.copy()
        frame_draw = ImageDraw.Draw(final_frame)

        # 4. Gambar Teks Utama Lapisan Teratas Menggunakan Koordinat Pre-Calculated
        for idx, w in enumerate(word_positions):
            is_word_active = (idx == active_index)
            current_font = font_active if is_word_active else font_normal
            text_color = active_color if is_word_active else style_cfg.get("default_color", "#E0E0E0")

            # Jangkar titik tengah konstan dari data pre-calculated normal_width
            word_center_x = start_x + w["local_x"] + (w["w_normal"] // 2)
            
            # ELIMINASI SEJATI (V6.1 FIX): Pilih metrik yang sudah dihitung tanpa memanggil textbbox()!
            if is_word_active:
                curr_w = w["w_active"]
                curr_h = w["h_active"]
            else:
                curr_w = w["w_normal"]
                curr_h = w["h_normal"]
            
            # Hitung pergeseran jangkar tengah (Center Anchor Zoom) secara instan
            render_x = word_center_x - (curr_w // 2)
            render_y = start_y + (w["h_normal"] // 2) - (curr_h // 2)

            frame_draw.text(
                (render_x, render_y), w["text"], font=current_font,
                fill=text_color,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
            )

        return final_frame
