"""
Script Reviewer
===============
Mengevaluasi script sebelum masuk ke render pipeline.
Memberikan skor dan saran perbaikan berdasarkan kriteria retention.

Dilakukan SEBELUM render untuk menghindari pemborosan resource.
"""

import logging
from typing import Optional

logger = logging.getLogger("ai.script_reviewer")

# Threshold skor minimum untuk lolos review
MIN_HOOK_SCORE = 30        # dari 50 (5 dimensi x 10)
MIN_TOTAL_REVIEW_SCORE = 55  # dari 100
MIN_DURATION = 45.0        # detik minimum
MAX_DURATION = 75.0        # detik maksimum


class ReviewResult:
    """Hasil review script."""

    def __init__(self, passed: bool, score: int, issues: list, suggestions: list,
                 scores_breakdown: dict):
        self.passed = passed
        self.score = score               # 0-100
        self.issues = issues             # List masalah kritis
        self.suggestions = suggestions   # Saran perbaikan opsional
        self.scores_breakdown = scores_breakdown  # {hook, structure, pacing, cta}

    def __repr__(self):
        status = "PASSED" if self.passed else "FAILED"
        return f"<ReviewResult {status} score={self.score}/100 issues={len(self.issues)}>"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": self.score,
            "scores_breakdown": self.scores_breakdown,
            "issues": self.issues,
            "suggestions": self.suggestions,
        }


# ---------------------------------------------------------------------------
# Rule-based checks (cepat, tanpa AI call)
# ---------------------------------------------------------------------------

def _check_hook_strength(hook_score: dict) -> tuple:
    """Cek apakah hook cukup kuat berdasarkan skor dari script_director."""
    total = sum(hook_score.values())
    issues = []
    suggestions = []

    if total < MIN_HOOK_SCORE:
        issues.append(f"Hook score terlalu rendah: {total}/50 (minimum {MIN_HOOK_SCORE})")

    if hook_score.get("curiosity", 0) < 6 and hook_score.get("emotion", 0) < 6:
        issues.append("Hook tidak cukup kuat: curiosity DAN emotion di bawah 6")
        suggestions.append("Gunakan pertanyaan provokatif atau fakta mengejutkan di hook")

    if hook_score.get("shareability", 0) < 5:
        suggestions.append("Tingkatkan shareability: tambahkan angle yang relatable atau kontroversi ringan")

    return total, issues, suggestions


def _check_structure(segments: list) -> tuple:
    """Cek kelengkapan struktur storytelling."""
    issues = []
    suggestions = []
    roles_present = {s.role for s in segments}
    required_roles = {"HOOK", "ESCALATION", "REVEAL"}

    missing = required_roles - roles_present
    if missing:
        issues.append(f"Segmen wajib tidak ada: {', '.join(missing)}")

    if "OPEN_LOOP" not in roles_present:
        suggestions.append("Tambahkan OPEN_LOOP untuk menciptakan curiosity gap yang lebih kuat")

    if "CTA" not in roles_present:
        suggestions.append("Tambahkan CTA di akhir untuk loop closure dan engagement")

    return issues, suggestions


def _check_pacing(segments: list) -> tuple:
    """Cek pacing dan durasi total."""
    issues = []
    suggestions = []

    total_dur = sum(s.duration_hint for s in segments)

    if total_dur < MIN_DURATION:
        issues.append(f"Script terlalu pendek: ~{total_dur:.0f}s (minimum {MIN_DURATION}s)")
    elif total_dur > MAX_DURATION:
        suggestions.append(f"Script mungkin terlalu panjang (~{total_dur:.0f}s). Pertimbangkan mempersingkat ESCALATION")

    # Cek proporsi hook (harus singkat)
    for seg in segments:
        if seg.role == "HOOK" and seg.duration_hint > 5.0:
            suggestions.append(f"Hook terlalu panjang (~{seg.duration_hint}s). Idealnya < 4 detik")

    # Cek proporsi reveal vs escalation
    escalation = next((s for s in segments if s.role == "ESCALATION"), None)
    reveal = next((s for s in segments if s.role == "REVEAL"), None)
    if escalation and reveal:
        if reveal.duration_hint < 8.0:
            suggestions.append("REVEAL terlalu singkat. Berikan ruang untuk payoff yang berkesan")

    return total_dur, issues, suggestions


def _check_content_quality(segments: list) -> tuple:
    """Cek kualitas teks secara heuristik."""
    issues = []
    suggestions = []

    for seg in segments:
        text = seg.text.lower()

        # Cek opening yang buruk
        if seg.role == "HOOK":
            bad_openers = ["hai", "halo", "selamat", "assalamu", "welcome", "di video ini"]
            for opener in bad_openers:
                if text.startswith(opener):
                    issues.append(f"Hook dimulai dengan '{opener}' — sangat merusak retensi 3 detik pertama")

        # Cek teks kosong
        if len(seg.text.strip()) < 10:
            issues.append(f"Segmen {seg.role} hampir kosong: '{seg.text[:30]}'")

        # Cek emoji di teks narasi
        if any(ord(c) > 127 and ord(c) not in range(0xC0, 0x250) for c in seg.text[:50]):
            suggestions.append(f"Segmen {seg.role} mengandung karakter non-ASCII. Hapus emoji dari narasi")

    return issues, suggestions


# ---------------------------------------------------------------------------
# AI-powered deep review (opsional, digunakan untuk script penting)
# ---------------------------------------------------------------------------

async def _ai_deep_review(script_text: str, channel_niche: str) -> dict:
    """
    Gunakan Gemini untuk review mendalam: apakah script ini benar-benar
    akan membuat orang terus menonton?
    """
    from video_builder import call_gemini_with_retry, clean_and_parse_json

    prompt = f"""You are a brutally honest TikTok retention expert reviewing a script for "{channel_niche}" content.

SCRIPT:
{script_text}

Analyze this script from a viewer retention perspective and return a JSON evaluation:
{{
  "retention_prediction": 65,
  "weakest_point": "ESCALATION section loses momentum after the second sentence",
  "strongest_point": "Hook creates genuine curiosity gap",
  "improvement_priority": "Rewrite ESCALATION to have a mini-revelation every 8 seconds",
  "pass": true
}}

Scoring criteria for "retention_prediction" (0-100):
- 80-100: Excellent, will likely get >60% retention
- 60-79: Good, average retention expected  
- 40-59: Weak, high drop-off risk
- 0-39: Poor, should be rewritten

Return only valid JSON."""

    try:
        raw = await call_gemini_with_retry(prompt, is_json=True, temperature=0.4)
        return clean_and_parse_json(raw)
    except Exception as e:
        logger.warning(f"[ScriptReviewer] AI deep review gagal: {e}")
        return {}


# ---------------------------------------------------------------------------
# Main review function
# ---------------------------------------------------------------------------

async def review_script(
    script,  # DirectedScript dari script_director
    use_ai_review: bool = False,
) -> ReviewResult:
    """
    Review script sebelum masuk render pipeline.

    Args:
        script: DirectedScript object dari script_director.direct_script()
        use_ai_review: Jika True, tambahkan review mendalam via Gemini (lebih lambat)

    Returns:
        ReviewResult — jika .passed = False, script harus diperbaiki atau digenerate ulang
    """
    all_issues = []
    all_suggestions = []
    scores = {}

    # 1. Hook strength check
    hook_total, hook_issues, hook_suggestions = _check_hook_strength(script.hook_score)
    all_issues.extend(hook_issues)
    all_suggestions.extend(hook_suggestions)
    scores["hook"] = min(100, int((hook_total / 50) * 100))

    # 2. Structure check
    struct_issues, struct_suggestions = _check_structure(script.segments)
    all_issues.extend(struct_issues)
    all_suggestions.extend(struct_suggestions)
    scores["structure"] = max(0, 100 - (len(struct_issues) * 25))

    # 3. Pacing check
    total_dur, pacing_issues, pacing_suggestions = _check_pacing(script.segments)
    all_issues.extend(pacing_issues)
    all_suggestions.extend(pacing_suggestions)
    # Pacing score berdasarkan proximity ke target 60 detik
    target = 60.0
    pacing_deviation = abs(total_dur - target) / target
    scores["pacing"] = max(0, int(100 - (pacing_deviation * 100)))

    # 4. Content quality check
    quality_issues, quality_suggestions = _check_content_quality(script.segments)
    all_issues.extend(quality_issues)
    all_suggestions.extend(quality_suggestions)
    scores["content_quality"] = max(0, 100 - (len(quality_issues) * 30))

    # 5. (Opsional) AI deep review
    ai_score = None
    if use_ai_review:
        logger.info("[ScriptReviewer] Menjalankan AI deep review...")
        ai_data = await _ai_deep_review(script.full_text, script.channel_niche)
        ai_score = ai_data.get("retention_prediction", None)
        if ai_data.get("weakest_point"):
            all_suggestions.append(f"[AI] {ai_data['weakest_point']}")
        if ai_data.get("improvement_priority"):
            all_suggestions.append(f"[AI Priority] {ai_data['improvement_priority']}")

    # Hitung total score (weighted average)
    weights = {"hook": 0.35, "structure": 0.25, "pacing": 0.20, "content_quality": 0.20}
    total_score = int(sum(scores[k] * weights[k] for k in scores))

    # Jika ada AI score, blend dengan rule-based score
    if ai_score is not None:
        total_score = int(total_score * 0.6 + ai_score * 0.4)
        scores["ai_retention_prediction"] = ai_score

    passed = (total_score >= MIN_TOTAL_REVIEW_SCORE) and (len(all_issues) == 0)

    result = ReviewResult(
        passed=passed,
        score=total_score,
        issues=all_issues,
        suggestions=all_suggestions,
        scores_breakdown=scores,
    )

    status = "LOLOS" if passed else "GAGAL"
    logger.info(
        f"[ScriptReviewer] {status} | Skor: {total_score}/100 | "
        f"Masalah: {len(all_issues)} | Saran: {len(all_suggestions)}"
    )
    if all_issues:
        for issue in all_issues:
            logger.warning(f"[ScriptReviewer] ISSUE: {issue}")

    return result
