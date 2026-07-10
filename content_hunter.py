import os
import glob
import json
import logging
import subprocess
import re
import requests
from typing import Optional, Dict

logger = logging.getLogger("bot")

def sanitize_title(title: str) -> str:
    """Membersihkan judul dari emoji, hashtag berlebihan, dan junk characters."""
    # Hapus hashtag
    title = re.sub(r'#\w+', '', title)
    # Hapus karakter non-ascii (seperti emoji, simbol aneh)
    title = title.encode('ascii', 'ignore').decode('ascii')
    # Bersihkan whitespace ekstra
    title = ' '.join(title.split())
    return title.strip()

def json_cookies_to_netscape(json_filepath: str, netscape_filepath: str) -> bool:
    """Mengonversi file cookie JSON menjadi format Netscape (diperlukan oleh yt-dlp)."""
    try:
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        with open(netscape_filepath, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# http://curl.haxx.se/rfc/cookie_spec.html\n")
            f.write("# This is a generated file!  Do not edit.\n\n")
            for cookie in data:
                domain = cookie.get('domain', '')
                include_subdomains = 'TRUE' if domain.startswith('.') else 'FALSE'
                path = cookie.get('path', '/')
                secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                expiration = str(int(cookie.get('expirationDate', 0))) if 'expirationDate' in cookie else '0'
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                f.write(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")
        return True
    except Exception as e:
        logger.warning(f" Gagal mengonversi cookie JSON ke Netscape: {e}")
        return False

def hunt_trending_video(target_subreddit: str, download_dir: str = "data/raw_materials") -> Optional[Dict]:
    """
    Memindai Subreddit target menggunakan PRAW untuk mendapatkan video komedi terbaik.
    """
    import subprocess
    import random
    import praw
    import time
    
    os.makedirs(download_dir, exist_ok=True)
    
    for old_json in glob.glob(f"{download_dir}/*.info.json"):
        try:
            os.remove(old_json)
        except Exception:
            pass
            
    logger.info(f" 🕵️ Content Hunter memindai Subreddit target: 'r/{target_subreddit}'...")
    
    reddit_client_id = os.getenv("REDDIT_CLIENT_ID")
    reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    
    if not reddit_client_id or not reddit_client_secret:
        logger.error(" ❌ Kredensial PRAW (REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET) belum dikonfigurasi di Environment Variable.")
        return None
        
    try:
        reddit = praw.Reddit(
            client_id=reddit_client_id,
            client_secret=reddit_client_secret,
            user_agent="KomediHunterBot:v1.0 (by /u/developer)"
        )
        
        subreddit = reddit.subreddit(target_subreddit)
        # Ambil 25 post terpanas
        hot_posts = subreddit.hot(limit=25)
        
        videos = []
        for post in hot_posts:
            if hasattr(post, "is_video") and post.is_video and hasattr(post, "secure_media") and post.secure_media:
                reddit_video = post.secure_media.get("reddit_video", {})
                duration = reddit_video.get("duration", 0)
                
                if 15 <= duration <= 70:
                    videos.append({
                        "id": post.id,
                        "title": post.title,
                        "url": post.url,
                        "duration": duration,
                        "uploader": str(post.author),
                        "score": post.score
                    })
                    
        if not videos:
            logger.error(f" ❌ Tidak ada post berformat Video dengan durasi 15-70s di r/{target_subreddit} saat ini.")
            return None
            
        # Acak video untuk variasi
        random.shuffle(videos)
        selected_video = videos[0]
        
    except Exception as e:
        logger.error(f" ❌ Gagal menarik data dari Reddit via PRAW: {e}")
        return None
        
    video_id = selected_video["id"]
    uploader = selected_video["uploader"]
    title = sanitize_title(selected_video["title"])
    duration = selected_video["duration"]
    webpage_url = selected_video["url"]
    
    filepath = os.path.join(download_dir, f"{video_id}.mp4")
    info_path = os.path.join(download_dir, f"{video_id}.info.json")
    
    logger.info(f" 📥 Mengunduh video Reddit: {video_id} dari u/{uploader} (Score: {selected_video['score']})")
    
    dl_cmd = [
        "yt-dlp",
        webpage_url,
        "-o", filepath,
        "--no-warnings"
    ]
    
    try:
        # Delay sopan (Nana's Advice)
        time.sleep(4)
        subprocess.run(dl_cmd, capture_output=True, timeout=120)
    except Exception as e:
        logger.error(f" ❌ Error eksekusi yt-dlp untuk Reddit: {e}")
        
    if not os.path.exists(filepath):
        logger.error(" ❌ Gagal mengunduh file MP4 video Reddit.")
        return None
        
    metadata = {
        "id": video_id,
        "ext": "mp4",
        "uploader": uploader,
        "title": title,
        "duration": duration,
        "source": "reddit"
    }
    with open(info_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f)
        
    logger.info(f" ✅ Target terkunci! Video Reddit diunduh dari r/{target_subreddit} | u/{uploader} | Durasi: {duration}s")
    return {
        "filepath": filepath,
        "uploader": uploader,
        "title": title,
        "duration": duration,
        "id": video_id,
        "metadata": metadata
    }

if __name__ == "__main__":
    # Test sederhana
    logging.basicConfig(level=logging.INFO)
    res = hunt_trending_video("lucu prank indonesia")
    print(res)
