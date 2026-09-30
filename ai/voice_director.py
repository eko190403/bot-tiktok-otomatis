"""
Voice Director
==============
Menambahkan kontrol emosional ke sistem TTS (edge-tts).

Upgrade dari: text → speech
Menjadi:      text + emotion_tag → speech dengan pause, speed variation, emphasis

Setiap segmen script mendapatkan:
  - Rate (kecepatan bicara): slow | normal | fast
  - Volume: soft | normal | loud
  - Jeda strategis di dalam teks
  - Emphasis pada kata kunci
"""

import re
import logging
from typing import Optional

logger = logging.getLogger("ai.voice_director")


# ---------------------------------------------------------------------------
# Emotion presets untuk edge-tts SSML-style
# ---------------------------------------------------------------------------

EMOTION_VOICE_PRESETS = {
    "suspense": {
        "rate":   "-5%",    # sedikit lebih lambat untuk dramatik
        "volume": "+0%",
        "pitch":  "-2Hz",
        "pause_between_sentences": 0.5,   # detik
        "emphasis_words": ["ini", "tapi", "yang", "ternyata", "satu"],
    },
    "tense": {
        "rate":   "+5%",
        "volume": "+5%",
        "pitch":  "+0Hz",
        "pause_between_sentences": 0.3,
        "emphasis_words": ["tidak", "jangan", "harus", "wajib", "kritis"],
    },
    "calm": {
        "rate":   "+0%",
        "volume": "+0%",
        "pitch":  "+0Hz",
        "pause_between_sentences": 0.6,
        "emphasis_words": [],
    },
    "strong": {
        "rate":   "-8%",    # lebih lambat + kuat
        "volume": "+10%",
        "pitch":  "-5Hz",
        "pause_between_sentences": 0.7,
        "emphasis_words": ["bukti", "fakta", "terbukti", "nyata", "pasti", "selalu"],
    },
    "warm": {
        "rate":   "+3%",
        "volume": "-5%",
        "pitch":  "+3Hz",
        "pause_between_sentences": 0.4,
        "emphasis_words": ["kamu", "kita", "bersama", "follow", "subscribe"],
    },
}

# Voice emphasis
VOICE_EMPHASIS_PRESETS = {
    "soft":   {"rate": "-10%", "volume": "-10%"},
    "normal": {"rate": "+0%",  "volume": "+0%"},
    "strong": {"rate": "-12%", "volume": "+15%"},
}


# ---------------------------------------------------------------------------
# Text processing untuk TTS
# ---------------------------------------------------------------------------

def inject_pauses(text: str, emotion: str, pause_duration: float = None) -> str:
    """
    Tambahkan jeda strategis ke dalam teks sebelum dikirim ke TTS.
    
    Menggunakan tag koma dan titik untuk mengontrol jeda edge-tts.
    Jeda panjang menggunakan multiple spasi (edge-tts menghormati whitespace minimal).
    """
    preset = EMOTION_VOICE_PRESETS.get(emotion, EMOTION_VOICE_PRESETS["calm"])
    if pause_duration is None:
        pause_duration = preset["pause_between_sentences"]

    # Tambah jeda setelah tanda titik (akhir kalimat)
    # edge-tts tidak mendukung SSML penuh, jadi kita gunakan tanda baca
    text = re.sub(r'\. +', '. ', text)  # normalkan spasi setelah titik dulu

    # Jika suspense/strong, tambah koma sebelum kata kunci penting
    if emotion in ("suspense", "strong"):
        emphasis_words = preset.get("emphasis_words", [])
        for word in emphasis_words:
            # Tambah koma sebelum kata penting jika belum ada tanda baca di sana
            pattern = r'(?<![,\.!?])\s+(' + re.escape(word) + r')\s+'
            text = re.sub(pattern, r', \1 ', text, flags=re.IGNORECASE, count=2)

    return text.strip()


def add_strategic_ellipsis(text: str, emotion: str) -> str:
    """
    Tambahkan '...' di momen-momen dramatis untuk membuat jeda.
    Hanya untuk emosi suspense dan tense.
    """
    if emotion not in ("suspense", "tense"):
        return text

    # Tambah ellipsis setelah kalimat tanya yang kuat
    text = re.sub(r'\?(\s+)', r'?... ', text, count=1)

    return text


def build_voice_instructions(segment) -> dict:
    """
    Bangun instruksi lengkap untuk TTS berdasarkan metadata segmen script.

    Args:
        segment: ScriptSegment dari script_director

    Returns:
        Dict dengan:
          - processed_text: Teks yang sudah diproses untuk TTS
          - rate: Kecepatan bicara (untuk edge-tts)
          - volume: Volume (untuk edge-tts)
          - pitch: Nada suara
          - emotion: Emosi
    """
    emotion = segment.emotion
    emphasis = segment.voice_emphasis

    preset = EMOTION_VOICE_PRESETS.get(emotion, EMOTION_VOICE_PRESETS["calm"])
    emph_preset = VOICE_EMPHASIS_PRESETS.get(emphasis, VOICE_EMPHASIS_PRESETS["normal"])

    # Process teks
    processed = inject_pauses(segment.text, emotion)
    processed = add_strategic_ellipsis(processed, emotion)

    # Gabungkan rate dari emotion + emphasis
    def parse_percent(s: str) -> int:
        return int(s.replace("%", "").replace("+", ""))

    emotion_rate = parse_percent(preset["rate"])
    emphasis_rate = parse_percent(emph_preset["rate"])
    combined_rate = emotion_rate + emphasis_rate

    emotion_vol = parse_percent(preset["volume"])
    emphasis_vol = parse_percent(emph_preset["volume"])
    combined_vol = emotion_vol + emphasis_vol

    rate_str = f"{'+' if combined_rate >= 0 else ''}{combined_rate}%"
    vol_str  = f"{'+' if combined_vol >= 0 else ''}{combined_vol}%"

    return {
        "processed_text": processed,
        "rate": rate_str,
        "volume": vol_str,
        "pitch": preset.get("pitch", "+0Hz"),
        "emotion": emotion,
        "voice_emphasis": emphasis,
        "segment_role": segment.role,
    }


def direct_voice(script) -> list:
    """
    Proses seluruh script dan hasilkan instruksi suara per segmen.

    Args:
        script: DirectedScript dari script_director

    Returns:
        List dict instruksi per segmen, siap dipakai oleh audio.py
    """
    instructions = []

    for segment in script.segments:
        instr = build_voice_instructions(segment)
        instructions.append(instr)
        logger.debug(
            f"[VoiceDirector] [{segment.role}] rate={instr['rate']} "
            f"vol={instr['volume']} emotion={instr['emotion']}"
        )

    logger.info(
        f"[VoiceDirector] {len(instructions)} segmen diproses | "
        f"Topik: '{script.topic}'"
    )
    return instructions


def build_full_tts_text(voice_instructions: list) -> str:
    """
    Gabungkan semua segmen menjadi satu string teks untuk TTS.
    Tambahkan jeda antar segmen berdasarkan emosi.
    """
    parts = []
    for i, instr in enumerate(voice_instructions):
        text = instr["processed_text"].strip()
        role = instr.get("segment_role", "")

        # Tambah jeda lebih panjang di antara segmen utama
        if i > 0:
            prev_role = voice_instructions[i - 1].get("segment_role", "")
            if prev_role == "HOOK" or role == "REVEAL":
                text = "... " + text  # jeda dramatis antar segmen penting

        parts.append(text)

    return " ".join(parts)



async def generate_emotional_voiceover(
    script,
    voice_id: str = "id-ID-ArdiNeural",
    output_dir: str = "temp",
    voice_rate: str = "+0%",
    voice_pitch: str = "+0Hz",
) -> Optional[str]:
    """
    Generate voiceover dengan kontrol emosional penuh menggunakan edge-tts.
    Wrapper di atas generate_voiceover_resilient yang menambahkan pre-processing
    emosional (rate, pitch, emphasis) dari Voice Director sebelum TTS.

    NOTE: Fungsi ini adalah helper opsional. Pipeline utama (video_builder.py)
    menggunakan generate_voiceover_resilient secara langsung dengan rate/pitch
    dari channel config. Gunakan fungsi ini hanya jika ingin mengoverride
    dengan parameter emosional dari script.

    Args:
        script:      DirectedScript dari script_director
        voice_id:    ID suara edge-tts (dari config channel)
        output_dir:  Folder output audio
        voice_rate:  Rate override (opsional, default dari emotion preset)
        voice_pitch: Pitch override (opsional, default dari emotion preset)

    Returns:
        Tuple (timestamps, SyncMetadata) atau (None, None) jika gagal
    """
    import os
    from video_builder import generate_voiceover_resilient

    # Build instruksi suara per segmen
    voice_instructions = direct_voice(script)

    # Pakai rate & pitch dari HOOK segment (segmen pertama) sebagai panduan
    hook_instr = next((v for v in voice_instructions if v["segment_role"] == "HOOK"), None)
    effective_rate  = hook_instr["rate"]  if hook_instr else voice_rate
    effective_pitch = hook_instr["pitch"] if hook_instr else voice_pitch

    # Bangun teks final
    full_text = build_full_tts_text(voice_instructions)

    logger.info(
        f"[VoiceDirector] Memulai TTS emosional | Voice: {voice_id} | "
        f"Rate: {effective_rate} | Pitch: {effective_pitch} | "
        f"Panjang teks: {len(full_text)} karakter"
    )

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"voice_{script.topic[:20].replace(' ', '_')}.mp3")

    # Pisahkan full_text ke bagian hook / story / cta berdasarkan segmen
    hook_parts  = [v["processed_text"] for v in voice_instructions if v["segment_role"] == "HOOK"]
    cta_parts   = [v["processed_text"] for v in voice_instructions if v["segment_role"] == "CTA"]
    story_parts = [v["processed_text"] for v in voice_instructions
                   if v["segment_role"] not in ("HOOK", "CTA")]

    hook_text  = " ".join(hook_parts)
    story_text = " ".join(story_parts)
    cta_text   = " ".join(cta_parts)

    try:
        result = await generate_voiceover_resilient(
            hook=hook_text,
            story=story_text,
            cta=cta_text,
            path=output_path,
            voice_id=voice_id,
            voice_rate=effective_rate,
            voice_pitch=effective_pitch,
        )
        timestamps, meta = result
        if timestamps and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"[VoiceDirector] Voiceover selesai: {output_path} ({file_size // 1024}KB)")
            return output_path
        else:
            logger.error("[VoiceDirector] TTS gagal menghasilkan file audio")
            return None
    except Exception as e:
        logger.error(f"[VoiceDirector] Error saat generate voiceover emosional: {e}")
        return None
