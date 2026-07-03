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
            
            # Poin 9: Integrasi Upload Otomatis ke TikTok
            enable_upload = os.getenv("ENABLE_TIKTOK_UPLOAD", "false").lower() == "true"
            if enable_upload:
                print("📤 Memicu pengunggahan otomatis ke TikTok...")
                import glob
                from uploader import upload_to_tiktok
                
                # Cari file video terbaru di folder output
                video_files = glob.glob("output/*.mp4")
                if video_files:
                    latest_video = max(video_files, key=os.path.getctime)
                    print(f"🎬 Menemukan video terbaru: {latest_video}. Memulai upload...")
                    try:
                        await upload_to_tiktok(latest_video)
                        print("🚀 Sukses mengunggah video ke TikTok!")
                    except Exception as upload_err:
                        print(f"❌ Gagal mengunggah ke TikTok: {upload_err}")
                        # Jangan sys.exit(1) agar workflow tidak dianggap gagal hanya karena masalah upload/cookie
                else:
                    print("⚠️ Tidak ada file video di folder output untuk diunggah.")
            else:
                print("ℹ️ Pengunggahan otomatis ke TikTok dinonaktifkan (ENABLE_TIKTOK_UPLOAD=false).")
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
