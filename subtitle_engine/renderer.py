import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from subtitle_engine.styles import SubtitleStyles

class SubtitleRenderer:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height
        self.styles = SubtitleStyles()

    def create_progressive_frame(self, words_list: list, active_index: int, font_path: str, font_size: int, style_type: str = "body") -> Image.Image:
        """
        Merender seluruh kata dalam satu kalimat secara horizontal,
        dan hanya memberikan warna highlight kuning pada kata yang sedang aktif.
        """
        base_canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            font = ImageFont.load_default()

        style_cfg = self.styles.get_style_config(style_type)
        
        # 1. Hitung total lebar kalimat dan simpan posisi X untuk tiap kata
        text_draw = ImageDraw.Draw(base_canvas)
        word_positions = []
        current_x = 0
        space_w = text_draw.textbbox((0, 0), " ", font=font)[2]

        for idx, item in enumerate(words_list):
            w_text = item["word"].upper()
            bbox = text_draw.textbbox((0, 0), w_text, font=font)
            w_width = bbox[2] - bbox[0]
            w_height = bbox[3] - bbox[1]
            
            word_positions.append({
                "text": w_text,
                "width": w_width,
                "height": w_height,
                "local_x": current_x
            })
            current_x += w_width + space_w

        total_sentence_width = current_x - space_w
        max_word_height = max([w["height"] for w in word_positions]) if word_positions else 40

        # 2. Tentukan titik start X dan Y agar kalimat berada tepat di tengah horizontal layar
        start_x = (self.width - total_sentence_width) // 2
        # Sumbu vertikal relatif 65% tinggi video
        start_y = int(self.height * 0.65) - (max_word_height // 2)

        # 3. Gambar Background Rounded Box membungkus seluruh kalimat
        box_padding_x = self.styles.BOX_PADDING_X
        box_padding_y = self.styles.BOX_PADDING_Y
        
        box_x0 = start_x - box_padding_x
        box_y0 = start_y - box_padding_y
        box_x1 = start_x + total_sentence_width + box_padding_x
        box_y1 = start_y + max_word_height + box_padding_y + 10
        
        box_draw = ImageDraw.Draw(base_canvas)
        box_fill = (self.styles.BOX_COLOR[0], self.styles.BOX_COLOR[1], self.styles.BOX_COLOR[2], 120)
        box_draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=self.styles.BOX_ROUNDED_RADIUS, fill=box_fill)

        # 4. Gambar Teks (Drop Shadow & Lapisan Utama)
        for idx, w in enumerate(word_positions):
            word_x = start_x + w["local_x"]
            
            # Tentukan warna teks: Kuning jika aktif, Putih jika tidak aktif
            color = "#FFCC00" if idx == active_index else style_cfg["default_color"]

            # Drop Shadow Blur
            box_draw.text(
                (word_x + self.styles.SHADOW_OFFSET[0], start_y + self.styles.SHADOW_OFFSET[1]),
                w["text"],
                font=font,
                fill=self.styles.SHADOW_COLOR,
                stroke_width=self.styles.STROKE_WIDTH,
                stroke_fill=self.styles.SHADOW_COLOR
            )
            
            # Teks Utama
            box_draw.text(
                (word_x, start_y),
                w["text"],
                font=font,
                fill=color,
                stroke_width=self.styles.STROKE_WIDTH,
                stroke_fill=self.styles.STROKE_COLOR
            )

        return base_canvas
