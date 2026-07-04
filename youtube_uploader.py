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


async def get_top_comments(video_id: str, max_results: int = 20) -> list:
    """Mengambil komentar teratas dari video YouTube menggunakan YouTube Data API v3."""
    cred_file = "youtube_credentials.json"
    if not os.path.exists(cred_file):
        print("⚠️ youtube_credentials.json tidak ditemukan. Melewati pengambilan komentar.")
        return []
        
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
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=max_results,
            order="relevance"
        )
        
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, request.execute)
        
        comments = []
        for item in response.get("items", []):
            text = item["snippet"]["topLevelComment"]["snippet"]["textOriginal"]
            likes = item["snippet"]["topLevelComment"]["snippet"].get("likeCount", 0)
            comments.append({"text": text, "likes": likes})
            
        # Urutkan berdasarkan likes tertinggi
        comments.sort(key=lambda x: x["likes"], reverse=True)
        return [c["text"] for c in comments]
    except Exception as e:
        print(f"⚠️ Gagal mengambil komentar dari YouTube API: {e}")
        return []


async def reply_to_youtube_comments(video_id: str, max_replies: int = 2) -> None:
    """Mengambil komentar teratas, meminta Gemini merancang balasan, dan memposting balasan otomatis."""
    cred_file = "youtube_credentials.json"
    if not os.path.exists(cred_file):
        return
        
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
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=max_replies,
            order="relevance"
        )
        
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, request.execute)
        
        from video_builder import call_gemini_with_retry
        for item in response.get("items", []):
            top_comment = item["snippet"]["topLevelComment"]
            parent_id = top_comment["id"]
            comment_text = top_comment["snippet"]["textOriginal"]
            author_name = top_comment["snippet"].get("authorDisplayName", "Kawan")
            
            total_replies = item["snippet"].get("totalReplyCount", 0)
            if total_replies > 0:
                continue
                
            prompt = (
                "Kamu adalah pengelola kanal edukasi psikologi bernama 'Ruang Pikir'.\n"
                "Balaslah komentar penonton berikut dengan jawaban yang ramah, sopan, mendidik, dan singkat (maks 25 kata):\n\n"
                f"Nama Penonton: {author_name}\n"
                f"Komentar: \"{comment_text}\"\n\n"
                "OUTPUT: Tulis langsung teks balasannya saja dalam Bahasa Indonesia percakapan santai tapi mendidik."
            )
            
            reply_text = await call_gemini_with_retry(prompt, is_json=False)
            if reply_text:
                reply_body = {
                    "snippet": {
                        "parentId": parent_id,
                        "textOriginal": reply_text.strip()
                    }
                }
                print(f"💬 Memposting balasan otomatis ke komentar '{comment_text[:40]}...'")
                await loop.run_in_executor(
                    None, 
                    lambda: youtube.comments().insert(part="snippet", body=reply_body).execute()
                )
                print("💬 Balasan sukses diposting!")
                
    except Exception as e:
        print(f"⚠️ Gagal membalas komentar otomatis di YouTube: {e}")


async def upload_thumbnail(video_id: str, thumbnail_path: str) -> bool:
    """Mengunggah kustom thumbnail untuk video YouTube menggunakan YouTube Data API v3."""
    if not os.path.exists(thumbnail_path):
        print(f"⚠️ Berkas thumbnail tidak ditemukan: {thumbnail_path}")
        return False
        
    cred_file = "youtube_credentials.json"
    if not os.path.exists(cred_file):
        print("⚠️ youtube_credentials.json tidak ditemukan. Melewati upload thumbnail.")
        return False
        
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
        
        media = MediaFileUpload(
            thumbnail_path,
            mimetype="image/jpeg"
        )
        
        request = youtube.thumbnails().set(
            videoId=video_id,
            media_body=media
        )
        
        import asyncio
        loop = asyncio.get_event_loop()
        print(f"🖼️ Mengunggah custom thumbnail untuk Video ID: {video_id}...")
        response = await loop.run_in_executor(None, request.execute)
        print("🖼️ Sukses mengunggah custom thumbnail!")
        return True
    except Exception as e:
        print(f"⚠️ Gagal mengunggah thumbnail ke YouTube: {e}")
        return False

