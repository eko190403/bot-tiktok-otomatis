"""
Scene Director
==============
Mengubah script terstruktur menjadi storyboard visual yang lengkap.

Upgrade dari: Script → Image Prompt
Menjadi:      Script → Storyboard → Visual Scene

Setiap scene memiliki: durasi, emosi, tujuan, visual prompt, kamera, sound cue.
Tujuan: menghilangkan efek "AI slideshow" dan menciptakan visual storytelling.
"""

import logging
from typing import Optional

logger = logging.getLogger("ai.scene_director")

# Target jumlah scene per video
SCENES_PER_MINUTE = 3   # ~1 scene per 4-5 detik untuk pacing dinamis


class VisualScene:
    """Satu scene dalam storyboard visual."""

    def __init__(self, scene_index: int, script_role: str, duration: float,
                 emotion: str, narrative_goal: str, image_prompt: str,
                 camera_movement: str, sound_cue: str, color_mood: str):
        self.scene_index = scene_index
        self.script_role = script_role     # HOOK | OPEN_LOOP | ESCALATION | REVEAL | CTA
        self.duration = duration           # detik
        self.emotion = emotion             # suspense | calm | tense | strong | warm
        self.narrative_goal = narrative_goal  # "Buat penonton bertanya-tanya..."
        self.image_prompt = image_prompt   # prompt untuk text-to-image AI
        self.camera_movement = camera_movement  # zoom_in | pan_left | static | pull_back
        self.sound_cue = sound_cue         # ambient | tense_music | silence | impact
        self.color_mood = color_mood       # dark_blue | warm_gold | cold_grey | vibrant

    def to_dict(self) -> dict:
        return {
            "scene_index": self.scene_index,
            "script_role": self.script_role,
            "duration": self.duration,
            "emotion": self.emotion,
            "narrative_goal": self.narrative_goal,
            "image_prompt": self.image_prompt,
            "camera_movement": self.camera_movement,
            "sound_cue": self.sound_cue,
            "color_mood": self.color_mood,
        }

    def __repr__(self):
        return (f"<VisualScene #{self.scene_index} [{self.script_role}] "
                f"{self.duration}s cam={self.camera_movement}>")


class Storyboard:
    """Kumpulan scene yang membentuk video lengkap."""

    def __init__(self, topic: str, scenes: list, channel_aesthetic: str):
        self.topic = topic
        self.scenes = scenes
        self.channel_aesthetic = channel_aesthetic

    @property
    def total_duration(self) -> float:
        return sum(s.duration for s in self.scenes)

    @property
    def image_prompts(self) -> list:
        """Daftar image prompts siap dikirim ke ai_video_engine."""
        return [s.image_prompt for s in self.scenes]

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "channel_aesthetic": self.channel_aesthetic,
            "total_duration": self.total_duration,
            "scene_count": len(self.scenes),
            "scenes": [s.to_dict() for s in self.scenes],
        }


# ---------------------------------------------------------------------------
# Main director function
# ---------------------------------------------------------------------------

async def direct_scenes(
    script,              # DirectedScript dari script_director
    channel_aesthetic: str = "dark cinematic cold moody tone",
    channel_niche: str = "dark psychology and human behavior",
    target_scenes: Optional[int] = None,
) -> Optional[Storyboard]:
    """
    Ubah script terstruktur menjadi storyboard visual scene demi scene.

    Args:
        script: DirectedScript object dari script_director
        channel_aesthetic: Gaya visual channel (dari config)
        channel_niche: Niche channel (dari config)
        target_scenes: Jumlah scene target. Jika None, dihitung otomatis.

    Returns:
        Storyboard atau None jika gagal
    """
    from video_builder import call_gemini_with_retry, clean_and_parse_json

    if target_scenes is None:
        estimated_minutes = script.total_duration / 60.0
        target_scenes = max(5, int(estimated_minutes * SCENES_PER_MINUTE * 60 / 5))
        target_scenes = min(target_scenes, 15)  # cap 15 scene

    # Buat ringkasan script untuk prompt
    script_summary = "\n".join(
        f"[{seg.role}] ({seg.duration_hint:.0f}s, emotion={seg.emotion}): {seg.text[:120]}"
        for seg in script.segments
    )

    prompt = f"""You are a visual director for TikTok/YouTube Shorts videos about "{channel_niche}".
Channel aesthetic: "{channel_aesthetic}"
Topic: "{script.topic}"

Script breakdown:
{script_summary}

Create exactly {target_scenes} visual scenes that form a complete STORYBOARD.
Each scene must answer: "What should the viewer see at THIS exact moment?"

Rules for image prompts:
- Cinematic quality, photorealistic or stylized consistently
- No text, no subtitles, no UI in the images
- Each prompt must evoke the correct emotion for that script segment
- Consistent visual style across all scenes (use channel aesthetic)
- Include lighting direction, composition, atmosphere

Camera movements to use: zoom_in, zoom_out, pan_left, pan_right, pull_back, push_in, static, tilt_up, tilt_down

Return ONLY valid JSON:
{{
  "scenes": [
    {{
      "scene_index": 1,
      "script_role": "HOOK",
      "duration": 3.0,
      "emotion": "suspense",
      "narrative_goal": "Create immediate visual tension that matches the hook audio",
      "image_prompt": "cinematic close-up of a human eye reflecting city lights, dark atmosphere, shallow depth of field, dramatic lighting, ultra-detailed, photorealistic",
      "camera_movement": "zoom_in",
      "sound_cue": "tense_music",
      "color_mood": "dark_blue"
    }}
  ]
}}

Generate all {target_scenes} scenes. Return only valid JSON."""

    try:
        raw = await call_gemini_with_retry(prompt, is_json=True, temperature=0.80)
        data = clean_and_parse_json(raw)
    except Exception as e:
        logger.error(f"[SceneDirector] Gagal generate storyboard: {e}")
        return None

    if not isinstance(data, dict) or "scenes" not in data:
        logger.error(f"[SceneDirector] Format respons tidak valid")
        return None

    scenes = []
    for i, sc in enumerate(data.get("scenes", [])):
        try:
            scene = VisualScene(
                scene_index=sc.get("scene_index", i + 1),
                script_role=sc.get("script_role", "UNKNOWN"),
                duration=float(sc.get("duration", 5.0)),
                emotion=sc.get("emotion", "calm"),
                narrative_goal=sc.get("narrative_goal", ""),
                image_prompt=sc.get("image_prompt", ""),
                camera_movement=sc.get("camera_movement", "static"),
                sound_cue=sc.get("sound_cue", "ambient"),
                color_mood=sc.get("color_mood", "neutral"),
            )
            if scene.image_prompt:
                scenes.append(scene)
        except Exception as parse_err:
            logger.warning(f"[SceneDirector] Gagal parse scene {i}: {parse_err}")
            continue

    if not scenes:
        logger.error("[SceneDirector] Tidak ada scene yang berhasil diparsing")
        return None

    storyboard = Storyboard(
        topic=script.topic,
        scenes=scenes,
        channel_aesthetic=channel_aesthetic,
    )

    logger.info(
        f"[SceneDirector] Storyboard selesai | {len(scenes)} scene | "
        f"Total: ~{storyboard.total_duration:.0f}s"
    )
    return storyboard
