import os
import time
import logging

logger = logging.getLogger("bot")

db = None
is_firebase_enabled = False

try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    cred_file = "firebase_service_account.json"
    if os.path.exists(cred_file):
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_file)
                firebase_admin.initialize_app(cred)
            db = firestore.client()
            is_firebase_enabled = True
            logger.info("🔥 Firebase initialized. Firestore aktif sebagai single source of truth.")
        except Exception as e:
            logger.error(f"❌ Gagal inisialisasi Firebase Admin SDK: {e}")
    else:
        logger.warning("⚠️ firebase_service_account.json tidak ditemukan. Firestore tidak aktif — pipeline akan berhenti jika mencoba akses DB.")
except ImportError:
    logger.warning("⚠️ Pustaka 'firebase-admin' belum terpasang. Firestore tidak aktif.")


def _require_firestore(func_name: str) -> bool:
    """Cek apakah Firestore aktif. Log error dan return False jika tidak."""
    if not is_firebase_enabled or db is None:
        logger.error(f"❌ [{func_name}] Firestore tidak aktif. Operasi dibatalkan.")
        return False
    return True


# ─────────────────────────────────────────────
# HISTORY (anti-duplikasi naskah)
# ─────────────────────────────────────────────

def get_recent_history(limit: int = 25) -> list:
    """Mengambil riwayat naskah terbaru dari Firestore."""
    if not _require_firestore("get_recent_history"):
        return []
    try:
        docs = (
            db.collection("history")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [
            {
                "hook": d.to_dict().get("hook", ""),
                "story": d.to_dict().get("story", ""),
                "cta": d.to_dict().get("cta", ""),
                "caption": d.to_dict().get("caption", ""),
            }
            for d in docs
        ]
    except Exception as e:
        logger.error(f"❌ Gagal membaca riwayat dari Firestore: {e}")
        return []


def save_to_history(hook: str, story: str, cta: str, caption: str) -> None:
    """Menyimpan naskah yang berhasil ke koleksi 'history' di Firestore."""
    if not _require_firestore("save_to_history"):
        return
    try:
        db.collection("history").add({
            "timestamp": int(time.time()),
            "hook": hook,
            "story": story,
            "cta": cta,
            "caption": caption,
        })
        logger.info("🔥 Naskah berhasil disimpan ke Firestore history.")
    except Exception as e:
        logger.error(f"❌ Gagal menyimpan naskah ke Firestore: {e}")


# ─────────────────────────────────────────────
# DRAFTS (draf video yang sudah dipublish)
# ─────────────────────────────────────────────

def save_video_draft(video_id: str, data: dict) -> None:
    """Menyimpan draf video ke Firestore. video_id = document ID."""
    if not _require_firestore("save_video_draft"):
        return
    try:
        db.collection("drafts").document(video_id).set({
            "timestamp": int(time.time()),
            **data,
        })
        logger.info(f"🔥 Draf video '{video_id}' tersimpan ke Firestore.")
    except Exception as e:
        logger.error(f"❌ Gagal menyimpan draf video ke Firestore: {e}")


def get_video_draft(video_id: str) -> dict:
    """Mengambil data draf video berdasarkan ID dari Firestore."""
    if not _require_firestore("get_video_draft"):
        return {}
    try:
        doc = db.collection("drafts").document(video_id).get()
        return doc.to_dict() if doc.exists else {}
    except Exception as e:
        logger.error(f"❌ Gagal membaca draf dari Firestore: {e}")
        return {}


def cleanup_old_drafts(days: int = 7) -> None:
    """Menghapus draf dari Firestore yang usianya melebihi `days` hari."""
    if not _require_firestore("cleanup_old_drafts"):
        return
    cutoff = int(time.time()) - (days * 86400)
    try:
        docs = db.collection("drafts").where("timestamp", "<", cutoff).stream()
        batch = db.batch()
        count = 0
        for doc in docs:
            batch.delete(doc.reference)
            count += 1
            if count % 400 == 0:
                batch.commit()
                batch = db.batch()
        if count % 400 != 0:
            batch.commit()
        logger.info(f"🧹 Berhasil menghapus {count} draf kedaluwarsa dari Firestore.")
    except Exception as e:
        logger.error(f"❌ Gagal membersihkan draf dari Firestore: {e}")


def update_draft_status(video_id: str, platform: str, platform_video_id: str) -> None:
    """Mencatat platform dan ID video eksternal ke draf di Firestore."""
    if not _require_firestore("update_draft_status"):
        return
    try:
        db.collection("drafts").document(video_id).update({
            "platform": platform,
            "platform_video_id": platform_video_id,
        })
        logger.info(f"🔥 Status draf '{video_id}' diperbarui di Firestore.")
    except Exception as e:
        logger.error(f"❌ Gagal memperbarui status draf di Firestore: {e}")


def update_draft_stats(video_id: str, views: int, likes: int) -> None:
    """Memperbarui statistik views dan likes pada draf di Firestore."""
    if not _require_firestore("update_draft_stats"):
        return
    try:
        db.collection("drafts").document(video_id).update({
            "views": views,
            "likes": likes,
            "last_checked": int(time.time()),
        })
    except Exception as e:
        logger.error(f"❌ Gagal memperbarui stats draf di Firestore: {e}")


# ─────────────────────────────────────────────
# STATISTIK & ANALITIK
# ─────────────────────────────────────────────

def get_top_performing_scripts(limit: int = 3) -> list:
    """Mengambil naskah dengan views tertinggi dari Firestore."""
    if not _require_firestore("get_top_performing_scripts"):
        return []
    try:
        docs = (
            db.collection("drafts")
            .where("views", ">", 0)
            .order_by("views", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [
            {
                "caption": d.to_dict().get("caption", ""),
                "views": d.to_dict().get("views", 0),
                "likes": d.to_dict().get("likes", 0),
            }
            for d in docs
        ]
    except Exception as e:
        logger.warning(f"⚠️ Gagal mengambil naskah populer dari Firestore: {e}")
        return []


def get_active_youtube_video_ids(limit: int = 10) -> dict:
    """Mengambil peta video_id -> platform_video_id YouTube dari Firestore."""
    if not _require_firestore("get_active_youtube_video_ids"):
        return {}
    try:
        docs = (
            db.collection("drafts")
            .where("platform", "==", "youtube")
            .limit(limit)
            .stream()
        )
        video_map = {}
        for doc in docs:
            yt_id = doc.to_dict().get("platform_video_id")
            if yt_id:
                video_map[doc.id] = yt_id
        return video_map
    except Exception as e:
        logger.warning(f"⚠️ Gagal mengambil active YouTube video dari Firestore: {e}")
        return {}


def get_previous_views(video_id: str) -> int:
    """Mengambil jumlah views sebelumnya dari Firestore."""
    if not _require_firestore("get_previous_views"):
        return 0
    try:
        doc = db.collection("drafts").document(video_id).get()
        return doc.to_dict().get("views", 0) if doc.exists else 0
    except Exception as e:
        logger.warning(f"⚠️ Gagal membaca views sebelumnya dari Firestore: {e}")
        return 0


def get_viral_video_ids(min_views: int = 500, limit: int = 3) -> dict:
    """Mengambil video YouTube viral yang belum dianalisis komentarnya dari Firestore."""
    if not _require_firestore("get_viral_video_ids"):
        return {}
    try:
        docs = (
            db.collection("drafts")
            .where("platform", "==", "youtube")
            .limit(100)
            .stream()
        )
        video_map = {}
        for doc in docs:
            data = doc.to_dict()
            if (
                data.get("views", 0) >= min_views
                and not data.get("comments_analyzed", False)
            ):
                yt_id = data.get("platform_video_id")
                if yt_id:
                    video_map[doc.id] = yt_id
                    if len(video_map) >= limit:
                        break
        return video_map
    except Exception as e:
        logger.warning(f"⚠️ Gagal mengambil viral video dari Firestore: {e}")
        return {}


def mark_comments_analyzed(video_id: str, comment_insight: str = "") -> None:
    """Menandai video sudah dianalisis komentarnya di Firestore."""
    if not _require_firestore("mark_comments_analyzed"):
        return
    try:
        db.collection("drafts").document(video_id).update({
            "comments_analyzed": True,
            "comment_insight": comment_insight,
        })
    except Exception as e:
        logger.error(f"❌ Gagal menandai komentar teranalisis di Firestore: {e}")


def get_latest_comment_insight() -> str:
    """Mengambil insight komentar terbaru dari video viral di Firestore."""
    if not _require_firestore("get_latest_comment_insight"):
        return ""
    try:
        docs = (
            db.collection("drafts")
            .where("comments_analyzed", "==", True)
            .limit(50)
            .stream()
        )
        candidates = sorted(
            [d.to_dict() for d in docs],
            key=lambda x: x.get("views", 0),
            reverse=True,
        )
        return candidates[0].get("comment_insight", "") if candidates else ""
    except Exception as e:
        logger.warning(f"⚠️ Gagal mengambil comment insight dari Firestore: {e}")
        return ""


# ─────────────────────────────────────────────
# HOOK CANDIDATE (A/B Testing)
# ─────────────────────────────────────────────

def save_hook_candidate(hook_b: str) -> None:
    """Menyimpan hook alternatif (versi B) ke Firestore collection 'hook_candidates'."""
    if not _require_firestore("save_hook_candidate"):
        return
    try:
        db.collection("hook_candidates").document("latest").set({
            "hook_b": hook_b,
            "timestamp": int(time.time()),
            "used": False,
        })
        logger.info("🎯 Hook kandidat B berhasil disimpan ke Firestore.")
    except Exception as e:
        logger.error(f"❌ Gagal menyimpan hook kandidat ke Firestore: {e}")


def get_best_hook_candidate() -> str:
    """Mengambil hook kandidat B dari Firestore jika masih segar (< 7 hari) dan belum dipakai."""
    if not _require_firestore("get_best_hook_candidate"):
        return ""
    try:
        doc = db.collection("hook_candidates").document("latest").get()
        if not doc.exists:
            return ""
        data = doc.to_dict()
        age_seconds = int(time.time()) - data.get("timestamp", 0)
        if age_seconds < 7 * 86400 and not data.get("used", False):
            hook = data.get("hook_b", "")
            db.collection("hook_candidates").document("latest").update({"used": True})
            return hook
    except Exception as e:
        logger.error(f"⚠️ Gagal membaca hook kandidat dari Firestore: {e}")
    return ""


# ─────────────────────────────────────────────
# RATE LIMIT CHECK
# ─────────────────────────────────────────────

def get_last_upload_timestamp(channel_id: str) -> int:
    """Mengambil timestamp video terakhir untuk channel tertentu dari Firestore."""
    if not _require_firestore("get_last_upload_timestamp"):
        return 0
    try:
        docs = (
            db.collection("drafts")
            .where("channel_id", "==", channel_id)
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        for doc in docs:
            return doc.to_dict().get("timestamp", 0)
    except Exception as e:
        logger.error(f"⚠️ Gagal membaca timestamp terakhir dari Firestore: {e}")
    return 0

