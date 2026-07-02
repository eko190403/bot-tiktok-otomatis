"""
Audio Sync Optimizer V2 - Sinkronisasi Subtitle Presisi Tinggi (CapCut-like)
Menggunakan Voice Energy Analysis dan Dynamic Pace Detection
"""
import numpy as np
import librosa
import logging
from dataclasses import dataclass
from typing import List, Dict, Union

logger = logging.getLogger("audio_sync_optimizer")


@dataclass
class TimingAdjustment:
    word_idx: int
    original_start: float
    adjusted_start: float
    original_end: float
    adjusted_end: float
    confidence: float


# --- KONVERSI DATACLASS <-> DICT ---
# audio.py mengirim list objek WordTimestamp (dataclass slots=True), tapi semua
# fungsi optimizer di bawah ini bekerja dengan dict (ts["start"], ts.copy(), dll).
# Tanpa konversi ini, setiap fungsi di bawah akan langsung TypeError karena
# objek dataclass ber-slots tidak subscriptable dan tidak punya .copy().

def _to_dict_list(timestamps: List[Union[dict, object]]) -> List[Dict]:
    if not timestamps:
        return []
    if isinstance(timestamps[0], dict):
        return [dict(t) for t in timestamps]
    # Asumsikan objek dataclass WordTimestamp (punya atribut word/display/start/end/duration/section/confidence)
    return [
        {
            "word": t.word,
            "display": t.display,
            "start": t.start,
            "end": t.end,
            "duration": t.duration,
            "section": t.section,
            "confidence": t.confidence,
        }
        for t in timestamps
    ]


def _to_wordtimestamp_list(dict_list: List[Dict]):
    # Import lokal untuk menghindari circular import (audio.py tidak import file ini)
    from audio import WordTimestamp
    return [
        WordTimestamp(
            word=d["word"],
            display=d["display"],
            start=d["start"],
            end=d["end"],
            duration=d.get("duration", max(0.05, d["end"] - d["start"])),
            section=d["section"],
            confidence=d.get("confidence", 0.0),
        )
        for d in dict_list
    ]


def analyze_audio_energy(audio_file_path: str, sr: int = 22050) -> tuple:
    """
    Deteksi aktivitas suara menggunakan energy-based VAD.
    Mengembalikan: (time_frames, energy_levels, silence_regions)
    """
    try:
        y, sr = librosa.load(audio_file_path, sr=sr)
    except Exception as e:
        logger.error(f"Gagal memuat audio: {e}")
        return None, None, []

    # Frame-based energy calculation
    frame_length = 2048
    hop_length = 512
    S = np.abs(librosa.stft(y, n_fft=frame_length, hop_length=hop_length))
    energy = np.sqrt(np.sum(S**2, axis=0))

    # Normalisasi energy
    energy_norm = (energy - energy.min()) / (energy.max() - energy.min() + 1e-8)

    # Deteksi silence dengan dynamic threshold
    mean_energy = np.mean(energy_norm)
    threshold = mean_energy * 0.30  # Threshold agresif untuk menangkap jeda halus

    is_silence = energy_norm < threshold
    time_frames = librosa.frames_to_time(np.arange(len(energy_norm)), sr=sr, hop_length=hop_length)

    # Kelompokkan silence regions yang kontinu
    silence_regions = _extract_silence_regions(time_frames, is_silence)

    return time_frames, energy_norm, silence_regions


def _extract_silence_regions(time_frames, is_silence):
    """Ekstraksi continuous silence regions dari boolean array."""
    silence_regions = []
    in_silence = False
    start_time = 0.0

    for idx, silent in enumerate(is_silence):
        if silent and not in_silence:
            start_time = time_frames[idx]
            in_silence = True
        elif not silent and in_silence:
            silence_regions.append((start_time, time_frames[idx]))
            in_silence = False

    if in_silence:
        silence_regions.append((start_time, time_frames[-1]))

    return silence_regions


def calculate_speaking_rate(timestamps: list, audio_file_path: str) -> float:
    """
    Hitung rata-rata kecepatan berbicara (words per second).
    Digunakan untuk deteksi anomali timing.
    """
    try:
        y, sr = librosa.load(audio_file_path, sr=22050)
        total_duration = len(y) / sr
    except Exception:
        total_duration = timestamps[-1]["end"] if timestamps else 1.0

    word_count = len(timestamps)
    speaking_rate = word_count / total_duration if total_duration > 0 else 0

    logger.info(f"📊 Speaking Rate Detected: {speaking_rate:.2f} words/sec")
    return speaking_rate


def adjust_timestamps_with_gaps(timestamps: list, silence_regions: list) -> list:
    """
    Sesuaikan timestamp berdasarkan detected silence regions.
    Jika ada gap sebelum kata, hentikan subtitle lebih cepat.
    HANYA mempersingkat 'end' (tidak pernah menggeser 'start') — jadi tidak
    menimbulkan efek "subtitle muncul lebih cepat dari suara" seperti bug lama.
    """
    if not silence_regions or not timestamps:
        return timestamps

    adjusted = []

    for ts in timestamps:
        word_start = ts["start"]
        word_end = ts["end"]
        adjusted_end = word_end

        # Cek apakah ada silence setelah kata ini
        for silence_start, silence_end in silence_regions:
            if silence_start >= word_end and silence_start < word_end + 0.1:
                # Jika jeda hening terdeteksi dekat setelah kata, hentikan subtitle sebelum jeda
                adjusted_end = min(word_end, silence_start - 0.05)
                break

        ts_copy = ts.copy()
        ts_copy["end"] = max(word_start + 0.15, adjusted_end)  # Minimum duration 0.15s
        ts_copy["duration"] = ts_copy["end"] - ts_copy["start"]
        adjusted.append(ts_copy)

    return adjusted


def interpolate_missing_timestamps(target_tokens: list, actual_timestamps: list) -> list:
    """
    Untuk token yang tidak match (akurasi rendah), interpolasi timing dari tetangga.
    Catatan: sejak audio.py melakukan DP alignment + interpolasi sendiri, jumlah
    actual_timestamps seharusnya SELALU >= target_tokens, jadi fungsi ini normalnya
    no-op. Tetap dipertahankan sebagai safety net kalau ada perubahan upstream.
    """
    if len(actual_timestamps) >= len(target_tokens):
        return actual_timestamps

    result = []
    actual_idx = 0

    for target_idx, target in enumerate(target_tokens):
        if actual_idx < len(actual_timestamps):
            result.append(actual_timestamps[actual_idx])
            actual_idx += 1
        else:
            if result:
                last_ts = result[-1]
                interpolated = {
                    "word": target.get("word", ""),
                    "display": target.get("token", ""),
                    "start": last_ts["end"],
                    "end": last_ts["end"] + 0.25,
                    "duration": 0.25,
                    "section": target.get("section", "body"),
                    "confidence": 0.40,
                }
                result.append(interpolated)
            else:
                result.append({
                    "word": target.get("word", ""),
                    "display": target.get("token", ""),
                    "start": 0.0,
                    "end": 0.25,
                    "duration": 0.25,
                    "section": target.get("section", "body"),
                    "confidence": 0.40,
                })

    return result


def smooth_duration_outliers(timestamps: list, std_dev_threshold: float = 2.0) -> list:
    """
    Deteksi dan smoothing durasi kata yang outlier (terlalu panjang/pendek).
    Gunakan median filtering untuk stabilitas.
    """
    if len(timestamps) < 3:
        return timestamps

    durations = [ts["duration"] for ts in timestamps]
    median_duration = np.median(durations)
    std_duration = np.std(durations)

    result = []
    for ts in timestamps:
        duration = ts["duration"]

        if std_duration > 1e-6 and abs(duration - median_duration) > std_dev_threshold * std_duration:
            ts_copy = ts.copy()
            ts_copy["duration"] = float(median_duration)
            ts_copy["end"] = ts_copy["start"] + float(median_duration)
            logger.warning(f"⚠️ Duration outlier detected: {duration:.2f}s → {median_duration:.2f}s")
            result.append(ts_copy)
        else:
            result.append(ts)

    return result


async def optimize_subtitle_timing(
    timestamps: list,
    audio_file_path: str,
    target_tokens: list,
    enable_vad: bool = True,
    enable_smoothing: bool = True
) -> list:
    """
    Pipeline optimasi timing subtitle utama.
    Menggabungkan semua strategi untuk akurasi CapCut-like.

    Menerima & mengembalikan list objek WordTimestamp (dataclass) agar kompatibel
    dengan video_pipeline.py — konversi ke/dari dict dilakukan secara internal.
    """
    logger.info("🎯 Memulai optimasi timing subtitle presisi tinggi...")

    optimized = _to_dict_list(timestamps)

    # Step 1: Voice Activity Detection untuk gap detection (hanya mempersingkat 'end')
    if enable_vad:
        try:
            time_frames, energy, silence_regions = analyze_audio_energy(audio_file_path)
            if silence_regions:
                logger.info(f"📍 Terdeteksi {len(silence_regions)} region jeda pembicaraan")
                optimized = adjust_timestamps_with_gaps(optimized, silence_regions)
        except Exception as e:
            logger.warning(f"⚠️ VAD failed, melanjutkan tanpa gap detection: {e}")

    # Step 2: Smoothing duration outliers
    if enable_smoothing:
        try:
            optimized = smooth_duration_outliers(optimized)
        except Exception as e:
            logger.warning(f"⚠️ Smoothing gagal, dilewati: {e}")

    # Step 3: Interpolasi untuk missing tokens (safety net, normalnya no-op)
    if len(optimized) < len(target_tokens):
        logger.info(f"🔧 Interpolasi {len(target_tokens) - len(optimized)} token yang hilang")
        optimized = interpolate_missing_timestamps(target_tokens, optimized)

    # Step 4: Validasi continuity (tidak boleh ada overlap)
    optimized = _validate_and_fix_continuity(optimized)

    # Step 5: Konversi balik ke WordTimestamp + lockdown final (anti overlap/overflow
    # terhadap durasi audio asli) — satu-satunya jaring pengaman terakhir.
    result = _to_wordtimestamp_list(optimized)
    try:
        from audio import lockdown_timeline
        audio_duration = librosa.get_duration(path=audio_file_path)
        result = lockdown_timeline(result, audio_duration)
    except Exception as e:
        logger.warning(f"⚠️ Lockdown final gagal, memakai hasil optimasi apa adanya: {e}")

    logger.info(f"✅ Optimasi selesai. Total timestamps: {len(result)}")
    return result


def _validate_and_fix_continuity(timestamps: list) -> list:
    """
    Pastikan tidak ada overlap antara subtitle (dorong start maju kalau bentrok).
    """
    if len(timestamps) <= 1:
        return timestamps

    result = []
    for idx, ts in enumerate(timestamps):
        ts_copy = ts.copy()

        if idx > 0:
            prev_ts = result[-1]
            if ts_copy["start"] < prev_ts["end"]:
                ts_copy["start"] = prev_ts["end"]
                if ts_copy["end"] < ts_copy["start"] + 0.05:
                    ts_copy["end"] = ts_copy["start"] + ts_copy["duration"]

        result.append(ts_copy)

    return result
