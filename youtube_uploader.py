import os
import json
import asyncio
from playwright.async_api import async_playwright

async def upload_to_youtube(video_path: str, caption: str) -> str:
    """
    Mengunggah video secara otomatis ke YouTube Shorts menggunakan Playwright.
    Menggunakan cookie-based authentication untuk memintas login Google.
    """
    print("🚀 Playwright: Membuka browser headless di server GitHub untuk YouTube Shorts...")
    
    input_cookie = "youtube_cookies.json"
    if not os.path.exists(input_cookie):
        raise FileNotFoundError("❌ Eror: Berkas youtube_cookies.json tidak ditemukan! Bot tidak bisa login ke YouTube.")

    # Judul YouTube Shorts dibatasi 100 karakter. Potong caption jika terlalu panjang.
    title = caption
    if len(title) > 95:
        title = title[:90] + "... #shorts"
    elif "#shorts" not in title.lower():
        title = f"{title} #shorts"
        
    description = caption

    async with async_playwright() as p:
        # Jalankan browser Chromium secara headless dengan mode anti-deteksi bot
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        # Muat cookies YouTube hasil ekspor
        with open(input_cookie, "r", encoding="utf-8") as f:
            cookies = json.load(f)
            cookies_list = cookies.get("cookies", []) if isinstance(cookies, dict) else cookies
            
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="id-ID",
            timezone_id="Asia/Jakarta",
            geolocation={"latitude": -6.2088, "longitude": 106.8456}, # Jakarta coordinates
            permissions=["geolocation"]
        )
        await context.add_cookies(cookies_list)
        
        page = await context.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})
        
        try:
            print("🌐 Mengakses YouTube Creator Studio...")
            await page.goto("https://studio.youtube.com/", timeout=60000)
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(5)
            
            # Cek jika dialihkan kembali ke login akun Google
            if "accounts.google.com" in page.url or "signin" in page.url:
                raise RuntimeError("Cookies YouTube kadaluwarsa atau tidak valid. Harap login ulang di lokal.")
                
            print("📤 Memicu dialog unggah video...")
            # Klik tombol Create (Buat) di pojok kanan atas
            create_selectors = [
                '[id="create-icon"]',
                'ytcp-button:has-text("Create")',
                'ytcp-button:has-text("Buat")',
                'button:has-text("Create")'
            ]
            create_btn = None
            for sel in create_selectors:
                try:
                    create_btn = await page.wait_for_selector(sel, timeout=10000)
                    if create_btn:
                        break
                except:
                    continue
            if not create_btn:
                raise RuntimeError("Gagal menemukan tombol 'Create' di YouTube Studio.")
                
            await create_btn.click(force=True)
            await asyncio.sleep(1.5)
            
            # Klik menu item "Upload videos"
            upload_selectors = [
                'text="Upload videos"',
                'text="Unggah video"',
                '[id="text-item-0"]',
                'yt-formatted-string:has-text("Upload videos")'
            ]
            upload_menu = None
            for sel in upload_selectors:
                try:
                    upload_menu = await page.wait_for_selector(sel, timeout=10000)
                    if upload_menu:
                        break
                except:
                    continue
            if not upload_menu:
                raise RuntimeError("Gagal menemukan menu 'Upload videos'.")
                
            await upload_menu.click(force=True)
            await asyncio.sleep(2)
            
            # Memuat berkas ke input file (attached state)
            file_input = await page.wait_for_selector('input[type="file"]', state="attached", timeout=15000)
            await file_input.set_input_files(video_path)
            print("📤 Berkas video berhasil diunggah ke formulir. Menunggu form metadata terbuka...")
            
            # Tunggu form metadata dimuat sepenuhnya
            await page.wait_for_selector('div[id="title-textarea"]', timeout=60000)
            await asyncio.sleep(3)
            
            # 1. Isi Judul Video
            print(f"✍️ Menginput judul: {title}")
            title_box = await page.wait_for_selector('div[id="title-textarea"] div[id="textbox"]', timeout=15000)
            await title_box.click(force=True)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(title, delay=40)
            await asyncio.sleep(1)
            
            # 2. Isi Deskripsi Video
            print("✍️ Menginput deskripsi...")
            desc_box = await page.wait_for_selector('div[id="description-textarea"] div[id="textbox"]', timeout=15000)
            await desc_box.click(force=True)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(description, delay=20)
            await asyncio.sleep(1.5)
            
            # 3. Pengaturan Penargetan Anak-Anak (Wajib diisi)
            print("👶 Mengatur penargetan ke 'Not Made for Kids'...")
            kids_radio = await page.wait_for_selector('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MADE_FOR_KIDS"]', timeout=15000)
            await kids_radio.click(force=True)
            await asyncio.sleep(1.5)
            
            # 4. Melangkah Maju lewat Wizard Wizard (Details -> Video Elements -> Checks -> Visibility)
            # Klik tombol "Next" sebanyak 3 kali
            for step in range(3):
                print(f"➡️ Klik tombol 'Next' (Langkah {step+1}/3)...")
                next_btn = await page.wait_for_selector('[id="next-button"]', timeout=15000)
                await next_btn.click(force=True)
                await asyncio.sleep(2)
                
            # 5. Di Tab Visibilitas, Pilih Opsi "Public"
            print("🌐 Mengatur visibilitas video ke 'Public'...")
            public_selectors = [
                'tp-yt-paper-radio-button[name="PUBLIC"]',
                '[name="PUBLIC"]',
                'text="Public"',
                'text="Publik"'
            ]
            public_radio = None
            for sel in public_selectors:
                try:
                    public_radio = await page.wait_for_selector(sel, timeout=10000)
                    if public_radio:
                        break
                except:
                    continue
            if not public_radio:
                raise RuntimeError("Gagal menemukan opsi visibilitas 'Public'.")
                
            await public_radio.click(force=True)
            await asyncio.sleep(1.5)
            
            # 6. Klik tombol Publikasikan (Done / Publish)
            print("🎯 Klik tombol Publish video!")
            done_btn = await page.wait_for_selector('[id="done-button"]', timeout=15000)
            await done_btn.click(force=True)
            
            # Tunggu proses finalisasi postingan
            print("⏳ Menunggu publikasi selesai diproses di server YouTube...")
            await asyncio.sleep(12)
            
            print("🚀 Video berhasil diterbitkan ke YouTube Shorts!")
            return "YouTube Channel"
            
        except Exception as e:
            # Ambil screenshot jika terjadi kegagalan untuk mempermudah debugging di Telegram
            print(f"📸 Mengambil screenshot kegagalan YouTube karena terjadi eror: {e}")
            try:
                os.makedirs("output", exist_ok=True)
                await page.screenshot(path="output/youtube_error_screenshot.png", full_page=True)
                print("💾 Screenshot berhasil disimpan ke: output/youtube_error_screenshot.png")
            except Exception as screenshot_err:
                print(f"⚠️ Gagal mengambil screenshot: {screenshot_err}")
            raise e
        finally:
            await browser.close()
