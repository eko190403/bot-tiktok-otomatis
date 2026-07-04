import os
import json
import time
import logging

# Konfigurasi Logger dasar
logger = logging.getLogger("bot")

db = None
is_firebase_enabled = False

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    
    cred_file = "firebase_service_account.json"
    if os.path.exists(cred_file):
        try:
            # Cegah inisialisasi ganda jika modul dipanggil ulang
            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_file)
                firebase_admin.initialize_app(cred)
            db = firestore.client()
            is_firebase_enabled = True
            logger.info("🔥 Firebase initialized successfully. Menggunakan Cloud Firestore untuk state history.")
        except Exception as e:
            logger.error(f"❌ Gagal inisialisasi Firebase Admin SDK: {e}")
    else:
        logger.warning("⚠️ firebase_service_account.json tidak ditemukan. Menggunakan fallback lokal naskah_history.json.")
except ImportError:
    logger.warning("⚠️ Pustaka 'firebase-admin' belum terpasang. Menggunakan fallback lokal naskah_history.json.")


def get_local_history(limit: int = 25) -> list:
    """Mengambil riwayat cadangan lokal dari file JSON."""
    history_path = "naskah_history.json"
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data[-limit:]
        except Exception as e:
            logger.warning(f"⚠️ Gagal membaca riwayat lokal: {e}")
    return []


def save_local_history(hook: str, story: str, cta: str, caption: str) -> None:
    """Menyimpan entri naskah baru ke berkas cadangan lokal."""
    history_path = "naskah_history.json"
    history_data = []
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history_data = json.load(f)
                if not isinstance(history_data, list):
                    history_data = []
        except:
            pass
            
    history_data.append({
        "timestamp": int(time.time()),
        "hook": hook,
        "story": story,
        "cta": cta,
        "caption": caption
    })
    
    # Batasi agar ukuran file lokal tidak membengkak
    history_data = history_data[-100:]
    try:
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"❌ Gagal menulis berkas riwayat lokal: {e}")


def get_recent_history(limit: int = 25) -> list:
    """
    Mengambil daftar entri naskah terakhir (biasanya 25 entri).
    Menggunakan Cloud Firestore jika aktif, atau beralih otomatis ke file lokal.
    """
    if not is_firebase_enabled or db is None:
        return get_local_history(limit)
        
    try:
        # Ambil dari collection 'history' diurutkan berdasarkan timestamp descending
        docs = db.collection("history").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit).stream()
        history = []
        for doc in docs:
            data = doc.to_dict()
            history.append({
                "hook": data.get("hook", ""),
                "story": data.get("story", ""),
                "cta": data.get("cta", ""),
                "caption": data.get("caption", "")
            })
        return history
    except Exception as e:
        logger.error(f"⚠️ Gagal membaca riwayat Firestore: {e}. Beralih ke cadangan lokal.")
        return get_local_history(limit)


def save_to_history(hook: str, story: str, cta: str, caption: str) -> None:
    """
    Menyimpan data naskah yang sukses dibuat ke Cloud Firestore dan cadangan lokal.
    """
    # Selalu simpan ke lokal sebagai cadangan redundan
    save_local_history(hook, story, cta, caption)
    
    if not is_firebase_enabled or db is None:
        return
        
    try:
        db.collection("history").add({
            "timestamp": int(time.time()),
            "hook": hook,
            "story": story,
            "cta": cta,
            "caption": caption
        })
        logger.info("🔥 Sukses mencatat naskah baru ke Cloud Firestore.")
    except Exception as e:
        logger.error(f"❌ Gagal menyimpan naskah ke Cloud Firestore: {e}")


def save_video_draft(video_id: str, data: dict) -> None:
    """Menyimpan data draf publikasi video (caption, tags, category_id, file_id, dll) ke Firestore/lokal."""
    # Simpan ke cadangan lokal dulu
    local_drafts_path = "video_drafts.json"
    drafts_data = {}
    if os.path.exists(local_drafts_path):
        try:
            with open(local_drafts_path, "r", encoding="utf-8") as f:
                drafts_data = json.load(f)
        except:
            pass
    drafts_data[video_id] = {**data, "timestamp": int(time.time())}
    try:
        with open(local_drafts_path, "w", encoding="utf-8") as f:
            json.dump(drafts_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"❌ Gagal menyimpan draf video lokal: {e}")

    if not is_firebase_enabled or db is None:
        return

    try:
        db.collection("drafts").document(video_id).set({
            "timestamp": int(time.time()),
            **data
        })
        logger.info(f"🔥 Sukses mencatat draf video '{video_id}' ke Cloud Firestore.")
    except Exception as e:
        logger.error(f"❌ Gagal menyimpan draf video ke Cloud Firestore: {e}")


def get_video_draft(video_id: str) -> dict:
    """Mengambil data draf video berdasarkan ID dari Firestore atau fallback lokal."""
    if is_firebase_enabled and db is not None:
        try:
            doc = db.collection("drafts").document(video_id).get()
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            logger.error(f"⚠️ Gagal membaca draf dari Firestore: {e}. Mencoba fallback lokal.")

    local_drafts_path = "video_drafts.json"
    if os.path.exists(local_drafts_path):
        try:
            with open(local_drafts_path, "r", encoding="utf-8") as f:
                drafts_data = json.load(f)
                return drafts_data.get(video_id)
        except Exception as e:
            logger.error(f"⚠️ Gagal membaca draf video lokal: {e}")
    return None


def cleanup_old_drafts(days: int = 7) -> None:
    """Menghapus draf lama dari Firestore dan file lokal yang usianya melebihi batas hari tertentu."""
    cutoff_time = int(time.time()) - (days * 86400)
    
    # 1. Bersihkan draf lokal
    local_drafts_path = "video_drafts.json"
    if os.path.exists(local_drafts_path):
        try:
            with open(local_drafts_path, "r", encoding="utf-8") as f:
                drafts_data = json.load(f)
            if isinstance(drafts_data, dict):
                cleaned_drafts = {
                    vid: val for vid, val in drafts_data.items()
                    if val.get("timestamp", 0) >= cutoff_time
                }
                deleted_count = len(drafts_data) - len(cleaned_drafts)
                if deleted_count > 0:
                    with open(local_drafts_path, "w", encoding="utf-8") as f:
                        json.dump(cleaned_drafts, f, indent=4, ensure_ascii=False)
                    logger.info(f"🧹 Sukses menghapus {deleted_count} draf video lokal yang kedaluwarsa.")
        except Exception as e:
            logger.error(f"❌ Gagal membersihkan draf video lokal: {e}")

    # 2. Bersihkan draf Firestore
    if not is_firebase_enabled or db is None:
        return

    try:
        # Ambil draf yang lebih lama dari waktu cutoff
        docs = db.collection("drafts").where("timestamp", "<", cutoff_time).stream()
        deleted_fs_count = 0
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
            deleted_fs_count += 1
            if deleted_fs_count % 400 == 0:
                batch.commit()
                batch = db.batch()
        if deleted_fs_count % 400 != 0:
            batch.commit()
        if deleted_fs_count > 0:
            logger.info(f"🔥 Sukses menghapus {deleted_fs_count} draf kedaluwarsa dari Cloud Firestore.")
    except Exception as e:
        logger.error(f"❌ Gagal membersihkan draf dari Cloud Firestore: {e}")


def update_draft_status(video_id: str, platform: str, platform_video_id: str) -> None:
    """Mencatat platform dan ID video eksternal (misal YouTube video ID) ke draf."""
    # 1. Update lokal
    local_drafts_path = "video_drafts.json"
    if os.path.exists(local_drafts_path):
        try:
            with open(local_drafts_path, "r", encoding="utf-8") as f:
                drafts_data = json.load(f)
            if video_id in drafts_data:
                drafts_data[video_id]["platform"] = platform
                drafts_data[video_id]["platform_video_id"] = platform_video_id
                with open(local_drafts_path, "w", encoding="utf-8") as f:
                    json.dump(drafts_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Gagal memperbarui status draf lokal: {e}")

    # 2. Update Firestore
    if is_firebase_enabled and db is not None:
        try:
            db.collection("drafts").document(video_id).update({
                "platform": platform,
                "platform_video_id": platform_video_id
            })
            logger.info(f"🔥 Sukses memperbarui status draf '{video_id}' ke Firestore.")
        except Exception as e:
            logger.error(f"❌ Gagal memperbarui status draf ke Firestore: {e}")


def update_draft_stats(video_id: str, views: int, likes: int) -> None:
    """Memperbarui statistik jumlah views dan likes pada draf tertentu."""
    # 1. Update lokal
    local_drafts_path = "video_drafts.json"
    if os.path.exists(local_drafts_path):
        try:
            with open(local_drafts_path, "r", encoding="utf-8") as f:
                drafts_data = json.load(f)
            if video_id in drafts_data:
                drafts_data[video_id]["views"] = views
                drafts_data[video_id]["likes"] = likes
                drafts_data[video_id]["last_checked"] = int(time.time())
                with open(local_drafts_path, "w", encoding="utf-8") as f:
                    json.dump(drafts_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Gagal memperbarui stats draf lokal: {e}")

    # 2. Update Firestore
    if is_firebase_enabled and db is not None:
        try:
            db.collection("drafts").document(video_id).update({
                "views": views,
                "likes": likes,
                "last_checked": int(time.time())
            })
        except Exception as e:
            logger.error(f"❌ Gagal memperbarui stats draf ke Firestore: {e}")


def get_top_performing_scripts(limit: int = 3) -> list:
    """Mengambil naskah-naskah dengan kinerja terbaik (views tertinggi)."""
    top_scripts = []
    
    # 1. Ambil dari Firestore jika aktif
    if is_firebase_enabled and db is not None:
        try:
            docs = db.collection("drafts")\
                     .where("views", ">", 0)\
                     .order_by("views", direction=firestore.Query.DESCENDING)\
                     .limit(limit).stream()
            for doc in docs:
                data = doc.to_dict()
                top_scripts.append({
                    "caption": data.get("caption", ""),
                    "views": data.get("views", 0),
                    "likes": data.get("likes", 0)
                })
            if top_scripts:
                return top_scripts
        except Exception as e:
            logger.warning(f"⚠️ Gagal mengambil naskah populer dari Firestore: {e}. Menggunakan lokal.")

    # 2. Fallback ambil dari lokal
    local_drafts_path = "video_drafts.json"
    if os.path.exists(local_drafts_path):
        try:
            with open(local_drafts_path, "r", encoding="utf-8") as f:
                drafts_data = json.load(f)
            if isinstance(drafts_data, dict):
                # Filter yang memiliki views
                valid_drafts = [
                    val for val in drafts_data.values()
                    if val.get("views", 0) > 0
                ]
                # Urutkan views descending
                valid_drafts.sort(key=lambda x: x.get("views", 0), reverse=True)
                for item in valid_drafts[:limit]:
                    top_scripts.append({
                        "caption": item.get("caption", ""),
                        "views": item.get("views", 0),
                        "likes": item.get("likes", 0)
                    })
        except Exception as e:
            logger.error(f"⚠️ Gagal membaca draf lokal untuk pencarian performa: {e}")
            
    return top_scripts


def get_active_youtube_video_ids(limit: int = 10) -> dict:
    """Mengambil peta video_id -> platform_video_id YouTube yang butuh update statistik."""
    video_map = {}
    
    # 1. Ambil dari Firestore
    if is_firebase_enabled and db is not None:
        try:
            docs = db.collection("drafts")\
                     .where("platform", "==", "youtube")\
                     .limit(limit).stream()
            for doc in docs:
                data = doc.to_dict()
                yt_id = data.get("platform_video_id")
                if yt_id:
                    video_map[doc.id] = yt_id
            return video_map
        except Exception as e:
            logger.warning(f"⚠️ Gagal mengambil active YouTube video dari Firestore: {e}")

    # 2. Fallback lokal
    local_drafts_path = "video_drafts.json"
    if os.path.exists(local_drafts_path):
        try:
            with open(local_drafts_path, "r", encoding="utf-8") as f:
                drafts_data = json.load(f)
            if isinstance(drafts_data, dict):
                count = 0
                for vid, val in drafts_data.items():
                    if val.get("platform") == "youtube" and val.get("platform_video_id"):
                        video_map[vid] = val.get("platform_video_id")
                        count += 1
                        if count >= limit:
                            break
        except Exception as e:
            logger.error(f"⚠️ Gagal membaca active YouTube video dari lokal: {e}")
            
    return video_map


def get_previous_views(video_id: str) -> int:
    """Mengambil jumlah views sebelumnya untuk perbandingan Viral Alert."""
    if is_firebase_enabled and db is not None:
        try:
            doc = db.collection("drafts").document(video_id).get()
            if doc.exists:
                return doc.to_dict().get("views", 0)
        except Exception as e:
            logger.warning(f"⚠️ Gagal membaca views sebelumnya dari Firestore: {e}")

    local_drafts_path = "video_drafts.json"
    if os.path.exists(local_drafts_path):
        try:
            with open(local_drafts_path, "r", encoding="utf-8") as f:
                drafts_data = json.load(f)
            return drafts_data.get(video_id, {}).get("views", 0)
        except Exception:
            pass
    return 0


def get_viral_video_ids(min_views: int = 500, limit: int = 3) -> dict:
    """Mengambil video YouTube dengan views tinggi yang belum dianalisis komentarnya."""
    video_map = {}

    if is_firebase_enabled and db is not None:
        try:
            docs = db.collection("drafts")\
                     .where("platform", "==", "youtube")\
                     .where("views", ">=", min_views)\
                     .where("comments_analyzed", "==", False)\
                     .limit(limit).stream()
            for doc in docs:
                data = doc.to_dict()
                yt_id = data.get("platform_video_id")
                if yt_id:
                    video_map[doc.id] = yt_id
            return video_map
        except Exception as e:
            logger.warning(f"⚠️ Gagal mengambil viral video dari Firestore: {e}")

    # Fallback lokal
    local_drafts_path = "video_drafts.json"
    if os.path.exists(local_drafts_path):
        try:
            with open(local_drafts_path, "r", encoding="utf-8") as f:
                drafts_data = json.load(f)
            if isinstance(drafts_data, dict):
                count = 0
                for vid, val in drafts_data.items():
                    if (val.get("platform") == "youtube"
                            and val.get("platform_video_id")
                            and val.get("views", 0) >= min_views
                            and not val.get("comments_analyzed", False)):
                        video_map[vid] = val["platform_video_id"]
                        count += 1
                        if count >= limit:
                            break
        except Exception as e:
            logger.error(f"⚠️ Gagal membaca viral video dari lokal: {e}")

    return video_map


def mark_comments_analyzed(video_id: str, comment_insight: str = "") -> None:
    """Menandai video sudah dianalisis komentarnya dan menyimpan insight."""
    local_drafts_path = "video_drafts.json"
    if os.path.exists(local_drafts_path):
        try:
            with open(local_drafts_path, "r", encoding="utf-8") as f:
                drafts_data = json.load(f)
            if video_id in drafts_data:
                drafts_data[video_id]["comments_analyzed"] = True
                if comment_insight:
                    drafts_data[video_id]["comment_insight"] = comment_insight
            with open(local_drafts_path, "w", encoding="utf-8") as f:
                json.dump(drafts_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Gagal menandai komentar teranalisis (lokal): {e}")

    if is_firebase_enabled and db is not None:
        try:
            db.collection("drafts").document(video_id).update({
                "comments_analyzed": True,
                "comment_insight": comment_insight
            })
        except Exception as e:
            logger.error(f"❌ Gagal menandai komentar teranalisis (Firestore): {e}")


def get_latest_comment_insight() -> str:
    """Mengambil insight komentar terbaru dari video yang paling viral."""
    if is_firebase_enabled and db is not None:
        try:
            docs = db.collection("drafts")\
                     .where("comments_analyzed", "==", True)\
                     .order_by("views", direction=firestore.Query.DESCENDING)\
                     .limit(1).stream()
            for doc in docs:
                insight = doc.to_dict().get("comment_insight", "")
                if insight:
                    return insight
        except Exception as e:
            logger.warning(f"⚠️ Gagal mengambil comment insight dari Firestore: {e}")

    # Fallback lokal
    local_drafts_path = "video_drafts.json"
    if os.path.exists(local_drafts_path):
        try:
            with open(local_drafts_path, "r", encoding="utf-8") as f:
                drafts_data = json.load(f)
            if isinstance(drafts_data, dict):
                candidates = [
                    val for val in drafts_data.values()
                    if val.get("comments_analyzed") and val.get("comment_insight")
                ]
                candidates.sort(key=lambda x: x.get("views", 0), reverse=True)
                if candidates:
                    return candidates[0]["comment_insight"]
        except Exception:
            pass
    return ""


def save_hook_candidate(hook_b: str) -> None:
    """Menyimpan hook alternatif (versi B) untuk digunakan pada video berikutnya."""
    local_hook_path = "hook_candidate.json"
    try:
        with open(local_hook_path, "w", encoding="utf-8") as f:
            json.dump({"hook_b": hook_b, "timestamp": int(time.time())}, f, ensure_ascii=False)
        logger.info("🎯 Hook kandidat B berhasil disimpan.")
    except Exception as e:
        logger.error(f"❌ Gagal menyimpan hook kandidat: {e}")


def get_best_hook_candidate() -> str:
    """Mengambil hook kandidat B yang tersimpan jika masih segar (< 7 hari)."""
    local_hook_path = "hook_candidate.json"
    if not os.path.exists(local_hook_path):
        return ""
    try:
        with open(local_hook_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        age_seconds = int(time.time()) - data.get("timestamp", 0)
        if age_seconds < 7 * 86400:
            hook = data.get("hook_b", "")
            # Hapus setelah dibaca agar tidak dipakai berulang
            os.remove(local_hook_path)
            return hook
    except Exception as e:
        logger.error(f"⚠️ Gagal membaca hook kandidat: {e}")
    return ""
