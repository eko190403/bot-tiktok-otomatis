import asyncio
import edge_tts

async def generate_voiceover_with_timestamps(hook: str, story: str, cta: str, audio_path: str, voice: str = "id-ID-ArdiNeural"):
    """
    Membuat audio menggunakan SSML Mark untuk mendapatkan stempel waktu 
    kata-per-kata yang presisi langsung dari stream tunggal Edge-TTS.
    """
    # 1. Bersihkan kata dan susun array kata global untuk pencocokan indeks event
    words_hook = hook.split()
    words_story = story.split()
    words_cta = cta.split()
    
    all_words = words_hook + words_story + words_cta
    
    # 2. Bangun teks berformat SSML dengan injeksi tag <mark> di setiap kata
    ssml_parts = []
    word_counter = 0
    
    # Bungkus bagian Hook
    ssml_parts.append("<p>")
    for word in words_hook:
        ssml_parts.append(f'<mark name="{word_counter}"/>{word}')
        word_counter += 1
    ssml_parts.append("</p>")
    
    # Bungkus bagian Story
    ssml_parts.append("<p>")
    for word in words_story:
        ssml_parts.append(f'<mark name="{word_counter}"/>{word}')
        word_counter += 1
    ssml_parts.append("</p>")
    
    # Bungkus bagian CTA
    ssml_parts.append("<p>")
    for word in words_cta:
        ssml_parts.append(f'<mark name="{word_counter}"/>{word}')
        word_counter += 1
    ssml_parts.append("</p>")
    
    ssml_string = f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='id-ID'><voice name='{voice}'>{' '.join(ssml_parts)}</voice></speak>"

    # 3. Eksekusi komunikasi stream tunggal dengan server Edge-TTS
    communicate = edge_tts.Communicate(ssml_string, voice)
    
    audio_data = bytearray()
    timestamps_result = []

    # PERBAIKAN TOTAL: Ambil data timing langsung dari chunk stream tanpa lewat objek submaker internal
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            # Offset dan duration dari Edge-TTS menggunakan satuan 100-nanodetik (10^-7 detik)
            start_sec = chunk["offset"] / 10000000.0
            duration_sec = chunk["duration"] / 10000000.0
            end_sec = start_sec + duration_sec
            word_text = chunk["text"]
            
            timestamps_result.append({
                "word": word_text,
                "start": start_sec,
                "end": end_sec
            })

    # Simpan data audio ke file
    with open(audio_path, "wb") as f:
        f.write(audio_data)

    # 4. Jaga-jaga jika ada ketidaksesuaian jumlah token akibat pembersihan karakter oleh TTS server
    if not timestamps_result:
        print("⚠️ Peringatan: Data timestamp kosong dari stream. Membuat fallback durasi linear...")
        # Fallback instan jika stream bermasalah agar pipeline tidak crash
        return [{"word": w, "start": 0.0, "end": 1.0} for w in words_hook], \
               [{"word": w, "start": 1.0, "end": 2.0} for w in words_story], \
               [{"word": w, "start": 2.0, "end": 3.0} for w in words_cta]

    # 5. Pisahkan kembali daftar timestamp ke dalam 3 segmen asli (Hook, Story, CTA)
    hook_clips_data = timestamps_result[0:len(words_hook)]
    story_clips_data = timestamps_result[len(words_hook):len(words_hook)+len(words_story)]
    cta_clips_data = timestamps_result[len(words_hook)+len(words_story):]

    return hook_clips_data, story_clips_data, cta_clips_data
