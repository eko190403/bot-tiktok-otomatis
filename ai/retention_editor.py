"""
Retention Editor
================
Pemeriksa video sebelum export.

Analisa:
  - 3 detik pertama (hook visual)
  - Perubahan visual antar scene (pacing)
  - Bagian yang lambat (low visual change)
  - Pacing keseluruhan
  - Ending loop

Perbaikan otomatis yang disarankan:
  - Cut bagian lambat
  - Tambah zoom
  - Ubah subtitle
  - Tambah pattern interrupt
"""

import logging
import json
from typing import Optional

logger = logging.getLogger("ai.retention_editor")

# Threshold pacing
MAX_SCENE_DURATION_BEFORE_CUT = 8.0   # scene lebih dari 8 detik berisiko drop-off
MIN_VISUAL_CHANGE_RATE = 0.15          # minimum 1 perubahan per ~6.7 detik
HOOK_MAX_DURATION = 4.0                # hook harus selesai dalam 4 detik


class RetentionAnalysis:
    """Hasil analisis retention editor."""

    def __init__(self, score: int, risk_points: list, auto_fixes: list,
                 ai_insights: dict, approved: bool):
        self.score = score             # 0-100
        self.risk_points = risk_points # Titik-titik risiko drop-off
        self.auto_fixes = auto_fixes   # Perbaikan yang direkomendasikan
        self.ai_insights = ai_insights # Insight dari Gemini (jika dipakai)
        self.approved = approved       # True jika layak export

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "approved": self.approved,
            "risk_points": self.risk_points,
            "auto_fixes": self.auto_fixes,
            "ai_insights": self.ai_insights,
        }

    def __repr__(self):
        status = "APPROVED" if self.approved else "NEEDS_FIX"
        return f"<RetentionAnalysis {status} score={self.score}/100 risks={len(self.risk_points)}>"


# ---------------------------------------------------------------------------
# Rule-based analysis
# ---------------------------------------------------------------------------

def _analyze_first_three_seconds(storyboard, voice_instructions: list) -> list:
    """Cek apakah 3 detik pertama cukup kuat untuk menahan penonton."""
    issues = []
    if not storyboard or not storyboard.scenes:
        issues.append({
            "type": "CRITICAL",
            "second": 0,
            "issue": "Tidak ada storyboard — tidak bisa menganalisis 3 detik pertama",
            "fix": "Jalankan scene_director terlebih dahulu",
        })
        return issues

    first_scene = storyboard.scenes[0]

    if first_scene.script_role != "HOOK":
        issues.append({
            "type": "WARNING",
            "second": 0,
            "issue": f"Scene pertama bukan HOOK (saat ini: {first_scene.script_role})",
            "fix": "Pastikan scene pertama berisi konten hook yang kuat",
        })

    if first_scene.duration > HOOK_MAX_DURATION:
        issues.append({
            "type": "WARNING",
            "second": 0,
            "issue": f"Hook visual terlalu panjang ({first_scene.duration}s > {HOOK_MAX_DURATION}s)",
            "fix": "Potong hook menjadi maksimal 4 detik, pindahkan sisa ke OPEN_LOOP",
        })

    if first_scene.camera_movement == "static":
        issues.append({
            "type": "TIP",
            "second": 0,
            "issue": "Hook menggunakan kamera statis — kurang dinamis untuk 3 detik pertama",
            "fix": "Ubah camera_movement hook menjadi 'zoom_in' atau 'push_in'",
        })

    return issues


def _analyze_pacing(storyboard) -> tuple:
    """Analisa pacing video — deteksi bagian yang terlalu lambat."""
    issues = []
    fixes = []
    current_time = 0.0

    if not storyboard:
        return issues, fixes

    for scene in storyboard.scenes:
        if scene.duration > MAX_SCENE_DURATION_BEFORE_CUT:
            issues.append({
                "type": "WARNING",
                "second": int(current_time),
                "issue": (
                    f"Scene #{scene.scene_index} ({scene.script_role}) terlalu panjang: "
                    f"{scene.duration:.1f}s (batas aman: {MAX_SCENE_DURATION_BEFORE_CUT}s)"
                ),
                "fix": f"Potong scene #{scene.scene_index} atau tambahkan B-roll/pattern interrupt di tengahnya",
            })
            fixes.append({
                "action": "ADD_BROLL",
                "scene_index": scene.scene_index,
                "at_second": int(current_time + MAX_SCENE_DURATION_BEFORE_CUT),
            })

        current_time += scene.duration

    # Cek total scene count vs durasi
    if storyboard.scenes:
        total_dur = sum(s.duration for s in storyboard.scenes)
        scene_count = len(storyboard.scenes)
        change_rate = scene_count / total_dur if total_dur > 0 else 0

        if change_rate < MIN_VISUAL_CHANGE_RATE:
            issues.append({
                "type": "WARNING",
                "second": 0,
                "issue": (
                    f"Perubahan visual terlalu jarang: {scene_count} scene dalam {total_dur:.0f}s "
                    f"(rate: {change_rate:.2f}, minimum: {MIN_VISUAL_CHANGE_RATE:.2f})"
                ),
                "fix": "Tambahkan lebih banyak scene atau pecah scene yang panjang menjadi beberapa shot",
            })

    return issues, fixes


def _analyze_ending(storyboard, script) -> list:
    """Cek apakah ending memiliki loop closure yang kuat."""
    issues = []

    # Cek CTA di script
    has_cta = any(seg.role == "CTA" for seg in script.segments) if script else False
    if not has_cta:
        issues.append({
            "type": "WARNING",
            "second": -1,
            "issue": "Tidak ada segmen CTA di script",
            "fix": "Tambahkan CTA singkat (3-5 detik) di akhir video untuk engagement",
        })

    # Cek ending scene
    if storyboard and storyboard.scenes:
        last_scene = storyboard.scenes[-1]
        if last_scene.camera_movement == "zoom_in":
            issues.append({
                "type": "TIP",
                "second": -1,
                "issue": "Ending menggunakan zoom_in — bisa terasa abrupt",
                "fix": "Ubah camera ending menjadi 'pull_back' atau 'static' untuk closure yang lebih halus",
            })

    return issues


def _calculate_retention_score(risk_points: list, total_scenes: int) -> int:
    """Hitung skor retention berdasarkan jumlah dan severity masalah."""
    score = 100
    for issue in risk_points:
        severity = issue.get("type", "TIP")
        if severity == "CRITICAL":
            score -= 30
        elif severity == "WARNING":
            score -= 12
        elif severity == "TIP":
            score -= 3

    # Bonus jika banyak scene (lebih dinamis)
    if total_scenes >= 8:
        score += 5
    elif total_scenes >= 12:
        score += 10

    return max(0, min(100, score))


# ---------------------------------------------------------------------------
# AI-powered deep analysis (opsional)
# ---------------------------------------------------------------------------

async def _ai_retention_analysis(script_text: str, scene_metadata: list,
                                   channel_niche: str) -> dict:
    """Gunakan Gemini untuk analisis retention mendalam berbasis konten."""
    from video_builder import call_gemini_with_retry, clean_and_parse_json

    scene_summary = "\n".join(
        f"Scene {s['scene_index']} ({s['duration']}s, {s['script_role']}): {s['narrative_goal'][:60]}"
        for s in scene_metadata[:10]
    )

    prompt = f"""You are a TikTok retention expert. Analyze this video for drop-off risks.

CHANNEL NICHE: {channel_niche}

SCRIPT (first 400 chars):
{script_text[:400]}

VISUAL SCENES:
{scene_summary}

Identify the 3 highest drop-off risks and suggest fixes. Return JSON:
{{
  "predicted_retention_rate": 0.65,
  "highest_risk_second": 15,
  "risk_reason": "ESCALATION section lacks a re-engagement hook at the 15-second mark",
  "pattern_interrupt_needed_at": [8, 20],
  "cta_strength": "weak",
  "recommendations": [
    "Add a question or reveal teaser at second 15 to re-engage viewers",
    "Speed up the pacing in seconds 20-30 with more scene cuts"
  ]
}}"""

    try:
        raw = await call_gemini_with_retry(prompt, is_json=True, temperature=0.4)
        return clean_and_parse_json(raw)
    except Exception as e:
        logger.warning(f"[RetentionEditor] AI analysis gagal: {e}")
        return {}


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

async def analyze_retention(
    script=None,
    storyboard=None,
    voice_instructions: Optional[list] = None,
    scene_metadata: Optional[list] = None,
    use_ai_analysis: bool = False,
    approval_threshold: int = 55,
) -> RetentionAnalysis:
    """
    Analisis retention video sebelum export.

    Args:
        script: DirectedScript dari script_director
        storyboard: Storyboard dari scene_director
        voice_instructions: Output dari voice_director.direct_voice()
        scene_metadata: Output dari visual_director.direct_visuals()["scene_metadata"]
        use_ai_analysis: Jika True, gunakan Gemini untuk analisis mendalam
        approval_threshold: Skor minimum untuk approve (default 55)

    Returns:
        RetentionAnalysis — jika .approved = False, video perlu perbaikan
    """
    all_risks = []
    all_fixes = []

    # 1. Analisis 3 detik pertama
    first3_issues = _analyze_first_three_seconds(storyboard, voice_instructions or [])
    all_risks.extend(first3_issues)

    # 2. Analisis pacing
    pacing_issues, pacing_fixes = _analyze_pacing(storyboard)
    all_risks.extend(pacing_issues)
    all_fixes.extend(pacing_fixes)

    # 3. Analisis ending
    ending_issues = _analyze_ending(storyboard, script)
    all_risks.extend(ending_issues)

    # 4. AI deep analysis (opsional)
    ai_insights = {}
    if use_ai_analysis and script and scene_metadata:
        logger.info("[RetentionEditor] Menjalankan AI retention analysis...")
        ai_insights = await _ai_retention_analysis(
            script_text=script.full_text,
            scene_metadata=scene_metadata,
            channel_niche=script.channel_niche,
        )

        # Tambah pattern interrupt recommendations ke fixes
        for second in ai_insights.get("pattern_interrupt_needed_at", []):
            all_fixes.append({
                "action": "ADD_PATTERN_INTERRUPT",
                "at_second": second,
            })

    # 5. Hitung skor
    total_scenes = len(storyboard.scenes) if storyboard else 0
    score = _calculate_retention_score(all_risks, total_scenes)

    # Blend dengan AI prediction jika ada
    if ai_insights.get("predicted_retention_rate"):
        ai_score = int(ai_insights["predicted_retention_rate"] * 100)
        score = int(score * 0.6 + ai_score * 0.4)

    approved = score >= approval_threshold and not any(
        r["type"] == "CRITICAL" for r in all_risks
    )

    result = RetentionAnalysis(
        score=score,
        risk_points=all_risks,
        auto_fixes=all_fixes,
        ai_insights=ai_insights,
        approved=approved,
    )

    status = "APPROVED" if approved else "NEEDS_FIX"
    logger.info(
        f"[RetentionEditor] {status} | Skor: {score}/100 | "
        f"Risiko: {len(all_risks)} | Fixes tersedia: {len(all_fixes)}"
    )

    for risk in all_risks:
        if risk["type"] == "CRITICAL":
            logger.error(f"[RetentionEditor] CRITICAL @ {risk['second']}s: {risk['issue']}")
        elif risk["type"] == "WARNING":
            logger.warning(f"[RetentionEditor] WARNING @ {risk['second']}s: {risk['issue']}")

    return result
