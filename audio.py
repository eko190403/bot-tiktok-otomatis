import asyncio
import edge_tts

async def generate_voiceover_with_timestamps(hook: str, story: str, cta: str, audio_path: str, voice: str = "id-ID-ArdiNeural"):
    """
    Membuat audio dari teks bersih dan menangkap timestamp kata-per-kata secara real-time.
    Dilengkapi proteksi mutlak jika stream data WordBoundary kosong agar tidak memicu eror max().
    """
    words_hook = hook.split()
    words_story = story.split()
    words_cta = cta.split()
    
    full_clean_text = f"{hook}. {story} {cta}"

    communicate = edge_tts.Communicate(full_clean_text, voice)
    
    audio_data = bytearray()
    raw_timestamps = []

    # Konsumsi stream tunggal
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

    # Simpan file audio mentah
    with open(audio_path, "wb") as f:
        f.write(audio_data)

    # Filter tanda baca
    cleaned_timestamps = []
    for item in raw_timestamps:
        cleaned_word = item["word"].replace(".", "").replace(",", "").replace("?", "").replace("!", "").strip()
        if cleaned_word:
            cleaned_timestamps.append({
                "word": cleaned_word,
                "start": item["start"],
                "end": item["end"]
            })

    # PERBAIKAN UTAMA: Validasi langsung di awal. Jika kosong, langsung kembalikan data fallback linear.
    if not cleaned_timestamps:
        print("⚠️ Data timestamp kosong dari stream. Membuat fallback durasi linear...")
        fallback_timestamps = []
        
        # Buat estimasi run-time linear sederhana berdasarkan panjang kata agar aman
        current_time = 0.0
        for w in words_hook:
            fallback_timestamps.append({"word": w, "start": current_time, "end": current_time + 0.3, "section": "hook"})
            current_time += 0.3
        for w in words_story:
            fallback_timestamps.append({"word": w, "start": current_time, "end": current_time + 0.3, "section": "story"})
            current_time += 0.3
        for w in words_cta:
            fallback_timestamps.append({"word": w, "start": current_time, "end": current_time + 0.3, "section": "cta"})
            current_time += 0.3
            
        return fallback_timestamps

    # Normalisasi offset waktu (Masalah 2 Fix)
    first_offset = cleaned_timestamps[0]["start"]
    for item in cleaned_timestamps:
        item["start"] -= first_offset
        item["end"] -= first_offset

    # Pemetaan seksi sekuensial (Masalah 1 Fix)
    final_timestamps = []
    idx_hook = len(words_hook)
    idx_story = idx_hook + len(words_story)

    for idx, item in enumerate(cleaned_timestamps):
        if idx < idx_hook:
            section = "hook"
        elif idx < idx_story:
            section = "story"
        else:
            section = "cta"
            
        final_timestamps.append({
            "word": item["word"],
            "start": item["start"],
            "end": item["end"],
            "section": section
        })

    return final_timestamps
