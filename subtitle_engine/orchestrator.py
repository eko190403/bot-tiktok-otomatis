import os
import copy
import numpy as np
from PIL import Image
from moviepy import ImageClip
from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

# CONFIGURATION ENGINE V5.0 (Bebas Magic Numbers)
DEBUG_SUBTITLE = False
MIN_WORD_DURATION = 0.15

# 1. Poin Prioritas 2 & 3: Threshold Jeda Alami Suara (Napas/Tanda Baca)
NATURAL_BREAK_THRESHOLD = 0.45  # Jeda > 0.45 detik dianggap baris baru (bukan max_words)

# 2. Poin Prioritas 3 & 4: Optimalisasi Offset & Hold Time
VISUAL_OFFSET = 0.040           # Subtitle muncul 40ms lebih awal sebelum suara (Mata siap)
PHRASE_HOLD_TIME = 0.250        # Tahan frasa 250ms setelah kata terakhir selesai

class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def _group_words_into_rhythm_phrases(self, words: list) -> list:
        """
        Rhythm Analyzer & Phrase Builder (V5.0): Memecah kelompok frasa 
        murni berdasarkan jeda napas/waktu hening asli, bukan jumlah kata kaku.
        """
        phrases = []
        current_phrase = []
        
        for idx, item in enumerate(words):
            word_text = item["word"]
            
            # Cek deteksi jeda hening alami (Napas) dari END kata ini ke START kata berikutnya
            is_natural_pause = False
            if idx < len(words) - 1:
                silence_delta = words[idx + 1]["start"] - item["end"]
                if silence_delta > NATURAL_BREAK_THRESHOLD:
                    is_natural_pause = True

            # Cek pemisahan kontekstual berdasarkan tanda baca asli
            is_punctuation_stop = word_text.endswith((".", "!", "?"))
            
            # Masukkan kata ke dalam antrean grup aktif saat ini
            current_phrase.append(item)
            
            # Jika terdeteksi nafas atau akhir kalimat, potong menjadi satu frasa utuh
            if (is_natural_pause or is_punctuation_stop) and idx < len(words) - 1:
                phrases.append(current_phrase)
                current_phrase = []
                
        if current_phrase:
            phrases.append(current_phrase)
        return phrases

    def generate_subtitle_clips(self, section_words: list, font_size: int, style_type: str = "body") -> list:
        """
        Subtitle Engine V5.0 (Timing Optimizer):
        Menerapkan koordinat waktu absolut berbasis durasi asli dan offset antisipasi.
        """
        if not section_words:
            return []

        # Duplikasi aman agar data asal di video_builder tidak termutasi
        raw_words = copy.deepcopy(section_words)
        
        # Pecah baris berdasarkan ritme ketukan suara (Bukan berdasarkan 4 kata lagi!)
        grouped_phrases = self._group_words_into_rhythm_phrases(raw_words)
        clips = []

        for p_idx, phrase in enumerate(grouped_phrases):
            phrase_len = len(phrase)
            if phrase_len == 0:
                continue

            # Tentukan batas waktu tampil total untuk kelompok frasa ini di layar
            # Frasa mulai dari kata pertama dikurangi offset visual (muncul duluan)
            phrase_display_start = max(0.0, phrase[0]["start"] - VISUAL_OFFSET)
            
            # Frasa berakhir setelah kata terakhir selesai ditambah waktu tahan (Hold Time)
            phrase_display_end = phrase[-1]["end"] + PHRASE_HOLD_TIME
            
            # Jika bukan frasa terakhir, jangan sampai menabrak batas frasa berikutnya
            if p_idx < len(grouped_phrases) - 1:
                next_phrase_start = grouped_phrases[p_idx + 1][0]["start"] - VISUAL_OFFSET
                phrase_display_end = min(phrase_display_end, next_phrase_start)

            # Hitung total durasi tayang block frasa utuh ini di layar
            phrase_total_duration = max(0.1, phrase_display_end - phrase_display_start)

            # Proses perancangan waktu highlight kata aktif secara internal di dalam frasa
            for i, item in enumerate(phrase):
                # Poin Prioritas 1: RUMUS EMAS DURATION ASLI (Display end mengikuti duration asli Edge-TTS)
                word_raw_duration = item["end"] - item["start"]
                
                # Gunakan durasi asli, jika terlalu pendek baru gunakan batas minimal aman
                word_duration_base = max(word_raw_duration, MIN_WORD_DURATION)
                
                # Hitung kapan sorotan kuning aktif dimulai dan berakhir (Disuntik offset awal)
                highlight_start = max(phrase_display_start, item["start"] - VISUAL_OFFSET)
                highlight_end = item["start"] - VISUAL_OFFSET + word_duration_base
                
                # Khusus untuk kata terakhir di dalam frasa, tahan warna aktifnya hingga frasa selesai/hilang
                if i == phrase_len - 1:
                    highlight_end = phrase_display_end
                else:
                    # Cegah highlight kata menabrak batas waktu start kata berikutnya
                    next_word_target_start = phrase[i + 1]["start"] - VISUAL_OFFSET
                    highlight_end = min(highlight_end, next_word_target_start)

                word_clip_duration = max(MIN_WORD_DURATION, highlight_end - highlight_start)

                if DEBUG_SUBTITLE:
                    print(f"📌 [Engine V5.0]: {item['word']} | Tampil: {highlight_start:.2f}s | Durasi: {word_clip_duration:.2f}s")

                # Panggil renderer progresif (Kirim seluruh list frasa dan tandai indeks yang aktif)
                frame = self.renderer.create_progressive_frame(
                    words_list=phrase,
                    active_index=i,
                    font_path=FONT_PATH,
                    font_size=font_size,
                    style_type=style_type
                )
                
                img_rgba = np.array(frame.convert("RGBA"))
                
                # PERBAIKAN POIN PRIORITAS 5: Hapus .fade_in() total untuk menjamin perubahan instans karaoke!
                clip = (ImageClip(img_rgba)
                        .with_start(highlight_start)
                        .with_duration(word_clip_duration)
                        .with_position((0, 0)))
                
                clips.append(clip)

        # Bersihkan seluruh memori cache setelah seksi selesai agar RAM lega
        self.renderer.clear_cache()
        return clips
