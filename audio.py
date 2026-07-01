import asyncio
import edge_tts
from edge_tts import SubMaker

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
    submaker = SubMaker()
    
    audio_data = bytearray()

    # PERBAIKAN UTAMA: Konsumsi stream hanya SEKALI. Kumpulkan data audio dan data timing bersamaan.
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            submaker.create_sub((chunk["offset"], chunk["duration"]), chunk["text"])

    # Simpan kumpulan buffer audio mentah ke dalam file tujuan
    with open(audio_path, "wb") as f:
        f.write(audio_data)

    # 4. Konversi data SubMaker menjadi struktur data list timestamp absolut
    timestamps_result = []
    for event in submaker.events:
        start_sec = event.start.total_seconds()
        end_sec = event.end.total_seconds()
        word_text = event.value
        
        timestamps_result.append({
            "word": word_text,
            "start": start_sec,
            "end": end_sec
        })

    # 5. Pisahkan kembali daftar timestamp ke dalam 3 segmen asli (Hook, Story, CTA)
    hook_clips_data = timestamps_result[0:len(words_hook)]
    story_clips_data = timestamps_result[len(words_hook):len(words_hook)+len(words_story)]
    cta_clips_data = timestamps_result[len(words_hook)+len(words_story):]

    return hook_clips_data, story_clips_data, cta_clips_data
