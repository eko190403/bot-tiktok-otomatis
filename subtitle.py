import os
from moviepy import TextClip
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
    
    if style == "hook":
        font_size = FONT_SIZE_HOOK
        color = "orange"
    elif style == "cta":
        font_size = FONT_SIZE_BODY
        color = "cyan"
    else:
        font_size = FONT_SIZE_BODY
        color = "white"

    for i, chunk in enumerate(chunks):
        current_start = start_time + (i * chunk_duration)
        
        current_color = color
        if style == "body" and i % 2 == 0:
            current_color = "yellow"

        # PERBAIKAN: Menentukan ukuran tinggi bounding box pasti (font_size * 2) 
        # agar stroke tebal hitam di atas/bawah tidak tercekik dan terpotong.
        box_width = WIDTH - 150
        box_height = int(font_size * 2)

        txt_clip = TextClip(
            text=chunk, 
            font=FONT_PATH, 
            font_size=font_size, 
            color=current_color,
            stroke_color="black", 
            stroke_width=STROKE_WIDTH, 
            method="caption", 
            size=(box_width, box_height)
        )
        
        # Penyelarasan timeline & posisi vertikal tengah video
        txt_clip = (txt_clip
                    .with_start(current_start)
                    .with_duration(chunk_duration)
                    .with_position(('center', HEIGHT * 0.45)))
        
        clips.append(txt_clip)
        
    return clips
