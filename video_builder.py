import os
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

def create_tiktok_video(audio_path="vo.mp3", output_path="final_output.mp4"):
    print("🎬 MoviePy: Memproses perakitan komponen video...")
    
    # 1. Validasi Audio Voiceover
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"❌ File audio {audio_path} tidak ditemukan!")
        
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration
    
    # 2. Ambil Video Mentah (Dummy / Background Asset)
    # Untuk pengujian awal di GitHub, kita buat background hitam berdurasi sepanjang audio
    # Nanti bagian ini bisa dikembangkan untuk menembak API Pexels secara otomatis
    print(f"⏱️ Durasi video disesuaikan dengan audio: {duration} detik")
    
    # Membuat klip background (Pastikan di server sudah terunggah minimal 1 video mentah bernama 'background.mp4')
    if not os.path.exists("background.mp4"):
        print("⚠️ Background.mp4 tidak ditemukan. Membuat simulasi render text saja.")
        # Jika belum ada video mentah, proses dialihkan atau menggunakan aset default
        raise FileNotFoundError("❌ Silakan upload file 'background.mp4' sebagai video latar belakang di repo GitHub Anda.")

    video_clip = VideoFileClip("background.mp4").subclip(0, duration)
    
    # 3. Pengaturan Resolusi Vertikal 9:16 (Format TikTok)
    video_clip = video_clip.resize(newsize=(1080, 1920))
    
    # 4. Gabungkan Video dan Audio
    final_video = video_clip.set_audio(audio_clip)
    
    # 5. Render Video Akhir
    print("⏳ Menulis file video final_output.mp4 ke sistem server...")
    final_video.write_videofile(
        output_path, 
        fps=24, 
        codec="libx264", 
        audio_codec="aac",
        threads=4
    )
    
    # Tutup klip untuk membebaskan memori RAM server
    audio_clip.close()
    video_clip.close()
    final_video.close()
    print("✅ Video final_output.mp4 berhasil dirakit sempurna.")
