import os
import string
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from subtitle_engine.styles import SubtitleStyles

MAX_STATIC_CACHE = 40
MAX_FONT_CACHE = 20

class PhraseCache:
    """
    REKOMENDASI POIN 112: Mengunci aset statis (Box + Shadow + Teks Putih)
    dalam satu wadah memori per frasa untuk mengeliminasi draw berulang.
    """
    def __init__(self, base_image: Image.Image, word_positions: list, start_x: int, start_y: int, max_h: int):
        self.base_image = base_image       # Lapisan gabungan Box + Shadow + Semua Teks Normal (Putih)
        self.word_positions = word_positions # Koordinat geometri komprehensif tiap kata
        self.start_x = start_x
        self.start_y = start_y
        self.max_h = max_h

class SubtitleRenderer:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height
        self.styles = SubtitleStyles()
        
        # LRU Cache terkelola ketat untuk mencegah memory leak
        self.static_layer_cache = OrderedDict()
        self.font_cache = OrderedDict()
        
        # Kanvas bantu sekali pakai untuk mengukur geometri & memproses blur
        self.measure_img = Image.new("RGBA", (1, 1))
        self.measure_draw = ImageDraw.Draw(self.measure_img)
        self.shadow_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

    def clear_cache(self):
        """Mematikan potensi memory leak dengan mengosongkan seluruh cache memori."""
        self.static_layer_cache.clear()
        self.font_cache.clear()

    def _get_cached_font(self, font_path: str, font_size: int):
        """Mengambil atau menyimpan instans font dari cache memori dengan limit LRU ketat."""
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

    def _compile_phrase_cache(self, words_list: list, font_normal, font_active_base) -> PhraseCache:
        """
        GEOMETRY & LAYER COMPILER (V7.0): Dihitung hanya sekali saat frasa berpindah.
        Menyatukan Background Box, Shadow, dan SELURUH kata normal (Putih) ke dalam satu gambar dasar statis.
        """
        base_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        word_positions = []
        current_x = 0
        
        stroke_w = getattr(self.styles, 'STROKE_WIDTH', 0)
        space_w = self.measure_draw.textbbox((0, 0), " ", font=font_normal)[2] + 14

        # 1. Hitung pre-calculated geometry untuk ukuran normal & batas maksimal ukuran aktif zoom
        for item in words_list:
            clean_text = item["display"]
            
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

        total_sentence_width = current_x - space_w if word_positions else 0
        max_word_height = max(w["h_normal"] for w in word_positions) if word_positions else 40

        start_x = (self.width - total_sentence_width) // 2
        start_y = int(self.height * 0.58) - (max_word_height // 2)

        # Koordinat bounding box latar belakang
        box_x0 = start_x - self.styles.BOX_PADDING_X
        box_y0 = start_y - self.styles.BOX_PADDING_Y
        box_x1 = start_x + total_sentence_width + self.styles.BOX_PADDING_X
        box_y1 = start_y + max_word_height + self.styles.BOX_PADDING_Y + 12

        # 2. Gambar Layer 1: Background Box 
        static_draw = ImageDraw.Draw(base_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 130)
        static_draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=self.styles.BOX_ROUNDED_RADIUS, fill=box_fill)

        # 3. Gambar Layer 2: Shadow 
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
        base_canvas = Image.alpha_composite(base_canvas, shadow_blurred)

        # 4. Gambar Layer 3: Semua kata dengan warna Normal Teks (Putih Redup) secara permanen 
        main_static_draw = ImageDraw.Draw(base_canvas)
        for w in word_positions:
            word_x = start_x + w["local_x"]
            main_static_draw.text(
                (word_x, start_y), w["text"], font=font_normal,
                fill="#E0E0E0", # Putih redup premium
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
            )
        
        return PhraseCache(base_canvas, word_positions, start_x, start_y, max_word_height)

    def create_progressive_frame(self, words_list: list, active_index: int, font_path: str, font_size: int, scale_factor: float = 1.0, style_type: str = "body") -> Image.Image:
        """
        Subtitle Engine V7.0 (Static Base Patching Arsitektur):
        Mengimplementasikan pemisahan layer teks statis. Setiap frame loop HANYA menggambar SATU kata aktif
        dengan menimpa posisinya di atas pangkalan gambar PhraseCache jadi sangat menghemat CPU.
        """
        words_tuple = tuple(w["display"] for w in words_list)
        active_color = getattr(self.styles, 'ACTIVE_WORD_COLOR', "#FFCC00")
        
        # REKOMENDASI POIN 34: Mempercepat cache font dengan pembulatan 1 angka desimal
        safe_scale = round(min(scale_factor, 1.05), 1)
        
        font_normal = self._get_cached_font(font_path, font_size)
        # Ambil font aktif berbasis faktor zoom dinamis saat ini untuk animasi easing smooth
        font_active_current = font_normal if safe_scale == 1.0 else self._get_cached_font(font_path, int(font_size * safe_scale))
        
        # Ambil basis font aktif maksimal (1.05) untuk kebutuhan kompilasi geometry bounding box statis awal
        font_active_max = self._get_cached_font(font_path, int(font_size * 1.05))

        # Mengelola PhraseCache berbasis LRU
        static_key = (words_tuple, font_size, style_type)
        if static_key in self.static_layer_cache:
            self.static_layer_cache.move_to_end(static_key)
        else:
            self.static_layer_cache[static_key] = self._compile_phrase_cache(words_list, font_normal, font_active_max)
            if len(self.static_layer_cache) > MAX_STATIC_CACHE:
                self.static_layer_cache.popitem(last=False)
        
        phrase_storage = self.static_layer_cache[static_key]
        
        # 1. Panggil dasar gabungan gambar statis (Membawa Box + Shadow + Teks Putih) 
        # Operasi copy() di sini tidak bisa dihindari untuk mutasi frame baru, namun beban draw teks hilang total!
        final_frame = phrase_storage.base_image.copy()
        frame_draw = ImageDraw.Draw(final_frame) # Diizinkan membuat instans baru per frame (Aman & Sesuai Poin 65)

        # 2. Layer 4: Gambar HANYA SATU kata aktif di atas pangkalan gambar 
        if 0 <= active_index < len(phrase_storage.word_positions):
            w = phrase_storage.word_positions[active_index]
            stroke_w = getattr(self.styles, 'STROKE_WIDTH', 0)
            
            # Hitung geometry active saat ini secara dinamis tanpa textbbox berulang (Berdasarkan rasio interpolasi linear)
            if safe_scale == 1.0:
                curr_w, curr_h = w["w_normal"], w["h_normal"]
            elif safe_scale == 1.05:
                curr_w, curr_h = w["w_active_max"], w["h_active_max"]
            else:
                # Interpolasi presisi matematis: Menghitung pelebaran huruf secara instan tanpa textbbox!
                ratio = (safe_scale - 1.0) / 0.05
                curr_w = int(w["w_normal"] + (w["w_active_max"] - w["w_normal"]) * ratio)
                curr_h = int(w["h_normal"] + (w["h_active_max"] - w["h_normal"]) * ratio)

            # Hitung koordinat jangkar tengah penempatan agar teks tidak bergoyang (Zero-Shaking)
            word_center_x = phrase_storage.start_x + w["local_x"] + (w["w_normal"] // 2)
            render_x = word_center_x - (curr_w // 2)
            render_y = phrase_storage.start_y + (w["h_normal"] // 2) - (curr_h // 2)

            # Timpa posisi kata putih lama dengan memberikan warna kuning murni berukuran zoom aktif 
            frame_draw.text(
                (render_x, render_y), w["text"], font=font_active_current,
                fill=active_color,
                stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
            )

        return final_frame
