import os
import random
import requests
import json
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips

# 1. Fungsi Mengunduh Beberapa Video dari Pexels Berdasarkan Keyword
def download_multiple_background_videos(keyword, target_duration):
    print(f"📡 Mencari variasi video di Pexels dengan keyword: '{keyword}'...")
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        raise ValueError("❌ Eror: PEXELS_API_KEY tidak ditemukan!")

    headers = {"Authorization": api_key}
    # Membersihkan kata kunci pencarian agar aman untuk API Pexels
    search_query = keyword.replace("...", "").replace(",", "").strip()
    url = f"https://api.pexels.com/videos/search?query={search_query}&per_page=20&orientation=portrait"
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200 or not response.json().get("videos"):
        print("⚠️ Gagal mencari dengan keyword kustom, beralih ke tema dark-aesthetic...")
        url = "https://api.pexels.com/videos/search?query=dark-aesthetic&per_page=20&orientation=portrait"
        response = requests.get(url, headers=headers)

    data = response.json()
    videos = data.get("videos", [])
    
    if not videos:
        raise ValueError(f"❌ Tidak ditemukan video portrait untuk keyword: {search_query}")

    # Ambil maksimal 4 video acak dari hasil pencarian agar variatif
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

# 3. Fungsi Utama Perakitan Video Berstruktur (Hook, Story, CTA)
def create_tiktok_video(keyword="human"):
    # Load Audio Utama (Suara AI) terlebih dahulu untuk tahu total durasi
    audio_clip = AudioFileClip("vo.mp3")
    total_duration = audio_clip.duration

    # Unduh variasi video
    video_files = download_multiple_background_videos(keyword, total_duration)
    
    print("🎬 Memotong dan menyatukan klip video latar belakang...")
    clip_count = len(video_files)
    duration_per_clip = total_duration / clip_count
    
    video_clips = []
    for file in video_files:
        clip = VideoFileClip(file).subclip(0, duration_per_clip).set_audio(None).resize((1080, 1920))
        video_clips.append(clip)
    
    combined_bg_clip = concatenate_videoclips(video_clips, method="compose")
    combined_bg_clip = combined_bg_clip.set_duration(total_duration)

    # Membaca file json terstruktur untuk subtitle
    hook_text = "FAKTA PSIKOLOGI"
    story_text = ""
    cta_text = "FOLLOW UNTUK INFO LAINNYA"
    
    if os.path.exists("script.json"):
        with open("script.json", "r", encoding="utf-8") as f:
            meta_data = json.load(f)
            hook_text = meta_data.get("hook", "").upper()
            story_text = meta_data.get("story", "").upper()
            cta_text = meta_data.get("cta", "").upper()

    # Estimasi pembagian alokasi waktu tampil di layar secara proporsional
    # Hook di awal (15% durasi), CTA di akhir (15% durasi), sisanya untuk Story (70% durasi)
    hook_duration = total_duration * 0.15
    cta_duration = total_duration * 0.15
    story_duration = total_duration - hook_duration - cta_duration

    text_clips = []

    # A. Pembuatan Subtitle Hook (Muncuk di Awal, Warna Oranye Terang)
    hook_chunks = split_text_into_chunks(hook_text, max_words=3)
    hook_chunk_dur = hook_duration / len(hook_chunks) if hook_chunks else hook_duration
    for i, chunk in enumerate(hook_chunks):
        start = i * hook_chunk_dur
        end = (i + 1) * hook_chunk_dur
        txt_clip = TextClip(chunk, fontsize=65, color='orange', font='font.ttf', 
                            stroke_color='black', stroke_width=5, method='caption', size=(combined_bg_clip.w - 150, None))
        txt_clip = txt_clip.set_start(start).set_end(end).set_position(('center', combined_bg_clip.h * 0.45))
        text_clips.append(txt_clip)

    # B. Pembuatan Subtitle Story (Muncul di Tengah, Warna Selang-seling Kuning/Putih)
    story_chunks = split_text_into_chunks(story_text, max_words=3)
    story_chunk_dur = story_duration / len(story_chunks) if story_chunks else story_duration
    for i, chunk in enumerate(story_chunks):
        start = hook_duration + (i * story_chunk_dur)
        end = hook_duration + ((i + 1) * story_chunk_dur)
        text_color = 'yellow' if i % 2 == 0 else 'white'
        txt_clip = TextClip(chunk, fontsize=55, color=text_color, font='font.ttf', 
                            stroke_color='black', stroke_width=4, method='caption', size=(combined_bg_clip.w - 150, None))
        txt_clip = txt_clip.set_start(start).set_end(end).set_position(('center', combined_bg_clip.h * 0.45))
        text_clips.append(txt_clip)

    # C. Pembuatan Subtitle CTA (Muncul di Akhir, Warna Hijau Muda/Cyan Kontras)
    cta_chunks = split_text_into_chunks(cta_text, max_words=3)
    cta_chunk_dur = cta_duration / len(cta_chunks) if cta_chunks else cta_duration
    story_end_time = hook_duration + story_duration
    for i, chunk in enumerate(cta_chunks):
        start = story_end_time + (i * cta_chunk_dur)
        end = story_end_time + ((i + 1) * cta_chunk_dur)
        txt_clip = TextClip(chunk, fontsize=55, color='cyan', font='font.ttf', 
                            stroke_color='black', stroke_width=4, method='caption', size=(combined_bg_clip.w - 150, None))
        txt_clip = txt_clip.set_start(start).set_end(end).set_position(('center', combined_bg_clip.h * 0.45))
        text_clips.append(txt_clip)

    # Gabungkan semua komponen menjadi satu kesatuan video
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
    
    # Bersihkan memori server dan file sementara
    audio_clip.close()
    combined_bg_clip.close()
    for clip in video_clips:
        clip.close()
    final_video.close()
    
    for file in video_files:
        if os.path.exists(file):
            os.remove(file)
        
    print("✅ Video berstruktur komplit berhasil dirakit sempurna.")
