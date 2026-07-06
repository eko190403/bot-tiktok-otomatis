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

    CHOSEN_THEME = "classic_yellow"

    THEMES = {
        "classic_yellow": {
            "hook": {"default_color": "#FF9500", "active_color": "#FFFFFF", "glow_color": (255, 149, 0)},
            "body": {"default_color": "#FFFFFF", "active_color": "#FFCC00", "glow_color": (255, 204, 0)},
            "cta": {"default_color": "#5AC8FA", "active_color": "#FFFFFF", "glow_color": (90, 200, 250)}
        },
        "neon_green": {
            "hook": {"default_color": "#34C759", "active_color": "#FFFFFF", "glow_color": (52, 199, 89)},
            "body": {"default_color": "#FFFFFF", "active_color": "#30D158", "glow_color": (48, 209, 88)},
            "cta": {"default_color": "#FFD60A", "active_color": "#FFFFFF", "glow_color": (255, 214, 10)}
        },
        "cyberpunk_pink": {
            "hook": {"default_color": "#FF2D55", "active_color": "#FFFFFF", "glow_color": (255, 45, 85)},
            "body": {"default_color": "#FFFFFF", "active_color": "#FF375F", "glow_color": (255, 55, 95)},
            "cta": {"default_color": "#BF5AF2", "active_color": "#FFFFFF", "glow_color": (191, 90, 242)}
        }
    }

    # Glow efek pada kata aktif (blur warna pada layer terpisah)
    ACTIVE_GLOW_BLUR = 6     # Radius Gaussian blur untuk glow
    ACTIVE_GLOW_ALPHA = 160  # Intensitas glow (0-255)

    @staticmethod
    def get_style_config(style_type: str = "body"):
        """Mengembalikan konfigurasi warna dan glow berdasarkan jenis segmen konten."""
        theme_name = SubtitleStyles.CHOSEN_THEME
        if theme_name not in SubtitleStyles.THEMES:
            theme_name = "classic_yellow"
            
        theme_data = SubtitleStyles.THEMES[theme_name]
        
        styles = {
            "hook": {
                "default_color": theme_data["hook"]["default_color"],
                "active_color":  theme_data["hook"]["active_color"],
                "glow_color":    theme_data["hook"]["glow_color"],
                "font_scale":    1.2,
                "max_words":     2,
            },
            "body": {
                "default_color": theme_data["body"]["default_color"],
                "active_color":  theme_data["body"]["active_color"],
                "glow_color":    theme_data["body"]["glow_color"],
                "font_scale":    1.0,
                "max_words":     2,
            },
            "cta": {
                "default_color": theme_data["cta"]["default_color"],
                "active_color":  theme_data["cta"]["active_color"],
                "glow_color":    theme_data["cta"]["glow_color"],
                "font_scale":    1.1,
                "max_words":     2,
            },
        }
        return styles.get(style_type, styles["body"])
