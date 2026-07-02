import copy
import numpy as np
from moviepy import ImageClip

from subtitle_engine.renderer import SubtitleRenderer
from config import WIDTH, HEIGHT, FONT_PATH

MAX_WORDS_PHRASE = 4
MAX_CHARS_PHRASE = 28
NATURAL_GAP_LIMIT = 0.40


class SubtitleEngineV2:
    def __init__(self):
        self.renderer = SubtitleRenderer(width=WIDTH, height=HEIGHT)

    def _group_words_into_rhythm_phrases(self, words: list) -> list:
        phrases = []
        current_phrase = []
        current_char_count = 0

        for idx, item in enumerate(words):
            word_text = item["word"]
            current_phrase.append(item)
            current_char_count += len(word_text) + 1

            is_natural_pause = False
            if idx < len(words) - 1:
                gap = words[idx + 1]["start"] - item["start"]
                if gap > (item["duration"] + NATURAL_GAP_LIMIT):
                    is_natural_pause = True

            is_punctuation_split = False
            if word_text.endswith((".", "!", "?")):
                is_punctuation_split = True
            elif word_text.endswith((",", ";", ":")) and len(current_phrase) >= 2:
                is_punctuation_split = True

            should_split = (
                len(current_phrase) >= MAX_WORDS_PHRASE
                or current_char_count >= MAX_CHARS_PHRASE
                or is_natural_pause
                or is_punctuation_split
            )

            if should_split:
                phrases.append(current_phrase)
                current_phrase = []
                current_char_count = 0

        if current_phrase:
            phrases.append(current_phrase)

        return phrases

    def generate_subtitle_clips(
        self,
        section_words: list,
        font_size: int,
        style_type: str = "body",
    ) -> list:

        if not section_words:
            return []

        grouped_phrases = self._group_words_into_rhythm_phrases(
            copy.deepcopy(section_words)
        )

        clips = []

        for p_idx, phrase in enumerate(grouped_phrases):

            avg_duration = sum(w["duration"] for w in phrase) / len(phrase)

            visual_offset = min(0.05, avg_duration * 0.20)
            hold_padding = 0.25

            phrase_end = phrase[-1]["end"] + hold_padding

            if p_idx < len(grouped_phrases) - 1:
                next_start = grouped_phrases[p_idx + 1][0]["start"] - visual_offset
                phrase_end = min(phrase_end, next_start)

            for i, item in enumerate(phrase):

                highlight_start = max(
                    0,
                    item["start"] - visual_offset,
                )

                if i == len(phrase) - 1:
                    highlight_end = phrase_end
                else:
                    highlight_end = min(
                        item["end"],
                        phrase[i + 1]["start"] - visual_offset,
                    )

                duration = max(0.15, highlight_end - highlight_start)

                frame, bbox_w, bbox_h = self.renderer.create_progressive_frame(
                    words_list=phrase,
                    active_index=i,
                    font_path=FONT_PATH,
                    font_size=font_size,
                    scale_factor=1.10,
                    style_type=style_type,
                )

                img = np.array(frame.convert("RGBA"))

                pos_x = (WIDTH - bbox_w) // 2
                pos_y = int(HEIGHT * 0.70) - (bbox_h // 2)

                clip = (
                    ImageClip(img)
                    .with_start(highlight_start)
                    .with_duration(duration)
                    .with_position((pos_x, pos_y))
                )

                clips.append(clip)

        self.renderer.clear_cache()
        return clips                        .with_start(highlight_start)
                        .with_duration(word_total_duration)
                        .with_position((pos_x, pos_y)))
                clips.append(clip)

        self.renderer.clear_cache()
        return clips
                        .with_start(highlight_start)
                        .with_duration(word_total_duration)
                        .with_position((pos_x, pos_y)))
                clips.append(clip)

        self.renderer.clear_cache()
        return clips
        self.renderer.clear_cache()
        return clips
                        
                        clip = (ImageClip(img_rgba)
                                .with_start(current_time_pointer)
                                .with_duration(frame_time)
                                .with_position((0, 0)))
                        clips.append(clip)
                        current_time_pointer += frame_time
                
                remaining_duration = highlight_end - current_time_pointer
                if remaining_duration > 0:
                    frame = self.renderer.create_progressive_frame(
                        words_list=phrase, active_index=i, font_path=FONT_PATH,
                        font_size=font_size, scale_factor=1.10, style_type=style_type
                    )
                    img_rgba = np.array(frame.convert("RGBA"))
                    
                    clip = (ImageClip(img_rgba)
                            .with_start(current_time_pointer)
                            .with_duration(remaining_duration)
                            .with_position((0, 0)))
                    clips.append(clip)

        self.renderer.clear_cache()
        return clips
