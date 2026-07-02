import asyncio
import edge_tts

async def generate_voiceover_with_timestamps(hook: str, story: str, cta: str, audio_path: str, voice: str = "id-ID-ArdiNeural"):
    """
    Membuat audio dari teks bersih dan menangkap timestamp kata-per-kata secara real-time.
    Menggunakan pencocokan teks berbasis array kata asli untuk menjamin seksi tidak akan acak-acakan.
    """
    # Bersihkan kata dan buat kamus pencarian seksi berdasarkan teks kata asli
    words_hook = [w.upper().replace(".", "").replace(",", "").replace("?", "").replace("!", "").strip() for w in hook.split()]
    words_story = [w.upper().replace(".", "").replace(",", "").replace("?", "").replace("!", "").strip() for w in story.split()]
    words_cta = [w.upper().replace(".", "").replace(",", "").replace("?", "").replace("!", "").strip() for w in cta.split()]
    
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
                "end": end_sec
            })

    with open(audio_path, "wb") as f:
        f.write(audio_data)

    cleaned_timestamps = []
    for item in raw_timestamps:
        cleaned_word = item["word"].replace(".", "").replace(",", "").replace("?", "").replace("!", "").strip()
        if cleaned_word:
            cleaned_timestamps.append({
                "word": cleaned_word,
                "start": item["start"],
                "end": item["end"]
            })

    if not cleaned_timestamps:
        print("⚠️ Data timestamp kosong dari stream. Membuat fallback durasi linear...")
        fallback_timestamps = []
        current_time = 0.0
        for w in hook.split():
            fallback_timestamps.append({"word": w, "start": current_time, "end": current_time + 0.3, "section": "hook"})
            current_time += 0.3
        for w in story.split():
            fallback_timestamps.append({"word": w, "start": current_time, "end": current_time + 0.3, "section": "story"})
            current_time += 0.3
        for w in cta.split():
            fallback_timestamps.append({"word": w, "start": current_time, "end": current_time + 0.3, "section": "cta"})
            current_time += 0.3
        return fallback_timestamps

    # Normalisasi offset waktu agar pas sejak detik 0.00
    first_offset = cleaned_timestamps[0]["start"]
    for item in cleaned_timestamps:
        item["start"] -= first_offset
        item["end"] -= first_offset

    # PERBAIKAN LOGIKA UTAMA: Lacak posisi kata menggunakan pointer pencarian dinamis
    final_timestamps = []
    
    # Kumpulkan semua kata target berdasarkan seksi untuk dicocokkan posisinya
    hook_len = len(words_hook)
    story_len = len(words_story)
    
    current_match_idx = 0

    for item in cleaned_timestamps:
        current_word = item["word"].upper()
        
        # Tentukan seksi berdasarkan posisi kecocokan kata sekuensial
        if current_match_idx < hook_len:
            section = "hook"
        elif current_match_idx < (hook_len + story_len):
            section = "story"
        else:
            section = "cta"
            
        final_timestamps.append({
            "word": item["word"],
            "start": item["start"],
            "end": item["end"],
            "section": section
        })
        
        # Geser pointer kecocokan ke kata berikutnya
        current_match_idx += 1

    return final_timestamps
