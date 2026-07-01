import asyncio
import edge_tts

async def generate_voiceover_with_timestamps(hook: str, story: str, cta: str, audio_path: str, voice: str = "id-ID-ArdiNeural"):
    """
    Membuat audio dari teks bersih murni dan menangkap timestamp 
    kata-per-kata secara real-time langsung dari event WordBoundary bawaan.
    """
    # 1. Bersihkan kata untuk kebutuhan pemisahan array indeks nanti
    words_hook = hook.split()
    words_story = story.split()
    words_cta = cta.split()
    
    # Gabungkan menjadi satu kalimat polos utuh agar dibaca natural oleh TTS
    full_clean_text = f"{hook}. {story} {cta}"

    # 2. Kirim teks bersih murni ke server Edge-TTS (Tanpa SSML)
    communicate = edge_tts.Communicate(full_clean_text, voice)
    
    audio_data = bytearray()
    raw_timestamps = []

    # 3. Konsumsi stream tunggal: Kumpulkan audio dan catat data timing kata asli
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            # Konversi satuan waktu dari server ke detik desimal
            start_sec = chunk["offset"] / 10000000.0
            duration_sec = chunk["duration"] / 10000000.0
            end_sec = start_sec + duration_sec
            word_text = chunk["text"].strip()
            
            raw_timestamps.append({
                "word": word_text,
                "start": start_sec,
                "end": end_sec
            })

    # Simpan data audio murni ke file temp
    with open(audio_path, "wb") as f:
        f.write(audio_data)

    # 4. Filter dan bersihkan data timestamp dari noise karakter kosong atau tanda baca
    timestamps_result = []
    for item in raw_timestamps:
        cleaned_word = item["word"].replace(".", "").replace(",", "").replace("?", "").replace("!", "").strip()
        if cleaned_word:
            timestamps_result.append({
                "word": cleaned_word,
                "start": item["start"],
                "end": item["end"]
            })

    # 5. Jika pembacaan gagal/kosong, buatkan penanganan cadangan linear agar tidak crash
    if not timestamps_result:
        print("⚠️ Data timestamp kosong. Menggunakan pembagian linear...")
        return [{"word": w, "start": 0.0, "end": 1.0} for w in words_hook], \
               [{"word": w, "start": 1.0, "end": 2.0} for w in words_story], \
               [{"word": w, "start": 2.0, "end": 3.0} for w in words_cta]

    # 6. Distribusikan stempel waktu secara presisi berdasarkan pembagian jumlah kata asli segmen
    hook_clips_data = timestamps_result[0:len(words_hook)]
    story_clips_data = timestamps_result[len(words_hook):len(words_hook)+len(words_story)]
    cta_clips_data = timestamps_result[len(words_hook)+len(words_story):]

    return hook_clips_data, story_clips_data, cta_clips_data
