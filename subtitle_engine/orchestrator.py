import os
import copy
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.orchestrator import SubtitleEngineV2 as BaseEngine
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

# Konfigurasi bersih dari Magic Number
DEBUG_SUBTITLE = False
MAX_WORDS_PER_PHRASE = 4
MAX_CHARS_PER_PHRASE = 30
NATURAL_GAP_THRESHOLD = 0.45

CHAIN_GAP_MAX = 0.03
MIN_WORD_DURATION = 0.15

CTA_LAST_PADDING = 0.30
HOOK_LAST_PADDING = 0.15
BODY_LAST_PADDING = 0.20

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def _group_words_into_phrases(self, words: list) -> list:
        """
        Phrase Grouper Cerdas (V4.8): Memotong kelompok frasa berdasarkan panjang teks,
        jeda nafas alami (berbasis waktu END kata), dan deteksi tanda baca.
        """
        phrases = []
        current_phrase = []
        current_char_count = 0

        for idx, item in enumerate(words):
            word_text = item["word"]
            word_len = len(word_text)
            
            # 1. Masukkan kata saat ini ke dalam antrean grup terlebih dahulu
            current_phrase.append(item)
            current_char_count += word_len + 1
            
            # 2. Cek deteksi jeda alami berbasis END kata saat ini ke START kata berikutnya
            is_natural_pause = False
            if idx < len(words) - 1:
                # Perbaikan Poin 2: Menggunakan item["end"] untuk akurasi jeda nafas
                delta_time = words[idx + 1]["start"] - item["end"]
                if delta_time > NATURAL_GAP_THRESHOLD:
                    is_natural_pause = True

            # 3. Cek pemisahan berdasarkan tanda baca asli dari teks Edge-TTS
            is_punctuation_split = False
            if word_text.endswith((".", "!", "?")):
                is_punctuation_split = True
            elif word_text.endswith(",") and len(current_phrase) >= 2:
                is_punctuation_split = True

            # Perbaikan Poin 1: Evaluasi kondisi tunggal (should_split) untuk menghindari split ganda
            should_split = (
                len(current_phrase) >= MAX_WORDS_PER_PHRASE or
                current_char_count >= MAX_CHARS_PER_PHRASE or
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
        Subtitle Engine V4.8: Orkestrator rantai waktu karaoke progresif bebas bug overlap.
        """
        if not section_words:
            return []

        raw_words = copy.deepcopy(section_words)
        grouped_phrases = self._group_words_into_phrases(raw_words)
        
        if style_type == "cta":
            last_padding = CTA_LAST_PADDING
        elif style_type == "hook":
            last_padding = HOOK_LAST_PADDING
        else:
            last_padding = BODY_LAST_PADDING

        clips = []

        for p_idx, phrase in enumerate(grouped_phrases):
            phrase_len = len(phrase)
            
            # Bangun koordinat rantai waktu internal grup frasa
            for i in range(phrase_len - 1):
                gap = min(CHAIN_GAP_MAX, (phrase[i+1]["start"] - phrase[i]["start"]) * 0.4)
                phrase[i]["end"] = phrase[i + 1]["start"] - gap
            
            # Perbaikan Poin 3: Proteksi durasi negatif frasa terakhir menggunakan rumus proporsional adaptif
            if p_idx == len(grouped_phrases) - 1:
                phrase[-1]["end"] += last_padding
            else:
                next_start = grouped_phrases[p_idx + 1][0]["start"]
                gap = min(CHAIN_GAP_MAX, max(0.0, (next_start - phrase[-1]["start"]) * 0.4))
                phrase[-1]["end"] = next_start - gap

            # Render frame karaoke progresif untuk kata aktif
            for i, item in enumerate(phrase):
                word_start = item["start"]
                word_duration = max(item["end"] - item["start"], MIN_WORD_DURATION)
                
                if DEBUG_SUBTITLE:
                    print(f"📌 Sub V4.8 [{style_type.upper()}]: {item['word']} | {word_start:.2f}s - {word_start+word_duration:.2f}s")

                frame = self.renderer.create_progressive_frame(
                    words_list=phrase,
                    active_index=i,
                    font_path=FONT_PATH,
                    font_size=font_size,
                    style_type=style_type
                )
                
                img_rgba = np.array(frame.convert("RGBA"))
                
                clip = (ImageClip(img_rgba)
                        .with_start(word_start)
                        .with_duration(word_duration)
                        .with_position((0, 0)))
                
                clips.append(clip)

        # Bersihkan seluruh cache renderer setelah satu seksi selesai
        self.renderer.clear_cache()
        return clips
