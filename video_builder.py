import os
from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

def create_tiktok_video(audio_path="vo.mp3", output_path="final_output.mp4"):
    print("🎬 MoviePy: Memproses perakitan komponen video...")
    
    # 1. Validasi Audio Voiceover
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"❌ File audio {audio_path} tidak ditemukan!")
        
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration
    
    # 2. Ambil Video Mentah (Background Asset)
    print(f"⏱️ Durasi video disesuaikan dengan audio: {duration} detik")
    
    if not os.path.exists("background.mp4"):
        raise FileNotFoundError("❌ Silakan upload file 'background.mp4' sebagai video latar belakang di repo GitHub Anda.")

    # Mengambil potongan video sesuai durasi audio
    video_clip = VideoFileClip("background.mp4").subclip(0, duration)
    
    # 3. Pengaturan Resolusi Vertikal 9:16 (Format Standard TikTok)
    video_clip = video_clip.resized(newsize=(1080, 1920))
    
    # 4. Gabungkan Video dan Audio
    final_video = video_clip.with_audio(audio_clip)
    
    # 5. Render Video Akhir ke Sistem Server
    print("⏳ Menulis file video final_output.mp4 ke sistem server...")
    final_video.write_videofile(
        output_path, 
        fps=24, 
        codec="libx264", 
        audio_codec="aac",
        threads=4
    )
    
    # Tutup klip untuk membebaskan RAM server agar tidak crash
    audio_clip.close()
    video_clip.close()
    final_video.close()
    print("✅ Video final_output.mp4 berhasil dirakit sempurna.")
