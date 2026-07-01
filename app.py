import os
import asyncio
from video_builder import create_video
# from uploader import upload_video  # Aktifkan jika modul uploader sudah siap

async def main():
    try:
        print("🚀 Memulai Pipeline Pembuatan Video Otomatis...")
        
        # 1. Jalankan proses orchestrator video_builder
        success = create_video()
        
        if success:
            print("🎬 Video Berhasil Dirender Sempurna!")
            # 2. Jalankan uploader ke TikTok Shorts
            # upload_video()
        else:
            print("❌ Gagal membuat video.")
            
    except Exception as e:
        print(f"❌ Terjadi Eror pada Pipeline Utama: {e}")

if __name__ == "__main__":
    asyncio.run(main())
