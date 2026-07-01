import os
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def wrap_text(self, text: str, max_chars_per_line: int = 22) -> str:
        """Memotong kalimat panjang secara otomatis menjadi beberapa baris (Auto-Wrap)."""
        words = text.upper().split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            # +1 untuk spasi
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

    def generate_subtitle_clips(self, text: str, start_time: float, duration: float, font_size: int, style_type: str = "body", fps: int = 30) -> list:
        """
        Memecah kalimat menjadi teks berbaris rapi (Auto-Wrap) dengan efek karaoke highlight per kata.
        """
        # 1. Atur teks agar otomatis turun baris jika terlalu panjang (Maksimal 22 karakter per baris)
        wrapped_text = self.wrap_text(text, max_chars_per_line=22)
        
        # Bersihkan naskah asli dari tanda baca untuk pencarian indeks kata yang akurat
        clean_source_words = text.upper().replace(".", "").replace(",", "").replace("?", "").replace("!", "").split()
        
        if not clean_source_words:
            return []

        duration_per_word = duration / len(clean_source_words)
        clips = []

        for i, word in enumerate(clean_source_words):
            word_start = start_time + (i * duration_per_word)
            
            # 2. Render gambar PNG dengan teks yang sudah di-wrap, namun indeks kata yang aktif tetap berjalan tepat
            base_frame = self.renderer.create_text_frame(
                text=wrapped_text,  # Gunakan teks berformat baris baru '\n'
                current_word_index=i,
                font_path=FONT_PATH,
                font_size=font_size,
                style_type=style_type
            )
            
            img_rgba = base_frame.convert("RGBA")
            img_array = np.array(img_rgba)
            
            rgb_array = img_array[:, :, :3]
            alpha_array = img_array[:, :, 3] / 255.0

            frame_clip = (ImageClip(rgb_array)
                          .with_start(word_start)
                          .with_duration(duration_per_word)
                          .with_position(('center', 'center')))
            
            mask_clip = ImageClip(alpha_array, is_mask=True).with_duration(duration_per_word)
            frame_clip.mask = mask_clip

            clips.append(frame_clip)

        return clips
