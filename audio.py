import asyncio
import edge_tts

async def generate_voiceover_with_timestamps(hook: str, story: str, cta: str, audio_path: str, voice: str = "id-ID-ArdiNeural"):
    """
    Membuat audio dari teks bersih dan menangkap timestamp kata-per-kata secara real-time.
    Menggunakan pendekatan satu list dengan penanda seksi untuk akurasi 100%.
    """
    # Pecah kata dari naskah asli untuk penandaan seksi
    words_hook = hook.split()
    words_story = story.split()
    words_cta = cta.split()
    
    # Gabungkan menjadi kalimat polos untuk dibaca alami oleh TTS
    full_clean_text = f"{hook}. {story} {cta}"

    # Kirim ke server Edge-TTS
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

    # Filter tanda baca dari hasil stream boundary
    cleaned_timestamps = []
    for item in raw_timestamps:
        cleaned_word = item["word"].replace(".", "").replace(",", "").replace("?", "").replace("!", "").strip()
        if cleaned_word:
            cleaned_timestamps.append({
                "word": cleaned_word,
                "start": item["start"],
                "end": item["end"]
            })

    # MASALAH 2 FIX: Normalisasi offset waktu agar dimulai tepat dari 0.00
    if cleaned_timestamps:
        first_offset = cleaned_timestamps[0]["start"]
        for item in cleaned_timestamps:
            item["start"] -= first_offset
            item["end"] -= first_offset

    # MASALAH 1 & RECOMMENDED FIX: Petakan seksi secara sekuensial berdasarkan urutan kata asli
    final_timestamps = []
    total_generated = len(cleaned_timestamps)
    
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
