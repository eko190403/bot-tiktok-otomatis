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
        """Merender satu frame PNG transparan berisi teks berbaris rapi dengan satu kata aktif yang di-highlight."""
        base_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            font = ImageFont.load_default()

        style_cfg = self.styles.get_style_config(style_type)
        
        # 1. Kalkulasi ukuran teks multi-baris untuk background rounded box
        temp_draw = ImageDraw.Draw(base_canvas)
        bbox = temp_draw.multiline_textbbox((0, 0), text, font=font, spacing=10)
        total_text_width = bbox[2] - bbox[0]
        max_word_height = bbox[3] - bbox[1]
        
        start_x = (self.width - total_text_width) // 2
        start_y = (self.height - max_word_height) // 2

        # 2. Gambar Background Rounded Box dengan Opasitas 45%
        box_padding_x = self.styles.BOX_PADDING_X
        box_padding_y = self.styles.BOX_PADDING_Y
        
        box_x0 = start_x - box_padding_x
        box_y0 = start_y - box_padding_y
        box_x1 = start_x + total_text_width + box_padding_x
        box_y1 = start_y + max_word_height + box_padding_y + 10
        
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
        
        shadow_draw.multiline_text(
            (start_x + off_x, start_y + off_y), 
            text, 
            font=font, 
            fill=self.styles.SHADOW_COLOR,
            stroke_width=self.styles.STROKE_WIDTH,
            stroke_fill=self.styles.SHADOW_COLOR,
            spacing=10
        )
        shadow_canvas = shadow_canvas.filter(ImageFilter.GaussianBlur(self.styles.SHADOW_BLUR_RADIUS))
        base_canvas = Image.alpha_composite(base_canvas, shadow_canvas)

        # 4. Gambar Teks Utama per Kata (Sistem Karaoke Multi-baris)
        text_draw = ImageDraw.Draw(base_canvas)
        lines = text.split("\n")
        current_global_word_idx = 0
        cursor_y = start_y

        for line in lines:
            line_bbox = text_draw.textbbox((0, 0), line, font=font)
            line_w = line_bbox[2] - line_bbox[0]
            line_h = line_bbox[3] - line_bbox[1]
            cursor_x = (self.width - line_w) // 2
            
            line_words = line.split()
            space_w = text_draw.textbbox((0, 0), " ", font=font)[2]
            
            for word in line_words:
                w_bbox = text_draw.textbbox((0, 0), word, font=font)
                w_w = w_bbox[2] - w_bbox[0]
                
                if current_global_word_idx == current_word_index:
                    word_color = self.highlighter.get_word_color(word, default_color="#FFCC00")
                else:
                    word_color = style_cfg["default_color"]

                text_draw.text(
                    (cursor_x, cursor_y), 
                    word, 
                    font=font, 
                    fill=word_color,
                    stroke_width=self.styles.STROKE_WIDTH,
                    stroke_fill=self.styles.STROKE_COLOR
                )
                cursor_x += w_w + space_w
                current_global_word_idx += 1
                
            cursor_y += line_h + 10
            
        return base_canvas
