import os
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

# Batas minimum durasi visual stiker agar nyaman dibaca mata
MIN_WORD_DURATION = 0.25
MAX_GAP_SUSTAIN = 0.40  # Jeda maksimal (detik) untuk menahan teks sebelum dianggap sebagai jeda napas

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def generate_subtitle_clips(self, section_words: list, font_size: int, style_type: str = "body") -> list:
        """
        Subtitle Engine V4.0: Menggunakan teknik Chain-Timing di mana kata aktif akan 
        ditahan di layar sampai kata berikutnya muncul agar transisi subtitle natural dan tidak terlalu cepat.
        """
        if not section_words:
            return []

        clips = []
        total_words = len(section_words)

        for i, item in enumerate(section_words):
            word_text = item["word"].upper()
            word_start = item["start"]
            raw_end = item["end"]
            
            # PERBAIKAN UTAMA: Hitung durasi secara berantai (Chain-Timing)
            if i < total_words - 1:
                next_word_start = section_words[i + 1]["start"]
                # Jika jarak ke kata berikutnya sangat dekat, tahan kata ini sampai kata berikutnya muncul
                if next_word_start - word_start <= MAX_GAP_SUSTAIN:
                    word_duration = next_word_start - word_start
                else:
                    word_duration = max(raw_end - word_start, MIN_WORD_DURATION)
            else:
                # Untuk kata terakhir di dalam seksi
                word_duration = max(raw_end - word_start, MIN_WORD_DURATION) + 0.1

            # Pastikan durasi tidak pernah lebih kecil dari batas minimal pandang mata
            word_duration = max(word_duration, MIN_WORD_DURATION)
            
            # Render stiker grafis kata tunggal
            frame = self.renderer.create_text_frame(
                word=word_text,
                font_path=FONT_PATH,
                font_size=font_size,
                style_type=style_type,
                current_index=i
            )
            
            img_rgba = np.array(frame.convert("RGBA"))
            
            # Tempelkan ke video dengan durasi berantai yang halus
            clip = (ImageClip(img_rgba, transparent=True)
                    .with_start(word_start)
                    .with_duration(word_duration)
                    .with_position(("center", 0.65)))
            
            clips.append(clip)

        return clips
