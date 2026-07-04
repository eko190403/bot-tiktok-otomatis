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
