"""
Analytics Brain
===============
Mengubah analytics dari pencatat data menjadi sistem pembelajaran.

Pipeline:
  Video → Analisa → Kesimpulan → Update Prompt → Video Berikutnya

Data yang diproses:
  - Retention rate & watch time
  - Drop-off point
  - Komentar (sentiment & topik)
  - Share & replay
  - Hook performance

Output:
  - performance_hints: String ringkasan untuk script_director
  - hook_insights: Data historis untuk hook laboratory
  - topic_recommendations: Topik konten berikutnya
  - improvement_prompt: Instruksi untuk memperbaiki video berikutnya
"""

import os
import json
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("ai.analytics_brain")

# Path penyimpanan lokal data pembelajaran
BRAIN_DATA_PATH = os.path.join("data", "analytics_brain.json")
MAX_HISTORY_ENTRIES = 200   # Batasi agar file tidak terlalu besar


# ---------------------------------------------------------------------------
# Data I/O — local JSON store
# ---------------------------------------------------------------------------

def _load_brain_data() -> dict:
    """Load data historis dari file lokal."""
    if not os.path.exists(BRAIN_DATA_PATH):
        return {
            "video_performances": [],
            "hook_performances": [],
            "topic_performances": [],
            "last_updated": None,
        }
    try:
        with open(BRAIN_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[AnalyticsBrain] Gagal load brain data: {e}")
        return {"video_performances": [], "hook_performances": [], "topic_performances": [], "last_updated": None}


def _save_brain_data(data: dict):
    """Simpan data pembelajaran ke file lokal."""
    os.makedirs(os.path.dirname(BRAIN_DATA_PATH), exist_ok=True)
    try:
        # Batasi ukuran history
        for key in ("video_performances", "hook_performances", "topic_performances"):
            if len(data.get(key, [])) > MAX_HISTORY_ENTRIES:
                data[key] = data[key][-MAX_HISTORY_ENTRIES:]

        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(BRAIN_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[AnalyticsBrain] Data pembelajaran disimpan ke {BRAIN_DATA_PATH}")
    except Exception as e:
        logger.error(f"[AnalyticsBrain] Gagal simpan brain data: {e}")


# ---------------------------------------------------------------------------
# Data ingestion — simpan performa video baru
# ---------------------------------------------------------------------------

def record_video_performance(
    video_id: str,
    hook_text: str,
    topic: str,
    channel_id: str,
    views: int,
    likes: int,
    comments: list,
    drop_off_second: int = 0,
    watch_time_avg: float = 0.0,
    shares: int = 0,
    replays: int = 0,
    hook_score: Optional[dict] = None,
):
    """
    Catat performa satu video ke dalam analytics brain.
    Dipanggil setelah data dari YouTube/TikTok berhasil diambil.
    """
    brain = _load_brain_data()

    # Hitung retention rate heuristik
    video_duration_est = 60.0
    retention_rate = min(1.0, watch_time_avg / video_duration_est) if watch_time_avg > 0 else (
        min(1.0, drop_off_second / video_duration_est) if drop_off_second > 0 else 0.0
    )

    # Like rate
    like_rate = likes / views if views > 0 else 0.0

    entry = {
        "video_id": video_id,
        "hook_text": hook_text,
        "topic": topic,
        "channel_id": channel_id,
        "views": views,
        "likes": likes,
        "shares": shares,
        "replays": replays,
        "comment_count": len(comments),
        "drop_off_second": drop_off_second,
        "watch_time_avg": watch_time_avg,
        "retention_rate": retention_rate,
        "like_rate": like_rate,
        "hook_score": hook_score or {},
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }

    brain["video_performances"].append(entry)

    # Simpan juga ke hook_performances untuk Hook Laboratory
    if hook_text:
        brain["hook_performances"].append({
            "hook": hook_text,
            "topic": topic,
            "channel_id": channel_id,
            "avg_retention": retention_rate,
            "like_rate": like_rate,
            "views": views,
        })

    # Simpan ke topic_performances
    brain["topic_performances"].append({
        "topic": topic,
        "channel_id": channel_id,
        "retention_rate": retention_rate,
        "like_rate": like_rate,
        "views": views,
    })

    _save_brain_data(brain)
    logger.info(
        f"[AnalyticsBrain] Performa dicatat | Video: {video_id} | "
        f"Retention: {retention_rate:.0%} | Like Rate: {like_rate:.2%}"
    )


# ---------------------------------------------------------------------------
# Learning functions — hasilkan insight dari data historis
# ---------------------------------------------------------------------------

def get_best_hooks(channel_id: Optional[str] = None, top_n: int = 10) -> list:
    """
    Ambil hook-hook terbaik berdasarkan retention rate historis.
    Digunakan oleh Hook Laboratory di script_director.
    """
    brain = _load_brain_data()
    hooks = brain.get("hook_performances", [])

    if channel_id:
        hooks = [h for h in hooks if h.get("channel_id") == channel_id]

    # Sort berdasarkan gabungan retention + like rate
    hooks.sort(
        key=lambda h: (h.get("avg_retention", 0) * 0.7 + h.get("like_rate", 0) * 30 * 0.3),
        reverse=True
    )

    return hooks[:top_n]


def get_worst_drop_off_patterns(channel_id: Optional[str] = None) -> list:
    """
    Temukan pola-pola yang menyebabkan drop-off cepat.
    Berguna untuk menghindari kesalahan yang sama.
    """
    brain = _load_brain_data()
    videos = brain.get("video_performances", [])

    if channel_id:
        videos = [v for v in videos if v.get("channel_id") == channel_id]

    # Filter video dengan retention rendah (< 40%)
    bad_videos = [v for v in videos if v.get("retention_rate", 1.0) < 0.40]
    bad_videos.sort(key=lambda v: v.get("retention_rate", 1.0))

    return bad_videos[:10]


def get_best_topics(channel_id: Optional[str] = None, top_n: int = 5) -> list:
    """Ambil topik-topik yang menghasilkan performa terbaik."""
    brain = _load_brain_data()
    topics = brain.get("topic_performances", [])

    if channel_id:
        topics = [t for t in topics if t.get("channel_id") == channel_id]

    # Grup per topik dan rata-rata skornya
    topic_map = {}
    for t in topics:
        key = t["topic"]
        if key not in topic_map:
            topic_map[key] = {"topic": key, "scores": [], "total_views": 0}
        topic_map[key]["scores"].append(t.get("retention_rate", 0))
        topic_map[key]["total_views"] += t.get("views", 0)

    topic_list = []
    for key, val in topic_map.items():
        scores = val["scores"]
        avg = sum(scores) / len(scores) if scores else 0
        topic_list.append({
            "topic": key,
            "avg_retention": avg,
            "total_views": val["total_views"],
            "sample_count": len(scores),
        })

    topic_list.sort(key=lambda t: t["avg_retention"] * 0.6 + (t["total_views"] / 10000) * 0.4, reverse=True)
    return topic_list[:top_n]


# ---------------------------------------------------------------------------
# AI synthesis — buat performance_hints untuk script_director
# ---------------------------------------------------------------------------

async def synthesize_performance_hints(
    channel_id: Optional[str] = None,
    channel_niche: str = "dark psychology",
) -> str:
    """
    Gunakan Gemini untuk mensintesis data historis menjadi
    performance_hints yang bisa langsung dipakai oleh script_director.

    Returns:
        String hints dalam Bahasa Indonesia, siap dipakai sebagai konteks Gemini
    """
    from video_builder import call_gemini_with_retry

    best_hooks = get_best_hooks(channel_id, top_n=5)
    worst_patterns = get_worst_drop_off_patterns(channel_id)
    best_topics = get_best_topics(channel_id, top_n=5)

    if not best_hooks and not worst_patterns and not best_topics:
        logger.info("[AnalyticsBrain] Belum ada data performa yang cukup untuk sintesis")
        return ""

    # Format data untuk prompt
    hooks_text = "\n".join(
        f"- \"{h['hook']}\" → retention {h.get('avg_retention', 0):.0%}"
        for h in best_hooks
    ) or "(belum ada data)"

    bad_text = "\n".join(
        f"- \"{v['hook_text'][:60]}\" → drop-off di detik {v.get('drop_off_second', '?')}"
        for v in worst_patterns
    ) or "(belum ada data)"

    topics_text = "\n".join(
        f"- \"{t['topic']}\" → avg retention {t.get('avg_retention', 0):.0%} ({t['total_views']} views)"
        for t in best_topics
    ) or "(belum ada data)"

    prompt = f"""You are analyzing historical video performance data for a "{channel_niche}" TikTok/YouTube channel.

BEST PERFORMING HOOKS (high retention):
{hooks_text}

WORST PERFORMING VIDEOS (low retention / early drop-off):
{bad_text}

BEST PERFORMING TOPICS:
{topics_text}

Based on this data, write a SHORT performance insight summary (3-5 sentences max) in Bahasa Indonesia.
Focus on:
1. What makes hooks work for this channel's audience
2. What to AVOID (patterns that cause early drop-off)
3. Which topic angles have proven most effective

Write as direct instructions for a script writer. Be specific and actionable.
Do NOT use JSON. Just plain text."""

    try:
        hints = await call_gemini_with_retry(prompt, is_json=False, temperature=0.4)
        logger.info(f"[AnalyticsBrain] Performance hints disintesis ({len(hints)} karakter)")
        return hints.strip()
    except Exception as e:
        logger.error(f"[AnalyticsBrain] Gagal sintesis hints: {e}")
        # Fallback: buat hints manual dari data
        return _manual_hints(best_hooks, worst_patterns, best_topics)


def _manual_hints(best_hooks: list, worst_patterns: list, best_topics: list) -> str:
    """Fallback: buat hints tanpa AI."""
    lines = []
    if best_hooks:
        lines.append(f"Hook terbaik menghasilkan retention tinggi: \"{best_hooks[0]['hook'][:80]}\"")
    if worst_patterns:
        lines.append(f"Hindari hook yang menyebabkan drop-off cepat seperti: \"{worst_patterns[0]['hook_text'][:60]}\"")
    if best_topics:
        lines.append(f"Topik yang paling efektif: {', '.join(t['topic'] for t in best_topics[:3])}")
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Topic recommendation
# ---------------------------------------------------------------------------

async def recommend_next_topics(
    channel_niche: str,
    channel_id: Optional[str] = None,
    count: int = 5,
) -> list:
    """
    Rekomendasikan topik konten berikutnya berdasarkan:
    1. Performa historis topik serupa
    2. Komentar terbaru penonton
    3. Tren saat ini

    Returns:
        List dict topik rekomendasi: [{"topic": "...", "rationale": "...", "priority": 8}, ...]
    """
    from video_builder import call_gemini_with_retry, clean_and_parse_json, get_indonesia_trending_searches

    best_topics = get_best_topics(channel_id, top_n=5)
    trends = get_indonesia_trending_searches()

    topics_text = "\n".join(f"- {t['topic']} (retention {t.get('avg_retention',0):.0%})" for t in best_topics) or "(belum ada data)"
    trends_text = "\n".join(f"- {t}" for t in trends) or "(tidak tersedia)"

    prompt = f"""You are a content strategist for a "{channel_niche}" TikTok/YouTube channel.

TOP PERFORMING PAST TOPICS:
{topics_text}

CURRENT INDONESIA TRENDING SEARCHES:
{trends_text}

Recommend {count} new video topics that:
1. Match the channel niche "{channel_niche}"
2. Build on what has worked (based on past performance)
3. Potentially intersect with current trends where relevant

Return ONLY valid JSON:
{{
  "recommendations": [
    {{
      "topic": "Rahasia di Balik Diam: Kenapa Orang Pendiam Justru Lebih Berbahaya",
      "rationale": "Topik psikologi populer yang belum dibahas, berpotensi viral karena relatable",
      "priority": 9,
      "hook_angle": "curiosity_gap"
    }}
  ]
}}

All topics in Bahasa Indonesia. Return only JSON."""

    try:
        raw = await call_gemini_with_retry(prompt, is_json=True, temperature=0.85)
        data = clean_and_parse_json(raw)
        recs = data.get("recommendations", [])
        recs.sort(key=lambda r: r.get("priority", 0), reverse=True)
        logger.info(f"[AnalyticsBrain] {len(recs)} rekomendasi topik digenerate")
        return recs
    except Exception as e:
        logger.error(f"[AnalyticsBrain] Gagal generate topic recommendations: {e}")
        return []


# ---------------------------------------------------------------------------
# Full learning loop — dipanggil setelah analytics sync
# ---------------------------------------------------------------------------

async def run_learning_loop(channel_id: str, channel_niche: str) -> dict:
    """
    Jalankan full learning loop setelah data analytics terbaru masuk.

    Menghasilkan:
      - performance_hints: untuk script_director
      - best_hooks: untuk Hook Laboratory
      - topic_recommendations: untuk pipeline berikutnya

    Returns:
        Dict dengan semua output learning loop
    """
    logger.info(f"[AnalyticsBrain] Memulai learning loop untuk channel '{channel_id}'...")

    # Jalankan secara paralel
    hints_task = asyncio.create_task(
        synthesize_performance_hints(channel_id, channel_niche)
    )
    topics_task = asyncio.create_task(
        recommend_next_topics(channel_niche, channel_id, count=5)
    )

    hints = await hints_task
    topics = await topics_task
    best_hooks = get_best_hooks(channel_id, top_n=10)

    result = {
        "channel_id": channel_id,
        "performance_hints": hints,
        "best_hooks": best_hooks,
        "topic_recommendations": topics,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        f"[AnalyticsBrain] Learning loop selesai | "
        f"Hints: {len(hints)} char | "
        f"Best hooks: {len(best_hooks)} | "
        f"Topic recs: {len(topics)}"
    )

    return result
