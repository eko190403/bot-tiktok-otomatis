import asyncio
import edge_tts
import unicodedata

async def generate_voiceover_with_timestamps(hook: str, story: str, cta: str, audio_path: str, voice: str = "id-ID-ArdiNeural"):
    """
    Membuat audio dari teks bersih dan menangkap timestamp kata-per-kata secara real-time.
    Mengalokasikan display_word bersih sejak awal untuk mengeliminasi pemanggilan berulang di renderer.
    """
    words_hook = hook.split()
    words_story = story.split()
    words_cta = cta.split()
    
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

    # PEMBERSIHAN DINI: Buat properti "display" bersih universal sejak awal (Poin 2 Fix)
    cleaned_timestamps = []
    for item in raw_timestamps:
        raw_word = item["word"]
        
        # Saring karakter non-huruf/non-angka menggunakan Unicode Category
        cleaned_chars = []
        for ch in raw_word:
            cat = unicodedata.category(ch)
            if cat.startswith('L') or cat.startswith('N') or cat == 'Zs':
                cleaned_chars.append(ch)
        display_word = "".join(cleaned_chars).upper().strip()
        
        if display_word:
            cleaned_timestamps.append({
                "word": raw_word,          # Dipertahankan untuk pengecekan tanda baca frasa
                "display": display_word,    # Teks visual super bersih siap pakai untuk renderer
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

    # Pemetaan seksi sekuensial
    final_timestamps = []
    limit_hook = len(words_hook)
    limit_story = limit_hook + len(words_story)

    for idx, item in enumerate(cleaned_timestamps):
        if idx < limit_hook:
            section = "hook"
        elif idx < limit_story:
            section = "story"
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
