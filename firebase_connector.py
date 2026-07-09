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
            logger.info(" Firebase initialized. Firestore aktif sebagai single source of truth.")
        except Exception as e:
            logger.error(f" Gagal inisialisasi Firebase Admin SDK: {e}")
    else:
        logger.warning(" firebase_service_account.json tidak ditemukan. Firestore tidak aktif — pipeline akan berhenti jika mencoba akses DB.")
except ImportError:
    logger.warning(" Pustaka 'firebase-admin' belum terpasang. Firestore tidak aktif.")


def _require_firestore(func_name: str) -> bool:
    """Cek apakah Firestore aktif. Log error dan return False jika tidak."""
    if not is_firebase_enabled or db is None:
        logger.error(f" [{func_name}] Firestore tidak aktif. Operasi dibatalkan.")
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
        logger.error(f" Gagal membaca riwayat dari Firestore: {e}")
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
        logger.info(" Naskah berhasil disimpan ke Firestore history.")
    except Exception as e:
        logger.error(f" Gagal menyimpan naskah ke Firestore: {e}")


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
            "drop_off_second": 0, # Blueprint untuk menganalisis kurva retensi
            **data,
        })
        logger.info(f" Draf video '{video_id}' tersimpan ke Firestore.")
    except Exception as e:
        logger.error(f" Gagal menyimpan draf video ke Firestore: {e}")


def get_video_draft(video_id: str) -> dict:
    """Mengambil data draf video berdasarkan ID dari Firestore."""
    if not _require_firestore("get_video_draft"):
        return {}
    try:
        doc = db.collection("drafts").document(video_id).get()
        return doc.to_dict() if doc.exists else {}
    except Exception as e:
        logger.error(f" Gagal membaca draf dari Firestore: {e}")
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
        logger.info(f" Berhasil menghapus {count} draf kedaluwarsa dari Firestore.")
    except Exception as e:
        logger.error(f" Gagal membersihkan draf dari Firestore: {e}")


def update_draft_status(video_id: str, platform: str, platform_video_id: str) -> None:
    """Mencatat platform dan ID video eksternal ke draf di Firestore."""
    if not _require_firestore("update_draft_status"):
        return
    try:
        db.collection("drafts").document(video_id).update({
            "platform": platform,
            "platform_video_id": platform_video_id,
        })
        logger.info(f" Status draf '{video_id}' diperbarui di Firestore.")
    except Exception as e:
        logger.error(f" Gagal memperbarui status draf di Firestore: {e}")


def update_draft_stats(video_id: str, views: int, likes: int) -> None:
    """Memperbarui statistik views dan likes pada draf di Firestore."""
    if not _require_firestore("update_draft_stats"):
        return
    try:
        doc_ref = db.collection("drafts").document(video_id)
        doc = doc_ref.get()
        if not doc.exists:
            return
            
        data = doc.to_dict()
        prev_views = data.get("views", 0)
        prev_likes = data.get("likes", 0)
        
        delta_views = views - prev_views
        delta_likes = likes - prev_likes
        
        batch = db.batch()
        batch.update(doc_ref, {
            "views": views,
            "likes": likes,
            "last_checked": int(time.time()),
        })
        
        # A/B Testing Aggregation: Increment theme stats
        theme = data.get("theme")
        if theme and (delta_views > 0 or delta_likes > 0):
            theme_ref = db.collection("theme_stats").document(theme)
            batch.set(theme_ref, {
                "views": firestore.Increment(delta_views),
                "likes": firestore.Increment(delta_likes)
            }, merge=True)
            
        # A/B Testing Aggregation: Increment hook stats
        hook = data.get("hook")
        if hook and (delta_views > 0 or delta_likes > 0):
            # Membatasi ID dokumen maksimal 100 karakter agar tidak terlalu panjang
            hook_id = hook[:100].replace("/", "-").strip() if hook else ""
            if hook_id:
                hook_ref = db.collection("hook_stats").document(hook_id)
                batch.set(hook_ref, {
                    "views": firestore.Increment(delta_views),
                    "likes": firestore.Increment(delta_likes),
                    "full_text": hook
                }, merge=True)
                
        batch.commit()
    except Exception as e:
        logger.error(f" Gagal memperbarui stats draf & analitik di Firestore: {e}")


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
        logger.warning(f" Gagal mengambil naskah populer dari Firestore: {e}")
        return []


def get_active_youtube_video_ids(limit: int = 50) -> dict:
    """Mengambil peta video_id -> platform_video_id YouTube dari draf terbaru di Firestore."""
    if not _require_firestore("get_active_youtube_video_ids"):
        return {}
    try:
        # Ambil draf terbaru, filter platform di Python untuk menghindari butuhnya Composite Index
        docs = (
            db.collection("drafts")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        video_map = {}
        for doc in docs:
            data = doc.to_dict()
            if data.get("platform") == "youtube":
                yt_id = data.get("platform_video_id")
                if yt_id:
                    video_map[doc.id] = yt_id
        return video_map
    except Exception as e:
        logger.warning(f" Gagal mengambil active YouTube video dari Firestore: {e}")
        return {}


def get_previous_views(video_id: str) -> int:
    """Mengambil jumlah views sebelumnya dari Firestore."""
    if not _require_firestore("get_previous_views"):
        return 0
    try:
        doc = db.collection("drafts").document(video_id).get()
        return doc.to_dict().get("views", 0) if doc.exists else 0
    except Exception as e:
        logger.warning(f" Gagal membaca views sebelumnya dari Firestore: {e}")
        return 0


def get_viral_video_ids(min_views: int = 500, limit: int = 3, channel_id: str = None) -> dict:
    """Mengambil video YouTube viral yang belum dianalisis komentarnya dari Firestore, difilter berdasarkan channel_id jika diberikan."""
    if not _require_firestore("get_viral_video_ids"):
        return {}
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter
        query = db.collection("drafts").where(filter=FieldFilter("platform", "==", "youtube"))
        if channel_id:
            query = query.where(filter=FieldFilter("channel_id", "==", channel_id))
            
        docs = query.limit(100).stream()
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
        logger.warning(f" Gagal mengambil viral video dari Firestore: {e}")
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
        logger.error(f" Gagal menandai komentar teranalisis di Firestore: {e}")


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
        logger.warning(f" Gagal mengambil comment insight dari Firestore: {e}")
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
        logger.info(" Hook kandidat B berhasil disimpan ke Firestore.")
    except Exception as e:
        logger.error(f" Gagal menyimpan hook kandidat ke Firestore: {e}")


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
        logger.error(f" Gagal membaca hook kandidat dari Firestore: {e}")
    return ""


# ─────────────────────────────────────────────
# RATE LIMIT CHECK
# ─────────────────────────────────────────────

def get_last_upload_timestamp(channel_id: str) -> int:
    """Mengambil timestamp video terakhir untuk channel tertentu dari Firestore."""
    if not _require_firestore("get_last_upload_timestamp"):
        return 0
    try:
        # BUGFIX: Menghindari Composite Index Trap.
        # Hapus .where("channel_id") agar tidak bertabrakan dengan .order_by("timestamp").
        # Kita ambil 50 draft terakhir, lalu filter channel_id di memori Python.
        docs = (
            db.collection("drafts")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(50)
            .stream()
        )
        for doc in docs:
            data = doc.to_dict()
            if data.get("channel_id") == channel_id:
                return data.get("timestamp", 0)
    except Exception as e:
        logger.error(f" Gagal membaca timestamp terakhir dari Firestore: {e}")
    return 0


# ─────────────────────────────────────────────
# THEME PERFORMANCE (Visual A/B Analytics helpers)
# ─────────────────────────────────────────────

def get_top_themes(limit: int = 5) -> list:
    """Ambil top theme berdasarkan total views dari koleksi 'theme_stats' (sudah diagregasi oleh Increment)."""
    if not _require_firestore("get_top_themes"):
        return []
    try:
        docs = (
            db.collection("theme_stats")
            .order_by("views", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [{"theme": d.id, **d.to_dict()} for d in docs]
    except Exception as e:
        logger.warning(f" Gagal mengambil theme performance dari Firestore: {e}")
        return []


def get_top_hooks(limit: int = 3) -> list:
    """Ambil top hook berdasarkan total views dari koleksi 'hook_stats'."""
    if not _require_firestore("get_top_hooks"):
        return []
    try:
        docs = (
            db.collection("hook_stats")
            .order_by("views", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [{"hook": d.id, **d.to_dict()} for d in docs]
    except Exception as e:
        logger.warning(f" Gagal mengambil hook performance dari Firestore: {e}")
        return []


def is_clip_used(clip_id: str) -> bool:
    """Periksa apakah klip Pexels (berdasarkan ID) pernah dipakai sebelumnya."""
    if not _require_firestore("is_clip_used"):
        return False
    try:
        doc = db.collection("used_clips").document(str(clip_id)).get()
        return doc.exists
    except Exception as e:
        logger.warning(f" Gagal memeriksa used_clips di Firestore: {e}")
        return False

_used_clips_queue = []

def mark_clip_used(clip_id: str) -> None:
    """Tandai klip Pexels sebagai sudah dipakai (simpan di antrean memori dulu)."""
    _used_clips_queue.append(str(clip_id))
    logger.info(f" Klip Pexels '{clip_id}' dimasukkan ke antrean memori (belum dicatat ke database).")

def commit_used_clips() -> None:
    """Catat secara permanen semua klip yang ada di antrean ke Firestore (dieksekusi jika video sukses dibuat)."""
    if not _require_firestore("commit_used_clips"):
        return
    for clip_id in _used_clips_queue:
        try:
            db.collection("used_clips").document(clip_id).set({"used_at": int(time.time())})
            logger.info(f" Klip '{clip_id}' resmi dicatat sebagai dipakai di database.")
        except Exception as e:
            logger.error(f" Gagal mencatat klip {clip_id}: {e}")
    _used_clips_queue.clear()

def clear_used_clips_queue() -> None:
    """Hapus antrean klip jika terjadi error (video gagal dibuat)."""
    if _used_clips_queue:
        logger.info(f" Membersihkan {len(_used_clips_queue)} klip dari antrean memori (video batal/gagal dibuat).")
    _used_clips_queue.clear()


def cleanup_used_clips(days: int = 30) -> None:
    """Hapus entri `used_clips` yang lebih tua dari `days` hari."""
    if not _require_firestore("cleanup_used_clips"):
        return
    cutoff = int(time.time()) - (days * 86400)
    try:
        docs = db.collection("used_clips").where("used_at", "<", cutoff).stream()
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
        logger.info(f" Berhasil menghapus {count} entri used_clips yang kedaluwarsa dari Firestore.")
    except Exception as e:
        logger.error(f" Gagal membersihkan used_clips dari Firestore: {e}")

