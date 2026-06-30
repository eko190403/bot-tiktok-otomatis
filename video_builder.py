import os
import random
import requests
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, afx

# 1. Fungsi Mengunduh Video Relevan dari Pexels
def download_background_video(keyword):
    print(f"📡 Mencari video portrait Pexels untuk keyword: '{keyword}'...")
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        raise ValueError("❌ Eror: PEXELS_API_KEY tidak ditemukan!")

    headers = {"Authorization": api_key}
    url = f"https://api.pexels.com/videos/search?query={keyword}&per_page=15&orientation=portrait"
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200 or not response.json().get("videos"):
        print("⚠️ Gagal mencari dengan keyword kustom, beralih ke tema dark-aesthetic...")
        url = "https://api.pexels.com/videos/search?query=dark-aesthetic&per_page=15&orientation=portrait"
        response = requests.get(url, headers=headers)

    data = response.json()
    videos = data.get("videos", [])
    
    selected_video = random.choice(videos)
    video_files = selected_video.get("video_files", [])
    
    download_url = ""
    for vf in video_files:
        if vf.get("width") == 720 or vf.get("quality") == "hd":
            download_url = vf.get("link")
            break
    if not download_url and video_files:
        download_url = video_files[0].get("link")

    print("📥 Mengunduh file video latar belakang...")
    v_resp = requests.get(download_url)
    with open("background.mp4", "wb") as f:
        f.write(v_resp.content)
    print("✅ Video latar belakang siap.")

# 2. Fungsi Memecah Teks Menjadi Potongan Pendek
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

# 3. Fungsi Utama Perakitan Video Sempurna
def create_tiktok_video(keyword="urban"):
    download_background_video(keyword)
    
    print("🎬 Merakit komponen video, audio, backsound, dan subtitle...")
    
    # Load Audio Utama (Suara AI)
    audio_clip = AudioFileClip("vo.mp3")
    duration = audio_clip.duration

    # Load & Potong Video Mentah
    video_clip = VideoFileClip("background.mp4").subclip(0, duration)
    video_clip = video_clip.set_audio(None)
    video_clip = video_clip.resize((1080, 1920)) # Paksa resolusi TikTok standard

    # PROSES BACKSOUND OTOMATIS
    if os.path.exists("backsound.mp3"):
        print("🎵 Menambahkan backsound musik ke latar suara...")
        bg_audio = AudioFileClip("backsound.mp3")
        
        # Jika backsound kependekan, loop. Jika kepanjangan, potong.
        if bg_audio.duration < duration:
            bg_audio = bg_audio.fx(afx.audio_loop, duration=duration)
        else:
            bg_audio = bg_audio.subclip(0, duration)
            
        # Turunkan volume backsound menjadi 15% agar suara utama tetap jelas
        bg_audio = bg_audio.volumex(0.15)
        
        # Gabungkan Audio Utama + Backsound
        from moviepy.audio.AudioClip import CompositeAudioClip
        final_audio = CompositeAudioClip([audio_clip, bg_audio])
    else:
        print("⚠️ File backsound.mp3 tidak ditemukan, video hanya menggunakan suara AI.")
        final_audio = audio_clip

    # PROSES SUBTITLE OTOMATIS
    script_text = "FAKTA PSIKOLOGI"
    if os.path.exists("script.txt"):
        with open("script.txt", "r", encoding="utf-8") as f:
            script_text = f.read()

    text_chunks = split_text_into_chunks(script_text, max_words=3)
    num_chunks = len(text_chunks)
    chunk_duration = duration / num_chunks if num_chunks > 0 else duration

    text_clips = []
    for i, chunk in enumerate(text_chunks):
        start_time = i * chunk_duration
        end_time = (i + 1) * chunk_duration
        
        # Bikin warna selang-seling (Kuning & Putih) agar lebih memikat mata
        text_color = 'yellow' if i % 2 == 0 else 'white'
        
        txt_clip = TextClip(
            chunk, 
            fontsize=55, 
            color=text_color, 
            font='font.ttf',
            stroke_color='black',
            stroke_width=4,
            method='caption',
            size=(video_clip.w - 150, None)
        )
        
        # Posisikan teks agak ke atas (center, 0.45 dari tinggi video) agar tidak tertutup tombol TikTok
        txt_clip = txt_clip.set_start(start_time).set_end(end_time).set_position(('center', video_clip.h * 0.45))
        text_clips.append(txt_clip)

    # Gabungkan Semuanya
    final_video = CompositeVideoClip([video_clip] + text_clips)
    final_video = final_video.set_audio(final_audio)

    print("🔄 Menulis file video kualitas tinggi (final_output.mp4)...")
    final_video.write_videofile(
        "final_output.mp4", 
        fps=30, # Naikkan ke 30fps agar pergerakan video lebih mulus
        codec="libx264", 
        audio_codec="aac",
        threads=4
    )
    
    # Bersihkan memori server
    audio_clip.close()
    if os.path.exists("backsound.mp3"): bg_audio.close()
    video_clip.close()
    final_video.close()
    if os.path.exists("background.mp4"): os.remove("background.mp4")
        
    print("✅ Video final_output.mp4 berhasil disempurnakan.")
