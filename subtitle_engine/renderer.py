import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from subtitle_engine.highlighter import KeywordHighlighter
from subtitle_engine.styles import SubtitleStyles

class SubtitleRenderer:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height
        self.highlighter = KeywordHighlighter()
        self.styles = SubtitleStyles()

    def create_text_frame(self, text: str, current_word_index: int, font_path: str, font_size: int, style_type: str = "body") -> Image.Image:
        """
        Merender satu frame PNG transparan berisi teks penuh dengan satu kata aktif yang di-highlight,
        lengkap dengan background rounded box, stroke, dan drop shadow premium.
        """
        # 1. Buat kanvas transparan utama ukuran full-screen (RGBA)
        base_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        
        # Load Font menggunakan Pillow
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            font = ImageFont.load_default()

        # Ambil konfigurasi gaya teks dasar (Hook/Body/CTA)
        style_cfg = self.styles.get_style_config(style_type)
        words = text.upper().split()
        
        if not words:
            return base_canvas

        # 2. Kalkulasi ukuran masing-masing kata untuk penataan layout horizontal
        # Kita buat kanvas coretan sementara untuk mengukur teks
        temp_draw = ImageDraw.Draw(base_canvas)
        word_positions = []
        total_text_width = 0
        max_word_height = 0
        
        # Spasi antar kata (piksel)
        space_width = temp_draw.textbbox((0, 0), " ", font=font)[2]

        for i, word in enumerate(words):
            bbox = temp_draw.textbbox((0, 0), word, font=font)
            w_w = bbox[2] - bbox[0]
            w_h = bbox[3] - bbox[1]
            max_word_height = max(max_word_height, w_h)
            
            # Catat lebar akumulatif
            word_positions.append({
                "word": word,
                "width": w_w,
                "height": w_h,
                "local_x": total_text_width
            })
            total_text_width += w_w
            if i < len(words) - 1:
                total_text_width += space_width

        # 3. Tentukan koordinat tengah layar (Center Alignment)
        start_x = (self.width - total_text_width) // 2
        start_y = (self.height - max_word_height) // 2

        # 4. Gambar Background Rounded Box pada lapisan terpisah (supaya bisa diberi opasitas)
        box_padding_x = self.styles.BOX_PADDING_X
        box_padding_y = self.styles.BOX_PADDING_Y
        
        box_x0 = start_x - box_padding_x
        box_y0 = start_y - box_padding_y
        box_x1 = start_x + total_text_width + box_padding_x
        box_y1 = start_y + max_word_height + box_padding_y + 10
        
        box_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        box_draw = ImageDraw.Draw(box_canvas)
        
        # Warna box dengan opasitas 45% (255 * 0.45 = 114)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 114)
        
        box_draw.rounded_rectangle(
            [box_x0, box_y0, box_x1, box_y1], 
            radius=self.styles.BOX_ROUNDED_RADIUS, 
            fill=box_fill
        )
        
        # Gabungkan box ke kanvas utama
        base_canvas = Image.alpha_composite(base_canvas, box_canvas)

        # 5. Gambar Lapisan Drop Shadow Blur
        shadow_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_canvas)
        off_x, off_y = self.styles.SHADOW_OFFSET
        
        for pos in word_positions:
            word_x = start_x + pos["local_x"] + off_x
            word_y = start_y + (max_word_height - pos["height"]) // 2 + off_y
            
            shadow_draw.text(
                (word_x, word_y), 
                pos["word"], 
                font=font, 
                fill=self.styles.SHADOW_COLOR,
                stroke_width=self.styles.STROKE_WIDTH,
                stroke_fill=self.styles.SHADOW_COLOR
            )
            
        # Terapkan efek Blur Gaussian pada bayangan
        shadow_canvas = shadow_canvas.filter(ImageFilter.GaussianBlur(self.styles.SHADOW_BLUR_RADIUS))
        base_canvas = Image.alpha_composite(base_canvas, shadow_canvas)

        # 6. Gambar Teks Utama + Stroke Tepi
        text_draw = ImageDraw.Draw(base_canvas)
        for i, pos in enumerate(word_positions):
            word_x = start_x + pos["local_x"]
            # Ratakan posisi vertikal kata agar sejajar rapi
            word_y = start_y + (max_word_height - pos["height"]) // 2
            
            # Aturan penentuan warna kata:
            if i == current_word_index:
                # Jika kata ini sedang diucapkan oleh Voice Over, jalankan highlight otomatis kustom
                word_color = self.highlighter.get_word_color(pos["word"], default_color="#FFCC00") # Default kuning jika tidak masuk keyword khusus
            else:
                # Jika bukan kata aktif, gunakan warna bawaan tema segmen (Hook/Body/CTA)
                word_color = style_cfg["default_color"]

            text_draw.text(
                (word_x, word_y), 
                pos["word"], 
                font=font, 
                fill=word_color,
                stroke_width=self.styles.STROKE_WIDTH,
                stroke_fill=self.styles.STROKE_COLOR
            )

        return base_canvas
