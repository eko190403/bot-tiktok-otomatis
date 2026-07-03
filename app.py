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

            # Poin 9: Integrasi Upload Otomatis ke TikTok
            enable_upload = os.getenv("ENABLE_TIKTOK_UPLOAD", "false").lower() == "true"
            if enable_upload:
                print("📤 Memicu pengunggahan otomatis ke TikTok...")
                import glob
                from uploader import upload_to_tiktok
                
                # Cari file video terbaru di folder output
                video_files = glob.glob("output/*.mp4")
                if video_files:
                    latest_video = max(video_files, key=os.path.getctime)
                    print(f"🎬 Menemukan video terbaru: {latest_video}. Memulai upload...")
                    try:
                        await upload_to_tiktok(latest_video, caption=caption)
                        print("🚀 Sukses mengunggah video ke TikTok!")
                        
                        # Kirim notifikasi SUKSES ke Telegram
                        msg = (
                            "🚀 <b>TIKTOK UPLOAD SUKSES!</b>\n\n"
                            f"🎬 <b>Video:</b> <code>{os.path.basename(latest_video)}</code>\n\n"
                            f"✍️ <b>Caption & Hashtags:</b>\n<i>{caption}</i>"
                        )
                        send_telegram_message(msg)
                    except Exception as upload_err:
                        print(f"❌ Gagal mengunggah ke TikTok: {upload_err}")
                        
                        # Kirim notifikasi GAGAL ke Telegram
                        msg = (
                            "⚠️ <b>TIKTOK UPLOAD GAGAL!</b>\n\n"
                            f"🎬 <b>Video:</b> <code>{os.path.basename(latest_video)}</code>\n\n"
                            f"❌ <b>Error Log:</b>\n<code>{upload_err}</code>"
                        )
                        send_telegram_message(msg)
                else:
                    print("⚠️ Tidak ada file video di folder output untuk diunggah.")
            else:
                print("ℹ️ Pengunggahan otomatis ke TikTok dinonaktifkan (ENABLE_TIKTOK_UPLOAD=false).")
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
