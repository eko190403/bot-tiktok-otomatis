import os
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

MIN_WORD_DURATION = 0.15
WORD_OVERLAP = 0.05

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def generate_subtitle_clips(self, text_or_words: list, font_size: int, style_type: str = "body") -> list:
        """
        Subtitle Engine V3.5: Menerima langsung list of dict kata dengan 
        timestamp absolut hasil deteksi SSML Mark Edge-TTS.
        """
        if not text_or_words:
            return []

        clips = []

        for i, item in enumerate(text_or_words):
            word_text = item["word"].upper().replace(".", "").replace(",", "").replace("?", "").replace("!", "").strip()
            if not word_text:
                continue
                
            word_start = item["start"]
            # Amankan durasi jika ada pembacaan super cepat
            word_duration = max(item["end"] - item["start"], MIN_WORD_DURATION) + WORD_OVERLAP
            
            # Panggil renderer untuk membuat gambar stiker kata tunggal
            frame = self.renderer.create_text_frame(
                word=word_text,
                font_path=FONT_PATH,
                font_size=font_size,
                style_type=style_type,
                current_index=i
            )
            
            img_rgba = np.array(frame.convert("RGBA"))
            
            # Letakkan stiker kata di posisi tengah bawah layar (koordinat relatif 0.65)
            clip = (ImageClip(img_rgba, transparent=True)
                    .with_start(word_start)
                    .with_duration(word_duration)
                    .with_position(("center", 0.65)))
            
            clips.append(clip)

        return clips
