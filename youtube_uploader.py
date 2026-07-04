import os
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

async def upload_to_youtube(video_path: str, caption: str, tags: list = None, category_id: str = None, comment_text: str = None) -> str:
    """
    Mengunggah video ke YouTube Shorts menggunakan official YouTube Data API v3.
    OAuth2 credential-based authentication bypasses IP location security checks.
    """
    print(" YouTube API: Memulai proses unggah video ke YouTube Shorts...")
    
    cred_file = "youtube_credentials.json"
    if not os.path.exists(cred_file):
        raise FileNotFoundError(" Eror: Berkas youtube_credentials.json tidak ditemukan! Harap lakukan otorisasi di lokal terlebih dahulu.")
        
    with open(cred_file, "r") as f:
        cred_data = json.load(f)
        
    if not caption or not isinstance(caption, str):
        caption = ""
        
    # Judul YouTube Shorts dibatasi maksimal 100 karakter dan TIDAK boleh berisi baris baru (newline).
    # Bersihkan title dari newline, carriage return, dan spasi ganda.
    clean_title = caption.replace("\r", " ").replace("\n", " ")
    clean_title = " ".join(clean_title.split())  # Menghapus spasi berlebih/ganda dan trim
    
    if not clean_title:
        clean_title = "Video Baru Ruang Pikir"
        
    # Pastikan diakhiri dengan #shorts jika belum ada
    if "#shorts" not in clean_title.lower():
        clean_title = f"{clean_title} #shorts"
        
    # Potong jika melebihi batas 100 karakter
    if len(clean_title) > 100:
        clean_title = clean_title[:88].strip() + " ... #shorts"
        
    title = clean_title
    description = caption
    
    # Load OAuth2 credentials
    credentials = Credentials(
        token=cred_data.get("token"),
        refresh_token=cred_data.get("refresh_token"),
        token_uri=cred_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=cred_data.get("client_id"),
        client_secret=cred_data.get("client_secret"),
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    
    # Inisialisasi Google YouTube Service
    youtube = build("youtube", "v3", credentials=credentials)
    
    # Tentukan tags dan categoryId secara dinamis
    yt_tags = tags if tags else ["shorts", "faktapsikologi", "mindset", "ruangpikir"]
    if "shorts" not in [t.lower() for t in yt_tags]:
        yt_tags.append("shorts")
        
    yt_category = category_id if category_id else "22"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": yt_tags,
            "categoryId": yt_category
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }
    
    # Mempersiapkan media file upload
    media = MediaFileUpload(
        video_path,
        chunksize=1024*1024,
        resumable=True,
        mimetype="video/mp4"
    )
    
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f" Mengunggah video ke YouTube API: {int(status.progress() * 100)}% selesai...")
            
    video_id = response.get("id")
    video_url = f"https://youtu.be/{video_id}"
    print(f" Video sukses diunggah ke YouTube Shorts! Video ID: {video_id}")
    
    # Kirim komentar otomatis jika disertakan
    if video_id and comment_text:
        try:
            print(f"💬 Menulis komentar otomatis pertama di YouTube...")
            comment_body = {
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text
                        }
                    }
                }
            }
            youtube.commentThreads().insert(part="snippet", body=comment_body).execute()
            print("💬 Sukses mempublikasikan komentar pertama di YouTube!")
        except Exception as comm_err:
            print(f"⚠️ Gagal memposting komentar otomatis pertama: {comm_err}")
            
    print(f" Tautan Video: {video_url}")
    return video_url


async def get_youtube_stats(video_ids: list) -> dict:
    """Mengambil statistik views dan likes dari daftar video ID YouTube."""
    if not video_ids:
        return {}
        
    cred_file = "youtube_credentials.json"
    if not os.path.exists(cred_file):
        print("⚠️ youtube_credentials.json tidak ditemukan. Melewati update statistik.")
        return {}
        
    try:
        with open(cred_file, "r") as f:
            cred_data = json.load(f)
            
        credentials = Credentials(
            token=cred_data.get("token"),
            refresh_token=cred_data.get("refresh_token"),
            token_uri=cred_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=cred_data.get("client_id"),
            client_secret=cred_data.get("client_secret")
        )
        
        youtube = build("youtube", "v3", credentials=credentials)
        
        # Gabungkan video_ids dengan koma
        ids_str = ",".join(video_ids)
        request = youtube.videos().list(
            part="statistics",
            id=ids_str
        )
        # Jalankan di thread pool executor karena execute() synchronous
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, request.execute)
        
        stats = {}
        for item in response.get("items", []):
            vid_id = item.get("id")
            item_stats = item.get("statistics", {})
            views = int(item_stats.get("viewCount", 0))
            likes = int(item_stats.get("likeCount", 0))
            stats[vid_id] = {"views": views, "likes": likes}
            
        return stats
    except Exception as e:
        print(f"⚠️ Gagal mengambil statistik dari YouTube API: {e}")
        return {}
