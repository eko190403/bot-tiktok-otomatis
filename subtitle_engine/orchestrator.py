import os
import copy
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

# EVALUASI 7: Taruh variabel konfigurasi di atas (Jangan di-hardcode)
CHAIN_GAP = 0.03
MIN_DURATION = 0.15
LAST_WORD_PADDING = 0.25

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def generate_subtitle_clips(self, section_words: list, font_size: int, style_type: str = "body") -> list:
        """
        Subtitle Engine V4.2 (Orchestrator Clean Integration):
        Memproses duplikasi list aman, penahan durasi minimal, dan transisi fade halus.
        """
        if not section_words:
            return []

        # EVALUASI 1: Lakukan deepcopy agar list asal tidak bermutasi/berubah di tempat lain
        words = copy.deepcopy(section_words)
        total_len = len(words)
        
        # Ikat rantai waktu berurutan
        for i in range(total_len - 1):
            words[i]["end"] = words[i + 1]["start"] - CHAIN_GAP
        
        # EVALUASI 6: Berikan padding waktu istirahat yang lebih longgar di akhir kalimat CTA
        words[-1]["end"] += LAST_WORD_PADDING

        clips = []

        for i, item in enumerate(words):
            word_start = item["start"]
            
            # EVALUASI 2: Amankan kalkulasi dari potensi durasi bernilai negatif menggunakan fungsi max()
            word_duration = max(item["end"] - item["start"], MIN_DURATION)
            
            frame = self.renderer.create_progressive_frame(
                words_list=words,
                active_index=i,
                font_path=FONT_PATH,
                font_size=font_size,
                style_type=style_type
            )
            
            img_rgba = np.array(frame.convert("RGBA"))
            
            # EVALUASI 8: MoviePy 2.x membaca channel alpha RGBA secara otomatis dari numpy array
            # EVALUASI 3 FADE: Suntikkan efek fade_in berdurasi 50ms agar perpindahan tidak kaku mendadak
            clip = (ImageClip(img_rgba)
                    .with_start(word_start)
                    .with_duration(word_duration)
                    .with_position((0, 0))
                    .fade_in(0.05))
            
            clips.append(clip)

        return clips
