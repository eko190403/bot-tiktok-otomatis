"""
subtitle_engine/renderer.py
Subtitle Renderer Premium V2 — Multi-line word-wrap + Active Word Glow Effect
"""
import os
import string
import unicodedata
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from subtitle_engine.styles import SubtitleStyles

MAX_STATIC_CACHE = 40
MAX_FONT_CACHE   = 20

# Lebar maksimal frase sebagai persentase lebar layar (80%)
MAX_LINE_WIDTH_RATIO = 0.80


class PhraseCache:
    def __init__(self, base_image: Image.Image, word_positions: list,
                 bbox_w: int, bbox_h: int, line_count: int = 1):
        self.base_image    = base_image
        self.word_positions = word_positions  # list of dict, sudah berisi koordinat absolut di canvas
        self.bbox_w        = bbox_w
        self.bbox_h        = bbox_h
        self.line_count    = line_count


class SubtitleRenderer:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width  = width
        self.height = height
        self.styles = SubtitleStyles()

        self.static_layer_cache = OrderedDict()
        self.font_cache         = OrderedDict()

        # Canvas ukur kecil — hindari alokasi 1080x1920 saat inisialisasi
        self.measure_img  = Image.new("RGBA", (1, 1))
        self.measure_draw = ImageDraw.Draw(self.measure_img)

    def clear_cache(self):
        self.static_layer_cache.clear()
        self.font_cache.clear()

    # ─────────────────────────────────────────────────────────────────────────
    # Font helper
    # ─────────────────────────────────────────────────────────────────────────
    def _get_cached_font(self, font_path: str, font_size: int) -> ImageFont.FreeTypeFont:
        safe_size = max(10, int(font_size))
        key = (font_path, safe_size)

        if key in self.font_cache:
            self.font_cache.move_to_end(key)
            return self.font_cache[key]

        paths_to_try = [
            font_path,
            "assets/fonts/Oswald-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        font_obj = None
        for path in paths_to_try:
            if path and os.path.exists(path):
                try:
                    font_obj = ImageFont.truetype(path, safe_size)
                    break
                except IOError:
                    continue

        if font_obj is None:
            font_obj = ImageFont.load_default()

        self.font_cache[key] = font_obj
        if len(self.font_cache) > MAX_FONT_CACHE:
            self.font_cache.popitem(last=False)
        return font_obj

    # ─────────────────────────────────────────────────────────────────────────
    # Text cleaning
    # ─────────────────────────────────────────────────────────────────────────
    def _clean_text(self, raw: str) -> str:
        return str(raw).strip().upper().translate(
            str.maketrans("", "", string.punctuation)
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Multi-line word-wrap layout builder
    # ─────────────────────────────────────────────────────────────────────────
    def _build_lines(self, words_list: list, font_normal, space_w: int) -> list:
        """
        Memecah daftar kata menjadi baris-baris otomatis berdasarkan MAX_LINE_WIDTH_RATIO.
        Mengembalikan list of list-of-word-dicts, setiap sub-list adalah satu baris.
        """
        max_px = int(self.width * MAX_LINE_WIDTH_RATIO)
        lines = []
        current_line = []
        current_w = 0

        for item in words_list:
            text = self._clean_text(item.get("display", item.get("word", "")))
            if not text:
                continue
            try:
                bb = self.measure_draw.textbbox((0, 0), text, font=font_normal)
                w = max(10, bb[2] - bb[0])
                h = max(10, bb[3] - bb[1])
            except Exception:
                w, h = len(text) * 24, 40

            # Jika menambahkan kata ini melebihi batas baris, mulai baris baru
            needed = current_w + w + (space_w if current_line else 0)
            if current_line and needed > max_px:
                lines.append(current_line)
                current_line = []
                current_w = 0

            current_line.append({
                "original": item,
                "text": text,
                "w": w,
                "h": h,
            })
            current_w += w + (space_w if len(current_line) > 1 else 0)

        if current_line:
            lines.append(current_line)
        return lines

    # ─────────────────────────────────────────────────────────────────────────
    # Static base renderer (dipanggil sekali per frase unik, di-cache)
    # ─────────────────────────────────────────────────────────────────────────
    def _render_static_base(self, words_list: list, font_normal,
                            font_active_max, style_type: str = "body") -> PhraseCache:
        from subtitle_engine.highlighter import KeywordHighlighter
        highlighter  = KeywordHighlighter()
        style_cfg    = self.styles.get_style_config(style_type)
        default_color = style_cfg.get("default_color", "#FFFFFF")
        stroke_w      = self.styles.STROKE_WIDTH

        try:
            space_w = int(self.measure_draw.textbbox((0, 0), " ", font=font_normal)[2]) + 12
        except Exception:
            space_w = 18

        # ── Bangun layout multi-baris ────────────────────────────────────────
        lines = self._build_lines(words_list, font_normal, space_w)

        padding_x  = self.styles.BOX_PADDING_X
        padding_y  = self.styles.BOX_PADDING_Y
        line_gap   = 10   # Jarak antar baris (px)

        line_widths  = []
        line_heights = []
        for line in lines:
            lw = sum(wd["w"] for wd in line) + space_w * (len(line) - 1)
            lh = max((wd["h"] for wd in line), default=40)
            line_widths.append(lw)
            line_heights.append(lh)

        total_w = max(line_widths) if line_widths else 100
        total_h = sum(line_heights) + line_gap * (len(lines) - 1) if line_heights else 40

        bbox_w = total_w + padding_x * 2 + 20
        bbox_h = total_h + padding_y * 2 + 24

        static_canvas = Image.new("RGBA", (bbox_w, bbox_h), (0, 0, 0, 0))

        start_x = padding_x + 10   # titik kiri dalam canvas
        start_y = padding_y + 8    # titik atas dalam canvas

        # Gambar rounded background box
        box_fill = (*self.styles.BOX_COLOR, 135)
        static_draw = ImageDraw.Draw(static_canvas)
        static_draw.rounded_rectangle(
            [start_x - padding_x, start_y - padding_y,
             start_x + total_w + padding_x, start_y + total_h + padding_y + 8],
            radius=self.styles.BOX_ROUNDED_RADIUS,
            fill=box_fill
        )

        # ── Shadow layer ─────────────────────────────────────────────────────
        shadow_canvas = Image.new("RGBA", (bbox_w, bbox_h), (0, 0, 0, 0))
        shadow_draw   = ImageDraw.Draw(shadow_canvas)
        ox, oy        = self.styles.SHADOW_OFFSET

        # ── Posisikan setiap kata & buat word_positions flat (urutan kata) ───
        word_positions = []
        cursor_y = start_y
        for line_idx, (line, lh) in enumerate(zip(lines, line_heights)):
            # Center-align setiap baris secara horizontal
            lw = line_widths[line_idx]
            cursor_x = start_x + (total_w - lw) // 2

            for wd in line:
                abs_x = cursor_x
                abs_y = cursor_y

                # Shadow
                try:
                    shadow_draw.text(
                        (abs_x + ox, abs_y + oy), wd["text"],
                        font=font_normal, fill=self.styles.SHADOW_COLOR,
                        stroke_width=stroke_w, stroke_fill=self.styles.SHADOW_COLOR,
                    )
                except Exception:
                    shadow_draw.text((abs_x + ox, abs_y + oy), wd["text"],
                                     font=font_normal, fill=self.styles.SHADOW_COLOR)

                word_positions.append({
                    "text":        wd["text"],
                    "w_normal":    wd["w"],
                    "h_normal":    wd["h"],
                    "abs_x":       abs_x,
                    "abs_y":       abs_y,
                    # Untuk kompatibilitas render aktif (digunakan di create_progressive_frame)
                    "render_start_x": abs_x,
                    "render_start_y": abs_y,
                    "local_x": 0,
                    "w_active_max": int(wd["w"] * 1.05),
                    "h_active_max": int(wd["h"] * 1.05),
                })
                cursor_x += wd["w"] + space_w

            cursor_y += lh + line_gap

        # Blur shadow & composite
        try:
            shadow_blurred = shadow_canvas.filter(
                ImageFilter.GaussianBlur(radius=self.styles.SHADOW_BLUR_RADIUS)
            )
            static_canvas = Image.alpha_composite(static_canvas, shadow_blurred)
        except Exception:
            pass

        # ── Gambar teks normal (non-aktif) ───────────────────────────────────
        main_draw = ImageDraw.Draw(static_canvas)
        for wp in word_positions:
            color = highlighter.get_word_color(wp["text"], default_color)
            try:
                main_draw.text(
                    (wp["abs_x"], wp["abs_y"]), wp["text"],
                    font=font_normal, fill=color,
                    stroke_width=stroke_w, stroke_fill=self.styles.STROKE_COLOR,
                )
            except Exception:
                main_draw.text((wp["abs_x"], wp["abs_y"]), wp["text"],
                               font=font_normal, fill=color)

        return PhraseCache(static_canvas, word_positions, bbox_w, bbox_h,
                           line_count=len(lines))

    # ─────────────────────────────────────────────────────────────────────────
    # Active word glow helper
    # ─────────────────────────────────────────────────────────────────────────
    def _draw_active_glow(self, canvas: Image.Image, wp: dict,
                          glow_color: tuple, font_active) -> Image.Image:
        """Menggambar efek glow berwarna pada kata aktif menggunakan Gaussian Blur."""
        glow_canvas = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        glow_draw   = ImageDraw.Draw(glow_canvas)
        glow_fill   = (*glow_color[:3], self.styles.ACTIVE_GLOW_ALPHA)
        try:
            glow_draw.text(
                (wp["abs_x"], wp["abs_y"]), wp["text"],
                font=font_active, fill=glow_fill,
                stroke_width=self.styles.STROKE_WIDTH + 2, stroke_fill=glow_fill,
            )
        except Exception:
            glow_draw.text((wp["abs_x"], wp["abs_y"]), wp["text"],
                           font=font_active, fill=glow_fill)
        try:
            glow_blurred = glow_canvas.filter(
                ImageFilter.GaussianBlur(radius=self.styles.ACTIVE_GLOW_BLUR)
            )
            return Image.alpha_composite(canvas, glow_blurred)
        except Exception:
            return canvas

    # ─────────────────────────────────────────────────────────────────────────
    # Public API — dipanggil oleh orchestrator setiap frame
    # ─────────────────────────────────────────────────────────────────────────
    def create_progressive_frame(
        self,
        words_list:   list,
        active_index: int,
        font_path:    str,
        font_size:    int,
        scale_factor: float = 1.0,
        style_type:   str   = "body",
    ) -> tuple:
        """
        Mengembalikan tuple: (PIL.Image, bbox_w, bbox_h)
        Canvas sudah berisi teks frase lengkap + highlight kata aktif + glow efek.
        """
        if not words_list:
            words_list = [{"word": "KONTEN", "display": "KONTEN"}]

        words_tuple  = tuple(w.get("display", w.get("word", "")) for w in words_list)
        safe_scale   = round(min(max(scale_factor, 1.0), 1.10), 2)

        font_normal  = self._get_cached_font(font_path, font_size)
        font_active  = (font_normal if safe_scale == 1.0
                        else self._get_cached_font(font_path, int(font_size * safe_scale)))

        # Ambil / buat cache static base
        static_key = (words_tuple, font_size, style_type)
        if static_key in self.static_layer_cache:
            self.static_layer_cache.move_to_end(static_key)
        else:
            font_active_max = self._get_cached_font(font_path, int(font_size * 1.10))
            self.static_layer_cache[static_key] = self._render_static_base(
                words_list, font_normal, font_active_max, style_type
            )
            if len(self.static_layer_cache) > MAX_STATIC_CACHE:
                self.static_layer_cache.popitem(last=False)

        phrase_cache = self.static_layer_cache[static_key]

        # Salin canvas dasar (bukan 1080×1920 — hanya canvas mini)
        final_frame  = phrase_cache.base_image.copy()

        if 0 <= active_index < len(phrase_cache.word_positions):
            wp = phrase_cache.word_positions[active_index]

            from subtitle_engine.highlighter import KeywordHighlighter
            highlighter   = KeywordHighlighter()
            style_cfg     = self.styles.get_style_config(style_type)
            default_active = style_cfg.get("active_color", "#FFCC00")
            glow_color     = style_cfg.get("glow_color", (255, 204, 0))

            # Warna kata aktif — keyword overrides default_active
            keyword_color = highlighter.get_word_color(wp["text"], None)
            active_color  = keyword_color if keyword_color else default_active

            # ── 1. Gambar glow efek dulu (di belakang teks) ─────────────────
            final_frame = self._draw_active_glow(final_frame, wp, glow_color, font_active)

            # ── 2. Gambar teks aktif di atas glow ───────────────────────────
            frame_draw = ImageDraw.Draw(final_frame)
            try:
                frame_draw.text(
                    (wp["abs_x"], wp["abs_y"]), wp["text"],
                    font=font_active, fill=active_color,
                    stroke_width=self.styles.STROKE_WIDTH,
                    stroke_fill=self.styles.STROKE_COLOR,
                )
            except Exception:
                frame_draw.text((wp["abs_x"], wp["abs_y"]), wp["text"],
                                font=font_active, fill=active_color)

        return final_frame, phrase_cache.bbox_w, phrase_cache.bbox_h
