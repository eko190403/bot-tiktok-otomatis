import os
import requests
import random
from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

# Fungsi Tambahan: Mencari dan men-download video secara otomatis dari Pexels
def download_random_background(duration):
    print("🔍 Menghubungi Pexels API untuk mencari video latar belakang...")
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        raise ValueError("❌ Eror: PEXELS_API_KEY tidak ditemukan di GitHub Secrets!")

    # Cari video vertikal bertema alam/nature yang menenangkan
    url = "https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=15"
    headers = {"Authorization": api_key}
    
    response = requests.get(url, headers=headers).json()
    videos = response.get("videos", [])
    
    if not videos:
        raise Exception("❌ Gagal mendapatkan daftar video dari Pexels.")
        
    # Pilih satu video secara acak dari hasil pencarian
    selected_video = random.choice(videos)
    
    # Ambil link download video dengan kualitas HD/Mobile yang sesuai
    video_files = selected_video.get("video_files", [])
    download_url = video_files[0].get("link") # Mengambil resolusi pertama yang tersedia
    
    print("📥 Mengunduh video mentah dari server Pexels...")
    video_data = requests.get(download_url).content
    
    with open("background.mp4", "wb") as f:
        f.write(video_data)
    print("✅ Video latar belakang sukses di-download otomatis.")

# Fungsi Utama Perakitan
def create_tiktok_video(audio_path="vo.mp3", output_path="final_output.mp4"):
    print("🎬 MoviePy: Memproses perakitan komponen video...")
    
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"❌ File audio {audio_path} tidak ditemukan!")
        
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration
    
    # Kuncinya di sini: Bot download sendiri sebelum merakit
    download_random_background(duration)
    
    if not os.path.exists("background.mp4"):
        raise FileNotFoundError("❌ File background.mp4 gagal diproses oleh downloader.")

    video_clip = VideoFileClip("background.mp4").subclip(0, duration)
    video_clip = video_clip.resized(newsize=(1080, 1920))
    
    final_video = video_clip.with_audio(audio_clip)
    
    print("⏳ Menulis file video final_output.mp4 ke sistem server...")
    final_video.write_videofile(
        output_path, 
        fps=24, 
        codec="libx264", 
        audio_codec="aac",
        threads=4
    )
    
    audio_clip.close()
    video_clip.close()
    final_video.close()
    
    # Hapus file mentah background agar tidak memenuhi penyimpanan server setelah selesai
    if os.path.exists("background.mp4"):
        os.remove("background.mp4")
        
    print("✅ Video final_output.mp4 berhasil dirakit sempurna.")
