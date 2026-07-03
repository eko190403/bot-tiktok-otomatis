"""
Subtitle Auto-Aligner (VAD & Whisper Forced Alignment)
Menyelaraskan subtitle asli (.srt/.vtt) dengan video/audio menggunakan Whisper & VAD.
"""
import os
import sys
import re
import argparse
import tempfile
import difflib
import numpy as np
import librosa
import soundfile as sf

# ----------------- FORMATTING HELPERS -----------------

def time_to_seconds(time_str: str) -> float:
    """Mengubah format HH:MM:SS,mmm atau MM:SS.mmm menjadi detik (float)."""
    time_str = time_str.replace(',', '.')
    parts = time_str.strip().split(':')
    if len(parts) == 3:
        h, m, s = parts
        return float(h) * 3600 + float(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return float(m) * 60 + float(s)
    else:
        return float(parts[0])

def seconds_to_srt_time(seconds: float) -> str:
    """Mengonversi detik ke format waktu SRT (HH:MM:SS,mmm)."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    if s >= 60:
        m += 1
        s -= 60
    if m >= 60:
        h += 1
        m -= 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def seconds_to_vtt_time(seconds: float) -> str:
    """Mengonversi detik ke format waktu VTT (HH:MM:SS.mmm)."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    if s >= 60:
        m += 1
        s -= 60
    if m >= 60:
        h += 1
        m -= 60
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


# ----------------- PARSING & EXTRACTION -----------------

def parse_subtitle_file(file_path: str) -> list:
    """Membaca file SRT atau VTT dan memparsing isinya menjadi list segment."""
    if not os.path.exists(file_path):
        print(f"❌ File subtitle tidak ditemukan: {file_path}")
        sys.exit(1)
        
    with open(file_path, "r", encoding="utf-8-sig") as f:
        content = f.read()
        
    lines = content.splitlines()
    segments = []
    
    # Regex untuk mencocokkan baris stempel waktu SRT/VTT
    time_pattern = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[,.]\d{3}|\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{3}|\d{2}:\d{2}[,.]\d{3})"
    )
    
    current_segment = None
    current_text = []
    
    for line in lines:
        line_strip = line.strip()
        match = time_pattern.search(line_strip)
        if match:
            # Simpan segmen sebelumnya jika ada
            if current_segment:
                current_segment["text"] = " ".join(current_text).strip()
                segments.append(current_segment)
                current_text = []
            
            start_str, end_str = match.groups()
            current_segment = {
                "index": len(segments) + 1,
                "start": time_to_seconds(start_str),
                "end": time_to_seconds(end_str),
                "original_start": time_to_seconds(start_str),
                "original_end": time_to_seconds(end_str),
                "text": ""
            }
        elif current_segment is not None:
            # Abaikan nomor indeks baris kosong/pemisah
            if line_strip == "" or (line_strip.isdigit() and len(current_text) == 0):
                continue
            else:
                current_text.append(line_strip)
                
    if current_segment:
        current_segment["text"] = " ".join(current_text).strip()
        segments.append(current_segment)
        
    return segments

def extract_and_convert_audio(input_path: str, output_wav_path: str):
    """Mengekstrak audio dari video atau mengonversi audio ke WAV 16kHz Mono."""
    print(f"🎵 Memproses input media: {input_path}")
    ext = os.path.splitext(input_path)[1].lower()
    
    is_video = ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv']
    
    # Coba jalankan FFmpeg CLI terlebih dahulu karena jauh lebih cepat dan hemat memori
    import subprocess
    try:
        if is_video:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", output_wav_path]
        else:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", output_wav_path]
            
        print(f"⚙️ Menjalankan perintah FFmpeg: {' '.join(cmd)}")
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"✅ Audio standar berhasil diekstraksi ke: {output_wav_path}")
        return
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"⚠️ FFmpeg CLI gagal atau tidak ditemukan ({e}). Menggunakan moviepy/librosa sebagai fallback...")
        
    if is_video:
        print("📹 Menggunakan moviepy untuk mengekstrak audio...")
        from moviepy import AudioFileClip
        audio_clip = AudioFileClip(input_path)
        audio_clip.write_audiofile(
            output_wav_path, 
            fps=16000, 
            nbytes=2, 
            codec='pcm_s16le', 
            ffmpeg_params=["-ac", "1"],
            logger=None
        )
        audio_clip.close()
    else:
        print("🎵 Menggunakan librosa/soundfile untuk konversi...")
        y, sr = librosa.load(input_path, sr=16000, mono=True)
        sf.write(output_wav_path, y, 16000, subtype='PCM_16')
    print(f"✅ Audio standar berhasil diekstraksi ke: {output_wav_path}")


# ----------------- VOICE ACTIVITY DETECTION (VAD) -----------------

def analyze_vad(audio_path: str) -> list:
    """Deteksi aktivitas suara (VAD) menggunakan analisis energi RMS dinamis."""
    print("🎙️ Menjalankan Deteksi Aktivitas Suara (VAD) berbasis RMS...")
    y, sr = librosa.load(audio_path, sr=16000, mono=True)
    duration = len(y) / sr
    
    # Hitung energi RMS per frame (128ms frame_length, 32ms hop_length)
    frame_length = 2048
    hop_length = 512
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    
    # Normalisasi RMS ke range [0, 1]
    rms_min = rms.min()
    rms_max = rms.max()
    if rms_max - rms_min > 1e-8:
        rms_norm = (rms - rms_min) / (rms_max - rms_min)
    else:
        rms_norm = rms
        
    # Threshold dinamis: 15% dari rata-rata energi
    threshold = np.mean(rms_norm) * 0.15
    is_speech = rms_norm > threshold
    times = librosa.frames_to_time(np.arange(len(rms_norm)), sr=sr, hop_length=hop_length)
    
    speech_segments = []
    in_speech = False
    start_time = 0.0
    
    for idx, active in enumerate(is_speech):
        current_time = times[idx]
        if active and not in_speech:
            start_time = current_time
            in_speech = True
        elif not active and in_speech:
            speech_segments.append((start_time, current_time))
            in_speech = False
            
    if in_speech:
        speech_segments.append((start_time, times[-1]))
        
    # Gabungkan segmen jeda yang sangat singkat (< 0.2 detik hening dianggap menyambung)
    merged_segments = []
    if speech_segments:
        curr_start, curr_end = speech_segments[0]
        for start, end in speech_segments[1:]:
            if start - curr_end < 0.2:
                curr_end = end
            else:
                merged_segments.append((curr_start, curr_end))
                curr_start, curr_end = start, end
        merged_segments.append((curr_start, curr_end))
        
    # Saring segmen suara yang terlalu pendek (< 0.1 detik dianggap derau/noise)
    filtered_segments = [(s, e) for s, e in merged_segments if (e - s) >= 0.1]
    print(f"✅ VAD selesai. Mendeteksi {len(filtered_segments)} segmen percakapan aktif dari total {duration:.2f} detik.")
    return filtered_segments


# ----------------- FORCED ALIGNMENT WITH WHISPER -----------------

def get_words_from_segments(segments: list) -> list:
    """Mengurai teks subtitle menjadi kata-kata dengan pemetaan segmennya."""
    words = []
    for seg in segments:
        text = seg["text"]
        raw_words = text.split()
        for w in raw_words:
            # Hilangkan tanda baca penulisan untuk pembandingan teks
            clean = re.sub(r"[^\w']", "", w).upper()
            words.append({
                "original": w,
                "clean": clean,
                "segment_index": seg["index"]
            })
    return words

def align_sequences(subtitle_words: list, whisper_words: list) -> list:
    """Melakukan pencocokan urutan Dynamic Programming global alignment."""
    n = len(subtitle_words)
    m = len(whisper_words)
    
    MATCH_SCORE = 2
    MISMATCH_PENALTY = -1
    GAP_PENALTY = -2
    
    dp = np.zeros((n + 1, m + 1), dtype=np.float32)
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] + GAP_PENALTY
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] + GAP_PENALTY
        
    for i in range(1, n + 1):
        sub_word = subtitle_words[i - 1]["clean"]
        for j in range(1, m + 1):
            wh_word = whisper_words[j - 1]["clean"]
            
            if sub_word == wh_word:
                score = MATCH_SCORE
            else:
                sim = difflib.SequenceMatcher(None, sub_word, wh_word).ratio()
                score = MATCH_SCORE * sim if sim >= 0.6 else MISMATCH_PENALTY
                
            diag = dp[i - 1][j - 1] + score
            up = dp[i - 1][j] + GAP_PENALTY
            left = dp[i][j - 1] + GAP_PENALTY
            dp[i][j] = max(diag, up, left)
            
    # Backtrace untuk mencari path pencocokan terbaik
    alignment = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            sub_word = subtitle_words[i - 1]["clean"]
            wh_word = whisper_words[j - 1]["clean"]
            if sub_word == wh_word:
                score = MATCH_SCORE
            else:
                sim = difflib.SequenceMatcher(None, sub_word, wh_word).ratio()
                score = MATCH_SCORE * sim if sim >= 0.6 else MISMATCH_PENALTY
                
            if abs(dp[i][j] - (dp[i - 1][j - 1] + score)) < 1e-5:
                alignment.append((i - 1, j - 1))
                i -= 1
                j -= 1
                continue
                
        if i > 0 and (j == 0 or abs(dp[i][j] - (dp[i - 1][j] + GAP_PENALTY)) < 1e-5):
            alignment.append((i - 1, None))
            i -= 1
            continue
            
        if j > 0:
            j -= 1
            continue
            
    alignment.reverse()
    return alignment

def interpolate_timestamps(subtitle_words: list, aligned_results: list, audio_duration: float):
    """Mengisi kata-kata kosong yang gagal dicocokkan menggunakan interpolasi linear."""
    n = len(aligned_results)
    for idx in range(n):
        if aligned_results[idx]["start"] is not None:
            continue
            
        prev_idx = idx - 1
        while prev_idx >= 0 and aligned_results[prev_idx]["start"] is None:
            prev_idx -= 1
            
        next_idx = idx + 1
        while next_idx < n and aligned_results[next_idx]["start"] is None:
            next_idx += 1
            
        prev_end = aligned_results[prev_idx]["end"] if prev_idx >= 0 else 0.0
        next_start = aligned_results[next_idx]["start"] if next_idx < n else audio_duration
        
        gap_span = max(0.1, next_start - prev_end)
        
        unaligned_indices = []
        for k in range(prev_idx + 1, next_idx):
            if aligned_results[k]["start"] is None:
                unaligned_indices.append(k)
                
        slot = gap_span / len(unaligned_indices)
        for order, k in enumerate(unaligned_indices):
            start = prev_end + slot * order
            end = start + slot
            aligned_results[k]["start"] = round(start, 3)
            aligned_results[k]["end"] = round(end, 3)

def forced_alignment_whisper(subtitle_segments: list, audio_path: str, model_size: str = "tiny") -> list:
    """Mencocokkan kata-kata subtitle dengan suara riil menggunakan OpenAI Whisper."""
    print(f"🤖 Mengunduh/memuat model Whisper '{model_size}' (CPU friendly)...")
    import whisper
    model = whisper.load_model(model_size)
    
    print("🎙️ Memulai pengenalan ucapan Whisper dengan word-level timestamps...")
    result = model.transcribe(audio_path, word_timestamps=True)
    
    # Ekstrak kata-kata dari transkripsi Whisper
    whisper_words = []
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            word_text = w["word"].strip()
            clean_text = re.sub(r"[^\w']", "", word_text).upper()
            if clean_text:
                whisper_words.append({
                    "word": word_text,
                    "clean": clean_text,
                    "start": w["start"],
                    "end": w["end"]
                })
    print(f"🗣️ Whisper mendeteksi {len(whisper_words)} kata bersuara di audio.")
    
    # Ambil daftar kata dari subtitle asli
    subtitle_words = get_words_from_segments(subtitle_segments)
    
    # Lakukan urutan alignment
    print("🔗 Mencocokkan kata teks asli dengan data timestamp audio...")
    alignment = align_sequences(subtitle_words, whisper_words)
    
    aligned_results = []
    for sub_idx, wh_idx in alignment:
        sub_word = subtitle_words[sub_idx]
        if wh_idx is not None:
            wh_word = whisper_words[wh_idx]
            aligned_results.append({
                "segment_index": sub_word["segment_index"],
                "start": wh_word["start"],
                "end": wh_word["end"]
            })
        else:
            aligned_results.append({
                "segment_index": sub_word["segment_index"],
                "start": None,
                "end": None
            })
            
    audio_duration = librosa.get_duration(path=audio_path)
    interpolate_timestamps(subtitle_words, aligned_results, audio_duration)
    
    # Gabungkan kata-kata kembali menjadi segmen
    seg_words = {}
    for item in aligned_results:
        s_idx = item["segment_index"]
        if s_idx not in seg_words:
            seg_words[s_idx] = []
        seg_words[s_idx].append(item)
        
    for seg in subtitle_segments:
        s_idx = seg["index"]
        words_in_seg = seg_words.get(s_idx, [])
        if words_in_seg:
            seg["start"] = words_in_seg[0]["start"]
            seg["end"] = words_in_seg[-1]["end"]
            
    return subtitle_segments


# ----------------- TIMING CORRECTION & SHIFTING -----------------

def adjust_with_vad(subtitle_segments: list, vad_segments: list) -> list:
    """Menyelaraskan batas waktu subtitle dengan segmen VAD agar pas dengan suara."""
    print("⏳ Menyelaraskan stempel waktu akhir dengan Voice Activity Detection...")
    
    # Hitung offset rata-rata
    offsets = []
    for seg in subtitle_segments:
        old_center = (seg["original_start"] + seg["original_end"]) / 2.0
        new_center = (seg["start"] + seg["end"]) / 2.0
        offsets.append(new_center - old_center)
        
    if offsets:
        avg_offset = np.mean(offsets)
        std_offset = np.std(offsets)
        print(f"📊 Offset Rata-rata Subtitle Baru vs Lama: {avg_offset:+.3f}s (Deviasi Standar: {std_offset:.3f}s)")
        
    # Koreksi batas waktu start & end dengan VAD
    for seg in subtitle_segments:
        start = seg["start"]
        end = seg["end"]
        
        best_vad_start = None
        best_vad_end = None
        min_dist = float('inf')
        
        # Cari segmen VAD yang tumpang tindih
        for v_start, v_end in vad_segments:
            overlap = max(0.0, min(end, v_end) - max(start, v_start))
            if overlap > 0:
                best_vad_start = v_start
                best_vad_end = v_end
                break
            else:
                dist = min(abs(start - v_end), abs(end - v_start))
                if dist < min_dist:
                    min_dist = dist
                    best_vad_start = v_start
                    best_vad_end = v_end
                    
        # Snapping ke batas VAD jika dekat (< 0.5 detik)
        if best_vad_start is not None:
            if abs(start - best_vad_start) < 0.5:
                start = max(best_vad_start, start)
            if abs(end - best_vad_end) < 0.5:
                end = min(best_vad_end, end)
                
        # Pastikan tidak berbalik dan durasi minimal 0.15 detik
        if end <= start:
            end = start + 0.15
            
        seg["start"] = start
        seg["end"] = end
        
    # Cegah tumpang tindih berurutan
    for i in range(1, len(subtitle_segments)):
        prev = subtitle_segments[i-1]
        curr = subtitle_segments[i]
        if curr["start"] < prev["end"]:
            curr["start"] = prev["end"]
            if curr["end"] < curr["start"] + 0.1:
                curr["end"] = curr["start"] + 0.1
                
    return subtitle_segments


# ----------------- EXPORT OUTPUT -----------------

def write_subtitle_file(segments: list, output_path: str):
    """Menyimpan data subtitle baru dalam format SRT atau VTT."""
    print(f"💾 Mengekspor subtitle hasil sinkronisasi ke: {output_path}")
    ext = os.path.splitext(output_path)[1].lower()
    is_vtt = ext == ".vtt"
    
    with open(output_path, "w", encoding="utf-8") as f:
        if is_vtt:
            f.write("WEBVTT\n\n")
            
        for seg in segments:
            idx = seg["index"]
            start_str = seconds_to_vtt_time(seg["start"]) if is_vtt else seconds_to_srt_time(seg["start"])
            end_str = seconds_to_vtt_time(seg["end"]) if is_vtt else seconds_to_srt_time(seg["end"])
            text = seg["text"]
            
            f.write(f"{idx}\n{start_str} --> {end_str}\n{text}\n\n")
            
    print("🎉 File subtitle berhasil diekspor sempurna!")


# ----------------- MAIN PIPELINE -----------------

def main():
    parser = argparse.ArgumentParser(description="Alat sinkronisasi otomatis subtitle (.srt/.vtt) berbasis AI.")
    parser.add_argument("--video", required=True, help="Path ke berkas video atau audio input.")
    parser.add_argument("--subtitle", required=True, help="Path ke berkas subtitle asli (.srt atau .vtt).")
    parser.add_argument("--output", required=True, help="Path untuk menyimpan berkas subtitle output.")
    parser.add_argument("--model", default="tiny", help="Ukuran model Whisper (tiny, base, small, medium, large). Default: tiny.")
    
    args = parser.parse_args()
    
    # Pastikan folder output ada
    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        
    # Buat file audio WAV temporer untuk analisis
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_wav_path = os.path.join(tmpdir, "extracted_temp.wav")
        
        # Langkah 1: Ekstraksi Input
        extract_and_convert_audio(args.video, temp_wav_path)
        
        # Langkah 2: Deteksi Aktivitas Suara (VAD)
        vad_segments = analyze_vad(temp_wav_path)
        
        # Langkah 3: Forced Alignment (Membaca & mencocokkan teks via Whisper)
        subtitle_segments = parse_subtitle_file(args.subtitle)
        subtitle_aligned = forced_alignment_whisper(subtitle_segments, temp_wav_path, model_size=args.model)
        
        # Langkah 4: Koreksi dan Penyesuaian Waktu (Shift & Snap ke VAD)
        final_segments = adjust_with_vad(subtitle_aligned, vad_segments)
        
        # Langkah 5: Ekspor Output
        write_subtitle_file(final_segments, args.output)

if __name__ == "__main__":
    main()
