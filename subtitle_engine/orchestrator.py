import os
import copy
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

MAX_WORDS_PHRASE = 4
MAX_CHARS_PHRASE = 28
NATURAL_GAP_LIMIT = 0.40 # Jeda hening pembicaraan (detik)

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def _group_words_into_rhythm_phrases(self, words: list) -> list:
        """
        Smart Phrase Builder (V5.2): Memecah baris sensitif koma, 
        titik, panjang teks, dan waktu hening (Poin 2 & 3 Fix).
        """
        phrases = []
        current_phrase = []
        current_char_count = 0

        for idx, item in enumerate(words):
            word_text = item["word"]
            word_len = len(word_text)
            
            current_phrase.append(item)
            current_char_count += word_len + 1
            
            # Perbaikan Jeda Alami Aman: Menggunakan next.start - current.start untuk antisipasi overlap suara
            is_natural_pause = False
            if idx < len(words) - 1:
                gap_delta = words[idx + 1]["start"] - item["start"]
                if gap_delta > (item["duration"] + NATURAL_GAP_LIMIT):
                    is_natural_pause = True

            # Pemotongan Cerdas Berbasis Tanda Baca Asli (Koma & Titik dipertahankan)
            is_punctuation_split = False
            if word_text.endswith((".", "!", "?")):
                is_punctuation_split = True
            elif word_text.endswith((",", ";", ":")) and len(current_phrase) >= 2:
                is_punctuation_split = True

            should_split = (
                len(current_phrase) >= MAX_WORDS_PHRASE or
                current_char_count >= MAX_CHARS_PHRASE or
                is_natural_pause or
                is_punctuation_split
            )
            
            if should_split and idx < len(words) - 1:
                phrases.append(current_phrase)
                current_phrase = []
                current_char_count = 0
                
        if current_phrase:
            phrases.append(current_phrase)
        return phrases

    def generate_subtitle_clips(self, section_words: list, font_size: int, style_type: str = "body") -> list:
        """
        Timing Optimizer Mesin Utama V5.2 + Easing Animation Loop.
        """
        if not section_words:
            return []

        raw_words = copy.deepcopy(section_words)
        grouped_phrases = self._group_words_into_rhythm_phrases(raw_words)
        clips = []

        for p_idx, phrase in enumerate(grouped_phrases):
            phrase_len = len(phrase)
            if phrase_len == 0:
                continue

            # Konfigurasi Offset adaptif berbasis tempo (Poin 5 Adaptif Offset Fix)
            avg_duration = sum(w["duration"] for w in phrase) / phrase_len
            visual_offset = min(0.050, avg_duration * 0.20) # Maksimal 50ms antisipasi
            hold_padding = 0.250 # Tahan 250ms di akhir frasa (Hold Time)

            phrase_display_start = max(0.0, phrase[0]["start"] - visual_offset)
            phrase_display_end = phrase[-1]["end"] + hold_padding
            
            if p_idx < len(grouped_phrases) - 1:
                next_phrase_start = grouped_phrases[p_idx + 1][0]["start"] - visual_offset
                phrase_display_end = min(phrase_display_end, next_phrase_start)

            # Proses Rantai Waktu Subtitle Kata Dinamis
            for i, item in enumerate(phrase):
                # PERBAIKAN BUG TINGKAT TINGGI: Gunakan properti item["duration"] murni asli Edge-TTS (BUG 1 FIX)
                highlight_start = max(phrase_display_start, item["start"] - visual_offset)
                highlight_end = item["start"] - visual_offset + item["duration"]
                
                if i == phrase_len - 1:
                    highlight_end = phrase_display_end
                else:
                    next_word_target = phrase[i + 1]["start"] - visual_offset
                    highlight_end = min(highlight_end, next_word_target)

                word_total_duration = max(0.15, highlight_end - highlight_start)

                # =============================================================
                # PERBAIKAN POIN 4 EASING SCALE: Pecah 1 kata menjadi Sub-Frame Easing (60ms)
                # =============================================================
                frame_fps = 30.0
                frame_time = 1.0 / frame_fps  # ~0.033 detik (33ms per frame)
                
                # Tahap Easing Array: 1.00 -> 1.04 -> 1.08 -> 1.10 (Target Skala Emas 1.10)
                easing_scales = [1.04, 1.08, 1.10]
                current_time_pointer = highlight_start

                for s_idx, scale in enumerate(easing_scales):
                    if word_total_duration > (s_idx * frame_time):
                        frame = self.renderer.create_progressive_frame(
                            words_list=phrase, active_index=i, font_path=FONT_PATH,
                            font_size=font_size, scale_factor=scale, style_type=style_type
                        )
                        img_rgba = np.array(frame.convert("RGBA"))
                        
                        clip = (ImageClip(img_rgba)
                                .with_start(current_time_pointer)
                                .with_duration(frame_time)
                                .with_position((0, 0)))
                        clips.append(clip)
                        current_time_pointer += frame_time
                
                # Sisa Durasi Kata Mengunci Skala Penuh 1.10 (Tahan Diam)
                remaining_duration = highlight_end - current_time_pointer
                if remaining_duration > 0:
                    frame = self.renderer.create_progressive_frame(
                        words_list=phrase, active_index=i, font_path=FONT_PATH,
                        font_size=font_size, scale_factor=1.10, style_type=style_type
                    )
                    img_rgba = np.array(frame.convert("RGBA"))
                    
                    clip = (ImageClip(img_rgba)
                            .with_start(current_time_pointer)
                            .with_duration(remaining_duration)
                            .with_position((0, 0)))
                    clips.append(clip)

        self.renderer.clear_cache()
        return clips
