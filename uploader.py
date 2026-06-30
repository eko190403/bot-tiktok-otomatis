import os
import asyncio
from playwright.async_api import async_playwright

async def upload_to_tiktok(video_path="final_output.mp4"):
    print("🚀 Playwright: Membuka browser headless di server GitHub...")
    
    if not os.path.exists("cookies.json"):
        raise FileNotFoundError("❌ Eror: File cookies.json tidak ditemukan! Bot tidak bisa login ke TikTok.")

    async with async_playwright() as p:
        # Menjalankan browser Chromium bawaan Playwright
        browser = await p.chromium.launch(headless=True)
        
        # Membuat konteks browser baru dan menyuntikkan cookies login
        context = await browser.new_context(storage_state="cookies.json")
        page = await context.new_page()
        
        print("🌐 Mengakses halaman TikTok Creator Studio Upload...")
        await page.goto("https://www.tiktok.com/creator-center/upload?lang=id-ID", timeout=60000)
        await page.wait_for_load_state("networkidle")
        
        # Cek apakah berhasil masuk atau malah mental ke halaman login biasa
        if "login" in page.url:
            print("❌ Eror: Cookies kedaluwarsa atau tidak valid. TikTok meminta login ulang.")
            await browser.close()
            return
            
        print("📤 Memilih dan mengunggah berkas video...")
        # Menemukan elemen input file di halaman TikTok Studio
        file_input = await page.wait_for_selector("input[type='file']")
        await file_input.set_input_files(video_path)
        
        print("⏳ Menunggu proses upload dan enkoding video selesai di server TikTok...")
        # Menunggu tombol "Posting" aktif (menandakan video selesai terunggah)
        # Selektor di bawah ini disesuaikan dengan struktur berkala tombol upload TikTok Studio
        button_post = await page.wait_for_selector("button:has-text('Post')", timeout=120000)
        
        # Eksekusi klik tombol posting
        print("🎯 Klik tombol posting konten!")
        await button_post.click()
        
        # Beri jeda 5 detik untuk memastikan request selesai dikirim
        await asyncio.sleep(5)
        print("🚀 Video sukses terbit di akun TikTok Anda.")
        
        await browser.close()
