import os
import random
import requests
from config import PEXELS_API_KEY, PIXABAY_API_KEY, DIR_TEMP
try:
    import firebase_connector
except Exception:
    firebase_connector = None

def search_pexels_videos(keyword: str, per_page: int = 5, page: int = 1) -> list:
    """Mencari video portrait di Pexels berdasarkan keyword dari Gemini."""
    if not PEXELS_API_KEY:
        raise ValueError("❌ PEXELS_API_KEY belum dikonfigurasi di GitHub Secrets.")
        
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={keyword}&per_page={per_page}&page={page}&orientation=portrait"
    
    import time
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                return response.json().get("videos", [])
            else:
                print(f"⚠️ Pexels API mengembalikan status {response.status_code} pada percobaan {attempt + 1}/3.")
        except Exception as e:
            print(f"⚠️ Gagal menghubungi Pexels untuk keyword '{keyword}' pada percobaan {attempt + 1}/3: {e}")
        if attempt < 2:
            time.sleep(2)
    return []

def search_pixabay_videos(keyword: str, per_page: int = 15, page: int = 1) -> list:
    """Mencari video di Pixabay dan menormalisasi outputnya agar sesuai dengan format Pexels."""
    if not PIXABAY_API_KEY:
        print("⚠️ PIXABAY_API_KEY belum dikonfigurasi. Lewati pencarian Pixabay.")
        return []
        
    import urllib.parse
    q = urllib.parse.quote(keyword)
    url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={q}&per_page={per_page}&page={page}&video_type=film"
    
    import time
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                hits = response.json().get("hits", [])
                normalized = []
                for hit in hits:
                    videos_dict = hit.get("videos", {})
                    best_vid = None
                    for res in ["large", "medium", "small"]:
                        v = videos_dict.get(res, {})
                        if v and v.get("url"):
                            best_vid = v
                            break
                    if best_vid and best_vid.get("url"):
                        normalized.append({
                            "id": f"pix_{hit.get('id')}",
                            "source": "pixabay",
                            "video_files": [{"link": best_vid.get("url"), "width": best_vid.get("width"), "height": best_vid.get("height")}]
                        })
                return normalized
            else:
                print(f"⚠️ Pixabay API mengembalikan status {response.status_code} pada percobaan {attempt + 1}/3.")
        except Exception as e:
            print(f"⚠️ Gagal menghubungi Pixabay untuk keyword '{keyword}' pada percobaan {attempt + 1}/3: {e}")
        if attempt < 2:
            time.sleep(2)
    return []

def search_multi_source(keyword: str, per_page: int = 15, page: int = 1) -> list:
    """Load balancer: Acak penggunaan Pexels atau Pixabay, jika satu gagal, fallback ke yang lain."""
    sources = ["pexels", "pixabay"] if PIXABAY_API_KEY else ["pexels"]
    random.shuffle(sources)
    
    for source in sources:
        if source == "pexels":
            res = search_pexels_videos(keyword, per_page, page)
            if res: return res
        elif source == "pixabay":
            res = search_pixabay_videos(keyword, per_page, page)
            if res: return res
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

def download_youtube_retention_video(keyword: str) -> str:
    """Mengunduh video panjang dari YouTube menggunakan yt-dlp untuk retention background."""
    import yt_dlp
    
    retention_dir = os.path.join(os.path.dirname(__file__), "assets", "retention")
    os.makedirs(retention_dir, exist_ok=True)
    
    # Cek apakah sudah ada file mp4 di direktori (Gunakan yang ada agar tidak download ulang)
    existing_files = [f for f in os.listdir(retention_dir) if f.endswith(".mp4")]
    if existing_files:
        print(f"📦 Menggunakan video retention yang sudah ada di cache: {existing_files[0]}")
        return os.path.join(retention_dir, existing_files[0])
        
    print(f"📡 Mencari dan mengunduh video retention dari YouTube: '{keyword}'...")
    
    ydl_opts = {
        'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]',
        'outtmpl': os.path.join(retention_dir, '%(id)s.%(ext)s'),
        'noplaylist': True,
        'quiet': False,
        'max_downloads': 1
    }
    
    # Deteksi Cookie untuk by-pass Bot Protection YouTube
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = "cookies.txt"
        print("🍪 Menggunakan cookies.txt untuk otentikasi YouTube-DL")
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # ytsearch1: mencari dan mengambil 1 hasil pertama
            info = ydl.extract_info(f"ytsearch1:{keyword}", download=True)
            if 'entries' in info and len(info['entries']) > 0:
                entry = info['entries'][0]
                filename = ydl.prepare_filename(entry)
                print(f"✅ Berhasil mengunduh retention video: {filename}")
                return filename
            elif 'id' in info:
                filename = ydl.prepare_filename(info)
                print(f"✅ Berhasil mengunduh retention video: {filename}")
                return filename
    except Exception as e:
        print(f"⚠️ Gagal mengunduh video retention YouTube: {e}")
        
    return ""

def download_video_clips(keywords: list, target_count: int = 4, aesthetic_style: str = "dark cinematic cold moody tone") -> list:
    """Mendownload klip video berdasarkan daftar keyword relevan, mendukung multi-download per keyword."""
    os.makedirs(DIR_TEMP, exist_ok=True)
    os.makedirs(DIR_TEMP, exist_ok=True)
    downloaded_paths = []
    reusable_clips = []  # Tempat menyimpan klip yang pernah dipakai untuk fallback darurat
    clip_idx = 0
    
    print(f"📡 Memulai pencarian video AI (Pexels & Pixabay) berdasarkan keyword: {keywords} (Target: {target_count} klip)")
    
    # Hitung jumlah klip yang perlu diambil dari masing-masing keyword secara rata
    num_kws = len(keywords) if keywords else 1
    clips_per_kw = max(1, (target_count + num_kws - 1) // num_kws)
    
    for kw in keywords:
        if clip_idx >= target_count:
            break
            
        # Poin 1: Sinkronisasi Gaya Visual Estetik (Aesthetic Matching)
        aesthetic_query = f"{kw} {aesthetic_style}" if aesthetic_style else kw
        videos = search_multi_source(aesthetic_query, per_page=15)
        if not videos:
            # Fallback ke keyword murni jika pencarian estetik tidak mengembalikan video
            videos = search_multi_source(kw, per_page=15)
            
        if not videos:
            continue
            
        # Acak seluruh video hasil pencarian agar bervariasi
        random.shuffle(videos)
        
        # Lacak jumlah klip yang berhasil didapat untuk keyword ini
        kws_clip_count = 0
        
        for vid_data in videos:
            # Berhenti jika kuota total keseluruhan klip sudah terpenuhi
            if clip_idx >= target_count:
                break
                
            # Berhenti jika kuota klip untuk keyword ini sudah terpenuhi (agar jatah keyword lain tidak terambil semua)
            if kws_clip_count >= clips_per_kw:
                break
                
            vid_id = vid_data.get("id")
            # Jika Firestore tersedia, lewati klip yang sudah pernah dipakai (simpan untuk darurat)
            try:
                if vid_id and firebase_connector and getattr(firebase_connector, "is_clip_used", None):
                    if firebase_connector.is_clip_used(vid_id):
                        print(f"⛔ Klip {vid_id} pernah dipakai. Disimpan untuk cadangan darurat (reuse).")
                        reusable_clips.append(vid_data)
                        continue
            except Exception as e:
                print(f"⚠️ Gagal memeriksa used_clips: {e}")
            pool_dir = os.path.join("assets", "video_pool")
            os.makedirs(pool_dir, exist_ok=True)
            cached_file = os.path.join(pool_dir, f"{vid_id}.mp4") if vid_id else None
            
            download_url = choose_best_quality(vid_data.get("video_files", []))
            if download_url:
                file_path = os.path.join(DIR_TEMP, f"bg_clip_{clip_idx}.mp4")
                
                # Cek apakah sudah ada di cache lokal
                if cached_file and os.path.exists(cached_file) and os.path.getsize(cached_file) > 0:
                    print(f"📦 Menggunakan klip cache Pexels: {cached_file} -> {file_path}")
                    import shutil
                    try:
                        shutil.copy2(cached_file, file_path)
                        downloaded_paths.append(file_path)
                        # tandai sebagai dipakai di Firestore
                        try:
                            if vid_id and firebase_connector and getattr(firebase_connector, "mark_clip_used", None):
                                firebase_connector.mark_clip_used(vid_id)
                        except Exception:
                            pass
                        clip_idx += 1
                        kws_clip_count += 1
                        continue
                    except Exception as copy_err:
                        print(f"⚠️ Gagal menyalin cache: {copy_err}. Mengulang unduhan...")
                
                print(f"📥 Mengunduh klip {clip_idx + 1}/{target_count} untuk keyword '{kw}'...")
                import time
                for attempt in range(3):
                    try:
                        resp = requests.get(download_url, timeout=30)
                        if resp.status_code == 200:
                            with open(file_path, "wb") as f:
                                f.write(resp.content)

                            # Simpan ke cache lokal
                            if cached_file:
                                try:
                                    with open(cached_file, "wb") as cf:
                                        cf.write(resp.content)
                                    print(f"💾 Klip disimpan ke cache lokal: {cached_file}")
                                except Exception as cache_err:
                                    print(f"⚠️ Gagal menyimpan ke cache: {cache_err}")

                            downloaded_paths.append(file_path)
                            # tandai sebagai dipakai di Firestore
                            try:
                                if vid_id and firebase_connector and getattr(firebase_connector, "mark_clip_used", None):
                                    firebase_connector.mark_clip_used(vid_id)
                            except Exception:
                                pass

                            clip_idx += 1
                            kws_clip_count += 1
                            break
                        else:
                            print(f"⚠️ Gagal mengunduh klip (status {resp.status_code}) pada percobaan {attempt + 1}/3.")
                    except Exception as e:
                        print(f"⚠️ Gagal mengunduh klip {clip_idx} pada percobaan {attempt + 1}/3: {e}")
                    if attempt < 2:
                        time.sleep(2)
                    
    # Fallback Pexels Online jika jumlah klip terkumpul kurang dari target (Prioritas 1)
    if len(downloaded_paths) < target_count:
        remaining_count = target_count - len(downloaded_paths)
        if downloaded_paths:
            print(f"⚠️ Hanya berhasil mengunduh {len(downloaded_paths)}/{target_count} klip dari kata kunci utama.")
            print(f"📡 Mengisi sisa {remaining_count} klip menggunakan fallback Pexels online...")
        else:
            print("⚠️ Keyword spesifik tidak menghasilkan video. Mencari klip fallback di Pexels online...")
            
        print(f"ℹ️ Kekurangan {remaining_count} klip. Menggunakan tema fallback Multi-Source (dark cinematic)...")
        # Acak halaman pencarian fallback agar tidak selalu dapat klip yang sama
        random_page = random.randint(1, 3)
        fallback_videos = search_multi_source("dark cinematic", per_page=20, page=random_page)
        
        if fallback_videos:
            random.shuffle(fallback_videos)
            for vid_data in fallback_videos:
                if len(downloaded_paths) >= target_count:
                    break
                    
                vid_id = vid_data.get("id")
                # Cek apakah sudah pernah dipakai
                try:
                    if vid_id and firebase_connector and getattr(firebase_connector, "is_clip_used", None):
                        if firebase_connector.is_clip_used(vid_id):
                            reusable_clips.append(vid_data)
                            continue
                except Exception:
                    pass
                    
                download_url = choose_best_quality(vid_data.get("video_files", []))
                if download_url:
                    file_path = os.path.join(DIR_TEMP, f"bg_clip_fallback_pexels_{len(downloaded_paths)}.mp4")
                    
                    try:
                        resp = requests.get(download_url, timeout=30)
                        if resp.status_code == 200:
                            with open(file_path, "wb") as f:
                                f.write(resp.content)
                            downloaded_paths.append(file_path)
                            # tandai sebagai dipakai
                            try:
                                if vid_id and firebase_connector and getattr(firebase_connector, "mark_clip_used", None):
                                    firebase_connector.mark_clip_used(vid_id)
                            except Exception:
                                pass
                    except Exception as e:
                        print(f"⚠️ Gagal mengunduh klip fallback Pexels: {e}")
                        
    # 3. Fallback Darurat: REUSE (Menggunakan ulang klip yang pernah dipakai, tapi diacak)
    if len(downloaded_paths) < target_count and reusable_clips:
        remaining_count = target_count - len(downloaded_paths)
        print(f"♻️ Darurat: Kekurangan {remaining_count} klip. Menggunakan ulang (REUSE) klip yang pernah dipakai agar proses tidak gagal...")
        random.shuffle(reusable_clips)
        for vid_data in reusable_clips:
            if len(downloaded_paths) >= target_count:
                break
                
            download_url = choose_best_quality(vid_data.get("video_files", []))
            if download_url:
                file_path = os.path.join(DIR_TEMP, f"bg_clip_reuse_{len(downloaded_paths)}.mp4")
                try:
                    resp = requests.get(download_url, timeout=30)
                    if resp.status_code == 200:
                        with open(file_path, "wb") as f:
                            f.write(resp.content)
                        downloaded_paths.append(file_path)
                        print(f"✅ Berhasil me-reuse klip {vid_data.get('id')}.")
                except Exception as e:
                    print(f"⚠️ Gagal me-reuse klip: {e}")
                        
    # Fallback Folder Lokal (Prioritas Terakhir, hanya jika Pexels gagal total atau internet mati)
    if len(downloaded_paths) < target_count:
        remaining_count = target_count - len(downloaded_paths)
        print(f"⚠️ Pexels Fallback gagal memenuhi {remaining_count} klip. Menggunakan folder fallback_clips lokal...")
        
        fallback_dir = os.path.join("assets", "fallback_clips")
        local_fallbacks = []
        if os.path.exists(fallback_dir):
            local_fallbacks = [f for f in os.listdir(fallback_dir) if f.lower().endswith(".mp4")]
            
        if local_fallbacks:
            import shutil
            sample_size = min(len(local_fallbacks), remaining_count)
            chosen_local = random.sample(local_fallbacks, sample_size)
            for i, fname in enumerate(chosen_local):
                file_path = os.path.join(DIR_TEMP, f"bg_clip_fallback_local_{i}.mp4")
                src_path = os.path.join(fallback_dir, fname)
                try:
                    shutil.copy2(src_path, file_path)
                    downloaded_paths.append(file_path)
                    print(f"📦 Menggunakan klip fallback lokal: {src_path} -> {file_path}")
                except Exception as copy_err:
                    print(f"⚠️ Gagal menyalin klip fallback lokal: {copy_err}")
            
    return downloaded_paths
