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

    def create_text_frame(self, word: str, font_path: str, font_size: int, style_type: str = "body", current_index: int = 0) -> Image.Image:
        """Merender gambar mini transparan yang dipotong pas seukuran kata aktif (Bukan ukuran layar penuh)."""
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            font = ImageFont.load_default()

        style_cfg = self.styles.get_style_config(style_type)
        active_word = word.upper().strip()

        if not active_word:
            # Kembalikan gambar kosong 1x1 jika tidak ada kata
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

        # 1. Ukur dimensi kata aktif seketat mungkin
        temp_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_img)
        bbox = temp_draw.textbbox((0, 0), active_word, font=font)
        
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # 2. Tentukan ukuran total kanvas mini (ditambah padding ruang napas box & shadow)
        padding_x = self.styles.BOX_PADDING_X + 20
        padding_y = self.styles.BOX_PADDING_Y + 20
        
        canvas_w = text_w + (padding_x * 2)
        canvas_h = text_h + (padding_y * 2) + 10

        # Buat kanvas mini khusus seukuran kata
        word_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        
        # Koordinat lokal teks di dalam kanvas mini
        text_x = padding_x
        text_y = padding_y

        # 3. Gambar Background Rounded Box di kanvas mini
        box_draw = ImageDraw.Draw(word_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 114)
        box_draw.rounded_rectangle(
            [text_x - self.styles.BOX_PADDING_X, text_y - self.styles.BOX_PADDING_Y, 
             text_x + text_w + self.styles.BOX_PADDING_X, text_y + text_h + self.styles.BOX_PADDING_Y + 10], 
            radius=self.styles.BOX_ROUNDED_RADIUS, 
            fill=box_fill
        )

        # 4. Gambar Lapisan Drop Shadow Blur di kanvas mini
        shadow_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_canvas)
        off_x, off_y = self.styles.SHADOW_OFFSET
        shadow_draw.text(
            (text_x + off_x, text_y + off_y), 
            active_word, 
            font=font, 
            fill=self.styles.SHADOW_COLOR,
            stroke_width=self.styles.STROKE_WIDTH,
            stroke_fill=self.styles.SHADOW_COLOR
        )
        shadow_canvas = shadow_canvas.filter(ImageFilter.GaussianBlur(self.styles.SHADOW_BLUR_RADIUS))
        word_canvas = Image.alpha_composite(word_canvas, shadow_canvas)

        # 5. Gambar Teks Utama (Highlight Warna)
        main_draw = ImageDraw.Draw(word_canvas)
        word_color = self.highlighter.get_word_color(active_word, default_color=style_cfg["default_color"])
        
        if style_type == "body" and word_color == style_cfg["default_color"] and current_index % 2 == 0:
            word_color = "#FFCC00"

        main_draw.text(
            (text_x, text_y), 
            active_word, 
            font=font, 
            fill=word_color,
            stroke_width=self.styles.STROKE_WIDTH,
            stroke_fill=self.styles.STROKE_COLOR
        )
            
        return word_canvas
