import os
import random
import requests
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips

# 1. Fungsi Mengunduh Beberapa Video dari Pexels Berdasarkan Keyword
def download_multiple_background_videos(keyword, target_duration):
    print(f"📡 Mencari variasi video di Pexels dengan keyword: '{keyword}'...")
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        raise ValueError("❌ Eror: PEXELS_API_KEY tidak ditemukan!")

    headers = {"Authorization": api_key}
    url = f"https://api.pexels.com/videos/search?query={keyword}&per_page=20&orientation=portrait"
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200 or not response.json().get("videos"):
        print("⚠️ Gagal mencari dengan keyword kustom, beralih ke tema dark-aesthetic...")
        url = "https://api.pexels.com/videos/search?query=dark-aesthetic&per_page=20&orientation=portrait"
        response = requests.get(url, headers=headers)

    data = response.json()
    videos = data.get("videos", [])
    
    if not videos:
        raise ValueError(f"❌ Tidak ditemukan video portrait untuk keyword: {keyword}")

    # Ambil 4 video acak dari hasil pencarian agar variatif
    selected_videos = random.sample(videos, min(4, len(videos)))
    
    downloaded_files = []
    for idx, vid in enumerate(selected_videos):
        video_files = vid.get("video_files", [])
        download_url = ""
        for vf in video_files:
            if vf.get("width") == 720 or vf.get("quality") == "hd":
                download_url = vf.get("link")
                break
        if not download_url and video_files:
            download_url = video_files[0].get("link")

        print(f"📥 Mengunduh video latar belakang variasi ke-{idx+1}...")
        v_resp = requests.get(download_url)
        filename = f"bg_{idx}.mp4"
        with open(filename, "wb") as f:
            f.write(v_resp.content)
        downloaded_files.append(filename)
        
    print(f"✅ Berhasil mengunduh {len(downloaded_files)} variasi video latar belakang.")
    return downloaded_files

# 2. Fungsi Memecah Teks Menjadi Potongan Pendek untuk Subtitle
def split_text_into_chunks(text, max_words=3):
    words = text.upper().split() # Otomatis UPPERCASE khas TikTok
    chunks = []
    current_chunk = []
    
    for word in words:
        current_chunk.append(word)
        if len(current_chunk) >= max_words:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

# 3. Fungsi Utama Perakitan Video Sempurna & Dinamis
def create_tiktok_video(keyword="urban"):
    # Load Audio Utama (Suara AI) terlebih dahulu untuk tahu total durasi
    audio_clip = AudioFileClip("vo.mp3")
    total_duration = audio_clip.duration

    # Unduh variasi video
    video_files = download_multiple_background_videos(keyword, total_duration)
    
    print("🎬 Memotong dan menyatukan klip video latar belakang...")
    
    # Hitung durasi potongan per video (misal total 15 detik dibagi 3 klip = 5 detik per klip)
    clip_count = len(video_files)
    duration_per_clip = total_duration / clip_count
    
    video_clips = []
    for file in video_files:
        # Load klip, matikan audionya, paksa resolusi portrait TikTok
        clip = VideoFileClip(file).subclip(0, duration_per_clip).set_audio(None).resize((1080, 1920))
        video_clips.append(clip)
    
    # Satukan semua potongan video tadi menjadi satu timeline yang mengalir berkelanjutan
    combined_bg_clip = concatenate_videoclips(video_clips, method="compose")
    # Jika hasil penggabungan sedikit kurang karena pembulatan, paksa pas dengan durasi audio
    combined_bg_clip = combined_bg_clip.set_duration(total_duration)

    # PROSES SUBTITLE OTOMATIS
    script_text = "FAKTA PSIKOLOGI"
    if os.path.exists("script.txt"):
        with open("script.txt", "r", encoding="utf-8") as f:
            script_text = f.read()

    text_chunks = split_text_into_chunks(script_text, max_words=3)
    num_chunks = len(text_chunks)
    chunk_duration = total_duration / num_chunks if num_chunks > 0 else total_duration

    text_clips = []
    for i, chunk in enumerate(text_chunks):
        start_time = i * chunk_duration
        end_time = (i + 1) * chunk_duration
        
        # Variasi warna teks (Kuning & Putih) agar memikat mata
        text_color = 'yellow' if i % 2 == 0 else 'white'
        
        txt_clip = TextClip(
            chunk, 
            fontsize=55, 
            color=text_color, 
            font='font.ttf',
            stroke_color='black',
            stroke_width=4,
            method='caption',
            size=(combined_bg_clip.w - 150, None)
        )
        
        # Posisikan teks agak ke atas (center, 0.45 dari tinggi video) agar tidak tertutup menu TikTok
        txt_clip = txt_clip.set_start(start_time).set_end(end_time).set_position(('center', combined_bg_clip.h * 0.45))
        text_clips.append(txt_clip)

    # Gabungkan Video Latar Belakang Gabungan dengan Teks Subtitle
    final_video = CompositeVideoClip([combined_bg_clip] + text_clips)
    final_video = final_video.set_audio(audio_clip)

    print("🔄 Menulis file video kualitas tinggi (final_output.mp4)...")
    final_video.write_videofile(
        "final_output.mp4", 
        fps=30, 
        codec="libx264", 
        audio_codec="aac",
        threads=4
    )
    
    # Bersihkan memori server dan hapus file sementara
    audio_clip.close()
    combined_bg_clip.close()
    for clip in video_clips:
        clip.close()
    final_video.close()
    
    for file in video_files:
        if os.path.exists(file):
            os.remove(file)
        
    print("✅ Video final_output.mp4 dengan multi-background berhasil dirakit sempurna.")
