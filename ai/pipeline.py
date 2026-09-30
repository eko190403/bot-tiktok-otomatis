"""
AI Content Pipeline — Orchestrator
====================================
Menjalankan pipeline penuh dari TOPIC sampai RENDER-READY output.

Alur:
  TOPIC
   └─► script_director  (buat script terstruktur)
   └─► script_reviewer  (validasi sebelum lanjut)
   └─► scene_director   (buat storyboard visual)
   └─► visual_director  (perkaya prompt & kamera)
   └─► voice_director   (instruksi suara emosional)
   └─► retention_editor (analisis drop-off risk)
   └─► return RenderPayload (siap masuk video_builder)
"""

import logging
import asyncio
from typing import Optional

logger = logging.getLogger("ai.pipeline")

MAX_SCRIPT_RETRIES = 3   # Coba generate ulang script jika review gagal


class RenderPayload:
    """
    Output akhir dari AI pipeline — siap dikirim ke video_builder.
    Berisi semua data yang dibutuhkan untuk merender video.
    """

    def __init__(
        self,
        topic: str,
        script,              # DirectedScript
        storyboard,          # Storyboard
        visual_data: dict,   # Output visual_director.direct_visuals()
        voice_instructions: list,
        retention_analysis,  # RetentionAnalysis
        full_narration_text: str,
        hook_text: str,
        hook_b: str = "",
    ):
        self.topic = topic
        self.script = script
        self.storyboard = storyboard
        self.visual_data = visual_data
        self.voice_instructions = voice_instructions
        self.retention_analysis = retention_analysis
        self.full_narration_text = full_narration_text
        self.hook_text = hook_text
        self.hook_b = hook_b

        # Shortcut ke data yang paling sering dipakai
        self.image_prompts = visual_data.get("enhanced_prompts", [])
        self.ffmpeg_filters = visual_data.get("ffmpeg_filters", [])
        self.scene_metadata = visual_data.get("scene_metadata", [])

    def to_summary(self) -> dict:
        return {
            "topic": self.topic,
            "hook": self.hook_text,
            "segment_count": len(self.script.segments),
            "scene_count": len(self.storyboard.scenes),
            "estimated_duration": self.script.total_duration,
            "hook_score_total": sum(self.script.hook_score.values()),
            "retention_score": self.retention_analysis.score,
            "retention_approved": self.retention_analysis.approved,
            "image_prompts_count": len(self.image_prompts),
        }

    def __repr__(self):
        return (
            f"<RenderPayload topic='{self.topic[:40]}' "
            f"scenes={len(self.storyboard.scenes)} "
            f"retention={self.retention_analysis.score}/100>"
        )


async def run_ai_pipeline(
    topic: str,
    channel_config: dict,
    performance_hints: Optional[str] = None,
    use_ai_review: bool = False,
    use_ai_retention: bool = False,
) -> Optional[RenderPayload]:
    """
    Jalankan pipeline AI intelligence penuh untuk satu topik.

    Args:
        topic: Topik video yang akan dibuat
        channel_config: Dict config channel (dari config.get_channel_config())
        performance_hints: String insight dari analytics_brain (opsional)
        use_ai_review: Aktifkan AI-powered script review (lebih lambat)
        use_ai_retention: Aktifkan AI-powered retention analysis (lebih lambat)

    Returns:
        RenderPayload siap masuk ke video_builder, atau None jika pipeline gagal
    """
    from ai.script_director import direct_script
    from ai.script_reviewer import review_script
    from ai.scene_director import direct_scenes
    from ai.visual_director import direct_visuals
    from ai.voice_director import direct_voice, build_full_tts_text
    from ai.retention_editor import analyze_retention

    channel_niche = channel_config.get("niche", "dark psychology and human behavior")
    channel_name  = channel_config.get("name", "Ruang Pikir")
    aesthetic     = channel_config.get("aesthetic_query", "dark cinematic cold moody tone")

    # ─────────────────────────────────────────────
    # PHASE 1: Script Director + Reviewer
    # ─────────────────────────────────────────────
    script = None
    review = None

    for attempt in range(1, MAX_SCRIPT_RETRIES + 1):
        logger.info(f"[Pipeline] Phase 1 — Script Director (attempt {attempt}/{MAX_SCRIPT_RETRIES})")

        script = await direct_script(
            topic=topic,
            channel_niche=channel_niche,
            channel_name=channel_name,
            performance_hints=performance_hints,
        )
        if not script:
            logger.error(f"[Pipeline] Script Director gagal (attempt {attempt})")
            continue

        logger.info(f"[Pipeline] Phase 1 — Script Reviewer")
        review = await review_script(script, use_ai_review=use_ai_review)

        if review.passed:
            logger.info(f"[Pipeline] Script LOLOS review (skor {review.score}/100)")
            break
        else:
            logger.warning(
                f"[Pipeline] Script GAGAL review (skor {review.score}/100). "
                f"Issues: {review.issues}. Retry {attempt}/{MAX_SCRIPT_RETRIES}..."
            )
            # Tambahkan issue ke hints untuk retry berikutnya
            issue_hints = " ".join(review.issues)
            performance_hints = (performance_hints or "") + f"\nHindari masalah ini: {issue_hints}"
            script = None  # reset untuk generate ulang

    if not script:
        logger.error(f"[Pipeline] Script gagal setelah {MAX_SCRIPT_RETRIES} percobaan. Abort.")
        return None

    # ─────────────────────────────────────────────
    # PHASE 2: Scene Director + Visual Director
    # ─────────────────────────────────────────────
    logger.info("[Pipeline] Phase 2 — Scene Director")
    storyboard = await direct_scenes(
        script=script,
        channel_aesthetic=aesthetic,
        channel_niche=channel_niche,
    )
    if not storyboard:
        logger.error("[Pipeline] Scene Director gagal. Abort.")
        return None

    logger.info("[Pipeline] Phase 2 — Visual Director")
    visual_data = direct_visuals(storyboard, channel_aesthetic=aesthetic)

    # ─────────────────────────────────────────────
    # PHASE 3: Voice Director
    # ─────────────────────────────────────────────
    logger.info("[Pipeline] Phase 3 — Voice Director")
    voice_instructions = direct_voice(script)
    full_narration_text = build_full_tts_text(voice_instructions)

    # ─────────────────────────────────────────────
    # PHASE 4: Retention Editor
    # ─────────────────────────────────────────────
    logger.info("[Pipeline] Phase 4 — Retention Editor")
    retention_analysis = await analyze_retention(
        script=script,
        storyboard=storyboard,
        voice_instructions=voice_instructions,
        scene_metadata=visual_data.get("scene_metadata"),
        use_ai_analysis=use_ai_retention,
    )

    if not retention_analysis.approved:
        logger.warning(
            f"[Pipeline] Retention Editor: Video BELUM optimal (skor {retention_analysis.score}/100). "
            f"Quand meme, lanjut render dengan catatan perbaikan:"
        )
        for fix in retention_analysis.auto_fixes:
            logger.warning(f"[Pipeline]   Fix: {fix}")
    else:
        logger.info(f"[Pipeline] Retention Editor: APPROVED (skor {retention_analysis.score}/100)")

    # ─────────────────────────────────────────────
    # FINAL: Assemble RenderPayload
    # ─────────────────────────────────────────────
    payload = RenderPayload(
        topic=topic,
        script=script,
        storyboard=storyboard,
        visual_data=visual_data,
        voice_instructions=voice_instructions,
        retention_analysis=retention_analysis,
        full_narration_text=full_narration_text,
        hook_text=script.hook_text,
        hook_b=getattr(script, "hook_b", ""),
    )

    summary = payload.to_summary()
    logger.info(
        f"[Pipeline] ✅ Pipeline selesai!\n"
        f"  Topic     : {summary['topic']}\n"
        f"  Hook      : {summary['hook'][:60]}\n"
        f"  Scenes    : {summary['scene_count']}\n"
        f"  Duration  : ~{summary['estimated_duration']:.0f}s\n"
        f"  Hook Score: {summary['hook_score_total']}/50\n"
        f"  Retention : {summary['retention_score']}/100 ({'✅' if summary['retention_approved'] else '⚠️'})"
    )

    return payload
