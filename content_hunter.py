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

def hunt_trending_video(target_url: str, download_dir: str = "data/raw_materials") -> Optional[Dict]:
    """
    Memindai profil Instagram target menggunakan yt-dlp untuk mendapatkan video terbaru.
    """
    import subprocess
    import random
    
    os.makedirs(download_dir, exist_ok=True)
    
    for old_json in glob.glob(f"{download_dir}/*.info.json"):
        try:
            os.remove(old_json)
        except Exception:
            pass
            
    logger.info(f" 🕵️ Content Hunter memindai Instagram target: '{target_url}'...")
    
    cmd = [
        "yt-dlp",
        target_url,
        "--playlist-end", "10",
        "--dump-json",
        "--ignore-errors",
        "--no-warnings"
    ]
    
    cookie_file = "ig_cookies.txt" if os.path.exists("ig_cookies.txt") else ("cookies.txt" if os.path.exists("cookies.txt") else None)
    if cookie_file:
        cmd.extend(["--cookies", cookie_file])
        
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        logger.error(f" ❌ yt-dlp gagal dieksekusi: {e}")
        return None
        
    videos = []
    for line in result.stdout.strip().split("\n"):
        if not line: continue
        try:
            v_data = json.loads(line)
            videos.append(v_data)
        except:
            pass
            
    if not videos:
        logger.error(f" ❌ Tidak ada video ditemukan di {target_url}. (Mungkin butuh cookies IG yang valid atau profil diprivasi).")
        if result.stderr:
            logger.error(f" Error: {result.stderr[:200]}")
        return None
        
    random.shuffle(videos)
    
    selected_video = None
    for v in videos:
        title_lower = v.get("title", "").lower()
        desc_lower = v.get("description", "").lower()
        if any(x in title_lower or x in desc_lower for x in ["react", "duet", "reaction", "part"]):
            continue
            
        duration = v.get("duration")
        if duration and not (15 <= duration <= 70):
            continue
            
        selected_video = v
        break
            
    if not selected_video:
        selected_video = videos[0] # Fallback
        
    video_id = selected_video.get("id", "unknown_id")
    uploader = selected_video.get("uploader", "unknown_user")
    title = sanitize_title(selected_video.get("title", "Untitled"))
    duration = selected_video.get("duration", 0)
    webpage_url = selected_video.get("webpage_url", target_url)
    
    filepath = os.path.join(download_dir, f"{video_id}.mp4")
    info_path = os.path.join(download_dir, f"{video_id}.info.json")
    
    logger.info(f" 📥 Mengunduh video IG: {video_id} dari {uploader}")
    dl_cmd = [
        "yt-dlp",
        webpage_url,
        "-o", filepath,
        "--no-warnings"
    ]
    if cookie_file:
        dl_cmd.extend(["--cookies", cookie_file])
        
    subprocess.run(dl_cmd, capture_output=True)
    
    if not os.path.exists(filepath):
        logger.error(" ❌ Gagal mengunduh file video IG.")
        return None
        
    metadata = {
        "id": video_id,
        "ext": "mp4",
        "uploader": uploader,
        "title": title,
        "duration": duration,
        "source": "instagram"
    }
    with open(info_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f)
        
    logger.info(f" ✅ Target terkunci! Video IG diunduh dari @{uploader} | Durasi: {duration}s")
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
