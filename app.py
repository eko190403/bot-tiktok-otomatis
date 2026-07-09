import os
import sys
import time
import traceback
import asyncio

def send_telegram_message(message: str):
    """
    Mengirim pesan notifikasi ke Telegram menggunakan library bawaan Python (urllib)
    agar 100% bebas dari masalah missing-dependency di runner cloud.
    """
    import urllib.request
    import json
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(" TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID tidak diset. Notifikasi dilewati.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                response.read()
            print(" Notifikasi status upload berhasil dikirim ke Telegram.")
            return
        except Exception as e:
            print(f" Percobaan {attempt + 1}/3 gagal mengirim notifikasi ke Telegram: {e}")
            if attempt < 2:
                time.sleep(2)


def send_telegram_photo(photo_path: str, caption: str = ""):
    """
    Mengirim file foto ke Telegram menggunakan library requests.
    """
    import requests
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(" TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID tidak diset. Notifikasi dilewati.")
        return
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    
    if not os.path.exists(photo_path):
        print(f" File foto tidak ditemukan: {photo_path}")
        return
        
    for attempt in range(3):
        try:
            with open(photo_path, "rb") as f:
                files = {"photo": f}
                data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
                response = requests.post(url, files=files, data=data, timeout=15)
                if response.status_code == 200:
                    print(" Notifikasi screenshot berhasil dikirim ke Telegram.")
                    return
                else:
                    print(f" Telegram sendPhoto gagal dengan status {response.status_code} pada percobaan {attempt + 1}/3: {response.text}")
        except Exception as e:
            print(f" Percobaan {attempt + 1}/3 gagal mengirim screenshot ke Telegram: {e}")
        if attempt < 2:
            time.sleep(2)


async def send_telegram_video_with_buttons(video_path: str, caption: str, video_id: str) -> str:
    """
    Mengirim file video ke Telegram lengkap dengan tombol inline publikasi.
    Mengmengembalikan file_id jika sukses.
    """
    import requests
    import json
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(" TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID tidak diset. Video tidak bisa dikirim.")
        return None
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    
    if not os.path.exists(video_path):
        print(f" Berkas video tidak ditemukan untuk dikirim ke Telegram: {video_path}")
        return None
        
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": " Upload YouTube", "callback_data": f"pub:yt:{video_id}"},
                {"text": " Upload TikTok", "callback_data": f"pub:tt:{video_id}"}
            ]
        ]
    }
    
    for attempt in range(3):
        try:
            print(f" Mengirim berkas video draf beserta tombol kontrol ke Telegram (percobaan {attempt + 1}/3)...")
            with open(video_path, "rb") as f:
                files = {"video": f}
                data = {
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "reply_markup": json.dumps(reply_markup)
                }
                import asyncio
                response = await asyncio.to_thread(requests.post, url, files=files, data=data, timeout=60)
                if response.status_code == 200:
                    res_data = response.json()
                    video_obj = res_data.get("result", {}).get("video", {})
                    file_id = video_obj.get("file_id")
                    print(f" Video draf berhasil dikirim ke Telegram! File ID: {file_id}")
                    return file_id
                else:
                    print(f" Telegram sendVideo gagal dengan status {response.status_code} pada percobaan {attempt + 1}/3: {response.text}")
        except Exception as e:
            print(f" Percobaan {attempt + 1}/3 gagal mengirim video dengan tombol ke Telegram: {e}")
        if attempt < 2:
            time.sleep(3)
    return None


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bot Video Auto Pipeline")
    parser.add_argument("--channel", default="ruangpikir", help="Channel ID dari config/channels.json")
    parser.add_argument("--force", action="store_true", help="Paksa jalankan pipeline meskipun baru saja upload")
    args, unknown = parser.parse_known_args()
    channel_id = args.channel

    firebase_connector = None
    try:
        print(f" Memulai Pipeline Pembuatan Video Otomatis untuk Channel: {channel_id}...")
        
        # Cegah double upload berdekatan khusus untuk trigger jadwal otomatis (cron schedule)
        import os
        import time
        import firebase_connector
        
        is_schedule = os.getenv("GITHUB_EVENT_NAME") == "schedule"
        if is_schedule and not args.force:
            last_upload = firebase_connector.get_last_upload_timestamp(channel_id)
            if last_upload > 0:
                elapsed_seconds = time.time() - last_upload
                # Batasi minimal 3 jam (10800 detik) antar upload otomatis
                if elapsed_seconds < 10800:
                    hours_ago = elapsed_seconds / 3600
                    print(f" Channel {channel_id} baru saja mengunggah video {hours_ago:.2f} jam yang lalu.")
                    print(" Lewati jadwal otomatis kali ini untuk mencegah upload berdekatan. Selesai.")
                    return
                    
        #  PRIME TIME SCHEDULER: Jangan publikasi di jam tidur (01:00 - 06:00 WIB)
        if is_schedule and not args.force:
            from datetime import datetime, timezone, timedelta
            wib_timezone = timezone(timedelta(hours=7))
            current_wib = datetime.now(wib_timezone)
            hour = current_wib.hour
            
            if 1 <= hour <= 6:
                print(f" Saat ini jam {hour:02d}:00 WIB. Waktunya penonton tidur.")
                print(" Membatalkan eksekusi otomatis untuk mencegah video sepi. Selesai.")
                return

        
        # Jalankan pembersihan draf lama (> 7 hari) untuk menghemat limit database
        try:
            import firebase_connector
            firebase_connector.cleanup_old_drafts(days=7)
        except Exception as clean_err:
            print(f" Gagal menjalankan pembersihan draf otomatis: {clean_err}")
            
        # Jalankan pembaruan statistik video YouTube secara otomatis
        try:
            import firebase_connector
            from youtube_uploader import get_youtube_stats
            yt_video_map = firebase_connector.get_active_youtube_video_ids(limit=50)
            if yt_video_map:
                print(f" Menemukan {len(yt_video_map)} video YouTube untuk diperiksa statistiknya...")
                stats = await get_youtube_stats(list(yt_video_map.values()))
                for draft_id, yt_id in yt_video_map.items():
                    if yt_id in stats:
                        prev_views = firebase_connector.get_previous_views(draft_id)
                        views = stats[yt_id]["views"]
                        likes = stats[yt_id]["likes"]
                        firebase_connector.update_draft_stats(draft_id, views, likes)
                        
                        #  VIRAL ALERT: Deteksi lonjakan views > 200%
                        if prev_views > 0 and views >= prev_views * 3:
                            growth_pct = int((views / prev_views - 1) * 100)
                            viral_msg = (
                                f" <b>VIDEO VIRAL ALERT!</b>\n\n"
                                f" <b>Lonjakan Views:</b> {prev_views:,} → {views:,} (+{growth_pct}%)\n"
                                f" <b>Likes:</b> {likes:,}\n\n"
                                f" <b>Draft ID:</b> <code>{draft_id}</code>\n"
                                f" https://youtu.be/{yt_id}\n\n"
                                f" Video ini sedang viral! Pertimbangkan membuat konten lanjutan."
                            )
                            send_telegram_message(viral_msg)
                            print(f" VIRAL ALERT dikirim! Views naik {growth_pct}% untuk {draft_id}")
                            
                print(" Pembaruan statistik video YouTube selesai.")
        except Exception as stats_err:
            print(f" Gagal memperbarui statistik video: {stats_err}")

        #  ANALISIS KOMENTAR & BALASAN OTOMATIS: Baca komentar video viral, buat insight AI, dan balas otomatis
        try:
            import firebase_connector
            from youtube_uploader import get_top_comments, reply_to_youtube_comments
            viral_map = firebase_connector.get_viral_video_ids(min_views=500, limit=2, channel_id=channel_id)
            if viral_map:
                print(f" Ditemukan {len(viral_map)} video viral untuk dianalisis komentarnya...")
                from video_builder import analyze_comments_with_gemini
                for draft_id, yt_id in viral_map.items():
                    # 1. Jalankan Balasan Otomatis menggunakan Gemini
                    await reply_to_youtube_comments(yt_id, max_replies=2)
                    
                    # 2. Ambil komentar untuk analisis insight naskah
                    comments = await get_top_comments(yt_id, max_results=20)
                    
                    # --- NLP Filter Sederhana ---
                    def sanitize_comments_nlp(raw_comments):
                        sanitized = []
                        for c in raw_comments:
                            text = c.get("text", "")
                            words = text.split()
                            # Syarat 1: Minimal 3 kata agar ada konteks
                            if len(words) < 3:
                                continue
                            # Syarat 2: Tidak boleh ada link promosi
                            if "http" in text or "www" in text:
                                continue
                            # Syarat 3: Rasio karakter alfabetis minimal 50% untuk mencegah spam emoji penuh
                            alpha_count = sum(1 for char in text if char.isalpha())
                            if alpha_count / max(len(text), 1) < 0.5:
                                continue
                            sanitized.append(c)
                        return sanitized
                        
                    if comments:
                        clean_comments = sanitize_comments_nlp(comments)
                        insight = None
                        if clean_comments:
                            insight = await analyze_comments_with_gemini(clean_comments)
                        if insight:
                            firebase_connector.mark_comments_analyzed(draft_id, insight)
                            print(f" Insight komentar disimpan untuk {draft_id}: {insight[:80]}...")
        except Exception as comment_err:
            print(f" Gagal menganalisis/membalas komentar video: {comment_err}")


        
        # Lakukan import secara lokal di dalam fungsi untuk melacak jika eror berasal dari file import
        print(" Meng-import modul video_builder...")
        from video_builder import create_video
        
        if firebase_connector:
            firebase_connector.clear_used_clips_queue()
        
        print(f" Menjalankan fungsi create_video() untuk channel: {channel_id}...")
        success = await create_video(channel_id=channel_id)
        
        if success:
            print(" Video Berhasil Dirender Sempurna!")
            
            # Ambil metadata hasil rancangan Gemini dari berkas
            from config import DIR_TEMP
            caption = ""
            tags = []
            category_id = "22"
            interactive_comment = ""
            theme = "classic_yellow"
            niche = "psychology"
            hook = "FAKTA MENARIK"
            yt_title = ""
            yt_description = ""
            metadata_path = os.path.join(DIR_TEMP, "video_metadata.json")
            if os.path.exists(metadata_path):
                try:
                    import json
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        meta_data = json.load(f)
                        caption = meta_data.get("caption", "")
                        tags = meta_data.get("tags", [])
                        category_id = meta_data.get("category_id", "22")
                        interactive_comment = meta_data.get("interactive_comment", "")
                        theme = meta_data.get("theme", "classic_yellow")
                        niche = meta_data.get("niche", "psychology")
                        hook = meta_data.get("hook", "FAKTA MENARIK")
                        yt_title = meta_data.get("yt_title", "")
                        yt_description = meta_data.get("yt_description", "")
                    os.remove(metadata_path) # Bersihkan setelah dibaca
                except Exception as meta_err:
                    print(f" Gagal membaca/menghapus metadata: {meta_err}")

            # Cari file video terbaru di folder output untuk diunggah (digunakan untuk TikTok & YouTube)
            import glob
            video_files = glob.glob("output/*.mp4")
            latest_video = max(video_files, key=os.path.getctime) if video_files else None

            # Pembuatan Thumbnail: ambil frame bersih dari detik ke-2 video
            thumbnail_path = "output/thumbnail.jpg"
            has_thumbnail = False
            if latest_video:
                print(" Memulai proses pembuatan auto-thumbnail...")
                try:
                    import subprocess
                    import asyncio
                    result = await asyncio.to_thread(
                        subprocess.run,
                        [
                            "ffmpeg", "-y",
                            "-ss", "2",
                            "-i", latest_video,
                            "-vframes", "1",
                            "-q:v", "2",
                            thumbnail_path
                        ],
                        capture_output=True, text=True
                    )
                    if os.path.exists(thumbnail_path):
                        has_thumbnail = True
                        print(f" Thumbnail berhasil dibuat: {thumbnail_path}")
                    else:
                        print(f" FFmpeg gagal membuat thumbnail: {result.stderr[-200:]}")
                except Exception as thumb_err:
                    print(f" Gagal membuat thumbnail: {thumb_err}")

            # Poin 9: Integrasi Upload Otomatis ke TikTok
            enable_upload = os.getenv("ENABLE_TIKTOK_UPLOAD", "false").lower() == "true"
            any_upload_success = False
            
            if enable_upload and channel_id == "ruangpikir":
                if latest_video:
                    print(" Memicu pengunggahan otomatis ke TikTok...")
                    from uploader import upload_to_tiktok
                    print(f" Menemukan video terbaru untuk TikTok: {latest_video}. Memulai upload...")
                    try:
                        tiktok_username = await upload_to_tiktok(latest_video, caption=caption, comment_text=interactive_comment)
                        print(" Sukses mengunggah video ke TikTok!")
                        any_upload_success = True
                        
                        # Kirim notifikasi SUKSES ke Telegram
                        msg = (
                            " <b>TIKTOK UPLOAD SUKSES!</b>\n\n"
                            f" <b>Akun TikTok:</b> <code>{tiktok_username}</code>\n"
                            f" <b>Video:</b> <code>{os.path.basename(latest_video)}</code>\n\n"
                            f" <b>Caption & Hashtags:</b>\n<i>{caption}</i>"
                        )
                        send_telegram_message(msg)
                    except Exception as upload_err:
                        print(f" Gagal mengunggah ke TikTok: {upload_err}")
                        
                        # Ambil username untuk ditaruh di log error
                        from uploader import get_tiktok_username_from_cookies
                        failed_user = get_tiktok_username_from_cookies()
                        
                        import html
                        escaped_err = html.escape(str(upload_err))
                        
                        # Deteksi khusus: Cookie TikTok Kedaluwarsa
                        cookie_expired_keywords = ["cookies kedaluwarsa", "cookie expired", "login ulang", "login" , "signup"]
                        if any(kw in str(upload_err).lower() for kw in cookie_expired_keywords):
                            msg = (
                                " <b>COOKIE TIKTOK KEDALUWARSA!</b>\n\n"
                                f" <b>Akun:</b> <code>{failed_user}</code>\n\n"
                                " <b>Tindakan yang diperlukan:</b>\n"
                                "1. Login ulang ke TikTok di browser.\n"
                                "2. Ekspor cookie menggunakan ekstensi EditThisCookie.\n"
                                "3. Perbarui secret <code>TIKTOK_COOKIES</code> di GitHub Settings → Secrets."
                            )
                        else:
                            msg = (
                                " <b>TIKTOK UPLOAD GAGAL!</b>\n\n"
                                f" <b>Akun TikTok:</b> <code>{failed_user}</code>\n"
                                f" <b>Video:</b> <code>{os.path.basename(latest_video)}</code>\n\n"
                                f" <b>Error Log:</b>\n<code>{escaped_err}</code>"
                            )
                        send_telegram_message(msg)
                        
                        # Kirim screenshot kegagalan jika ada berkas hasil tangkapan layar
                        screenshot_path = "output/error_screenshot.png"
                        if os.path.exists(screenshot_path):
                            send_telegram_photo(
                                screenshot_path,
                                caption=f" <b>Bukti Kegagalan Layar (TikTok Upload)</b>\nAkun: <code>{failed_user}</code>"
                            )
                else:
                    print(" Tidak ada file video di folder output untuk diunggah ke TikTok.")
            else:
                print(" Pengunggahan otomatis ke TikTok dinonaktifkan (ENABLE_TIKTOK_UPLOAD=false).")

            # Integrasi Upload Otomatis ke YouTube Shorts
            enable_yt_upload = os.getenv("ENABLE_YOUTUBE_UPLOAD", "false").lower() == "true"
            if enable_yt_upload:
                if latest_video:
                    print(" Memicu pengunggahan otomatis ke YouTube Shorts...")
                    from youtube_uploader import upload_to_youtube
                    print(f" Menemukan video terbaru untuk YouTube: {latest_video}. Memulai upload...")
                    try:
                        youtube_url = await upload_to_youtube(
                            latest_video, 
                            caption=caption, 
                            tags=tags, 
                            category_id=category_id,
                            comment_text=interactive_comment,
                            yt_title=yt_title,
                            yt_description=yt_description,
                            channel_id=channel_id
                        )
                        print(" Sukses mengunggah video ke YouTube Shorts!")
                        any_upload_success = True
                        
                        # Ekstrak ID dari URL https://youtu.be/ID
                        yt_video_id = youtube_url.split("/")[-1]
                        
                        # Unggah custom thumbnail jika sukses dibuat
                        if has_thumbnail:
                            try:
                                from youtube_uploader import upload_thumbnail
                                await upload_thumbnail(yt_video_id, thumbnail_path, channel_id=channel_id)
                            except Exception as thumb_up_err:
                                print(f" Gagal mengunggah thumbnail ke YouTube: {thumb_up_err}")
                                
                        # Simpan info publikasi ke draf agar performanya bisa dipantau
                        direct_video_id = f"video_{int(time.time())}"
                        try:
                            import firebase_connector
                            draft_data = {
                                "video_id": direct_video_id,
                                "caption": caption,
                                "tags": tags,
                                "category_id": category_id,
                                "interactive_comment": interactive_comment,
                                "theme": theme,
                                "platform": "youtube",
                                "platform_video_id": yt_video_id,
                                "niche": niche,
                                "yt_title": yt_title,
                                "yt_description": yt_description,
                                "channel_id": channel_id
                            }
                            firebase_connector.save_video_draft(direct_video_id, draft_data)
                        except Exception as draft_err:
                            print(f" Gagal mencatat draf untuk direct upload: {draft_err}")
                            
                        # Kirim notifikasi SUKSES ke Telegram
                        msg = (
                            " <b>YOUTUBE SHORTS UPLOAD SUKSES!</b>\n\n"
                            f" <b>Video:</b> <code>{os.path.basename(latest_video)}</code>\n"
                            f" <b>Tautan Shorts:</b> {youtube_url}\n\n"
                            f" <b>Caption:</b>\n<i>{caption}</i>"
                        )
                        send_telegram_message(msg)
                    except Exception as yt_err:
                        print(f" Gagal mengunggah ke YouTube Shorts: {yt_err}")
                        
                        # Kirim notifikasi GAGAL ke Telegram
                        import html
                        escaped_err = html.escape(str(yt_err))
                        msg = (
                            " <b>YOUTUBE SHORTS UPLOAD GAGAL!</b>\n\n"
                            f" <b>Video:</b> <code>{os.path.basename(latest_video)}</code>\n\n"
                            f" <b>Error Log:</b>\n<code>{escaped_err}</code>"
                        )
                        send_telegram_message(msg)
                        
                        # Kirim screenshot kegagalan jika ada berkas hasil tangkapan layar
                        yt_screenshot = "output/youtube_error_screenshot.png"
                        if os.path.exists(yt_screenshot):
                            send_telegram_photo(
                                yt_screenshot,
                                caption=" <b>Bukti Kegagalan Layar (YouTube Upload)</b>"
                            )
                else:
                    print(" Tidak ada file video di folder output untuk diunggah ke YouTube Shorts.")
            else:
                print(" Pengunggahan otomatis ke YouTube Shorts dinonaktifkan (ENABLE_YOUTUBE_UPLOAD=false).")

            # Mode Draf Jarak Jauh (Telegram Control Panel) jika kedua upload mati
            if not enable_upload and not enable_yt_upload and latest_video:
                print(" Mode Draf Aktif: Mengirim video ke Telegram dengan panel tombol...")
                video_id = f"video_{int(time.time())}"
                
                # Kirim ke Telegram dan dapatkan file_id
                tg_caption = (
                    " <b>Draf Video Siap!</b>\n\n"
                    f" <b>Caption:</b>\n<i>{caption}</i>\n\n"
                    f" <b>Pancingan Komentar:</b>\n<i>{interactive_comment}</i>"
                )
                file_id = await send_telegram_video_with_buttons(latest_video, caption=tg_caption, video_id=video_id)
                
                if file_id:
                    # Simpan ke Firestore/Lokal
                    import firebase_connector
                    draft_data = {
                        "video_id": video_id,
                        "file_id": file_id,
                        "caption": caption,
                        "tags": tags,
                        "category_id": category_id,
                        "interactive_comment": interactive_comment,
                        "theme": theme,
                        "niche": niche,
                        "channel_id": channel_id
                    }
                    try:
                        firebase_connector.save_video_draft(video_id, draft_data)
                    except Exception as draft_err:
                        print(f" Gagal mencatat draf ke database: {draft_err}")
            
            # 6. Commit status "Terpakai" HANYA jika upload sukses (mencegah pemborosan clip saat testing)
            if firebase_connector:
                if any_upload_success:
                    firebase_connector.commit_used_clips()
                else:
                    logger = __import__("logging").getLogger("bot")
                    logger.info(" Tidak ada video yang berhasil diunggah ke sosmed. Antrean klip Pexels dibuang (tidak ditandai terpakai).")
                    firebase_connector.clear_used_clips_queue()
                
        else:
            print(" Gagal membuat video (Kembalian Bernilai False).")
            if firebase_connector:
                firebase_connector.clear_used_clips_queue()
            sys.exit(1)
            
    except Exception as e:
        print(f" Terjadi Eror Fatal pada Pipeline Utama: {e}")
        print("\n DETAIL TRACEBACK EROR:")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    # Paksa cetak langsung ke log tanpa buffer agar terlihat di GitHub Actions
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(main())
