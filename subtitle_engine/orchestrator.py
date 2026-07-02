import os
import copy
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def _group_words_into_phrases(self, words: list, max_words: int = 4, max_chars: int = 32) -> list:
        """
        EVALUASI 6 & 10: Memotong list WordBoundary panjang menjadi kelompok frasa pendek (Phrase Grouper)[cite: 62, 63, 64, 194].
        """
        phrases = []
        current_phrase = []
        current_char_count = 0

        for item in words:
            word_len = len(item["word"])
            # Jika grup sudah menyentuh batas kata atau batas karakter, kunci grup tersebut [cite: 63, 64]
            if len(current_phrase) >= max_words or (current_char_count + word_len > max_chars and current_phrase):
                phrases.append(current_phrase)
                current_phrase = []
                current_char_count = 0
            
            current_phrase.append(item)
            current_char_count += word_len + 1
            
        if current_phrase:
            phrases.append(current_phrase)
        return phrases

    def generate_subtitle_clips(self, section_words: list, font_size: int, style_type: str = "body") -> list:
        """
        Subtitle Engine V4.5: Memisahkan tanggung jawab penataan waktu grup frasa pendek.
        """
        if not section_words:
            return []

        # EVALUASI 1: Lakukan deepcopy agar data asal tidak bermutasi bebas [cite: 1]
        raw_words = copy.deepcopy(section_words)
        
        # Pecah kata menjadi kelompok frasa pendek (TikTok Style) [cite: 67]
        grouped_phrases = self._group_words_into_phrases(raw_words, max_words=4, max_chars=30)
        
        # EVALUASI 3: Atur padding akhir adaptif berdasarkan tipe seksi agar fleksibel [cite: 36, 37]
        if style_type == "cta":
            last_padding = 0.30
        elif style_type == "hook":
            last_padding = 0.15
        else:
            last_padding = 0.20

        clips = []

        # Proses rantai waktu per grup frasa
        for phrase in grouped_phrases:
            phrase_len = len(phrase)
            
            # Bangun koordinat rantai waktu internal grup
            for i in range(phrase_len - 1):
                # EVALUASI 2: Buat gap adaptif proporsional terhadap kecepatan ketukan kata (Anti-Negatif) [cite: 12, 25, 26]
                gap = min(0.03, (phrase[i+1]["start"] - phrase[i]["start"]) * 0.4) [cite: 14, 25]
                phrase[i]["end"] = phrase[i + 1]["start"] - gap [cite: 25]
            
            # Berikan padding pada kata terakhir di frasa ini
            phrase[-1]["end"] += last_padding

            # Render frame karaoke progresif untuk kata aktif di dalam grup frasa ini
            for i, item in enumerate(phrase):
                word_start = item["start"]
                word_duration = max(item["end"] - item["start"], 0.15) # Batas aman durasi minimal [cite: 22]
                
                # EVALUASI 5 DEBUG: Cetak data sinkronisasi ke log GitHub Actions untuk kemudahan pelacakan [cite: 50, 51]
                print(f"📌 Sub V4.5 [{style_type.upper()}]: {item['word']} | {word_start:.2f}s - {word_start+word_duration:.2f}s") [cite: 52]

                frame = self.renderer.create_progressive_frame(
                    words_list=phrase,
                    active_index=i,
                    font_path=FONT_PATH,
                    font_size=font_size,
                    style_type=style_type
                )
                
                img_rgba = np.array(frame.convert("RGBA"))
                
                # Gunakan .subclipped() jika memakai MoviePy 2.x, hapus .fade_in jika memicu error runtime [cite: 3, 10]
                clip = (ImageClip(img_rgba)
                        .with_start(word_start)
                        .with_duration(word_duration)
                        .with_position((0, 0)))
                
                clips.append(clip)

        # Bersihkan cache render setelah satu seksi video selesai dikerjakan agar RAM tetap lega [cite: 124]
        self.renderer.clear_cache()
        return clips
