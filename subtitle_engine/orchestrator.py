import os
import numpy as np
from PIL import Image
from moviepy import ImageClip, CompositeVideoClip
from subtitle_engine.renderer import SubtitleRenderer
from subtitle_engine.animation import SubtitleAnimator
from config import WIDTH, HEIGHT, FONT_PATH

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)
        self.animator = SubtitleAnimator()

    def generate_subtitle_clips(self, text: str, start_time: float, duration: float, font_size: int, style_type: str = "body", fps: int = 30) -> list:
        """
        Memecah kalimat menjadi rangkaian kata bertingkat (Karaoke Highlight + Pop Animation)
        dan mengembalikannya dalam bentuk list ImageClip MoviePy 2.x yang presisi.
        """
        words = text.upper().split()
        if not words:
            return []

        # Hitung durasi dasar penayangan per kata
        duration_per_word = duration / len(words)
        clips = []

        # Durasi animasi pembesaran pop (0.18 detik)
        animation_duration = 0.18

        for i, word in enumerate(words):
            word_start = start_time + (i * duration_per_word)
            
            # Rentang frame per kata berdasarkan FPS target
            total_frames = int(duration_per_word * fps)
            if total_frames <= 0:
                total_frames = 1
                
            frame_duration = 1.0 / fps

            # Buat susunan frame sekuensial untuk mengunci efek animasi
            for f in range(total_frames):
                current_frame_time = f * frame_duration
                
                # Hitung progress animasi (0.0 sampai 1.0 dalam jendela 0.18 detik)
                anim_progress = current_frame_time / animation_duration
                
                # 1. Render gambar dasar dari struktur teks penuh dengan highlight kata aktif
                base_frame = self.renderer.create_text_frame(
                    text=text,
                    current_word_index=i,
                    font_path=FONT_PATH,
                    font_size=font_size,
                    style_type=style_type
                )
                
                # 2. Suntikkan efek Pop Scale Animasi menggunakan Pillow jika masih dalam durasi pop
                animated_frame = self.animator.apply_pop_animation(base_frame, anim_progress)
                
                # 3. Konversi gambar Pillow RGBA menjadi matriks NumPy RGB + Alpha Mask untuk MoviePy 2.x
                img_rgba = animated_frame.convert("RGBA")
                img_array = np.array(img_rgba)
                
                rgb_array = img_array[:, :, :3]
                alpha_array = img_array[:, :, 3] / 255.0  # Normalisasi alpha ke skala 0.0 - 1.0

                # 4. Bangun ImageClip tunggal berdurasi mikro (1 frame) sesuai standar MoviePy 2.x
                frame_clip = (ImageClip(rgb_array)
                              .with_start(word_start + current_frame_time)
                              .with_duration(frame_duration)
                              .with_position(('center', 'center')))
                
                # Suntikkan topeng transparansi (mask) agar latar belakang video tembus pandang
                mask_clip = ImageClip(alpha_array, is_mask=True).with_duration(frame_duration)
                frame_clip.mask = mask_clip

                clips.append(frame_clip)

        return clips
