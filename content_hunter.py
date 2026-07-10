import os
import glob
import json
import logging
import subprocess
import re
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
    Mencari dan mengunduh satu video trending (Shorts) berdasarkan keyword menggunakan yt-dlp.
    Mengembalikan dictionary berisi path file dan metadata (username, judul).
    """
    os.makedirs(download_dir, exist_ok=True)
    
    # yt-dlp mencari 1 video shorts. 
    search_query = f"ytsearch1: {keyword} shorts"
    
    # -f: format terbaik (MP4)
    # --write-info-json: menyimpan metadata lengkap (.info.json)
    # --no-playlist: pastikan hanya 1 video
    # -o: template nama file
    command = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--write-info-json",
        "--no-playlist",
        "--match-filter", "view_count >= 100000",
        "--extractor-args", "youtube:player_client=android,web",
        "-o", f"{download_dir}/%(id)s.%(ext)s",
        search_query
    ]
    
    logger.info(f" 🕵️ Content Hunter sedang melacak video untuk keyword: '{keyword}'...")
    try:
        # Jalankan yt-dlp
        subprocess.run(command, capture_output=True, text=True, check=True)
        
        # Cari file .info.json terbaru di direktori
        # yt-dlp biasanya menyimpan dengan nama id.info.json
        list_of_files = glob.glob(f"{download_dir}/*.info.json")
        if not list_of_files:
            logger.error(" ❌ Hunter gagal menemukan metadata video yang diunduh.")
            return None
            
        # Ambil file terbaru yang diunduh
        latest_info = max(list_of_files, key=os.path.getctime)
        
        with open(latest_info, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
            
        video_id = metadata.get("id")
        ext = metadata.get("ext", "mp4")
        uploader = metadata.get("uploader", "unknown_user")
        title = sanitize_title(metadata.get("title", "Untitled"))
        duration = metadata.get("duration", 0)
        
        filepath = os.path.join(download_dir, f"{video_id}.{ext}")
        
        if not os.path.exists(filepath):
             logger.error(f" ❌ File video mentah tidak ditemukan: {filepath}")
             return None
             
        logger.info(f" ✅ Target terkunci! Video diunduh dari @{uploader} | Durasi: {duration}s")
        
        return {
            "filepath": filepath,
            "uploader": uploader,
            "title": title,
            "duration": duration,
            "id": video_id
        }
        
    except subprocess.CalledProcessError as e:
        logger.error(f" ❌ yt-dlp gagal mengunduh video: {e.stderr}")
        return None
    except Exception as e:
        logger.error(f" ❌ Kesalahan sistem pada Content Hunter: {e}")
        return None

if __name__ == "__main__":
    # Test sederhana
    logging.basicConfig(level=logging.INFO)
    res = hunt_trending_video("lucu prank indonesia")
    print(res)
