"""
A/B Test Manager — Draft Mode Telegram
=======================================
Memanfaatkan hook_b dari Script Director untuk membuat DUA varian video
dengan hook berbeda, lalu mengirim keduanya ke Telegram sebagai DRAFT.
Bot menunggu keputusan manual dari operator (kamu) sebelum upload ke platform.

Cara kerja:
  1. Script Director menghasilkan hook_a (utama) + hook_b (alternatif)
  2. ab_test_manager merender video hook_a dari pipeline utama
  3. ab_test_manager menyimpan hook_b sebagai candidates untuk run berikutnya
  4. Keduanya dikirim ke Telegram dengan caption berbeda
  5. Operator menekan tombol "Upload V1" atau "Upload V2" dari chat Telegram
"""

import os
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("ai.ab_test_manager")

AB_CANDIDATES_PATH = os.path.join("data", "ab_hook_candidates.json")


# ---------------------------------------------------------------------------
# Simpan & ambil kandidat hook_b
# ---------------------------------------------------------------------------

def save_hook_b_candidate(hook_b: str, topic: str, channel_id: str, hook_a: str = ""):
    """Simpan hook_b sebagai kandidat untuk run A/B test berikutnya."""
    if not hook_b or hook_b in ("Tidak ada alternatif", "Hook Alternatif tidak tersedia"):
        return

    os.makedirs(os.path.dirname(AB_CANDIDATES_PATH), exist_ok=True)

    try:
        with open(AB_CANDIDATES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"candidates": []}

    entry = {
        "hook_b": hook_b,
        "hook_a": hook_a,
        "topic": topic,
        "channel_id": channel_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "used": False,
    }

    existing_hooks = {c["hook_b"] for c in data.get("candidates", [])}
    if hook_b not in existing_hooks:
        data.setdefault("candidates", []).append(entry)
        data["candidates"] = data["candidates"][-20:]

    with open(AB_CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"[ABTestManager] Hook B disimpan: '{hook_b[:60]}...'")


def get_unused_hook_candidate(channel_id: str = None):
    """Ambil kandidat hook_b yang belum pernah dipakai."""
    if not os.path.exists(AB_CANDIDATES_PATH):
        return None

    try:
        with open(AB_CANDIDATES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    for candidate in reversed(data.get("candidates", [])):
        if not candidate.get("used", False):
            if channel_id is None or candidate.get("channel_id") == channel_id:
                return candidate

    return None


def mark_candidate_used(hook_b: str):
    """Tandai kandidat sebagai sudah dipakai."""
    if not os.path.exists(AB_CANDIDATES_PATH):
        return
    try:
        with open(AB_CANDIDATES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for c in data.get("candidates", []):
            if c["hook_b"] == hook_b:
                c["used"] = True
        with open(AB_CANDIDATES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[ABTestManager] Gagal menandai kandidat: {e}")


# ---------------------------------------------------------------------------
# Format pesan Telegram Draft A/B
# ---------------------------------------------------------------------------

def format_ab_draft_captions(hook_a: str, hook_b: str, topic: str, caption: str):
    """Buat dua varian caption Telegram untuk A/B testing."""
    caption_v1 = (
        "\U0001f3ac <b>DRAFT VIDEO \u2014 Varian A (Hook Utama)</b>\n\n"
        f"\U0001f4cc <b>Topik:</b> <i>{topic}</i>\n\n"
        f"\U0001f525 <b>Hook A:</b>\n<code>{hook_a}</code>\n\n"
        f"\U0001f4dd <b>Caption Platform:</b>\n<i>{caption[:200]}</i>\n\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u2705 Tekan <b>Upload Varian A</b> untuk upload video ini\n"
        "\u23ed\ufe0f Tekan <b>Simpan Draft</b> untuk putuskan nanti"
    )
    caption_v2 = (
        "\u26a1 <b>HOOK ALTERNATIF \u2014 Varian B (A/B Test)</b>\n\n"
        f"\U0001f4cc <b>Topik:</b> <i>{topic}</i>\n\n"
        f"\U0001f9ea <b>Hook B:</b>\n<code>{hook_b}</code>\n\n"
        "\U0001f4ca <i>Hook ini berbeda angle. Akan otomatis dipakai di jadwal upload berikutnya.</i>"
    )
    return caption_v1, caption_v2


async def send_ab_draft_to_telegram(
    video_path: str,
    hook_a: str,
    hook_b: str,
    topic: str,
    caption: str,
    interactive_comment: str,
    channel_id: str,
    video_id: str,
    tags: list = None,
    category_id: str = "22",
    niche: str = "psychology",
    theme: str = "classic_yellow",
    yt_title: str = "",
    yt_description: str = "",
):
    """Kirim video draft ke Telegram dengan dual caption A/B."""
    from app import send_telegram_video_with_buttons, send_telegram_message
    import firebase_connector

    caption_v1, caption_v2 = format_ab_draft_captions(hook_a, hook_b, topic, caption)

    file_id = await send_telegram_video_with_buttons(
        video_path=video_path,
        caption=caption_v1,
        video_id=video_id,
    )

    if file_id:
        draft_data = {
            "video_id": video_id,
            "file_id": file_id,
            "caption": caption,
            "tags": tags or [],
            "category_id": category_id,
            "interactive_comment": interactive_comment,
            "hook": hook_a,
            "hook_b": hook_b,
            "drop_off_second": 0,
            "theme": theme,
            "niche": niche,
            "channel_id": channel_id,
            "yt_title": yt_title,
            "yt_description": yt_description,
            "ab_test_mode": True,
        }
        try:
            firebase_connector.save_video_draft(video_id, draft_data)
        except Exception as e:
            logger.warning(f"[ABTestManager] Gagal simpan draf: {e}")

    # Simpan hook_b sebagai kandidat run berikutnya
    save_hook_b_candidate(hook_b=hook_b, topic=topic, channel_id=channel_id, hook_a=hook_a)

    # Kirim info Varian B sebagai pesan teks terpisah
    send_telegram_message(caption_v2)

    logger.info("[ABTestManager] Draft A/B berhasil dikirim. Hook B disimpan untuk jadwal berikutnya.")
