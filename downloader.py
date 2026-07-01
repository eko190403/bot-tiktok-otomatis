import os
import random
import requests
from config import PEXELS_API_KEY, DIR_TEMP

def search_pexels_videos(keyword: str, per_page: int = 5) -> list:
    """Mencari video portrait di Pexels berdasarkan keyword dari Gemini."""
    if not PEXELS_API_KEY:
        raise ValueError("❌ PEXELS_API_KEY belum dikonfigurasi di GitHub Secrets.")
        
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={keyword}&per_page={per_page}&orientation=portrait"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json().get("videos", [])
    except Exception as e:
        print(f"⚠️ Gagal menghubungi Pexels untuk keyword '{keyword}': {e}")
    return []

def choose_best_quality(video_files: list) -> str:
    """Memilih tautan unduhan dengan resolusi HD portrait terbaik."""
    for vf in video_files:
        # Cari resolusi portrait standar HD (720x1280 atau 1080x1920)
        if vf.get("width") == 720 or vf.get("quality") == "hd":
            return vf.get("link")
    if video_files:
        return video_files[0].get("link")
    return ""

def download_video_clips(keywords: list, target_count: int = 4) -> list:
    """Mendownload klip video berdasarkan daftar keyword relevan."""
    os.makedirs(DIR_TEMP, exist_ok=True)
    downloaded_paths = []
    clip_idx = 0
    
    print(f"📡 Memulai pencarian video Pexels berdasarkan keyword AI: {keywords}")
    
    for kw in keywords:
        if clip_idx >= target_count:
            break
            
        videos = search_pexels_videos(kw)
        if not videos:
            continue
            
        # Ambil satu video acak dari hasil pencarian keyword tersebut
        vid_data = random.choice(videos)
        download_url = choose_best_quality(vid_data.get("video_files", []))
        
        if download_url:
            print(f"📥 Mengunduh klip relevan untuk keyword '{kw}'...")
            try:
                resp = requests.get(download_url, timeout=30)
                if resp.status_code == 200:
                    file_path = os.path.join(DIR_TEMP, f"bg_clip_{clip_idx}.mp4")
                    with open(file_path, "wb") as f:
                        f.write(resp.content)
                    downloaded_paths.append(file_path)
                    clip_idx += 1
            except Exception as e:
                print(f"⚠️ Gagal mengunduh klip {clip_idx}: {e}")
                
    # Fallback jika tidak ada keyword yang menghasilkan video
    if not downloaded_paths:
        print("⚠️ Keyword spesifik tidak menghasilkan video. Menggunakan tema fallback...")
        videos = search_pexels_videos("dark-aesthetic", per_page=10)
        for i in range(min(target_count, len(videos))):
            download_url = choose_best_quality(videos[i].get("video_files", []))
            file_path = os.path.join(DIR_TEMP, f"bg_clip_{i}.mp4")
            with open(file_path, "wb") as f:
                f.write(requests.get(download_url).content)
            downloaded_paths.append(file_path)
            
    return downloaded_paths
