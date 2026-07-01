import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from subtitle_engine.highlighter import KeywordHighlighter
from subtitle_engine.styles import SubtitleStyles
from config import HEIGHT

class SubtitleRenderer:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height
        self.highlighter = KeywordHighlighter()
        self.styles = SubtitleStyles()

    def create_text_frame(self, word: str, font_path: str, font_size: int, style_type: str = "body", current_index: int = 0) -> Image.Image:
        """Merender satu frame PNG transparan berisi SATU kata aktif tepat pada koordinat Y-V3."""
        base_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            font = ImageFont.load_default()

        style_cfg = self.styles.get_style_config(style_type)
        active_word = word.upper().strip()

        if not active_word:
            return base_canvas

        # 1. Kalkulasi ukuran teks untuk kata tunggal
        text_draw = ImageDraw.Draw(base_canvas)
        bbox = text_draw.textbbox((0, 0), active_word, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        start_x = (self.width - text_w) // 2
        start_y = int(HEIGHT * 0.62) - (text_h // 2)

        # 2. Gambar Background Rounded Box murni seukuran kata aktif
        box_padding_x = self.styles.BOX_PADDING_X
        box_padding_y = self.styles.BOX_PADDING_Y
        
        box_x0 = start_x - box_padding_x
        box_y0 = start_y - box_padding_y
        box_x1 = start_x + text_w + box_padding_x
        box_y1 = start_y + text_h + box_padding_y + 10
        
        box_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        box_draw = ImageDraw.Draw(box_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 114)
        
        box_draw.rounded_rectangle(
            [box_x0, box_y0, box_x1, box_y1], 
            radius=self.styles.BOX_ROUNDED_RADIUS, 
            fill=box_fill
        )
        base_canvas = Image.alpha_composite(base_canvas, box_canvas)

        # 3. Gambar Lapisan Drop Shadow Blur
        shadow_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_canvas)
        off_x, off_y = self.styles.SHADOW_OFFSET
        
        shadow_draw.text(
            (start_x + off_x, start_y + off_y), 
            active_word, 
            font=font, 
            fill=self.styles.SHADOW_COLOR,
            stroke_width=self.styles.STROKE_WIDTH,
            stroke_fill=self.styles.SHADOW_COLOR
        )
        shadow_canvas = shadow_canvas.filter(ImageFilter.GaussianBlur(self.styles.SHADOW_BLUR_RADIUS))
        base_canvas = Image.alpha_composite(base_canvas, shadow_canvas)

        # 4. Gambar Teks Utama Utama (Highlight Warna)
        word_draw = ImageDraw.Draw(base_canvas)
        word_color = self.highlighter.get_word_color(active_word, default_color=style_cfg["default_color"])
        
        # Variasi warna selang-seling untuk body teks biasa
        if style_type == "body" and word_color == style_cfg["default_color"] and current_index % 2 == 0:
            word_color = "#FFCC00"

        word_draw.text(
            (start_x, start_y), 
            active_word, 
            font=font, 
            fill=word_color,
            stroke_width=self.styles.STROKE_WIDTH,
            stroke_fill=self.styles.STROKE_COLOR
        )
            
        return base_canvas
