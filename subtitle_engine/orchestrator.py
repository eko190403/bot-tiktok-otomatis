import os
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

SUBTITLE_Y = int(HEIGHT * 0.62)
MIN_WORD_DURATION = 0.18
WORD_OVERLAP = 0.08

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def generate_subtitle_clips(self, text: str, start_time: float, duration: float, font_size: int, style_type: str = "body", fps: int = 30, timestamps: list = None) -> list:
        """Subtitle Engine V3: Mengirimkan kata tunggal langsung ke renderer untuk menjamin visual muncul tepat waktu."""
        clean_source_words = text.upper().replace(".", "").replace(",", "").replace("?", "").replace("!", "").split()
        
        if not clean_source_words:
            return []

        clips = []

        # MODE 1 : Pakai Whisper Timestamp
        if timestamps:
            for i, item in enumerate(timestamps):
                word_start = item["start"]
                word_duration = max(item["end"] - item["start"], MIN_WORD_DURATION) + WORD_OVERLAP
                active_word = item["word"].upper()
                
                frame = self.renderer.create_text_frame(
                    word=active_word,
                    font_path=FONT_PATH,
                    font_size=font_size,
                    style_type=style_type,
                    current_index=i
                )
                
                img = np.array(frame.convert("RGBA"))
                rgb = img[:, :, :3]
                alpha = img[:, :, 3] / 255.0
                
                clip = (ImageClip(rgb)
                        .with_start(word_start)
                        .with_duration(word_duration)
                        .with_position(("center", SUBTITLE_Y)))
                
                mask = ImageClip(alpha, is_mask=True).with_duration(word_duration)
                clip.mask = mask
                clips.append(clip)

        # MODE 2 : Fallback Linier Otomatis
        else:
            base_duration = duration / len(clean_source_words)
            for i, word in enumerate(clean_source_words):
                word_start = start_time + (i * base_duration)
                word_duration = max(base_duration, MIN_WORD_DURATION) + WORD_OVERLAP
                
                frame = self.renderer.create_text_frame(
                    word=word,
                    font_path=FONT_PATH,
                    font_size=font_size,
                    style_type=style_type,
                    current_index=i
                )
                
                img = np.array(frame.convert("RGBA"))
                rgb = img[:, :, :3]
                alpha = img[:, :, 3] / 255.0
                
                clip = (ImageClip(rgb)
                        .with_start(word_start)
                        .with_duration(word_duration)
                        .with_position(("center", SUBTITLE_Y)))
                
                mask = ImageClip(alpha, is_mask=True).with_duration(word_duration)
                clip.mask = mask
                clips.append(clip)

        return clips
