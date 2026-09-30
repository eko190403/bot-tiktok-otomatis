"""
Script Director
===============
Mengubah topik mentah menjadi script terstruktur dengan format storytelling:
  HOOK → OPEN LOOP → ESCALATION → REVEAL → CTA/LOOP END

Setiap bagian ditulis dengan tujuan retention, bukan sekadar informasi.
"""

import json
import logging
import asyncio
import re
from typing import Optional

logger = logging.getLogger("ai.script_director")


# ---------------------------------------------------------------------------
# Model output
# ---------------------------------------------------------------------------

class ScriptSegment:
    """Satu segmen dalam script yang memiliki metadata lengkap."""

    def __init__(self, role: str, text: str, emotion: str, duration_hint: float,
                 voice_emphasis: str = "normal"):
        self.role = role              # HOOK | OPEN_LOOP | ESCALATION | REVEAL | CTA
        self.text = text
        self.emotion = emotion        # suspense | calm | tense | strong | warm
        self.duration_hint = duration_hint  # estimasi detik narasi
        self.voice_emphasis = voice_emphasis  # soft | normal | strong

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "text": self.text,
            "emotion": self.emotion,
            "duration_hint": self.duration_hint,
            "voice_emphasis": self.voice_emphasis,
        }

    def __repr__(self):
        return f"<ScriptSegment role={self.role} emotion={self.emotion} len={len(self.text)}>"


class DirectedScript:
    """Hasil lengkap dari Script Director."""

    def __init__(self, topic: str, channel_niche: str, segments: list,
                 hook_score: dict, raw: dict):
        self.topic = topic
        self.channel_niche = channel_niche
        self.segments = segments
        self.hook_score = hook_score  # {curiosity, emotion, conflict, novelty, shareability}
        self.raw = raw

    @property
    def full_text(self) -> str:
        return " ".join(s.text for s in self.segments)

    @property
    def hook_text(self) -> str:
        for s in self.segments:
            if s.role == "HOOK":
                return s.text
        return self.segments[0].text if self.segments else ""

    @property
    def total_duration(self) -> float:
        return sum(s.duration_hint for s in self.segments)

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "channel_niche": self.channel_niche,
            "hook_score": self.hook_score,
            "total_duration_estimate": self.total_duration,
            "segments": [s.to_dict() for s in self.segments],
        }


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(topic: str, channel_niche: str, channel_name: str,
                   performance_hints: Optional[str] = None) -> str:
    hint_section = ""
    if performance_hints:
        hint_section = f"""
LEARNING FROM PAST PERFORMANCE:
{performance_hints}
Apply these insights when writing this new script.
"""

    return f"""You are an elite TikTok/YouTube Shorts script writer specializing in "{channel_niche}" content.
Channel: {channel_name}
Topic: {topic}
{hint_section}

Write a RETENTION-OPTIMIZED short-form video script using the following storytelling structure.
Each segment must serve a specific psychological purpose to keep viewers watching.

STRUCTURE RULES:
1. HOOK (0-3 seconds): Trigger immediate curiosity or emotion. NEVER start with "hai" or greetings.
   Use a provocative question, shocking statement, or conflict opener.
2. OPEN_LOOP (3-10s): Create a curiosity gap. Promise something the viewer NEEDS to know.
3. ESCALATION (10-35s): Build tension, add layers. Deliver value piece by piece, not all at once.
4. REVEAL (35-55s): The payoff. Deliver the insight/answer with emotional weight.
5. CTA (55-60s): Loop closure + call to action that feels natural, not forced.

Return ONLY a valid JSON object:
{{
  "hook_score": {{"curiosity": 8,"emotion": 7,"conflict": 6,"novelty": 7,"shareability": 8}},
  "segments": [
    {{"role": "HOOK","text": "...","emotion": "suspense","duration_hint": 3.0,"voice_emphasis": "strong"}},
    {{"role": "OPEN_LOOP","text": "...","emotion": "tense","duration_hint": 7.0,"voice_emphasis": "normal"}},
    {{"role": "ESCALATION","text": "...","emotion": "calm","duration_hint": 25.0,"voice_emphasis": "normal"}},
    {{"role": "REVEAL","text": "...","emotion": "strong","duration_hint": 18.0,"voice_emphasis": "strong"}},
    {{"role": "CTA","text": "...","emotion": "warm","duration_hint": 5.0,"voice_emphasis": "soft"}}
  ]
}}

IMPORTANT:
- Write ALL text in Bahasa Indonesia (conversational, Gen-Z friendly)
- Total script target: 55-65 seconds when spoken naturally
- Do NOT use emojis in the text field
- Return only valid JSON, no markdown fences"""


# ---------------------------------------------------------------------------
# Main director function
# ---------------------------------------------------------------------------

async def direct_script(
    topic: str,
    channel_niche: str = "dark psychology and human behavior",
    channel_name: str = "Ruang Pikir",
    performance_hints: Optional[str] = None,
) -> Optional[DirectedScript]:
    """
    Entry point utama: Hasilkan script terstruktur untuk satu topik.

    Args:
        topic: Topik atau judul video yang akan dibuat
        channel_niche: Niche channel (dari config)
        channel_name: Nama channel (dari config)
        performance_hints: String insight dari analytics_brain untuk meningkatkan kualitas

    Returns:
        DirectedScript atau None jika gagal
    """
    from video_builder import call_gemini_with_retry, clean_and_parse_json

    prompt = _build_prompt(topic, channel_niche, channel_name, performance_hints)

    try:
        raw_text = await call_gemini_with_retry(prompt, is_json=True, temperature=0.85)
        data = clean_and_parse_json(raw_text)
    except Exception as e:
        logger.error(f"[ScriptDirector] Gagal generate script untuk '{topic}': {e}")
        return None

    if not isinstance(data, dict) or "segments" not in data:
        logger.error(f"[ScriptDirector] Format JSON tidak valid: {str(data)[:200]}")
        return None

    segments = []
    for seg_data in data.get("segments", []):
        try:
            seg = ScriptSegment(
                role=seg_data.get("role", "UNKNOWN"),
                text=seg_data.get("text", "").strip(),
                emotion=seg_data.get("emotion", "calm"),
                duration_hint=float(seg_data.get("duration_hint", 10.0)),
                voice_emphasis=seg_data.get("voice_emphasis", "normal"),
            )
            if seg.text:
                segments.append(seg)
        except Exception as parse_err:
            logger.warning(f"[ScriptDirector] Gagal parse segmen: {parse_err}")
            continue

    if len(segments) < 3:
        logger.error(f"[ScriptDirector] Script terlalu pendek ({len(segments)} segmen). Abort.")
        return None

    hook_score = data.get("hook_score", {
        "curiosity": 0, "emotion": 0, "conflict": 0,
        "novelty": 0, "shareability": 0,
    })

    script = DirectedScript(
        topic=topic,
        channel_niche=channel_niche,
        segments=segments,
        hook_score=hook_score,
        raw=data,
    )

    total_score = sum(hook_score.values())
    logger.info(
        f"[ScriptDirector] Script selesai | Topik: '{topic}' | "
        f"Segmen: {len(segments)} | Hook Score: {total_score}/50 | "
        f"Durasi: ~{script.total_duration:.0f}s"
    )
    return script


# ---------------------------------------------------------------------------
# Hook Laboratory — multi-hook generation & ranking
# ---------------------------------------------------------------------------

async def generate_hook_candidates(
    topic: str,
    channel_niche: str,
    count: int = 5,
) -> list:
    """
    Hook Laboratory: Generate beberapa kandidat hook lalu ranking berdasarkan skor.

    Returns:
        List dict hook yang sudah diurutkan dari skor tertinggi,
        contoh: [{"hook": "...", "scores": {...}, "total": 38}, ...]
    """
    from video_builder import call_gemini_with_retry, clean_and_parse_json

    prompt = f"""You are a TikTok hook specialist for "{channel_niche}" content.

Generate {count} different HOOK options for this topic: "{topic}"

Each hook must use a DIFFERENT psychological trigger:
1. Curiosity gap
2. Emotional shock
3. Conflict opener
4. Novelty / counterintuitive angle
5. Relatability

Return ONLY valid JSON:
{{
  "hooks": [
    {{
      "hook": "Teks hook dalam Bahasa Indonesia...",
      "trigger_type": "curiosity_gap",
      "scores": {{"curiosity": 9,"emotion": 6,"conflict": 5,"novelty": 7,"shareability": 8}}
    }}
  ]
}}

Rules:
- All hooks in Bahasa Indonesia (conversational, no emojis)
- Maximum 15 words per hook
- NEVER start with "Hai", "Halo", "Selamat"
- Score each dimension 1-10 honestly
- Return only JSON"""

    try:
        raw = await call_gemini_with_retry(prompt, is_json=True, temperature=0.95)
        data = clean_and_parse_json(raw)
        hooks = data.get("hooks", [])

        for h in hooks:
            h["total"] = sum(h.get("scores", {}).values())

        hooks.sort(key=lambda x: x["total"], reverse=True)
        logger.info(f"[HookLab] {len(hooks)} kandidat hook digenerate untuk '{topic}'")
        return hooks

    except Exception as e:
        logger.error(f"[HookLab] Gagal generate hook candidates: {e}")
        return []


async def pick_best_hook(
    topic: str,
    channel_niche: str,
    historical_hooks: Optional[list] = None,
) -> Optional[dict]:
    """
    Pilih hook terbaik berdasarkan skor dan histori performa.

    Args:
        historical_hooks: Data dari analytics_brain tentang hook-hook yang pernah performa bagus.
                          Format: [{"hook": "...", "avg_retention": 0.78}, ...]
    """
    candidates = await generate_hook_candidates(topic, channel_niche, count=5)
    if not candidates:
        return None

    if historical_hooks:
        best_patterns = [h["hook"][:20] for h in historical_hooks if h.get("avg_retention", 0) > 0.6]
        for candidate in candidates:
            hook_text = candidate.get("hook", "")
            for pattern in best_patterns:
                if any(word in hook_text for word in pattern.split()[:3]):
                    candidate["total"] += 5
                    break
        candidates.sort(key=lambda x: x["total"], reverse=True)

    best = candidates[0]
    logger.info(f"[HookLab] Hook terpilih (skor {best['total']}): \"{best['hook'][:60]}\"")
    return best
