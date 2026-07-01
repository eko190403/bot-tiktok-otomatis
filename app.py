import os
import asyncio
from video_builder import create_video

async def main():
    try:
        print("🚀 Memulai Pipeline Pembuatan Video Otomatis...")
        
        # Eksekusi fungsi asinkronus dengan keyword await
        success = await create_video()
        
        if success:
            print("🎬 Video Berhasil Dirender Sempurna!")
        else:
            print("❌ Gagal membuat video.")
            
    except Exception as e:
        print(f"❌ Terjadi Eror pada Pipeline Utama: {e}")

if __name__ == "__main__":
    asyncio.run(main())
