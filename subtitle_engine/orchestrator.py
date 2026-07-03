"""
subtitle_engine/orchestrator.py
Subtitle Engine V3 — Per-style phrase grouping + Pop Animation Integration
"""
import os
import copy
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from subtitle_engine.animation import SubtitleAnimator
from config import WIDTH, HEIGHT, FONT_PATH

# Batas frase default (di-override oleh styles.py per style_type)
DEFAULT_MAX_WORDS = 4
DEFAULT_MAX_CHARS = 32
NATURAL_GAP_LIMIT = 0.38   # Detik jeda bicara yang dianggap pemisah frase natural

# Durasi frame animasi pop (dalam detik dari awal kata)
POP_ANIM_DURATION = 0.18   # 180ms — cukup untuk efek pop terasa, tidak terlalu panjang


class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)
        self.animator = SubtitleAnimator()

    def _group_words_into_rhythm_phrases(self, words: list, max_words: int, max_chars: int) -> list:
        """
        Smart Phrase Builder V6: batas kata & karakter dapat dikonfigurasi per style_type.
        Memecah berdasarkan: batas kata, batas karakter, jeda bicara alami, atau tanda baca.
        """
        phrases = []
        current_phrase = []
        current_char_count = 0

        for idx, item in enumerate(words):
            word_text = item.get("word", "")
            word_len  = len(word_text)

            current_phrase.append(item)
            current_char_count += word_len + 1

            # Deteksi jeda bicara alami antar kata
            is_natural_pause = False
            if idx < len(words) - 1:
                gap_delta = words[idx + 1]["start"] - item["start"]
                if gap_delta > (item.get("duration", 0.2) + NATURAL_GAP_LIMIT):
                    is_natural_pause = True

            # Deteksi split berdasarkan tanda baca
            is_punct_split = word_text.endswith((".", "!", "?"))
            if not is_punct_split and word_text.endswith((",", ";", ":")) and len(current_phrase) >= 2:
                is_punct_split = True

            should_split = (
                len(current_phrase) >= max_words or
                current_char_count  >= max_chars or
                is_natural_pause or
                is_punct_split
            )

            if should_split:
                phrases.append(current_phrase)
                current_phrase = []
                current_char_count = 0

        if current_phrase:
            phrases.append(current_phrase)
        return phrases

    def generate_subtitle_clips(self, section_words: list, font_size: int, style_type: str = "body") -> list:
        """
        Subtitle Clip Generator V3:
        - Per-style phrase grouping
        - Integrasi pop animation pada setiap kata aktif
        - Center-aligned multi-line rendering
        - Posisi subtitle Y = 75% tinggi layar (area aman TikTok)
        """
        if not section_words:
            return []

        # Ambil konfigurasi batas frase dari styles.py
        from subtitle_engine.styles import SubtitleStyles
        style_cfg = SubtitleStyles.get_style_config(style_type)
        max_words = style_cfg.get("max_words", DEFAULT_MAX_WORDS)
        max_chars = DEFAULT_MAX_CHARS

        raw_words       = copy.deepcopy(section_words)
        grouped_phrases = self._group_words_into_rhythm_phrases(raw_words, max_words, max_chars)
        clips           = []

        # Posisi Y subtitle: 75% tinggi layar (lebih aman dari area UI TikTok)
        subtitle_y_ratio = 0.75

        for p_idx, phrase in enumerate(grouped_phrases):
            phrase_len = len(phrase)
            if phrase_len == 0:
                continue

            avg_duration  = sum(w.get("duration", 0.2) for w in phrase) / phrase_len
            visual_offset = min(0.040, avg_duration * 0.15)
            hold_padding  = 0.220

            phrase_display_start = max(0.0, phrase[0]["start"] - visual_offset)
            phrase_display_end   = phrase[-1]["end"] + hold_padding

            if p_idx < len(grouped_phrases) - 1:
                next_phrase_start  = grouped_phrases[p_idx + 1][0]["start"] - visual_offset
                phrase_display_end = min(phrase_display_end, next_phrase_start)

            # Pre-render frame statis (tanpa highlight) agar koordinat bbox tersedia
            font_size_actual = int(font_size * style_cfg.get("font_scale", 1.0))

            for i, item in enumerate(phrase):
                highlight_start = max(phrase_display_start, item["start"] - visual_offset)
                highlight_end   = item["start"] - visual_offset + item.get("duration", 0.2)

                if i == phrase_len - 1:
                    highlight_end = phrase_display_end
                else:
                    next_word_target = phrase[i + 1]["start"] - visual_offset
                    highlight_end = min(highlight_end, next_word_target)

                word_duration = max(0.12, highlight_end - highlight_start)

                # ── Render frame subtitle (canvas mini) ──────────────────────
                frame_img, bbox_w, bbox_h = self.renderer.create_progressive_frame(
                    words_list=phrase,
                    active_index=i,
                    font_path=FONT_PATH,
                    font_size=font_size_actual,
                    scale_factor=1.08,
                    style_type=style_type,
                )

                # ── Posisi absolut di layar (center-X, 75% Y) ────────────────
                pos_x = (WIDTH  - bbox_w) // 2
                pos_y = int(HEIGHT * subtitle_y_ratio) - (bbox_h // 2)

                # ── Pop animation: pre-render 5 frames of scale animation ───────
                fps = 30
                frame_duration = 1.0 / fps
                num_anim_frames = 5
                pop_duration = num_anim_frames * frame_duration  # 0.167s

                # Jika durasi kata sangat singkat, sesuaikan jumlah frame pop
                if word_duration < pop_duration:
                    num_anim_frames = max(1, int(word_duration * fps))
                    pop_duration = num_anim_frames * frame_duration

                anim_clips = []
                for f_idx in range(num_anim_frames):
                    # Progress [0.2 - 1.0] untuk curve scaling
                    progress = (f_idx + 1) / num_anim_frames
                    animated_pil = SubtitleAnimator.apply_pop_animation(
                        frame_img.copy(), progress,
                        center_coords=(bbox_w // 2, bbox_h // 2),
                    )
                    animated_np = np.array(animated_pil.convert("RGBA"))
                    # imageio / moviepy akan membaca canvas mini RGBA ini dengan transparansi
                    anim_clips.append(ImageClip(animated_np).with_duration(frame_duration))

                remain_duration = word_duration - pop_duration
                if remain_duration > 0.001:
                    static_np = np.array(frame_img.convert("RGBA"))
                    anim_clips.append(ImageClip(static_np).with_duration(remain_duration))

                from moviepy import concatenate_videoclips
                clip = (concatenate_videoclips(anim_clips, method="compose")
                        .with_start(highlight_start)
                        .with_position((pos_x, pos_y)))
                clips.append(clip)

        self.renderer.clear_cache()
        return clips
