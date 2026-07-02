import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from subtitle_engine.styles import SubtitleStyles

class SubtitleRenderer:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height
        self.styles = SubtitleStyles()
        # EVALUASI 4: Gunakan cache memori agar tidak merender ulang grafis statis (Beban CPU turun drastis)
        self.render_cache = {}

    def _wrap_text_to_lines(self, words_list: list, font, max_width: int) -> list:
        """
        EVALUASI 3: Memotong kalimat panjang secara otomatis (Auto-Wrapping) 
        agar masuk ke dalam batas aman 80% layar tiktok dan maksimal terdiri dari 2 baris.
        """
        lines = []
        current_line = []
        current_w = 0
        space_w = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), " ", font=font)[2]
        # EVALUASI 6: Berikan tambahan spasi dinamis agar antar kata tidak terlalu rapat
        extended_space_w = space_w + 10 

        for item in words_list:
            word_text = item["word"].upper()
            w_w = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), word_text, font=font)[2]
            
            if current_w + w_w <= max_width:
                current_line.append(item)
                current_w += w_w + extended_space_w
            else:
                if current_line:
                    lines.append(current_line)
                current_line = [item]
                current_w = w_w + extended_space_w
                
        if current_line:
            lines.append(current_line)
            
        # Batasi paksa maksimal 2 baris demi kenyamanan pandang mata di TikTok
        return lines[:2]

    def create_progressive_frame(self, words_list: list, active_index: int, font_path: str, font_size: int, style_type: str = "body") -> Image.Image:
        """
        Subtitle Engine V4.2 (Premium Progressive Karaoke Style):
        Mendukung Auto-Wrap, Real Blur Shadow, Word Scale, dan Cache Performance Memory.
        """
        # EVALUASI 4 PERFORMANCE: Buat kunci identitas cache yang unik untuk kombinasi frame aktif
        words_tuple = tuple((w["word"], w["start"]) for w in words_list)
        cache_key = (active_index, words_tuple, font_size, style_type)
        if cache_key in self.render_cache:
            return self.render_cache[cache_key]

        base_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        
        try:
            font = ImageFont.truetype(font_path, font_size)
            # Buat font sedikit lebih tebal khusus untuk kata aktif (EVALUASI 5)
            font_active = ImageFont.truetype(font_path, int(font_size * 1.05))
        except IOError:
            font = ImageFont.load_default()
            font_active = ImageFont.load_default()

        style_cfg = self.styles.get_style_config(style_type)
        
        # Batasi lebar kotak maksimal 80% dari lebar layar kanvas asli (EVALUASI 3)
        max_box_width = int(self.width * 0.80)
        
        # Jalankan pembagian baris otomatis (Auto-Wrapping)
        wrapped_lines = self._wrap_text_to_lines(words_list, font, max_box_width)
        
        # Ambil total kata global untuk penentuan indeks pencocokan warna aktif
        text_draw = ImageDraw.Draw(base_canvas)
        space_w = text_draw.textbbox((0, 0), " ", font=font)[2] + 10
        
        line_data_compiled = []
        global_word_counter = 0
        
        # Hitung struktur geometri setiap baris teks
        for line in wrapped_lines:
            line_w = 0
            line_h = 0
            words_in_line_data = []
            
            for item in line:
                is_active = (global_word_counter == active_index)
                current_font = font_active if is_active else font
                
                w_text = item["word"].upper()
                bbox = text_draw.textbbox((0, 0), w_text, font=current_font)
                w_w = bbox[2] - bbox[0]
                w_h = bbox[3] - bbox[1]
                
                words_in_line_data.append({
                    "text": w_text,
                    "w": w_w,
                    "h": w_h,
                    "is_active": is_active,
                    "font": current_font,
                    "local_x": line_w
                })
                line_w += w_w + space_w
                line_h = max(line_h, w_h)
                global_word_counter += 1
                
            line_data_compiled.append({
                "words": words_in_line_data,
                "total_w": line_w - space_w if line_in_line_data else 0,
                "max_h": line_h
            })

        if not line_data_compiled:
            return base_canvas

        # EVALUASI 4 POSITION: Set posisi sumbu vertikal di area emas 58% layar TikTok
        total_block_height = sum([l["max_h"] for l in line_data_compiled]) + (len(line_data_compiled) * 20)
        start_y = int(self.height * 0.58) - (total_block_height // 2)

        # Hitung ukuran bounding box terluar yang membungkus seluruh baris
        max_line_width = max([l["total_w"] for l in line_data_compiled])
        box_x0 = (self.width - max_line_width) // 2 - self.styles.BOX_PADDING_X
        box_y0 = start_y - self.styles.BOX_PADDING_Y
        box_x1 = (self.width + max_line_width) // 2 + self.styles.BOX_PADDING_X
        box_y1 = start_y + total_block_height + self.styles.BOX_PADDING_Y

        # 1. Gambar Lapisan Background Rounded Box Utama
        box_draw = ImageDraw.Draw(base_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 130)
        box_draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=self.styles.BOX_ROUNDED_RADIUS, fill=box_fill)

        # 2. EVALUASI 1: Buat Lapisan Terpisah Khusus Mengolah Gaussian Blur Drop Shadow (Halus & Profesional)
        shadow_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_canvas)
        
        current_line_y = start_y
        for line in line_data_compiled:
            line_start_x = (self.width - line["total_w"]) // 2
            for w in line["words"]:
                target_x = line_start_x + w["local_x"]
                # Suntikkan offset bayangan jatuh
                sh_x = target_x + self.styles.SHADOW_OFFSET[0]
                sh_y = current_line_y + self.styles.SHADOW_OFFSET[1]
                
                shadow_draw.text(
                    (sh_x, sh_y), w["text"], font=w["font"], 
                    fill=self.styles.SHADOW_COLOR, 
                    stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.SHADOW_COLOR
                )
            current_line_y += line["max_h"] + 20

        # Terapkan penyaringan blur asli lalu satukan ke kanvas utama
        shadow_blurred = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=6))
        base_canvas = Image.alpha_composite(base_canvas, shadow_blurred)

        # 3. Gambar Lapisan Teks Utama di Atas Bayangan
        main_draw = ImageDraw.Draw(base_canvas)
        current_line_y = start_y
        for line in line_data_compiled:
            line_start_x = (self.width - line["total_w"]) // 2
            for w in line["words"]:
                target_x = line_start_x + w["local_x"]
                
                # EVALUASI 5 HIGHLIGHT: Berikan warna kuning murni, scale zoom 105% otomatis dari font aktif
                text_color = "#FFCC00" if w["is_active"] else style_cfg["default_color"]
                
                main_draw.text(
                    (target_x, current_line_y), w["text"], font=w["font"], 
                    fill=text_color, 
                    stroke_width=self.styles.STROKE_WIDTH, stroke_fill=self.styles.STROKE_COLOR
                )
            current_line_y += line["max_h"] + 20

        # Daftarkan hasil kerja keras render ke cache sebelum dikembalikan
        self.render_cache[cache_key] = base_canvas
        return base_canvas
