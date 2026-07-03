import os
import sys
import traceback
import asyncio

def send_telegram_message(message: str):
    """
    Mengirim pesan notifikasi ke Telegram menggunakan library bawaan Python (urllib)
    agar 100% bebas dari masalah missing-dependency di runner cloud.
    """
    import urllib.request
    import json
    
    token = os.getenv("TELEGRAM_BOT_TOKEN", "8644685615:AAERnJkiFVLR0HhFxmj5HTFmYhsmtytso1A")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "1120755820")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            response.read()
        print("📨 Notifikasi status upload berhasil dikirim ke Telegram.")
    except Exception as e:
        print(f"⚠️ Gagal mengirim notifikasi status upload ke Telegram: {e}")


def send_telegram_photo(photo_path: str, caption: str = ""):
    """
    Mengirim file foto ke Telegram menggunakan library requests.
    """
    import requests
    
    token = os.getenv("TELEGRAM_BOT_TOKEN", "8644685615:AAERnJkiFVLR0HhFxmj5HTFmYhsmtytso1A")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "1120755820")
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    
    if not os.path.exists(photo_path):
        print(f"⚠️ File foto tidak ditemukan: {photo_path}")
        return
        
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
            response = requests.post(url, files=files, data=data, timeout=15)
            if response.status_code == 200:
                print("📨 Notifikasi screenshot berhasil dikirim ke Telegram.")
            else:
                print(f"⚠️ Telegram sendPhoto gagal dengan status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"⚠️ Gagal mengirim screenshot ke Telegram: {e}")


async def main():
    try:
        print("🚀 Memulai Pipeline Pembuatan Video Otomatis...")
        
        # Lakukan import secara lokal di dalam fungsi untuk melacak jika eror berasal dari file import
        print("📦 Meng-import modul video_builder...")
        from video_builder import create_video
        
        print("🎬 Menjalankan fungsi create_video()...")
        success = await create_video()
        
        if success:
            print("✅ Video Berhasil Dirender Sempurna!")
            
            # Ambil caption hasil rancangan Gemini dari berkas metadata
            caption = ""
            metadata_path = "temp/video_metadata.json"
            if os.path.exists(metadata_path):
                try:
                    import json
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        meta_data = json.load(f)
                        caption = meta_data.get("caption", "")
                    os.remove(metadata_path) # Bersihkan setelah dibaca
                except Exception as meta_err:
                    print(f"⚠️ Gagal membaca/menghapus metadata caption: {meta_err}")

            # Cari file video terbaru di folder output untuk diunggah (digunakan untuk TikTok & YouTube)
            import glob
            video_files = glob.glob("output/*.mp4")
            latest_video = max(video_files, key=os.path.getctime) if video_files else None

            # Poin 9: Integrasi Upload Otomatis ke TikTok
            enable_upload = os.getenv("ENABLE_TIKTOK_UPLOAD", "false").lower() == "true"
            if enable_upload:
                if latest_video:
                    print("📤 Memicu pengunggahan otomatis ke TikTok...")
                    from uploader import upload_to_tiktok
                    print(f"🎬 Menemukan video terbaru untuk TikTok: {latest_video}. Memulai upload...")
                    try:
                        tiktok_username = await upload_to_tiktok(latest_video, caption=caption)
                        print("🚀 Sukses mengunggah video ke TikTok!")
                        
                        # Kirim notifikasi SUKSES ke Telegram
                        msg = (
                            "🚀 <b>TIKTOK UPLOAD SUKSES!</b>\n\n"
                            f"👤 <b>Akun TikTok:</b> <code>{tiktok_username}</code>\n"
                            f"🎬 <b>Video:</b> <code>{os.path.basename(latest_video)}</code>\n\n"
                            f"✍️ <b>Caption & Hashtags:</b>\n<i>{caption}</i>"
                        )
                        send_telegram_message(msg)
                    except Exception as upload_err:
                        print(f"❌ Gagal mengunggah ke TikTok: {upload_err}")
                        
                        # Ambil username untuk ditaruh di log error
                        from uploader import get_tiktok_username_from_cookies
                        failed_user = get_tiktok_username_from_cookies()
                        
                        # Kirim notifikasi GAGAL ke Telegram
                        import html
                        escaped_err = html.escape(str(upload_err))
                        msg = (
                            "⚠️ <b>TIKTOK UPLOAD GAGAL!</b>\n\n"
                            f"👤 <b>Akun TikTok:</b> <code>{failed_user}</code>\n"
                            f"🎬 <b>Video:</b> <code>{os.path.basename(latest_video)}</code>\n\n"
                            f"❌ <b>Error Log:</b>\n<code>{escaped_err}</code>"
                        )
                        send_telegram_message(msg)
                        
                        # Kirim screenshot kegagalan jika ada berkas hasil tangkapan layar
                        screenshot_path = "output/error_screenshot.png"
                        if os.path.exists(screenshot_path):
                            send_telegram_photo(
                                screenshot_path,
                                caption=f"📸 <b>Bukti Kegagalan Layar (TikTok Upload)</b>\nAkun: <code>{failed_user}</code>"
                            )
                else:
                    print("⚠️ Tidak ada file video di folder output untuk diunggah ke TikTok.")
            else:
                print("ℹ️ Pengunggahan otomatis ke TikTok dinonaktifkan (ENABLE_TIKTOK_UPLOAD=false).")

            # Integrasi Upload Otomatis ke YouTube Shorts
            enable_yt_upload = os.getenv("ENABLE_YOUTUBE_UPLOAD", "false").lower() == "true"
            if enable_yt_upload:
                if latest_video:
                    print("📤 Memicu pengunggahan otomatis ke YouTube Shorts...")
                    from youtube_uploader import upload_to_youtube
                    print(f"🎬 Menemukan video terbaru untuk YouTube: {latest_video}. Memulai upload...")
                    try:
                        youtube_url = await upload_to_youtube(latest_video, caption=caption)
                        print("🚀 Sukses mengunggah video ke YouTube Shorts!")
                        
                        # Kirim notifikasi SUKSES ke Telegram
                        msg = (
                            "🚀 <b>YOUTUBE SHORTS UPLOAD SUKSES!</b>\n\n"
                            f"🎬 <b>Video:</b> <code>{os.path.basename(latest_video)}</code>\n"
                            f"🔗 <b>Tautan Shorts:</b> {youtube_url}\n\n"
                            f"✍️ <b>Caption:</b>\n<i>{caption}</i>"
                        )
                        send_telegram_message(msg)
                    except Exception as yt_err:
                        print(f"❌ Gagal mengunggah ke YouTube Shorts: {yt_err}")
                        
                        # Kirim notifikasi GAGAL ke Telegram
                        import html
                        escaped_err = html.escape(str(yt_err))
                        msg = (
                            "⚠️ <b>YOUTUBE SHORTS UPLOAD GAGAL!</b>\n\n"
                            f"🎬 <b>Video:</b> <code>{os.path.basename(latest_video)}</code>\n\n"
                            f"❌ <b>Error Log:</b>\n<code>{escaped_err}</code>"
                        )
                        send_telegram_message(msg)
                        
                        # Kirim screenshot kegagalan jika ada berkas hasil tangkapan layar
                        yt_screenshot = "output/youtube_error_screenshot.png"
                        if os.path.exists(yt_screenshot):
                            send_telegram_photo(
                                yt_screenshot,
                                caption="📸 <b>Bukti Kegagalan Layar (YouTube Upload)</b>"
                            )
                else:
                    print("⚠️ Tidak ada file video di folder output untuk diunggah ke YouTube Shorts.")
            else:
                print("ℹ️ Pengunggahan otomatis ke YouTube Shorts dinonaktifkan (ENABLE_YOUTUBE_UPLOAD=false).")
        else:
            print("❌ Gagal membuat video (Kembalian Bernilai False).")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Terjadi Eror Fatal pada Pipeline Utama: {e}")
        print("\n🔍 DETAIL TRACEBACK EROR:")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    # Paksa cetak langsung ke log tanpa buffer agar terlihat di GitHub Actions
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(main())
