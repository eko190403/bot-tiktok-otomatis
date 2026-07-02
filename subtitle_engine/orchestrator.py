import os
import copy
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

# EVALUASI 4 & 7: Konfigurasi bersih dari Magic Number (Mudah di-tuning)
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
        EVALUASI 3 & 9 (Phrase Grouper Cerdas): Memotong kelompok frasa 
        berdasarkan panjang teks DAN jeda nafas alami pembicara (Delta > 0.45s).
        """
        phrases = []
        current_phrase = []
        current_char_count = 0

        for idx, item in enumerate(words):
            word_len = len(item["word"])
            
            # Cek deteksi jeda alami ke kata berikutnya
            is_natural_pause = False
            if idx < len(words) - 1:
                delta_time = words[idx + 1]["start"] - item["start"]
                if delta_time > NATURAL_GAP_THRESHOLD:
                    is_natural_pause = True

            # Kondisi pemotongan grup frasa
            if len(current_phrase) >= MAX_WORDS_PER_PHRASE or \
               (current_char_count + word_len > MAX_CHARS_PER_PHRASE and current_phrase) or \
               (is_natural_pause and current_phrase):
                
                phrases.append(current_phrase)
                current_phrase = []
                current_char_count = 0
            
            current_phrase.append(item)
            current_char_count += word_len + 1
            
            # Jika kata saat ini adalah akhir dari jeda nafas, langsung kunci grup setelah dimasukkan
            if is_natural_pause:
                phrases.append(current_phrase)
                current_phrase = []
                current_char_count = 0
            
        if current_phrase:
            phrases.append(current_phrase)
        return phrases

    def generate_subtitle_clips(self, section_words: list, font_size: int, style_type: str = "body") -> list:
        """
        Subtitle Engine V4.6: Memproses sinkronisasi waktu karaoke berantai bebas bug overlap.
        """
        if not section_words:
            return []

        raw_words = copy.deepcopy(section_words)
        
        # Pecah kata menjadi kelompok frasa pendek berbasis ritme bicara
        grouped_phrases = self._group_words_into_phrases(raw_words)
        
        # Atur padding adaptif berdasarkan tipe seksi
        if style_type == "cta":
            last_padding = CTA_LAST_PADDING
        elif style_type == "hook":
            last_padding = HOOK_LAST_PADDING
        else:
            last_padding = BODY_LAST_PADDING

        clips = []

        # Proses koordinat rantai waktu per grup frasa
        for p_idx, phrase in enumerate(grouped_phrases):
            phrase_len = len(phrase)
            
            # Bangun koordinat rantai waktu internal grup
            for i in range(phrase_len - 1):
                gap = min(CHAIN_GAP_MAX, (phrase[i+1]["start"] - phrase[i]["start"]) * 0.4)
                phrase[i]["end"] = phrase[i + 1]["start"] - gap
            
            # EVALUASI 2 FIXED: Padding hanya disuntikkan pada frasa paling akhir di dalam seksi tersebut (Anti-Overlap)
            if p_idx == len(grouped_phrases) - 1:
                phrase[-1]["end"] += last_padding
            else:
                # Frasa tengah ditahan tepat hingga frame frasa berikutnya mulai berjalan
                phrase[-1]["end"] = grouped_phrases[p_idx + 1][0]["start"] - CHAIN_GAP_MAX

            # Render frame karaoke progresif untuk kata aktif
            for i, item in enumerate(phrase):
                word_start = item["start"]
                word_duration = max(item["end"] - item["start"], MIN_WORD_DURATION)
                
                # EVALUASI 4 CONTROLLED: Log debug hanya aktif jika variabel DEBUG_SUBTITLE bernilai True
                if DEBUG_SUBTITLE:
                    print(f"📌 Sub V4.6 [{style_type.upper()}]: {item['word']} | {word_start:.2f}s - {word_start+word_duration:.2f}s")

                frame = self.renderer.create_progressive_frame(
                    words_list=phrase,
                    active_index=i,
                    font_path=FONT_PATH,
                    font_size=font_size,
                    style_type=style_type
                )
                
                img_rgba = np.array(frame.convert("RGBA"))
                
                # Render stiker berdimensi penuh tanpa redundansi parameter transparent=True
                clip = (ImageClip(img_rgba)
                        .with_start(word_start)
                        .with_duration(word_duration)
                        .with_position((0, 0)))
                
                clips.append(clip)

        # Bersihkan cache render setelah satu seksi selesai dikerjakan agar RAM tetap lega
        self.renderer.clear_cache()
        return clips
