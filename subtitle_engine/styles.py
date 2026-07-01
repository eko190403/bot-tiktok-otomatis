class SubtitleStyles:
    # Setelan Box Latar Belakang (Background Box)
    BOX_OPACITY = 0.45       # Opasitas 45%
    BOX_ROUNDED_RADIUS = 20  # Rounded corner 20px
    BOX_PADDING_X = 25
    BOX_PADDING_Y = 15
    BOX_COLOR = (0, 0, 0)    # Hitam murni

    # Setelan Efek Teks Premium
    STROKE_WIDTH = 4
    STROKE_COLOR = (0, 0, 0)
    SHADOW_BLUR_RADIUS = 8
    SHADOW_OFFSET = (4, 4)
    SHADOW_COLOR = (0, 0, 0, 180) # Hitam transparan untuk glow/shadow

    @staticmethod
    def get_style_config(style_type: str = "body"):
        """Mengembalikan warna dasar default berdasarkan jenis segmen konten."""
        styles = {
            "hook": {"default_color": "#FF9500", "font_scale": 1.2},  # Orange premium untuk Hook
            "body": {"default_color": "#FFFFFF", "font_scale": 1.0},  # Putih bersih untuk isi cerita
            "cta":  {"default_color": "#5AC8FA", "font_scale": 1.1}   # Cyan terang untuk ajakan CTA
        }
        return styles.get(style_type, styles["body"])
