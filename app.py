import os
import sys
import traceback
import asyncio

async def main():
    try:
        print("🚀 Memulai Pipeline Pembuatan Video Otomatis...")
        
        # Lakukan import secara lokal di dalam fungsi untuk melacak jika eror berasal dari file import
        print("📦 Meng-import modul video_builder...")
        from video_builder import create_video
        
        print("🎬 Menjalankan fungsi create_video()...")
        success = await create_video()
        
        if success:
            print("✅ Video Berhasil Dirender Sempurna!")
        else:
            print("❌ Gagal membuat video (Kembalian Bernilai False).")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Terjadi Eror Fatal pada Pipeline Utama: {e}")
        print("\n🔍 DETAIL TRACEBACK EROR:")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    # Paksa cetak langsung ke log tanpa buffer agar terlihat di GitHub Actions
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(main())
