import os
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

# Integrasi Konfigurasi Baru Subtitle Engine V3
SUBTITLE_Y = int(HEIGHT * 0.62)
MIN_WORD_DURATION = 0.18
WORD_OVERLAP = 0.08

class SubtitleEngineV2:  # Nama kelas dipertahankan agar tidak merusak import di video_builder
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def wrap_text(self, text: str, max_chars_per_line: int = 22) -> str:
        """Memotong kalimat panjang secara otomatis menjadi beberapa baris (Auto-Wrap)."""
        words = text.upper().split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            if current_length + len(word) + 1 > max_chars_per_line and current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_length = len(word)
            else:
                current_line.append(word)
                current_length += len(word) + 1
                
        if current_line:
            lines.append(" ".join(current_line))
            
        return "\n".join(lines)

    def generate_subtitle_clips(self, text: str, start_time: float, duration: float, font_size: int, style_type: str = "body", fps: int = 30, timestamps: list = None) -> list:
        """
        Subtitle Engine V3: Mendukung penayangan berbasis Whisper Timestamp 
        serta Fallback linear dengan proteksi overlapping durasi visual.
        """
        wrapped_text = self.wrap_text(text, max_chars_per_line=22)
        clean_source_words = text.upper().replace(".", "").replace(",", "").replace("?", "").replace("!", "").split()
        
        if not clean_source_words:
            return []

        clips = []

        # --------------------------
        # MODE 1 : Pakai Whisper Timestamp (Masa Depan)
        # --------------------------
        if timestamps:
            for i, item in enumerate(timestamps):
                word_start = item["start"]
                # Amankan durasi minimum kata pendek
                word_duration = max(item["end"] - item["start"], MIN_WORD_DURATION)
                # Tambahkan overlap transisi halus
                word_duration += WORD_OVERLAP
                
                frame = self.renderer.create_text_frame(
                    text=wrapped_text,
                    current_word_index=i,
                    font_path=FONT_PATH,
                    font_size=font_size,
                    style_type=style_type
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

        # --------------------------
        # MODE 2 : Fallback Linier Otomatis (Mode Sekarang)
        # --------------------------
        else:
            base_duration = duration / len(clean_source_words)
            for i, word in enumerate(clean_source_words):
                word_start = start_time + (i * base_duration)
                # Amankan durasi minimum kata pendek
                word_duration = max(base_duration, MIN_WORD_DURATION)
                # Tambahkan overlap transisi halus
                word_duration += WORD_OVERLAP
                
                frame = self.renderer.create_text_frame(
                    text=wrapped_text,
                    current_word_index=i,
                    font_path=FONT_PATH,
                    font_size=font_size,
                    style_type=style_type
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
