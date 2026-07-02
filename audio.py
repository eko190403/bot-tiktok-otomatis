import asyncio
import edge_tts
import unicodedata
import re
import os
import tempfile
import logging
import difflib
import librosa
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

logger = logging.getLogger("video_pipeline")
TICKS_PER_SECOND = 10_000_000

PHONETIC_DICTIONARY = {
    "NGGAK": "TIDAK", "NGAK": "TIDAK", "GAK": "TIDAK", "ENGGAK": "TIDAK",
    "TAU": "TAHU", "GITU": "BEGITU", "UDAH": "SUDAH", "TDK": "TIDAK",
    "DGN": "DENGAN", "YG": "YANG", "KRNA": "KARENA", "KARNA": "KARENA"
}

# Bobot scoring untuk DP alignment (Needleman-Wunsch style)
MATCH_SCORE = 2
MISMATCH_PENALTY = -1
GAP_PENALTY = -2
FUZZY_MATCH_MIN_RATIO = 0.55  # di bawah ini dianggap gagal match sama sekali


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


# --- TOKENIZATION & NORMALIZATION HELPERS ---

def normalize_for_match(word: str) -> str:
    """Menyeragamkan kata untuk perbandingan: uppercase, buang tanda baca & diakritik."""
    w = unicodedata.normalize("NFKD", word)
    w = "".join(c for c in w if not unicodedata.combining(c))
    w = re.sub(r"[^\w]", "", w)
    return w.upper()


def apply_phonetic_dictionary(word: str) -> str:
    """Mengganti kata slang/singkatan dengan versi baku agar pelafalan TTS lebih jelas."""
    core = normalize_for_match(word)
    replacement = PHONETIC_DICTIONARY.get(core)
    if replacement is None:
        return word
    # Pertahankan tanda baca penutup (misal koma/titik) dari kata asli
    trailing_punct = re.search(r"[.,!?;:]+$", word)
    return replacement + (trailing_punct.group(0) if trailing_punct else "")


def tokenize_section(text: str, section: str) -> List[Dict]:
    """Memecah teks section menjadi token dengan versi display (asli) & spoken (fonetik)."""
    raw_tokens = text.split()
    tokens = []
    for w in raw_tokens:
        spoken = apply_phonetic_dictionary(w)
        tokens.append({"display": w, "spoken": spoken, "section": section})
    return tokens


def build_target_sequence(hook: str, story: str, cta: str) -> List[Dict]:
    return (
        tokenize_section(hook, "hook")
        + tokenize_section(story, "story")
        + tokenize_section(cta, "cta")
    )


# --- AUDIO HELPERS ---

def get_audio_offset(audio_path: str, top_db: int = 25) -> float:
    """Mendeteksi durasi leading silence di awal file audio (HANYA untuk logging/diagnostik)."""
    try:
        y, sr = librosa.load(audio_path, sr=22050)
        non_silent = librosa.effects.split(y, top_db=top_db)
        if len(non_silent) > 0:
            offset = float(non_silent[0][0] / sr)
            logger.info(f"🎯 Leading silence terdeteksi: {offset:.4f}s")
            return offset
    except Exception as e:
        logger.error(f"Gagal deteksi offset: {e}")
    return 0.0


def lockdown_timeline(timestamps: List[WordTimestamp], audio_duration: float) -> List[WordTimestamp]:
    """Mengunci timeline agar tidak tumpang tindih dan tidak overflow. Satu-satunya lapisan koreksi timing."""
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


def validate_timeline_invariants(
    timestamps: List[WordTimestamp],
    audio_duration: float,
    min_duration: float = 0.05,
    strict: bool = False,
) -> List[WordTimestamp]:
    """
    GERBANG TUNGGAL untuk menegakkan invariant timeline sebelum dipakai render.
    Ini satu-satunya tempat aturan berikut didefinisikan secara eksplisit:

      1. start monotonic non-decreasing antar kata berurutan
      2. end >= start + min_duration (tidak ada subtitle berdurasi nol/negatif)
      3. tidak ada overlap (start[i] >= end[i-1])
      4. semua end <= audio_duration (tidak overflow melewati panjang audio)

    Jika strict=False (default): pelanggaran dicatat sebagai warning lalu
    diperbaiki otomatis via lockdown_timeline().
    Jika strict=True: pelanggaran yang ditemukan langsung raise ValueError
    (dipakai kalau ingin fail-fast, misal saat testing/debugging).
    """
    violations = []
    for i, ts in enumerate(timestamps):
        if ts.end < ts.start + min_duration - 1e-6:
            violations.append(f"idx={i} ('{ts.display}'): end({ts.end}) < start({ts.start})+{min_duration}")
        if i > 0 and ts.start < timestamps[i - 1].end - 1e-6:
            violations.append(
                f"idx={i} ('{ts.display}'): overlap — start({ts.start}) < prev_end({timestamps[i - 1].end})"
            )
        if ts.end > audio_duration + 1e-3:
            violations.append(f"idx={i} ('{ts.display}'): end({ts.end}) > audio_duration({audio_duration})")

    if not violations:
        return timestamps

    summary = "; ".join(violations[:5]) + (f" ... (+{len(violations) - 5} lagi)" if len(violations) > 5 else "")
    msg = f"⚠️ {len(violations)} pelanggaran invariant timeline terdeteksi: {summary}"

    if strict:
        raise ValueError(msg)

    logger.warning(msg)
    fixed = lockdown_timeline(timestamps, audio_duration)

    # Verifikasi ulang sekali setelah auto-fix — kalau masih ada pelanggaran, itu bug baru.
    still_broken = [
        i for i, ts in enumerate(fixed)
        if ts.end < ts.start + min_duration - 1e-6
        or (i > 0 and ts.start < fixed[i - 1].end - 1e-6)
    ]
    if still_broken:
        logger.error(f"❌ Invariant MASIH dilanggar setelah auto-fix pada index: {still_broken}")

    return fixed


# --- DP ALIGNMENT (Needleman-Wunsch style global alignment) ---

def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def align_target_to_boundaries(
    target_tokens: List[Dict],
    boundaries: List[Dict],
) -> List[Tuple[Optional[int], Optional[int], float]]:
    """
    Global alignment antara target_tokens (kata spoken hasil script) dan
    boundaries (kata hasil ucapan nyata dari edge-tts WordBoundary).

    Return: list of (target_idx atau None, boundary_idx atau None, confidence)
    Setiap target_idx WAJIB muncul tepat sekali di hasil (baik ter-match maupun gap).
    """
    n = len(target_tokens)
    m = len(boundaries)

    target_norm = [normalize_for_match(t["spoken"]) for t in target_tokens]
    bound_norm = [normalize_for_match(b["word"]) for b in boundaries]

    # DP table: dp[i][j] = skor alignment terbaik antara target[:i] dan boundaries[:j]
    dp = np.zeros((n + 1, m + 1), dtype=np.float32)
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] + GAP_PENALTY
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] + GAP_PENALTY

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if target_norm[i - 1] == bound_norm[j - 1]:
                match_score = MATCH_SCORE
            else:
                sim = _similarity(target_norm[i - 1], bound_norm[j - 1])
                match_score = MATCH_SCORE * sim if sim >= FUZZY_MATCH_MIN_RATIO else MISMATCH_PENALTY

            diag = dp[i - 1][j - 1] + match_score
            up = dp[i - 1][j] + GAP_PENALTY      # target token tidak terucap (skip)
            left = dp[i][j - 1] + GAP_PENALTY    # boundary ekstra (noise TTS, di-skip)
            dp[i][j] = max(diag, up, left)

    # Backtrace
    alignment = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            sim = _similarity(target_norm[i - 1], bound_norm[j - 1])
            match_score = MATCH_SCORE if target_norm[i - 1] == bound_norm[j - 1] else (
                MATCH_SCORE * sim if sim >= FUZZY_MATCH_MIN_RATIO else MISMATCH_PENALTY
            )
            if abs(dp[i][j] - (dp[i - 1][j - 1] + match_score)) < 1e-6:
                confidence = 1.0 if target_norm[i - 1] == bound_norm[j - 1] else sim
                alignment.append((i - 1, j - 1, confidence))
                i -= 1
                j -= 1
                continue
        if i > 0 and (j == 0 or abs(dp[i][j] - (dp[i - 1][j] + GAP_PENALTY)) < 1e-6):
            alignment.append((i - 1, None, 0.0))
            i -= 1
            continue
        if j > 0:
            # boundary tanpa target -> dibuang, tidak masuk hasil
            j -= 1
            continue

    alignment.reverse()
    return alignment


def _interpolate_missing(final_timestamps: List[WordTimestamp], audio_duration: float) -> None:
    """Mengisi start/end untuk token yang gagal match (confidence 0) via interpolasi linear."""
    n = len(final_timestamps)
    for idx, ts in enumerate(final_timestamps):
        if ts.confidence > 0.0:
            continue

        # Cari anchor tervalid sebelum & sesudah
        prev_idx = idx - 1
        while prev_idx >= 0 and final_timestamps[prev_idx].confidence == 0.0:
            prev_idx -= 1
        next_idx = idx + 1
        while next_idx < n and final_timestamps[next_idx].confidence == 0.0:
            next_idx += 1

        prev_end = final_timestamps[prev_idx].end if prev_idx >= 0 else 0.0
        next_start = final_timestamps[next_idx].start if next_idx < n else audio_duration

        gap_span = max(next_start - prev_end, 0.1)
        # Bagi rata slot waktu antara anchor kiri & kanan untuk semua token gap di antaranya
        gap_indices = [k for k in range(prev_idx + 1, next_idx) if final_timestamps[k].confidence == 0.0]
        slot = gap_span / max(len(gap_indices), 1)

        for order, k in enumerate(gap_indices):
            start = prev_end + slot * order
            end = min(start + slot, audio_duration)
            if end - start < 0.05:
                end = start + 0.05
            final_timestamps[k].start = round(start, 3)
            final_timestamps[k].end = round(end, 3)
            final_timestamps[k].duration = round(end - start, 3)


# --- PIPELINE ---

async def generate_voiceover_with_timestamps(
    hook: str, story: str, cta: str, audio_path: str, voice: str = "id-ID-ArdiNeural"
) -> Tuple[List[WordTimestamp], SyncMetadata]:

    target_tokens = build_target_sequence(hook, story, cta)
    if not target_tokens:
        raise RuntimeError("Naskah kosong, tidak ada kata untuk disintesis.")

    spoken_text_for_tts = " ".join(t["spoken"] for t in target_tokens)

    audio_data = bytearray()
    raw_boundaries: List[Dict] = []

    # 1. GENERATE AUDIO VIA EDGE-TTS (memakai teks fonetik agar pelafalan jelas)
    try:
        communicate = edge_tts.Communicate(spoken_text_for_tts, voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                raw_boundaries.append({
                    "word": chunk["text"].strip(),
                    "start": chunk["offset"] / TICKS_PER_SECOND,
                    "duration": chunk["duration"] / TICKS_PER_SECOND,
                })
    except Exception as e:
        raise RuntimeError(f"Edge-TTS Gagal: {e}")

    if not audio_data:
        raise RuntimeError("Edge-TTS tidak menghasilkan data audio.")

    # 2. SAVE FILE (disimpan apa adanya, tanpa trimming — WordBoundary tetap valid terhadap file ini)
    with open(audio_path, "wb") as f:
        f.write(audio_data)

    # 3. DETEKSI LEADING SILENCE — HANYA UNTUK LOG/DIAGNOSTIK, TIDAK DIPAKAI UNTUK SHIFT
    #    (raw_boundaries sudah relatif terhadap audio_path yang sama persis,
    #     jadi timestamp-nya sudah otomatis benar, termasuk leading silence-nya)
    leading_silence = get_audio_offset(audio_path)
    if leading_silence > 0.05:
        logger.info(
            f"ℹ️ Leading silence {leading_silence:.3f}s sudah otomatis tercakup "
            f"di WordBoundary edge-tts — tidak perlu koreksi manual."
        )

    audio_duration = librosa.get_duration(path=audio_path)

    # 4. DP ALIGNMENT: cocokkan target_tokens (spoken) <-> raw_boundaries
    alignment = align_target_to_boundaries(target_tokens, raw_boundaries)

    # 5. BANGUN FINAL TIMESTAMPS berdasarkan hasil alignment
    final_timestamps: List[WordTimestamp] = []
    matched_count = 0

    for target_idx, boundary_idx, confidence in alignment:
        tgt = target_tokens[target_idx]

        if boundary_idx is not None:
            b = raw_boundaries[boundary_idx]
            start = b["start"]
            end = max(start + 0.1, b["start"] + b["duration"])
            matched_count += 1
        else:
            # Gap sementara — akan diisi oleh _interpolate_missing di bawah
            start = 0.0
            end = 0.1
            confidence = 0.0

        final_timestamps.append(
            WordTimestamp(
                word=tgt["spoken"],
                display=tgt["display"],
                start=round(start, 3),
                end=round(end, 3),
                duration=round(end - start, 3),
                section=tgt["section"],
                confidence=round(confidence, 2),
            )
        )

    # 6. Interpolasi untuk token yang gagal match (confidence 0)
    _interpolate_missing(final_timestamps, audio_duration)

    # 7. LOCKDOWN — satu-satunya lapisan koreksi timing yang tersisa (anti overlap/overflow)
    final_timestamps = lockdown_timeline(final_timestamps, audio_duration)

    # 8. METADATA
    total = len(target_tokens)
    missed = total - matched_count
    accuracy = matched_count / total if total > 0 else 0.0
    failed_tokens = [
        ts.display for ts in final_timestamps if ts.confidence < 0.5
    ]

    metadata = SyncMetadata(
        matched=matched_count,
        total=total,
        accuracy=round(accuracy, 4),
        missed=missed,
        failed_tokens=failed_tokens,
    )

    logger.info(
        f"📊 Sinkronisasi selesai: {matched_count}/{total} kata match "
        f"({accuracy*100:.1f}% akurasi), {missed} kata di-interpolasi."
    )

    return final_timestamps, metadata
