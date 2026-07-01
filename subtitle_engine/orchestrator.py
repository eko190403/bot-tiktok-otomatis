import os
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

# MASALAH 4 FIX: Nilai batas aman sesuai saran teruji kamu
MIN_WORD_DURATION = 0.20
WORD_OVERLAP = 0.03

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def generate_subtitle_clips(self, section_words: list, font_size: int, style_type: str = "body") -> list:
        """
        Subtitle Engine V3.8: Menerima list kata spesifik dari seksi tertentu, 
        menerapkan batas durasi minimum, dan merender posisi stiker secara relatif.
        """
        if not section_words:
            return []

        clips = []

        for i, item in enumerate(section_words):
            word_text = item["word"].upper()
            word_start = item["start"]
            
            # Menerapkan durasi minimum dan overlap natural hasil rekomendasi kamu
            word_duration = max(item["end"] - item["start"], MIN_WORD_DURATION) + WORD_OVERLAP
            
            # Render stiker kata tunggal
            frame = self.renderer.create_text_frame(
                word=word_text,
                font_path=FONT_PATH,
                font_size=font_size,
                style_type=style_type,
                current_index=i
            )
            
            img_rgba = np.array(frame.convert("RGBA"))
            
            # Kunci stiker di area aman 65% tinggi video
            clip = (ImageClip(img_rgba, transparent=True)
                    .with_start(word_start)
                    .with_duration(word_duration)
                    .with_position(("center", 0.65)))
            
            clips.append(clip)

        return clips
