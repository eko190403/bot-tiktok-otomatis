import os
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def generate_subtitle_clips(self, text: str, start_time: float, duration: float, font_size: int, style_type: str = "body", fps: int = 30) -> list:
        """
        Memecah kalimat menjadi rangkaian kata bertingkat (Karaoke Highlight Word-by-Word)
        dengan optimasi durasi blok penuh agar sinkronisasi aman dan durasi video tidak menciut.
        """
        words = text.upper().split()
        if not words:
            return []

        # Hitung durasi tayang yang adil untuk setiap kata tunggal
        duration_per_word = duration / len(words)
        clips = []

        for i, word in enumerate(words):
            # Tentukan dengan presisi kapan kata ini mulai dan selesai diucapkan
            word_start = start_time + (i * duration_per_word)
            
            # 1. Cukup render 1 gambar PNG statis untuk kondisi kata aktif saat ini
            base_frame = self.renderer.create_text_frame(
                text=text,
                current_word_index=i,
                font_path=FONT_PATH,
                font_size=font_size,
                style_type=style_type
            )
            
            # 2. Konversi gambar Pillow RGBA menjadi matriks NumPy RGB + Alpha Mask
            img_rgba = base_frame.convert("RGBA")
            img_array = np.array(img_rgba)
            
            rgb_array = img_array[:, :, :3]
            alpha_array = img_array[:, :, 3] / 255.0

            # 3. PERBAIKAN UTAMA: Berikan durasi penuh sepanjang rentang kata hidup (bukan per frame mikro)
            frame_clip = (ImageClip(rgb_array)
                          .with_start(word_start)
                          .with_duration(duration_per_word)
                          .with_position(('center', 'center')))
            
            # Suntikkan topeng transparansi (mask)
            mask_clip = ImageClip(alpha_array, is_mask=True).with_duration(duration_per_word)
            frame_clip.mask = mask_clip

            clips.append(frame_clip)

        return clips
