"""
Visual Director
===============
Menetapkan standar visual konsisten untuk seluruh video.

Setiap scene harus menjawab:
  "Apa yang harus dilihat penonton pada detik ini?"

Modul ini:
1. Memperkaya image prompts dari scene_director dengan standar sinematik
2. Memastikan konsistensi warna dan mood antar scene
3. Menambahkan arahan kamera yang konkret ke metadata FFmpeg
"""

import logging
from typing import Optional

logger = logging.getLogger("ai.visual_director")


# ---------------------------------------------------------------------------
# Visual Style Library
# ---------------------------------------------------------------------------

VISUAL_STYLES = {
    "dark_cinematic": {
        "base_prompt_suffix": (
            "cinematic color grading, dark moody atmosphere, teal and orange color palette, "
            "dramatic volumetric lighting, film grain, anamorphic lens, "
            "ultra-detailed, 8K resolution, professional photography"
        ),
        "negative_prompt": "cartoon, anime, watermark, text, logo, blurry, low quality",
        "color_grade": "teal_orange",
        "contrast": "high",
    },
    "warm_storytelling": {
        "base_prompt_suffix": (
            "warm golden hour lighting, shallow depth of field, bokeh background, "
            "intimate close-up composition, soft shadows, cinematic aspect ratio, "
            "photorealistic, 4K"
        ),
        "negative_prompt": "cold, dark, horror, watermark, text",
        "color_grade": "warm_gold",
        "contrast": "medium",
    },
    "cold_psychology": {
        "base_prompt_suffix": (
            "cold blue-grey color palette, high contrast, stark lighting, "
            "minimalist composition, shadows and depth, psychological thriller aesthetic, "
            "cinematic, photorealistic"
        ),
        "negative_prompt": "warm colors, happy, cheerful, watermark, text",
        "color_grade": "cold_grey",
        "contrast": "high",
    },
    "mystery_conspiracy": {
        "base_prompt_suffix": (
            "dark vignette, mysterious atmosphere, deep shadows, single dramatic light source, "
            "documentary-style realism, gritty texture, muted desaturated colors with accent highlights"
        ),
        "negative_prompt": "bright, colorful, cartoon, text, watermark",
        "color_grade": "dark_muted",
        "contrast": "very_high",
    },
}

# Mapping dari aesthetic string channel ke visual style
AESTHETIC_TO_STYLE = {
    "dark cinematic cold moody": "cold_psychology",
    "dark cinematic": "dark_cinematic",
    "warm storytelling": "warm_storytelling",
    "mystery": "mystery_conspiracy",
    "psychology": "cold_psychology",
    "finance": "warm_storytelling",
    "comedy": "warm_storytelling",
    "horror": "mystery_conspiracy",
}

# Mapping camera movement ke filter FFmpeg
CAMERA_TO_FFMPEG = {
    "zoom_in":   "zoompan=z='min(zoom+0.002,1.5)':d=25*{dur}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    "zoom_out":  "zoompan=z='if(lte(zoom,1.0),1.5,max(1.0,zoom-0.002))':d=25*{dur}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    "pan_left":  "zoompan=z='1.2':d=25*{dur}:x='iw*0.3-iw*0.3*on/(25*{dur})':y='ih/2-(ih/zoom/2)'",
    "pan_right": "zoompan=z='1.2':d=25*{dur}:x='iw*0.3*on/(25*{dur})':y='ih/2-(ih/zoom/2)'",
    "pull_back": "zoompan=z='max(1.0,1.5-0.002*on)':d=25*{dur}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    "push_in":   "zoompan=z='min(1.0+0.002*on,1.5)':d=25*{dur}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    "tilt_up":   "zoompan=z='1.2':d=25*{dur}:x='iw/2-(iw/zoom/2)':y='ih*0.4-ih*0.2*on/(25*{dur})'",
    "tilt_down": "zoompan=z='1.2':d=25*{dur}:x='iw/2-(iw/zoom/2)':y='ih*0.2+ih*0.2*on/(25*{dur})'",
    "static":    "zoompan=z='1.05':d=25*{dur}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def resolve_visual_style(channel_aesthetic: str) -> dict:
    """
    Tentukan visual style yang tepat berdasarkan aesthetic string channel.
    Returns style dict dari VISUAL_STYLES.
    """
    aesthetic_lower = channel_aesthetic.lower()
    for key, style_name in AESTHETIC_TO_STYLE.items():
        if key in aesthetic_lower:
            style = VISUAL_STYLES.get(style_name, VISUAL_STYLES["dark_cinematic"])
            logger.info(f"[VisualDirector] Style terpilih: '{style_name}' untuk aesthetic '{channel_aesthetic}'")
            return style

    # Default fallback
    logger.info(f"[VisualDirector] Aesthetic tidak dikenali, menggunakan dark_cinematic sebagai default")
    return VISUAL_STYLES["dark_cinematic"]


def enhance_image_prompt(raw_prompt: str, visual_style: dict, emotion: str,
                          color_mood: str) -> str:
    """
    Perkaya raw image prompt dari scene_director dengan standar sinematik.

    Args:
        raw_prompt: Prompt mentah dari scene_director
        visual_style: Style dict dari resolve_visual_style()
        emotion: Emosi scene (suspense, calm, tense, strong, warm)
        color_mood: Mood warna (dark_blue, warm_gold, cold_grey, dll)

    Returns:
        Enhanced prompt yang lebih cinematic dan konsisten
    """
    emotion_modifiers = {
        "suspense": "tense atmosphere, foreboding, dark undertones",
        "tense": "high tension, dramatic, claustrophobic framing",
        "calm": "peaceful, serene, balanced composition",
        "strong": "powerful, bold, dominant composition, impact",
        "warm": "inviting, intimate, golden warmth",
    }

    color_modifiers = {
        "dark_blue": "deep blue shadows, midnight tones, cool highlights",
        "warm_gold": "golden hour, amber tones, warm backlighting",
        "cold_grey": "desaturated palette, steel grey, clinical coldness",
        "dark_muted": "muted earth tones, dark vignette, desaturated",
        "neutral": "",
    }

    emotion_mod = emotion_modifiers.get(emotion, "")
    color_mod = color_modifiers.get(color_mood, "")
    style_suffix = visual_style.get("base_prompt_suffix", "")

    parts = [raw_prompt.strip()]
    if emotion_mod:
        parts.append(emotion_mod)
    if color_mod:
        parts.append(color_mod)
    if style_suffix:
        parts.append(style_suffix)

    return ", ".join(filter(bool, parts))


def get_ffmpeg_filter(camera_movement: str, duration: float) -> str:
    """
    Hasilkan filter string FFmpeg untuk gerakan kamera tertentu.

    Args:
        camera_movement: Nama gerakan (zoom_in, pan_left, dll)
        duration: Durasi scene dalam detik

    Returns:
        String filter FFmpeg yang siap digunakan
    """
    template = CAMERA_TO_FFMPEG.get(camera_movement, CAMERA_TO_FFMPEG["static"])
    dur_int = max(1, int(duration))
    return template.replace("{dur}", str(dur_int))


def direct_visuals(storyboard, channel_aesthetic: str) -> dict:
    """
    Terapkan standar visual ke seluruh storyboard.
    Ini adalah fungsi SINKRON (tanpa async) karena tidak perlu AI call.

    Args:
        storyboard: Storyboard object dari scene_director
        channel_aesthetic: String aesthetic channel dari config

    Returns:
        Dict berisi:
          - enhanced_prompts: List prompt yang sudah diperkaya
          - ffmpeg_filters: List filter FFmpeg per scene
          - visual_style: Style yang digunakan
          - scene_metadata: Metadata lengkap per scene
    """
    visual_style = resolve_visual_style(channel_aesthetic)

    enhanced_prompts = []
    ffmpeg_filters = []
    scene_metadata = []

    for scene in storyboard.scenes:
        # Perkaya prompt
        ep = enhance_image_prompt(
            raw_prompt=scene.image_prompt,
            visual_style=visual_style,
            emotion=scene.emotion,
            color_mood=scene.color_mood,
        )
        enhanced_prompts.append(ep)

        # Buat FFmpeg filter
        ff = get_ffmpeg_filter(scene.camera_movement, scene.duration)
        ffmpeg_filters.append(ff)

        # Metadata lengkap per scene
        scene_metadata.append({
            "scene_index": scene.scene_index,
            "script_role": scene.script_role,
            "duration": scene.duration,
            "emotion": scene.emotion,
            "enhanced_prompt": ep,
            "camera_movement": scene.camera_movement,
            "ffmpeg_filter": ff,
            "sound_cue": scene.sound_cue,
            "color_mood": scene.color_mood,
            "narrative_goal": scene.narrative_goal,
        })

    logger.info(
        f"[VisualDirector] {len(scene_metadata)} scene diperkaya dengan standar visual "
        f"'{channel_aesthetic}'"
    )

    return {
        "enhanced_prompts": enhanced_prompts,
        "ffmpeg_filters": ffmpeg_filters,
        "visual_style": visual_style,
        "scene_metadata": scene_metadata,
    }
