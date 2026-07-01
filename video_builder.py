import os
import random
import requests
import json
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
import moviepy.video.fx.all as vfx

# 1. Mengunduh Video dengan Kata Kunci Estetik & Mood Sinematik
def download_multiple_background_videos(keyword, target_duration):
    print("📡 Mencari video dengan tone sinematik dan estetik di Pexels...")
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        raise ValueError("❌ Eror: PEXELS_API_KEY tidak ditemukan!")

    headers = {"Authorization": api_key}
    
    # Menggunakan tema visual yang terbukti FYP (Misterius, Moody, Abstrak, Estetik)
    aesthetic_themes = ["dark-aesthetic", "cinematic-moody", "abstract-motion", "cyberpunk-glitch", "dreamy-landscape"]
    chosen_theme = random.choice(aesthetic_themes)
    
    url = f"https://api.pexels.com/videos/search?query={chosen_theme}&per_page=15&orientation=portrait"
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200 or not response.json().get("videos"):
        # Fallback jika gagal
        url = "https://api.pexels.com/videos/search?query=nature-aesthetic&per_page=10&orientation=portrait"
        response = requests.get(url, headers=headers)

    data = response.json()
    videos = data.get("videos", [])
    
    if not videos:
        raise ValueError("❌ Tidak ditemukan video portrait sama sekali di Pexels.")

    # Ambil 4-5 video acak agar transisi visualnya cepat dan tidak membosankan
    selected_videos = random.sample(videos, min(5, len(videos)))
    
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

        print(f"📥 Mengunduh klip estetik ke-{idx+1}...")
        v_resp = requests.get(download_url)
        filename = f"bg_{idx}.mp4"
        with open(filename, "wb") as f:
            f.write(v_resp.content)
        downloaded_files.append(filename)
        
    return downloaded_files

# 2. Efek Zoom In Bergerak Perlahan (Membuat Video Hidup)
def apply_slow_zoom(clip, zoom_speed=0.03):
    # Efek memperbesar skala video secara perlahan seiring berjalannya waktu (t)
    return clip.fx(vfx.resize, lambda t: 1.0 + (zoom_speed * t))

# 3. Fungsi Memotong Teks Menjadi Potongan Subtitle Pendek
def split_text_into_chunks(text, max_words=3):
    words = text.upper().split()
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

# 4. Fungsi Utama Perakitan Video Kualitas FYP
def create_tiktok_video(keyword="human"):
    audio_clip = AudioFileClip("vo.mp3")
    total_duration = audio_clip.duration

    # Ambil video mentahan
    video_files = download_multiple_background_videos(keyword, total_duration)
    
    print("🎬 Memproses efek transisi, pemotongan, dan Zoom In pada background...")
    clip_count = len(video_files)
    duration_per_clip = total_duration / clip_count
    
    video_clips = []
    for file in video_files:
        # Load video, matikan audio bawaan, potong durasi, paksa resolusi standar TikTok 1080x1920
        clip = VideoFileClip(file).subclip(0, duration_per_clip).set_audio(None).resize((1080, 1920))
        # Berikan efek pergerakan kamera Zoom In dinamis agar tidak kaku
        clip = apply_slow_zoom(clip, zoom_speed=0.04)
        video_clips.append(clip)
    
    # Satukan klip video yang berganti-ganti setiap beberapa detik
    combined_bg_clip = concatenate_videoclips(video_clips, method="compose")
    combined_bg_clip = combined_bg_clip.set_duration(total_duration)

    # Membaca struktur script text
    hook_text, story_text, cta_text = "FAKTA PSIKOLOGI", "", "FOLLOW SEKARANG"
    if os.path.exists("script.json"):
        with open("script.json", "r", encoding="utf-8") as f:
            meta_data = json.load(f)
            hook_text = meta_data.get("hook", "").upper()
            story_text = meta_data.get("story", "").upper()
            cta_text = meta_data.get("cta", "").upper()

    # Hitung waktu proporsional kemunculan subtitle
    hook_duration = total_duration * 0.15
    cta_duration = total_duration * 0.15
    story_duration = total_duration - hook_duration - cta_duration

    text_clips = []

    # SUBTITLE HOOK: Besar, Tebal, Berwarna Oranye Menyala di awal video
    hook_chunks = split_text_into_chunks(hook_text, max_words=3)
    hook_chunk_dur = hook_duration / len(hook_chunks) if hook_chunks else hook_duration
    for i, chunk in enumerate(hook_chunks):
        start = i * hook_chunk_dur
        end = (i + 1) * hook_chunk_dur
        txt_clip = TextClip(chunk, fontsize=68, color='orange', font='font.ttf', 
                            stroke_color='black', stroke_width=5, method='caption', size=(combined_bg_clip.w - 120, None))
        txt_clip = txt_clip.set_start(start).set_end(end).set_position(('center', combined_bg_clip.h * 0.45))
        text_clips.append(txt_clip)

    # SUBTITLE STORY: Dinamis dengan transisi warna Kuning & Putih bergantian
    story_chunks = split_text_into_chunks(story_text, max_words=3)
    story_chunk_dur = story_duration / len(story_chunks) if story_chunks else story_duration
    for i, chunk in enumerate(story_chunks):
        start = hook_duration + (i * story_chunk_dur)
        end = hook_duration + ((i + 1) * story_chunk_dur)
        text_color = 'yellow' if i % 2 == 0 else 'white'
        txt_clip = TextClip(chunk, fontsize=58, color=text_color, font='font.ttf', 
                            stroke_color='black', stroke_width=4, method='caption', size=(combined_bg_clip.w - 150, None))
        txt_clip = txt_clip.set_start(start).set_end(end).set_position(('center', combined_bg_clip.h * 0.45))
        text_clips.append(txt_clip)

    # SUBTITLE CTA: Menarik perhatian di akhir video dengan warna Cyan/Hijau Stabilo
    cta_chunks = split_text_into_chunks(cta_text, max_words=3)
    cta_chunk_dur = cta_duration / len(cta_chunks) if cta_chunks else cta_duration
    story_end_time = hook_duration + story_duration
    for i, chunk in enumerate(cta_chunks):
        start = story_end_time + (i * cta_chunk_dur)
        end = story_end_time + ((i + 1) * cta_chunk_dur)
        txt_clip = TextClip(chunk, fontsize=58, color='cyan', font='font.ttf', 
                            stroke_color='black', stroke_width=4, method='caption', size=(combined_bg_clip.w - 150, None))
        txt_clip = txt_clip.set_start(start).set_end(end).set_position(('center', combined_bg_clip.h * 0.45))
        text_clips.append(txt_clip)

    # Gabungkan video background dinamis dengan tumpukan text subtitle
    final_video = CompositeVideoClip([combined_bg_clip] + text_clips)
    final_video = final_video.set_audio(audio_clip)

    print("🔄 Mengekspor video kualitas tinggi (final_output.mp4)...")
    final_video.write_videofile(
        "final_output.mp4", 
        fps=30, 
        codec="libx264", 
        audio_codec="aac",
        threads=4
    )
    
    # Pembersihan memori server
    audio_clip.close()
    combined_bg_clip.close()
    for clip in video_clips:
        clip.close()
    final_video.close()
    
    for file in video_files:
        if os.path.exists(file):
            os.remove(file)
        
    print("🎉 Sukses Besar! Video level profesional berhasil dirakit.")

