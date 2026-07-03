class SubtitleStyles:
    # Setelan Box Latar Belakang (Background Box)
    BOX_OPACITY = 0.45       # Opasitas 45%
    BOX_ROUNDED_RADIUS = 22  # Rounded corner 22px (lebih halus)
    BOX_PADDING_X = 28
    BOX_PADDING_Y = 16
    BOX_COLOR = (0, 0, 0)    # Hitam murni

    # Setelan Efek Teks Premium
    STROKE_WIDTH = 3
    STROKE_COLOR = (0, 0, 0)
    SHADOW_BLUR_RADIUS = 10
    SHADOW_OFFSET = (3, 3)
    SHADOW_COLOR = (0, 0, 0, 200)

    # Glow efek pada kata aktif (blur warna pada layer terpisah)
    ACTIVE_GLOW_BLUR = 6     # Radius Gaussian blur untuk glow
    ACTIVE_GLOW_ALPHA = 160  # Intensitas glow (0-255)

    @staticmethod
    def get_style_config(style_type: str = "body"):
        """Mengembalikan konfigurasi warna dan glow berdasarkan jenis segmen konten."""
        styles = {
            # Hook: Orange tegas, sorot Putih, glow Orange hangat
            "hook": {
                "default_color": "#FF9500",
                "active_color":  "#FFFFFF",
                "glow_color":    (255, 149, 0),    # Orange glow
                "font_scale":    1.2,
                "max_words":     3,                # Hook impactful — max 3 kata/frase
            },
            # Body: Putih bersih, sorot Kuning, glow Kuning hangat
            "body": {
                "default_color": "#FFFFFF",
                "active_color":  "#FFCC00",
                "glow_color":    (255, 204, 0),    # Kuning glow
                "font_scale":    1.0,
                "max_words":     5,                # Body lebih panjang — max 5 kata/frase
            },
            # CTA: Cyan terang, sorot Putih, glow Cyan
            "cta": {
                "default_color": "#5AC8FA",
                "active_color":  "#FFFFFF",
                "glow_color":    (90, 200, 250),   # Cyan glow
                "font_scale":    1.1,
                "max_words":     4,                # CTA sedang — max 4 kata/frase
            },
        }
        return styles.get(style_type, styles["body"])
