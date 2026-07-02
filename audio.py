import asyncio
import edge_tts
import unicodedata
import os
import tempfile
import logging
import librosa
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict

logger = logging.getLogger("video_pipeline")
TICKS_PER_SECOND = 10_000_000

# [DIAGNOSTIC & PHONETIC MAPS TETAP SAMA]
# ... (PHONETIC_DICTIONARY, WordTimestamp, SyncMetadata) ...

def get_audio_offset(audio_path: str, top_db: int = 25) -> float:
    """Deteksi silence di awal file audio."""
    try:
        y, sr = librosa.load(audio_path, sr=22050)
        non_silent = librosa.effects.split(y, top_db=top_db)
        if len(non_silent) > 0:
            return float(non_silent[0][0] / sr)
    except Exception as e:
        logger.error(f"Gagal deteksi offset: {e}")
    return 0.0

async def generate_voiceover_with_timestamps(hook: str, story: str, cta: str, audio_path: str, voice: str = "id-ID-ArdiNeural") -> Tuple[List[WordTimestamp], SyncMetadata]:
    """
    Generate audio + deterministik timing.
    Output: Timestamp yang sudah di-shift dengan offset audio.
    """
    full_clean_text = f"{hook} {story} {cta}"
    audio_data = bytearray()
    raw_boundaries = []

    # 1. GENERATE AUDIO
    try:
        communicate = edge_tts.Communicate(full_clean_text, voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                raw_boundaries.append({
                    "word": chunk["text"].strip(),
                    "start": chunk["offset"] / TICKS_PER_SECOND,
                    "duration": chunk["duration"] / TICKS_PER_SECOND
                })
    except Exception as e:
        raise RuntimeError(f"Edge-TTS Gagal: {e}")

    # 2. SAVE FILE
    with open(audio_path, "wb") as f:
        f.write(audio_data)

    # 3. DETEKSI MASTER OFFSET (Deterministic Anchor)
    # Ini adalah Single Source of Truth
    master_offset = get_audio_offset(audio_path)
    logger.info(f"Master Offset Terdeteksi: {master_offset:.4f}s")

    # 4. ALIGNMENT (Levenshtein Logic)
    # ... (Simpan logika DP/Levenshtein Anda di sini, ini sudah bagus) ...
    # Pastikan di akhir loop, saat membuat WordTimestamp:
    
    final_timestamps = []
    # ... saat membuat objek final_timestamps:
    for src in source_seq:
        # APLIKASIKAN SHIFT DI SINI
        start_shifted = max(0.0, src["start"] - master_offset)
        end_shifted = max(start_shifted + 0.1, src["end"] - master_offset)
        
        final_timestamps.append(
            WordTimestamp(
                word=src["word"], 
                display=src["display"],
                start=round(start_shifted, 3), 
                end=round(end_shifted, 3), 
                duration=src["duration"],
                section=section, 
                confidence=round(calculated_conf, 2)
            )
        )
        
    return final_timestamps, metadata
