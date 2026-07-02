import os
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def generate_subtitle_clips(self, section_words: list, font_size: int, style_type: str = "body") -> list:
        """
        Subtitle Engine V3.9 (Progressive Caption): Merender kalimat utuh berkelanjutan
        dengan rantai durasi presisi agar visual menyatu natural dengan suara dubbing.
        """
        if not section_words:
            return []

        # MASALAH 3 FIX: Terapkan rumus Rantai Durasi (Chain-Timing) rekomendasi kamumu
        total_len = len(section_words)
        for i in range(total_len - 1):
            # Tahan visual kata aktif hingga 0.03 detik sebelum kata berikutnya muncul
            section_words[i]["end"] = section_words[i + 1]["start"] - 0.03
        
        # Berikan padding napas 0.15 detik untuk kata paling akhir di seksi tersebut
        section_words[-1]["end"] += 0.15

        clips = []

        # Loop untuk membuat potongan klip per kata aktif di dalam satu baris kalimat yang sama
        for i, item in enumerate(section_words):
            word_start = item["start"]
            word_duration = item["end"] - item["start"]
            
            if word_duration <= 0:
                word_duration = 0.20

            # Panggil renderer progresif (Kirim seluruh list kalimat dan berikan indeks kata aktif)
            frame = self.renderer.create_progressive_frame(
                words_list=section_words,
                active_index=i,
                font_path=FONT_PATH,
                font_size=font_size,
                style_type=style_type
            )
            
            img_rgba = np.array(frame.convert("RGBA"))
            
            # Letakkan klip secara absolut. Dimensi gambar sudah full 1080x1920 sehingga set posisinya (0,0)
            clip = (ImageClip(img_rgba, transparent=True)
                    .with_start(word_start)
                    .with_duration(word_duration)
                    .with_position((0, 0)))
            
            clips.append(clip)

        return clips
