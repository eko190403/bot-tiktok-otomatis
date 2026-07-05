import os
import time
import logging
import json
import tempfile
from typing import Any

logger = logging.getLogger("bot")

db = None
is_firebase_enabled = False

# Lokasi data jika Firestore tidak tersedia
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _data_path(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def _read_json(name: str, default: Any):
    path = _data_path(name)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"⚠️ Gagal membaca {path}: {e}")
        return default


def _write_json_atomic(name: str, data: Any) -> None:
    path = _data_path(name)
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        logger.error(f"❌ Gagal menulis {path}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

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
    """Mengambil riwayat naskah terbaru dari Firestore atau fallback lokal."""
    if is_firebase_enabled and db is not None:
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

    # Fallback lokal
    items = _read_json("history.json", [])
    # urutkan berdasarkan timestamp desc dan potong
    items_sorted = sorted(items, key=lambda x: x.get("timestamp", 0), reverse=True)
    return [{"hook": i.get("hook", ""), "story": i.get("story", ""), "cta": i.get("cta", ""), "caption": i.get("caption", "")} for i in items_sorted[:limit]]


def save_to_history(hook: str, story: str, cta: str, caption: str) -> None:
    """Menyimpan naskah yang berhasil ke koleksi 'history' di Firestore atau fallback lokal."""
    entry = {"timestamp": int(time.time()), "hook": hook, "story": story, "cta": cta, "caption": caption}
    if is_firebase_enabled and db is not None:
        try:
            db.collection("history").add(entry)
            logger.info("🔥 Naskah berhasil disimpan ke Firestore history.")
            return
        except Exception as e:
            logger.error(f"❌ Gagal menyimpan naskah ke Firestore: {e}")

    # Fallback lokal
    items = _read_json("history.json", [])
    items.append(entry)
    _write_json_atomic("history.json", items)
    logger.info("🔥 Naskah berhasil disimpan ke history lokal.")


# ─────────────────────────────────────────────
# DRAFTS (draf video yang sudah dipublish)
# ─────────────────────────────────────────────

def save_video_draft(video_id: str, data: dict) -> None:
    """Menyimpan draf video ke Firestore atau fallback lokal. video_id = document ID."""
    entry = {"timestamp": int(time.time()), **data}
    if is_firebase_enabled and db is not None:
        try:
            db.collection("drafts").document(video_id).set(entry)
            logger.info(f"🔥 Draf video '{video_id}' tersimpan ke Firestore.")
            return
        except Exception as e:
            logger.error(f"❌ Gagal menyimpan draf video ke Firestore: {e}")

    drafts = _read_json("drafts.json", {})
    drafts[str(video_id)] = entry
    _write_json_atomic("drafts.json", drafts)
    logger.info(f"🔥 Draf video '{video_id}' tersimpan ke drafts lokal.")


def get_video_draft(video_id: str) -> dict:
    """Mengambil data draf video berdasarkan ID dari Firestore atau fallback lokal."""
    if is_firebase_enabled and db is not None:
        try:
            doc = db.collection("drafts").document(video_id).get()
            return doc.to_dict() if doc.exists else {}
        except Exception as e:
            logger.error(f"❌ Gagal membaca draf dari Firestore: {e}")
            return {}

    drafts = _read_json("drafts.json", {})
    return drafts.get(str(video_id), {})


def cleanup_old_drafts(days: int = 7) -> None:
    """Menghapus draf dari Firestore atau fallback lokal yang usianya melebihi `days` hari."""
    cutoff = int(time.time()) - (days * 86400)
    if is_firebase_enabled and db is not None:
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
            return
        except Exception as e:
            logger.error(f"❌ Gagal membersihkan draf dari Firestore: {e}")

    # Fallback lokal
    drafts = _read_json("drafts.json", {})
    keys_to_delete = [k for k, v in drafts.items() if v.get("timestamp", 0) < cutoff]
    for k in keys_to_delete:
        drafts.pop(k, None)
    _write_json_atomic("drafts.json", drafts)
    logger.info(f"🧹 Berhasil menghapus {len(keys_to_delete)} draf kedaluwarsa dari drafts lokal.")


def update_draft_status(video_id: str, platform: str, platform_video_id: str) -> None:
    """Mencatat platform dan ID video eksternal ke draf di Firestore atau fallback lokal."""
    if is_firebase_enabled and db is not None:
        try:
            db.collection("drafts").document(video_id).update({
                "platform": platform,
                "platform_video_id": platform_video_id,
            })
            logger.info(f"🔥 Status draf '{video_id}' diperbarui di Firestore.")
            return
        except Exception as e:
            logger.error(f"❌ Gagal memperbarui status draf di Firestore: {e}")

    drafts = _read_json("drafts.json", {})
    if str(video_id) in drafts:
        drafts[str(video_id)]["platform"] = platform
        drafts[str(video_id)]["platform_video_id"] = platform_video_id
        _write_json_atomic("drafts.json", drafts)
        logger.info(f"🔥 Status draf '{video_id}' diperbarui di drafts lokal.")


def update_draft_stats(video_id: str, views: int, likes: int) -> None:
    """Memperbarui statistik views dan likes pada draf di Firestore atau fallback lokal."""
    if is_firebase_enabled and db is not None:
        try:
            db.collection("drafts").document(video_id).update({
                "views": views,
                "likes": likes,
                "last_checked": int(time.time()),
            })
            return
        except Exception as e:
            logger.error(f"❌ Gagal memperbarui stats draf di Firestore: {e}")

    drafts = _read_json("drafts.json", {})
    if str(video_id) in drafts:
        drafts[str(video_id)]["views"] = views
        drafts[str(video_id)]["likes"] = likes
        drafts[str(video_id)]["last_checked"] = int(time.time())
        _write_json_atomic("drafts.json", drafts)


# ─────────────────────────────────────────────
# STATISTIK & ANALITIK
# ─────────────────────────────────────────────

def get_top_performing_scripts(limit: int = 3) -> list:
    """Mengambil naskah dengan views tertinggi dari Firestore atau fallback lokal."""
    if is_firebase_enabled and db is not None:
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

    drafts = _read_json("drafts.json", {})
    candidates = [v for v in drafts.values() if v.get("views", 0) > 0]
    candidates_sorted = sorted(candidates, key=lambda x: x.get("views", 0), reverse=True)[:limit]
    return [{"caption": c.get("caption", ""), "views": c.get("views", 0), "likes": c.get("likes", 0)} for c in candidates_sorted]


def get_active_youtube_video_ids(limit: int = 10) -> dict:
    """Mengambil peta video_id -> platform_video_id YouTube dari Firestore atau fallback lokal."""
    if is_firebase_enabled and db is not None:
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

    drafts = _read_json("drafts.json", {})
    video_map = {}
    for k, v in drafts.items():
        if v.get("platform") == "youtube" and v.get("platform_video_id"):
            video_map[k] = v.get("platform_video_id")
            if len(video_map) >= limit:
                break
    return video_map


def get_previous_views(video_id: str) -> int:
    """Mengambil jumlah views sebelumnya dari Firestore atau fallback lokal."""
    if is_firebase_enabled and db is not None:
        try:
            doc = db.collection("drafts").document(video_id).get()
            return doc.to_dict().get("views", 0) if doc.exists else 0
        except Exception as e:
            logger.warning(f"⚠️ Gagal membaca views sebelumnya dari Firestore: {e}")
            return 0

    drafts = _read_json("drafts.json", {})
    return drafts.get(str(video_id), {}).get("views", 0)


def get_viral_video_ids(min_views: int = 500, limit: int = 3) -> dict:
    """Mengambil video YouTube viral yang belum dianalisis komentarnya dari Firestore atau fallback lokal."""
    video_map = {}
    if is_firebase_enabled and db is not None:
        try:
            docs = (
                db.collection("drafts")
                .where("platform", "==", "youtube")
                .limit(100)
                .stream()
            )
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

    drafts = _read_json("drafts.json", {})
    for k, v in drafts.items():
        if v.get("platform") == "youtube" and v.get("views", 0) >= min_views and not v.get("comments_analyzed", False):
            video_map[k] = v.get("platform_video_id")
            if len(video_map) >= limit:
                break
    return video_map


def mark_comments_analyzed(video_id: str, comment_insight: str = "") -> None:
    """Menandai video sudah dianalisis komentarnya di Firestore atau fallback lokal."""
    if is_firebase_enabled and db is not None:
        try:
            db.collection("drafts").document(video_id).update({
                "comments_analyzed": True,
                "comment_insight": comment_insight,
            })
            return
        except Exception as e:
            logger.error(f"❌ Gagal menandai komentar teranalisis di Firestore: {e}")

    drafts = _read_json("drafts.json", {})
    if str(video_id) in drafts:
        drafts[str(video_id)]["comments_analyzed"] = True
        drafts[str(video_id)]["comment_insight"] = comment_insight
        _write_json_atomic("drafts.json", drafts)


def get_latest_comment_insight() -> str:
    """Mengambil insight komentar terbaru dari video viral di Firestore atau fallback lokal."""
    if is_firebase_enabled and db is not None:
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

    drafts = _read_json("drafts.json", {})
    candidates = [v for v in drafts.values() if v.get("comments_analyzed", False)]
    candidates_sorted = sorted(candidates, key=lambda x: x.get("views", 0), reverse=True)
    return candidates_sorted[0].get("comment_insight", "") if candidates_sorted else ""


# ─────────────────────────────────────────────
# HOOK CANDIDATE (A/B Testing)
# ─────────────────────────────────────────────

def save_hook_candidate(hook_b: str) -> None:
    """Menyimpan hook alternatif (versi B) ke Firestore collection 'hook_candidates'."""
    entry = {"hook_b": hook_b, "timestamp": int(time.time()), "used": False}
    if is_firebase_enabled and db is not None:
        try:
            db.collection("hook_candidates").document("latest").set(entry)
            logger.info("🎯 Hook kandidat B berhasil disimpan ke Firestore.")
            return
        except Exception as e:
            logger.error(f"❌ Gagal menyimpan hook kandidat ke Firestore: {e}")

    # fallback lokal
    _write_json_atomic("hook_candidates.json", entry)
    logger.info("🎯 Hook kandidat B berhasil disimpan ke hook_candidates lokal.")


def get_best_hook_candidate() -> str:
    """Mengambil hook kandidat B dari Firestore jika masih segar (< 7 hari) dan belum dipakai."""
    if is_firebase_enabled and db is not None:
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

    data = _read_json("hook_candidates.json", {})
    if not data:
        return ""
    age_seconds = int(time.time()) - data.get("timestamp", 0)
    if age_seconds < 7 * 86400 and not data.get("used", False):
        hook = data.get("hook_b", "")
        data["used"] = True
        _write_json_atomic("hook_candidates.json", data)
        return hook
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


# ─────────────────────────────────────────────
# THEME PERFORMANCE (Visual A/B Analytics helpers)
# ─────────────────────────────────────────────

def record_theme_performance(theme: str, views: int = 0, likes: int = 0) -> None:
    """Simpan satu data performa tema ke koleksi 'theme_stats'.

    Digunakan oleh pipeline setelah video dipublish untuk agregasi sederhana.
    """
    entry = {"timestamp": int(time.time()), "theme": theme, "views": int(views) if views else 0, "likes": int(likes) if likes else 0}
    if is_firebase_enabled and db is not None:
        try:
            db.collection("theme_stats").add(entry)
            logger.info(f"📊 Theme performance recorded: {theme} (views={views}, likes={likes})")
            return
        except Exception as e:
            logger.warning(f"⚠️ Gagal menyimpan theme performance ke Firestore: {e}")

    items = _read_json("theme_stats.json", [])
    items.append(entry)
    _write_json_atomic("theme_stats.json", items)
    logger.info(f"📊 Theme performance recorded ke theme_stats lokal: {theme} (views={views}, likes={likes})")


def get_top_themes(limit: int = 5) -> list:
    """Ambil top theme berdasarkan total views dari koleksi 'theme_stats'.

    Karena Firestore tidak mendukung agregasi server-side sederhana, fungsi ini
    membaca dokumen recent dan melakukan agregasi di sisi klien.
    """
    if is_firebase_enabled and db is not None:
        try:
            docs = db.collection("theme_stats").stream()
            agg = {}
            for d in docs:
                data = d.to_dict()
                t = data.get("theme")
                if not t:
                    continue
                s = agg.setdefault(t, {"views": 0, "likes": 0, "count": 0})
                s["views"] += int(data.get("views", 0))
                s["likes"] += int(data.get("likes", 0))
                s["count"] += 1

            sorted_items = sorted(agg.items(), key=lambda x: x[1]["views"], reverse=True)[:limit]
            return [{"theme": k, **v} for k, v in sorted_items]
        except Exception as e:
            logger.warning(f"⚠️ Gagal mengagregasi theme performance dari Firestore: {e}")

    items = _read_json("theme_stats.json", [])
    agg = {}
    for data in items:
        t = data.get("theme")
        if not t:
            continue
        s = agg.setdefault(t, {"views": 0, "likes": 0, "count": 0})
        s["views"] += int(data.get("views", 0))
        s["likes"] += int(data.get("likes", 0))
        s["count"] += 1
    sorted_items = sorted(agg.items(), key=lambda x: x[1]["views"], reverse=True)[:limit]
    return [{"theme": k, **v} for k, v in sorted_items]


def is_clip_used(clip_id: str) -> bool:
    """Periksa apakah klip Pexels (berdasarkan ID) pernah dipakai sebelumnya."""
    if is_firebase_enabled and db is not None:
        try:
            doc = db.collection("used_clips").document(str(clip_id)).get()
            return doc.exists
        except Exception as e:
            logger.warning(f"⚠️ Gagal memeriksa used_clips di Firestore: {e}")
            return False

    data = _read_json("used_clips.json", {})
    return str(clip_id) in data


def mark_clip_used(clip_id: str) -> None:
    """Tandai klip Pexels sebagai sudah dipakai (simpan timestamp)."""
    if is_firebase_enabled and db is not None:
        try:
            db.collection("used_clips").document(str(clip_id)).set({"used_at": int(time.time())})
            logger.info(f"🔖 Klip Pexels '{clip_id}' ditandai sebagai sudah dipakai.")
            return
        except Exception as e:
            logger.error(f"❌ Gagal menandai klip terpakai di Firestore: {e}")

    data = _read_json("used_clips.json", {})
    data[str(clip_id)] = int(time.time())
    _write_json_atomic("used_clips.json", data)
    logger.info(f"🔖 Klip Pexels '{clip_id}' ditandai sebagai sudah dipakai (lokal).")


def cleanup_used_clips(days: int = 90) -> None:
    """Hapus entri `used_clips` yang lebih tua dari `days` hari."""
    cutoff = int(time.time()) - (days * 86400)
    if is_firebase_enabled and db is not None:
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
            logger.info(f"🧹 Berhasil menghapus {count} entri used_clips yang kedaluwarsa dari Firestore.")
            return
        except Exception as e:
            logger.error(f"❌ Gagal membersihkan used_clips dari Firestore: {e}")

    data = _read_json("used_clips.json", {})
    keys_to_delete = [k for k, v in data.items() if int(v) < cutoff]
    for k in keys_to_delete:
        data.pop(k, None)
    _write_json_atomic("used_clips.json", data)
    logger.info(f"🧹 Berhasil menghapus {len(keys_to_delete)} entri used_clips yang kedaluwarsa (lokal).")

