import os
import json
import asyncio
import logging
from google.cloud import firestore

# Setup Logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AnalyticsSync")

import firebase_connector
import youtube_uploader

# Import Gemini wrapper
from video_builder import call_gemini_with_retry
from ai.analytics_brain import record_video_performance, run_learning_loop

async def analyze_retention_heuristic(hook_text: str, views: int, likes: int, comments: list) -> int:
    """Menggunakan Gemini untuk menebak drop-off second berdasarkan hook, view, like, dan komentar."""
    comments_text = "\n- ".join(comments[:15]) if comments else "(Tidak ada komentar)"
    prompt = (
        f"You are an expert YouTube retention analyst. Analyze this short video's stats.\n"
        f"Initial Hook: '{hook_text}'\n"
        f"Views: {views}\n"
        f"Likes: {likes}\n"
        f"Comments:\n{comments_text}\n\n"
        "Based on the hook text, the view-to-like ratio, and comments (if any), estimate the average 'drop_off_second' (at what second do most people stop watching, typically between 3 and 35 seconds). "
        "If the view-to-like ratio is very poor or there are no comments, return a lower number (e.g., 3-10). If the stats are good, return higher (15-35).\n"
        "Return ONLY a pure JSON object in this exact format: {\"drop_off_second\": 15}"
    )
    
    try:
        res = await call_gemini_with_retry(prompt, is_json=True, temperature=0.3)
        import re
        match = re.search(r'\{.*\}', res, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            return int(data.get("drop_off_second", 0))
    except Exception as e:
        logger.error(f"Gagal menganalisis retention via Gemini: {e}")
        
    return 0

async def sync_youtube_analytics():
    """Menarik data dari YouTube dan menyinkronkannya ke Firestore."""
    logger.info("Memulai sinkronisasi analitik YouTube...")
    
    if not firebase_connector.db:
        logger.error("Koneksi Firestore tidak tersedia.")
        return
        
    # Ambil semua draf yang sudah diunggah ke YouTube
    docs = firebase_connector.db.collection("drafts").where("platform", "==", "youtube").stream()
    
    # Kelompokkan berdasarkan channel_id
    videos_by_channel = {}
    doc_refs = {}
    
    for doc in docs:
        data = doc.to_dict()
        vid_id = data.get("platform_video_id")
        channel = data.get("channel_id", "ruangpikir") # Fallback default
        if vid_id:
            if channel not in videos_by_channel:
                videos_by_channel[channel] = []
            videos_by_channel[channel].append(vid_id)
            doc_refs[vid_id] = {"ref": doc.reference, "data": data}
            
    if not videos_by_channel:
        logger.info("Tidak ada video YouTube yang ditemukan di Firestore.")
        return
        
    for channel, vid_list in videos_by_channel.items():
        logger.info(f"Menarik statistik untuk {len(vid_list)} video di channel '{channel}'...")
        
        # YouTube API membatasi 50 ID per request, jadi kita batch
        batch_size = 50
        for i in range(0, len(vid_list), batch_size):
            batch_ids = vid_list[i:i+batch_size]
            
            # Ambil Views & Likes
            stats = await youtube_uploader.get_youtube_stats(batch_ids, channel)
            
            # Proses setiap video secara individual untuk komentar dan retensi
            for vid_id in batch_ids:
                if vid_id not in stats:
                    continue
                    
                v_stats = stats[vid_id]
                views = v_stats.get("views", 0)
                likes = v_stats.get("likes", 0)
                
                logger.info(f"[{vid_id}] Views: {views}, Likes: {likes}")
                
                # Ambil Komentar Teratas
                comments = await youtube_uploader.get_top_comments(vid_id, max_results=10, channel_id=channel)
                
                doc_info = doc_refs[vid_id]
                hook_text = doc_info["data"].get("hook", "")
                
                # Analisis Drop-off menggunakan Gemini (Selalu jalan meskipun 0 komentar)
                drop_off = await analyze_retention_heuristic(hook_text, views, likes, comments)
                logger.info(f"[{vid_id}] Estimasi Drop-off: {drop_off}s (berdasarkan {views} views, {likes} likes, {len(comments)} komentar)")
                
                # Update ke Firestore & Cadangan Lokal
                caption_text = doc_info["data"].get("caption", hook_text)
                try:
                    # Simpan data ke cadangan analitik lokal
                    firebase_connector.save_local_performance_data(
                        video_id=vid_id,
                        caption=caption_text,
                        views=views,
                        likes=likes
                    )
                    
                    # Gunakan fungsi bawaan untuk views dan likes (karena ada logic A/B test aggregation)
                    firebase_connector.update_draft_stats(doc_info["ref"].id, views, likes)
                    
                    # Update tambahan untuk kolom khusus (drop_off dan comments)
                    update_data = {}
                    if drop_off > 0:
                        update_data["drop_off_second"] = drop_off
                    
                    if comments:
                        update_data["latest_comments"] = comments
                        
                    if update_data:
                        doc_info["ref"].update(update_data)
                        
                    # Integrasi: Rekam performa ke Analytics Brain
                    topic = doc_info["data"].get("topic", caption_text[:30])
                    record_video_performance(
                        video_id=vid_id,
                        hook_text=hook_text,
                        topic=topic,
                        channel_id=channel,
                        views=views,
                        likes=likes,
                        comments=comments,
                        drop_off_second=drop_off,
                        hook_score=doc_info["data"].get("hook_score", {})
                    )
                        
                except Exception as update_err:
                    logger.error(f"Gagal memperbarui analitik untuk {vid_id}: {update_err}")

        # Integrasi: Jalankan learning loop untuk channel ini setelah semua data disinkronkan
        channel_niche = doc_info["data"].get("niche", "dark psychology") if vid_list else "dark psychology"
        logger.info(f"Menjalankan learning loop untuk channel {channel}...")
        report = await run_learning_loop(channel_id=channel, channel_niche=channel_niche)
        
        # Kirim Laporan Harian ke Telegram
        try:
            from app import send_telegram_message
            hints = report.get("performance_hints", "")
            top_hooks = report.get("best_hooks", [])
            topics = report.get("topic_recommendations", [])
            
            msg = f"📊 <b>Laporan Harian Analytics Brain</b>\n"
            msg += f"Channel: <code>{channel}</code>\n\n"
            
            msg += "🧠 <b>Insight Pembelajaran (Hints):</b>\n"
            msg += f"<i>{hints}</i>\n\n"
            
            if top_hooks:
                msg += "🔥 <b>Top 3 Hook Terampuh:</b>\n"
                for idx, h in enumerate(top_hooks[:3]):
                    msg += f"{idx+1}. {h['hook']} (Ret: {h.get('avg_retention',0):.0%})\n"
                msg += "\n"
                
            if topics:
                msg += "💡 <b>Rekomendasi Konten Esok Hari:</b>\n"
                for idx, t in enumerate(topics[:3]):
                    msg += f"• {t.get('topic')}\n"
            
            send_telegram_message(msg)
            logger.info("Laporan Dashboard Telegram berhasil dikirim.")
        except Exception as e:
            logger.error(f"Gagal mengirim laporan Telegram: {e}")

    logger.info("✅ Sinkronisasi Analitik YouTube Selesai!")

if __name__ == "__main__":
    asyncio.run(sync_youtube_analytics())
