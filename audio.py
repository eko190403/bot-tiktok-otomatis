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

PHONETIC_DICTIONARY = {
    "NGGAK": "TIDAK", "NGAK": "TIDAK", "GAK": "TIDAK", "ENGGAK": "TIDAK",
    "TAU": "TAHU", "GITU": "BEGITU", "UDAH": "SUDAH", "TDK": "TIDAK",
    "DGN": "DENGAN", "YG": "YANG", "KRNA": "KARENA", "KARNA": "KARENA"
}

@dataclass(slots=True)
class WordTimestamp:
    word: str
    display: str
    start: float
    end: float
    duration: float
    section: str
    confidence: float

@dataclass(slots=True)
class SyncMetadata:
    matched: int
    total: int
    accuracy: float
    missed: int
    failed_tokens: list

# --- CORE HELPERS ---

def get_audio_offset(audio_path: str, top_db: int = 25) -> float:
    """Mendeteksi silence di awal file audio sebagai Master Anchor."""
    try:
        y, sr = librosa.load(audio_path, sr=22050)
        non_silent = librosa.effects.split(y, top_db=top_db)
        if len(non_silent) > 0:
            offset = float(non_silent[0][0] / sr)
            logger.info(f"🎯 Master Offset Detected: {offset:.4f}s")
            return offset
    except Exception as e:
        logger.error(f"Gagal deteksi offset: {e}")
    return 0.0

def lockdown_timeline(timestamps: List[WordTimestamp], audio_duration: float) -> List[WordTimestamp]:
    """Mengunci timeline agar tidak tumpang tindih dan tidak overflow."""
    timestamps.sort(key=lambda x: x.start)
    clamped = []
    
    for i, ts in enumerate(timestamps):
        # 1. Mencegah overlap (geser start jika bentrok dengan prev)
        if i > 0 and ts.start < clamped[-1].end:
            ts.start = clamped[-1].end
            
        # 2. Mencegah overflow (potong end agar tidak lebih dari audio)
        if ts.end > audio_duration:
            ts.end = audio_duration
            
        # 3. Mencegah durasi nol/negatif
        if ts.end - ts.start < 0.1:
            ts.end = ts.start + 0.1
            
        clamped.append(ts)
    return clamped

# --- PIPELINE ---

async def generate_voiceover_with_timestamps(hook: str, story: str, cta: str, audio_path: str, voice: str = "id-ID-ArdiNeural") -> Tuple[List[WordTimestamp], SyncMetadata]:
    full_clean_text = f"{hook} {story} {cta}"
    audio_data = bytearray()
    raw_boundaries = []

    # 1. GENERATE AUDIO VIA EDGE-TTS
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
    master_offset = get_audio_offset(audio_path)
    
    # [SISIPKAN LOGIKA ALIGNMENT DP DI SINI - Disesuaikan dengan kode DP Anda sebelumnya]
    # Pastikan source_seq dan target_seq sudah terdefinisi.
    # ... (DP Alignment Loop) ...
    
    # 4. FINAL TIMESTAMP PROCESSING
    final_timestamps = []
    # Mengambil durasi total audio untuk Lockdown
    audio_duration = librosa.get_duration(path=audio_path)
    
    for src in source_seq:
        # A. SHIFT BERDASARKAN MASTER OFFSET
        s_shifted = max(0.0, src["start"] - master_offset)
        e_shifted = max(s_shifted + 0.1, src["end"] - master_offset)
        
        # B. MEMBUAT DATACLASS
        final_timestamps.append(
            WordTimestamp(
                word=src["word"], 
                display=src["display"],
                start=round(s_shifted, 3), 
                end=round(e_shifted, 3), 
                duration=src["duration"],
                section=src.get("section", "story"), # Pastikan section terpetakan
                confidence=round(src.get("confidence", 0.0), 2)
            )
        )

    # 5. LOCKDOWN (Enforce Consistency)
    final_timestamps = lockdown_timeline(final_timestamps, audio_duration)
    
    # 6. METADATA
    # ... (Hitung matched_count, accuracy, dll) ...
    metadata = SyncMetadata(matched=matched_count, total=M, accuracy=accuracy, missed=M-matched_count, failed_tokens=[])
        
    return final_timestamps, metadata
