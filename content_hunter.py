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

def hunt_trending_video(keyword: str, download_dir: str = "data/raw_materials") -> Optional[Dict]:
    """
    Mencari dan mengunduh satu video trending berdasarkan keyword menggunakan TikWM (TikTok).
    Mengembalikan dictionary berisi path file dan metadata (username, judul).
    """
    os.makedirs(download_dir, exist_ok=True)
    
    # Bersihkan sisa metadata dari pencarian sebelumnya
    for old_json in glob.glob(f"{download_dir}/*.info.json"):
        try:
            os.remove(old_json)
        except Exception:
            pass
            
    logger.info(f" 🕵️ Content Hunter sedang melacak TikTok untuk keyword: '{keyword}'...")
    
    try:
        # Panggil API TikWM untuk pencarian TikTok
        res = requests.post("https://tikwm.com/api/feed/search", data={"keywords": keyword, "count": 12}, timeout=20)
        res.raise_for_status()
        data = res.json()
        
        videos = data.get("data", {}).get("videos", [])
        if not videos:
            logger.error(" ❌ TikWM tidak mengembalikan hasil pencarian TikTok.")
            return None
            
        import random
        random.shuffle(videos)
        
        selected_video = None
        for v in videos:
            play_count = v.get("play_count", 0)
            duration = v.get("duration", 0)
            title_lower = v.get("title", "").lower()
            
            if play_count >= 100000:
                # Filter Split-Screen & Bersambung (Reaction/Duet/Part) via judul
                if any(x in title_lower for x in ["react", "duet", "reaction", "part"]):
                    logger.info(" ⏭️ Video dilewati: Kemungkinan format reaksi/duet/bersambung (indikasi split-screen).")
                    continue
                    
                # SOP Durasi: 15-70 detik agar AI punya waktu untuk Voice Hook & narasi yang utuh
                if 15 <= duration <= 70:
                    selected_video = v
                    break
                else:
                    logger.info(f" ⏭️ Video dilewati: Durasi tidak sesuai ({duration}s)")
                
        if not selected_video:
            logger.error(" ❌ Tidak ada video TikTok yang memenuhi kriteria view_count >= 100k dan durasi 15-70s.")
            return None
            
        video_id = selected_video.get("video_id")
        uploader = selected_video.get("author", {}).get("unique_id", "unknown_user")
        title = sanitize_title(selected_video.get("title", "Untitled"))
        duration = selected_video.get("duration", 0)
        play_url = selected_video.get("play")
        
        if not play_url:
            logger.error(" ❌ URL unduhan MP4 TikTok tidak ditemukan.")
            return None
            
        ext = "mp4"
        filepath = os.path.join(download_dir, f"{video_id}.{ext}")
        info_path = os.path.join(download_dir, f"{video_id}.info.json")
        
        # Unduh MP4 mentah (Tanpa Watermark)
        logger.info(f" 📥 Mengunduh video mentah TikTok: {video_id}")
        mp4_res = requests.get(play_url, stream=True, timeout=30)
        mp4_res.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in mp4_res.iter_content(chunk_size=8192):
                f.write(chunk)
                
        # Simpan metadata JSON agar kompatibel dengan alur video_builder yang lama
        metadata = {
            "id": video_id,
            "ext": ext,
            "uploader": uploader,
            "title": title,
            "duration": duration,
            "source": "tiktok"
        }
        with open(info_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f)
            
        logger.info(f" ✅ Target terkunci! Video diunduh dari TikTok @{uploader} | Durasi: {duration}s")
        return {
            "filepath": filepath,
            "uploader": uploader,
            "title": title,
            "duration": duration,
            "id": video_id,
            "metadata": metadata
        }
        
    except Exception as e:
        logger.error(f" ❌ Gagal mencari atau mengunduh video TikTok: {e}")
        return None

if __name__ == "__main__":
    # Test sederhana
    logging.basicConfig(level=logging.INFO)
    res = hunt_trending_video("lucu prank indonesia")
    print(res)
