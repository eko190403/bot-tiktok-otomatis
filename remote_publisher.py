import os
import sys
import json
import asyncio
import argparse
import requests
import html

# Konfigurasi token Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

def send_telegram_direct_message(chat_id: str, text: str):
    """Mengirim pesan langsung ke chat ID Telegram Vio."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"⚠️ Gagal mengirim status Telegram: {e}")


def download_video_from_telegram(file_id: str, dest_path: str):
    """Mengunduh berkas video draf dari server Telegram menggunakan file_id."""
    print(f"📡 Mendapatkan lokasi berkas Telegram untuk file_id: {file_id}...")
    info_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    
    try:
        resp = requests.get(info_url, timeout=20)
        if resp.status_code != 200:
            raise RuntimeError(f"Gagal getFile dari Telegram: {resp.text}")
            
        file_data = resp.json()
        file_path = file_data.get("result", {}).get("file_path")
        if not file_path:
            raise ValueError(f"file_path tidak ditemukan di respons Telegram: {file_data}")
            
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        print(f"📥 Mengunduh video dari {download_url}...")
        
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with requests.get(download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"💾 Video sukses diunduh ke: {dest_path} ({os.path.getsize(dest_path)} bytes)")
    except Exception as e:
        print(f"❌ Gagal mengunduh berkas dari Telegram: {e}")
        raise e


async def main():
    parser = argparse.ArgumentParser(description="Telegram Remote Control Publisher")
    parser.add_argument("--video_id", required=True, help="ID draf video unik dari Firestore")
    parser.add_argument("--platform", required=True, choices=["youtube", "tiktok"], help="Platform tujuan publikasi")
    parser.add_argument("--chat_id", required=True, help="Telegram Chat ID untuk pengiriman notifikasi")
    
    args = parser.parse_args()
    
    video_id = args.video_id
    platform = args.platform
    chat_id = args.chat_id
    
    platform_name = "YouTube Shorts" if platform == "youtube" else "TikTok"
    send_telegram_direct_message(
        chat_id, 
        f"⏳ <b>Memulai Publikasi Cloud:</b> Mengambil draf <code>{video_id}</code> untuk {platform_name}..."
    )
    
    # 1. Ambil draf dari Firestore/Lokal
    import firebase_connector
    draft = firebase_connector.get_video_draft(video_id)
    if not draft:
        err_msg = f"❌ <b>Gagal Publikasi:</b> Draf video dengan ID <code>{video_id}</code> tidak ditemukan di database Firestore/Lokal!"
        send_telegram_direct_message(chat_id, err_msg)
        print(f"❌ Draf tidak ditemukan untuk ID: {video_id}")
        sys.exit(1)
        
    file_id = draft.get("file_id")
    caption = draft.get("caption", "")
    tags = draft.get("tags", [])
    category_id = draft.get("category_id", "22")
    interactive_comment = draft.get("interactive_comment", "")
    
    if not file_id:
        send_telegram_direct_message(chat_id, f"❌ <b>Eror:</b> file_id Telegram tidak ditemukan pada draf <code>{video_id}</code>!")
        sys.exit(1)
        
    # 2. Unduh video ke folder sementara
    local_video_path = f"temp/downloaded_draft_{video_id}.mp4"
    try:
        download_video_from_telegram(file_id, local_video_path)
    except Exception as dl_err:
        send_telegram_direct_message(chat_id, f"❌ <b>Gagal Unduh Video:</b> Terjadi kesalahan mengunduh dari server Telegram.\nDetail: <code>{dl_err}</code>")
        sys.exit(1)
        
    # 3. Jalankan pengunggahan sesuai platform
    try:
        if platform == "youtube":
            print(f"🚀 Memulai unggah ke YouTube Shorts...")
            from youtube_uploader import upload_to_youtube
            youtube_url = await upload_to_youtube(
                local_video_path,
                caption=caption,
                tags=tags,
                category_id=category_id,
                comment_text=interactive_comment
            )
            
            msg = (
                "🚀 <b>YOUTUBE SHORTS UPLOAD SUKSES via TELEGRAM!</b>\n\n"
                f"🔗 <b>Tautan Shorts:</b> {youtube_url}\n"
                f"✍️ <b>Caption:</b>\n<i>{caption}</i>\n\n"
                f"💬 <b>Pancingan Komentar:</b>\n<i>{interactive_comment}</i>"
            )
            send_telegram_direct_message(chat_id, msg)
            
        elif platform == "tiktok":
            print(f"🚀 Memulai unggah ke TikTok Creator Studio...")
            from uploader import upload_to_tiktok
            tiktok_username = await upload_to_tiktok(
                local_video_path,
                caption=caption,
                comment_text=interactive_comment
            )
            
            msg = (
                "🚀 <b>TIKTOK UPLOAD SUKSES via TELEGRAM!</b>\n\n"
                f"👤 <b>Akun TikTok:</b> <code>{tiktok_username}</code>\n"
                f"✍️ <b>Caption & Hashtags:</b>\n<i>{caption}</i>\n\n"
                f"💬 <b>Pancingan Komentar:</b>\n<i>{interactive_comment}</i>"
            )
            send_telegram_direct_message(chat_id, msg)
            
    except Exception as upload_err:
        print(f"❌ Gagal mempublikasikan video: {upload_err}")
        escaped_err = html.escape(str(upload_err))
        
        # Deteksi khusus: Cookie TikTok Kedaluwarsa
        if platform == "tiktok":
            cookie_expired_keywords = ["cookies kedaluwarsa", "cookie expired", "login ulang", "login", "signup"]
            if any(kw in str(upload_err).lower() for kw in cookie_expired_keywords):
                msg = (
                    "🔑 <b>COOKIE TIKTOK KEDALUWARSA!</b>\n\n"
                    "❗ <b>Tindakan yang diperlukan:</b>\n"
                    "1. Login ulang ke TikTok di browser.\n"
                    "2. Ekspor cookie menggunakan ekstensi EditThisCookie.\n"
                    "3. Perbarui secret <code>TIKTOK_COOKIES</code> di GitHub Settings → Secrets."
                )
                send_telegram_direct_message(chat_id, msg)
                sys.exit(1)

        msg = (
            f"⚠️ <b>PUBLIKASI {platform_name.upper()} GAGAL!</b>\n\n"
            f"🎬 <b>Draf ID:</b> <code>{video_id}</code>\n"
            f"❌ <b>Error Log:</b>\n<code>{escaped_err}</code>"
        )
        send_telegram_direct_message(chat_id, msg)
        
        # Kirim screenshot jika ada (khusus TikTok Playwright)
        screenshot_path = "output/error_screenshot.png"
        if platform == "tiktok" and os.path.exists(screenshot_path):
            from app import send_telegram_photo
            try:
                send_telegram_photo(
                    screenshot_path,
                    caption=f"📸 <b>Bukti Kegagalan Layar (TikTok Remote)</b>"
                )
            except:
                pass
        sys.exit(1)
    finally:
        # Bersihkan file video yang diunduh
        if os.path.exists(local_video_path):
            try:
                os.remove(local_video_path)
            except:
                pass
                
    print("✅ Proses remote publishing selesai dengan sukses!")


if __name__ == "__main__":
    asyncio.run(main())
