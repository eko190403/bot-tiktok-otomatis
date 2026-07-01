import os
from moviepy.editor import TextClip
from config import FONT_PATH, FONT_SIZE_HOOK, FONT_SIZE_BODY, STROKE_WIDTH, WIDTH, HEIGHT

def split_text_into_chunks(text: str, max_words: int = 3) -> list:
    """Memecah kalimat panjang menjadi potongan pendek (khas TikTok)."""
    words = text.upper().split()
    chunks = []
    current_chunk = []
    
    for word in words:
        current_chunk.append(word)
        if len(current_chunk) >= max_words:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

def render_subtitles_for_section(text: str, start_time: float, duration: float, style: str = "body") -> list:
    """Membuat daftar objek TextClip berdurasi presisi untuk satu segmen video."""
    chunks = split_text_into_chunks(text)
    if not chunks:
        return []
        
    chunk_duration = duration / len(chunks)
    clips = []
    
    # Konfigurasi style teks berdasarkan segmen
    if style == "hook":
        font_size = FONT_SIZE_HOOK
        color = "orange"
    elif style == "cta":
        font_size = FONT_SIZE_BODY
        color = "cyan"
    else:
        font_size = FONT_SIZE_BODY
        color = "white" # Nanti bisa dibuat selang-seling putih/kuning di loop

    for i, chunk in enumerate(chunks):
        current_start = start_time + (i * chunk_duration)
        current_end = start_time + ((i + 1) * chunk_duration)
        
        # Variasi warna selang-seling khusus untuk isi cerita (Story)
        current_color = color
        if style == "body" and i % 2 == 0:
            current_color = "yellow"

        txt_clip = TextClip(
            chunk, 
            font=FONT_PATH, 
            fontsize=font_size, 
            color=current_color,
            stroke_color="black", 
            stroke_width=STROKE_WIDTH, 
            method="caption", 
            size=(WIDTH - 150, None)
        )
        
        # Mengatur timing dan posisi text clip (MoviePy 2.x)
        txt_clip = txt_clip.set_start(current_start).set_end(current_end).set_position(('center', HEIGHT * 0.45))
        clips.append(txt_clip)
        
    return clips
