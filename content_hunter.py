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

def hunt_trending_video(drive_folder_url: str, download_dir: str = "data/raw_materials") -> Optional[Dict]:
    """
    Mengunduh folder Google Drive publik yang berisi video mentah, mengecek ke Firebase,
    dan memilih 1 video yang belum pernah diunggah.
    """
    import gdown
    import random
    import shutil
    import firebase_connector
    
    os.makedirs(download_dir, exist_ok=True)
    
    # Bersihkan sisa unduhan sebelumnya
    for f in glob.glob(f"{download_dir}/*"):
        try:
            if os.path.isfile(f):
                os.remove(f)
            elif os.path.isdir(f):
                shutil.rmtree(f)
        except Exception:
            pass
            
    logger.info(f" 🕵️ Content Hunter menyedot folder Google Drive: '{drive_folder_url}'...")
    
    try:
        # Unduh isi folder (gdown butuh URL folder atau ID)
        gdown.download_folder(url=drive_folder_url, output=download_dir, quiet=False, use_cookies=False)
    except Exception as e:
        logger.error(f" ❌ Gagal mengunduh folder Google Drive via gdown: {e}")
        return None
        
    # Kumpulkan semua file MP4 yang berhasil diunduh (termasuk di dalam subfolder jika ada)
    mp4_files = []
    for root, dirs, files in os.walk(download_dir):
        for file in files:
            if file.lower().endswith('.mp4'):
                mp4_files.append(os.path.join(root, file))
                
    if not mp4_files:
        logger.error(f" ❌ Tidak ada file MP4 yang ditemukan di folder Google Drive tersebut.")
        return None
        
    # Acak urutan pengecekan
    random.shuffle(mp4_files)
    
    selected_filepath = None
    video_id = None
    
    for filepath in mp4_files:
        # Gunakan nama file tanpa ekstensi sebagai ID (sekaligus deskripsi kejadian)
        filename = os.path.basename(filepath)
        basename = os.path.splitext(filename)[0]
        
        # Cek ke Firebase apakah ID/nama file ini sudah pernah dipakai
        if not firebase_connector.is_clip_used(basename):
            selected_filepath = filepath
            video_id = basename
            break
            
    if not selected_filepath:
        logger.warning(f" ⚠️ Semua {len(mp4_files)} video di folder Drive sudah pernah dipakai! Mengambil file acak pertama sebagai fallback (MUNGKIN DUPLIKAT).")
        selected_filepath = mp4_files[0]
        filename = os.path.basename(selected_filepath)
        video_id = os.path.splitext(filename)[0]
        
    # Tandai akan dipakai (masuk antrean memori)
    firebase_connector.mark_clip_used(video_id)
    
    # Pindahkan ke root download_dir agar mudah diakses
    final_filepath = os.path.join(download_dir, f"{video_id}.mp4")
    if selected_filepath != final_filepath:
        shutil.move(selected_filepath, final_filepath)
        
    info_path = os.path.join(download_dir, f"{video_id}.info.json")
    
    # Judul/Caption didasarkan pada nama file yang ditulis oleh pengguna (ganti underscore dengan spasi)
    title = video_id.replace("_", " ").title()
    
    metadata = {
        "id": video_id,
        "ext": "mp4",
        "uploader": "google_drive",
        "title": title,
        "duration": 0, # Durasi tidak diketahui dari gdown, abaikan saja
        "source": "google_drive"
    }
    with open(info_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f)
        
    logger.info(f" ✅ Target terkunci! Video '{title}' dipilih dari Drive.")
    return {
        "filepath": final_filepath,
        "uploader": "google_drive",
        "title": title,
        "duration": 0,
        "id": video_id,
        "metadata": metadata
    }

if __name__ == "__main__":
    # Test sederhana
    logging.basicConfig(level=logging.INFO)
    res = hunt_trending_video("lucu prank indonesia")
    print(res)
