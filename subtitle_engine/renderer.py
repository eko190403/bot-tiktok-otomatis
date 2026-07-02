import os
import string
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from subtitle_engine.styles import SubtitleStyles

class SubtitleRenderer:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height
        self.styles = SubtitleStyles()
        
        # Inisialisasi sistem Cache Terkunci (Mencegah Memory Leak)
        self.render_cache = {}
        self.font_cache = {}
        self.static_layer_cache = {}
        
        # Objek pengukur geometry statis sekali pakai di memori (Hemat CPU)
        self.measure_img = Image.new("RGBA", (1, 1))
        self.measure_draw = ImageDraw.Draw(self.measure_img)

    def clear_cache(self):
        """Mematikan potensi memory leak dengan mengosongkan seluruh cache memori."""
        self.render_cache.clear()
        self.static_layer_cache.clear()

    def _get_cached_font(self, font_path: str, font_size: int):
        """Mengambil instans font dari cache memori agar tidak re-load file berulang kali."""
        font_key = (font_path, font_size)
        if font_key not in self.font_cache:
            try:
                self.font_cache[font_key] = ImageFont.truetype(font_path, font_size)
            except IOError:
                self.font_cache[font_key] = ImageFont.load_default()
        return self.font_cache[font_key]

    def _render_static_layer(self, words_tuple: tuple, font, style_cfg) -> tuple:
        """
        OPTIMASI SEJATI (Poin 2 Fix): Merender Latar Belakang Kotak DAN Lapisan Drop Shadow Blur.
        Hanya dihitung SEKALI per kelompok frasa baru, menghemat ratusan operasi GaussianBlur().
        """
        static_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        word_positions = []
        current_x = 0
        
        # EVALUASI 6: Berikan jarak horizontal tambahan (+14) untuk mencegah kata bertabrakan saat zoom
        space_w = self.measure_draw.textbbox((0, 0), " ", font=font)[2] + 14

        for item_word in words_tuple:
            # EVALUASI 5 FIXED: Pembersihan tanda baca total menggunakan string.punctuation komprehensif
            clean_text = item_word.upper().translate(str.maketrans("", "", string.punctuation))
            
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

        # Posisi sumbu vertikal presisi di zona nyaman 58% tinggi layar TikTok
        start_x = (self.width - total_sentence_width) // 2
        start_y = int(self.height * 0.58) - (max_word_height // 2)

        box_x0 = start_x - self.styles.BOX_PADDING_X
        box_y0 = start_y - self.styles.BOX_PADDING_Y
        box_x1 = start_x + total_sentence_width + self.styles.BOX_PADDING_X
        box_y1 = start_y + max_word_height + self.styles.BOX_PADDING_Y + 12

        # 1. Gambar Background Rounded Box langsung ke canvas dasar (PERBAIKAN SINTAKS DI BARIS INI)
        static_draw = ImageDraw.Draw(static_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 130)
        static_draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=self.styles.BOX_ROUNDED_RADIUS, fill=box_fill)

        # 2. Gambar Lapisan Drop Shadow Teks Statis (Putih Bayangan)
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
        
        # Lakukan pemrosesan filter blur berat hanya SATU kali saja di sini
        blur_radius = self.styles.SHADOW_BLUR_RADIUS
        shadow_blurred = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        
        # Satukan kotak latar belakang dan bayangan kabur menjadi satu lapisan dasar matang
        static_canvas = Image.alpha_composite(static_canvas, shadow_blurred)
        
        return static_canvas, word_positions, start_x, start_y

    def create_progressive_frame(self, words_list: list, active_index: int, font_path: str, font_size: int, scale_factor: float = 1.0, style_type: str = "body") -> Image.Image:
        """
        Subtitle Engine V5.5 (Ultimate Hybrid Cache Layer):
        Menggabungkan basis static layer (anti guncang) dengan dynamic highlight teks utama.
        """
        words_tuple = tuple(w["word"] for w in words_list)
        
        # Ambil warna aktif global dari konfigurasi gaya styles
        active_color = getattr(self.styles, 'ACTIVE_WORD_COLOR', "#FFCC00")
        
        # EVALUASI 3 CACHE: Batasi key cache hanya berdasarkan langkah index aktif agar memori RAM tidak bengkak
        cache_key = (active_index, words_tuple, font_size, scale_factor, active_color, style_type)
        if cache_key in self.render_cache:
            return self.render_cache[cache_key]

        font_normal = self._get_cached_font(font_path, font_size)
        
        # EVALUASI 6 SAFETY: Batasi faktor pembesaran kata aktif maksimal 1.05 agar teks tidak saling menimpa
        safe_scale = min(scale_factor, 1.05)
        font_active = self._get_cached_font(font_path, int(font_size * safe_scale))
        
        style_cfg = self.styles.get_style_config(style_type)

        # Panggil atau buat Static Layer (Background Box + Blur Shadow)
        static_key = (words_tuple, font_size, style_type)
        if static_key not in self.static_layer_cache:
            self.static_layer_cache[static_key] = self._render_static_layer(words_tuple, font_normal, style_cfg)
        
        static_layer_img, word_positions, start_x, start_y = self.static_layer_cache[static_key]
        
        # Lakukan salinan instan dari dasar cache statis (Sangat Ringan bagi CPU!)
        base_canvas = static_layer_img.copy()
        main_draw = ImageDraw.Draw(base_canvas)

        # 3. Gambar Teks Utama di atas bayangan (Kata aktif = Kuning, Kata tidak aktif = Warna Default Config)
        for idx, w in enumerate(word_positions):
            is_word_active = (idx == active_index)
            current_font = font_active if is_word_active else font_normal
            
            # EVALUASI 4 CONFIGURABLE: Membaca warna normal/tidak aktif langsung dari style_cfg
            text_color = active_color if is_word_active else style_cfg.get("default_color", "#E0E0E0")

            # Hitung jangkar titik tengah koordinat X per kata agar diam kokoh tanpa getaran guncang (Zero-Shaking)
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
