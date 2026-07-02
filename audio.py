import asyncio
import edge_tts
import unicodedata
import string

async def generate_voiceover_with_timestamps(hook: str, story: str, cta: str, audio_path: str, voice: str = "id-ID-ArdiNeural"):
    """
    Membuat audio dari teks bersih dan menangkap timestamp kata-per-kata secara real-time.
    Seksi ditentukan menggunakan metode pencarian teks bersih (Anti-Overlapping Index).
    """
    full_clean_text = f"{hook}. {story} {cta}"
    communicate = edge_tts.Communicate(full_clean_text, voice)
    
    audio_data = bytearray()
    raw_timestamps = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            start_sec = chunk["offset"] / 10000000.0
            duration_sec = chunk["duration"] / 10000000.0
            end_sec = start_sec + duration_sec
            word_text = chunk["text"].strip()
            
            raw_timestamps.append({
                "word": word_text,
                "start": start_sec,
                "end": end_sec,
                "duration": duration_sec
            })

    with open(audio_path, "wb") as f:
        f.write(audio_data)

    cleaned_timestamps = []
    for item in raw_timestamps:
        raw_word = item["word"]
        
        cleaned_chars = []
        for ch in raw_word:
            cat = unicodedata.category(ch)
            if cat.startswith('L') or cat.startswith('N') or cat == 'Zs':
                cleaned_chars.append(ch)
        display_word = "".join(cleaned_chars).upper().strip()
        
        if display_word:
            cleaned_timestamps.append({
                "word": raw_word,          
                "display": display_word,    
                "start": item["start"],
                "end": item["end"],
                "duration": item["duration"]
            })

    if not cleaned_timestamps:
        return []

    # Normalisasi offset waktu
    first_offset = cleaned_timestamps[0]["start"]
    for item in cleaned_timestamps:
        item["start"] -= first_offset
        item["end"] -= first_offset

    # PERBAIKAN TOTAL: Segmentasi Berbasis Teks Bersih
    final_timestamps = []
    
    # Buat versi huruf kecil tanpa tanda baca untuk pencarian akurat
    def clean_str(t):
        return t.lower().translate(str.maketrans('', '', string.punctuation)).split()

    hook_words_list = clean_str(hook)
    story_words_list = clean_str(story)

    for item in cleaned_timestamps:
        word_clean = item["display"].lower()
        
        # Cek keberadaan kata di dalam teks aslinya secara berurutan
        if word_clean in hook_words_list:
            section = "hook"
            # Hapus kata yang sudah dipakai agar tidak tertukar jika ada kata kembar
            hook_words_list.remove(word_clean)
        elif word_clean in story_words_list:
            section = "story"
            story_words_list.remove(word_clean)
        else:
            section = "cta"
            
        final_timestamps.append({
            "word": item["word"],
            "display": item["display"],
            "start": item["start"],
            "end": item["end"],
            "duration": item["duration"],
            "section": section
        })

    return final_timestamps
