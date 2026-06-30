import os
import random
import requests
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

# 1. Fungsi Mengunduh Video dari Pexels Berdasarkan Keyword Gemini
def download_background_video(keyword):
    print(f"📡 Mencari video di Pexels dengan keyword: '{keyword}'...")
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        raise ValueError("❌ Eror: PEXELS_API_KEY tidak ditemukan!")

    headers = {"Authorization": api_key}
    url = f"https://api.pexels.com/videos/search?query={keyword}&per_page=15&orientation=portrait"
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("⚠️ Gagal mencari dengan keyword kustom, beralih ke keyword cadangan...")
        url = "https://api.pexels.com/videos/search?query=dark-aesthetic&per_page=15&orientation=portrait"
        response = requests.get(url, headers=headers)

    data = response.json()
    videos = data.get("videos", [])
    
    if not videos:
        raise ValueError(f"❌ Tidak ditemukan video portrait untuk keyword: {keyword}")

    # Pilih video acak dari hasil pencarian agar variatif
    selected_video = random.choice(videos)
    
    # Ambil link download video dengan kualitas HD/Mobile yang pas
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
    print("✅ Video latar belakang siap pakai.")

# 2. Fungsi Memotong Kalimat Panjang Menjadi Subtitle Pendek
def split_text_into_chunks(text, max_words=4):
    words = text.split()
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

# 3. Fungsi Utama Perakitan Video
def create_tiktok_video(keyword="urban"):
    # Unduh video sesuai keyword kiriman Gemini
    download_background_video(keyword)
    
    print("🎬 Memproses penggabungan audio dan teks ke video...")
    
    # Load file audio pengisi suara
    audio_clip = AudioFileClip("vo.mp3")
    duration = audio_clip.duration

    # Load file video background, potong durasinya agar pas dengan suara
    video_clip = VideoFileClip("background.mp4").subclip(0, duration)
    # Matikan suara asli video background jika ada
    video_clip = video_clip.set_audio(None)

    # Ambil isi teks script untuk dipecah jadi subtitle
    # Kita baca script teks mentah dari file log sementara atau dari app.py
    # Supaya aman, kita buat logika pembagian durasi teks di layar
    import json
    with open("vo.mp3", "r") as f: pass # Hanya memastikan file audio ada
    
    # Karena kita butuh teks aslinya, kita baca dari file sementara jika disimpan, 
    # atau kita buat teks statis/dinamis. Di sini kita buat penanganan teks bawaan:
    # (Untuk akurasi penuh, teks dibaca dari teks Gemini yang kita simpan lewat app.py)
    # Anggap skrip dikirim/disimpan ke file text.txt di langkah sebelumnya.
    script_text = "Fakta Psikologi Manusia"
    if os.path.exists("script.txt"):
        with open("script.txt", "r", encoding="utf-8") as f:
            script_text = f.read()

    text_chunks = split_text_into_chunks(script_text, max_words=3)
    num_chunks = len(text_chunks)
    chunk_duration = duration / num_chunks if num_chunks > 0 else duration

    text_clips = []
    
    # Loop untuk menempelkan potongan teks ke layar
    for i, chunk in enumerate(text_chunks):
        start_time = i * chunk_duration
        end_time = (i + 1) * chunk_duration
        
        # Buat objek teks visual di layar
        # Membutuhkan file font.ttf di root folder repositori kamu
        txt_clip = TextClip(
            chunk, 
            fontsize=45, 
            color='white', 
            font='font.ttf',
            stroke_color='black',
            stroke_width=2,
            method='caption',
            size=(video_clip.w - 100, None)
        )
        
        # Tentukan posisi tengah layar dan durasi tampil teks
        txt_clip = txt_clip.set_start(start_time).set_end(end_time).set_position(('center', 'center'))
        text_clips.append(txt_clip)

    # Gabungkan video dasar dengan semua potongan teks subtitle
    final_video = CompositeVideoClip([video_clip] + text_clips)
    
    # Tempelkan audio pengisi suara ke video final
    final_video = final_video.set_audio(audio_clip)

    # Ekspor hasil akhir ke file mp4
    print("🔄 Merender video akhir (final_output.mp4)...")
    final_video.write_videofile(
        "final_output.mp4", 
        fps=24, 
        codec="libx264", 
        audio_codec="aac",
        threads=4
    )
    
    # Bersihkan file sampah agar hemat memori server
    audio_clip.close()
    video_clip.close()
    final_video.close()
    if os.path.exists("background.mp4"):
        os.remove("background.mp4")
        
    print("✅ Video final_output.mp4 berhasil dirakit sempurna.")
