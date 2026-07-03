"""
uploader.py — Mengunggah video otomatis ke TikTok Creator Studio via Playwright.
Dilengkapi dengan adapter konverter cookies otomatis dari format Chrome/EditThisCookie ke Playwright.
"""
import os
import json
import asyncio
from playwright.async_api import async_playwright

def convert_to_playwright_cookies(input_path: str, output_path: str):
    """
    Adapter otomatis: Mengonversi berkas cookies standar (EditThisCookie/Chrome)
    menjadi format storageState resmi Playwright.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Berkas cookie {input_path} tidak ditemukan!")

    with open(input_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    # 1. Pastikan data berupa list cookie
    cookies_list = []
    if isinstance(raw_data, dict) and "cookies" in raw_data:
        cookies_list = raw_data["cookies"]
    elif isinstance(raw_data, list):
        cookies_list = raw_data
    else:
        raise ValueError("Format cookies.json tidak dikenali (harus berupa JSON Array atau Object)")

    playwright_cookies = []
    for c in cookies_list:
        if "name" not in c or "value" not in c or "domain" not in c:
            continue

        # Petakan expirationDate -> expires
        expires = c.get("expirationDate") or c.get("expires")

        # Petakan sameSite agar kompatibel dengan enum Playwright: Lax, Strict, atau None
        same_site = c.get("sameSite", "None")
        if same_site is not None:
            ss_str = str(same_site).lower()
            if "no_restriction" in ss_str:
                same_site = "None"
            elif "lax" in ss_str:
                same_site = "Lax"
            elif "strict" in ss_str:
                same_site = "Strict"
            else:
                same_site = "None"
        else:
            same_site = "None"

        # Buat objek cookie yang valid untuk Playwright
        pw_cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", True),
            "sameSite": same_site
        }
        
        if expires is not None:
            try:
                pw_cookie["expires"] = float(expires)
            except (ValueError, TypeError):
                pass

        playwright_cookies.append(pw_cookie)

    # Bungkus dalam format storageState Playwright
    storage_state = {
        "cookies": playwright_cookies,
        "origins": []
    }

    # Pastikan folder output dari temporary state ada
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(storage_state, f, indent=4, ensure_ascii=False)
    
    print(f"✅ Cookies dikonversi secara sukses ke format Playwright di: {output_path}")


async def upload_to_tiktok(video_path="final_output.mp4", caption=""):
    print("🚀 Playwright: Membuka browser headless di server GitHub...")
    
    input_cookie = "cookies.json"
    temp_cookie = "temp/cookies_playwright.json"
    
    if not os.path.exists(input_cookie):
        raise FileNotFoundError("❌ Eror: File cookies.json tidak ditemukan! Bot tidak bisa login ke TikTok.")

    # Jalankan adapter konversi sebelum memuat browser
    try:
        convert_to_playwright_cookies(input_cookie, temp_cookie)
    except Exception as conv_err:
        print(f"⚠️ Gagal mengonversi cookies: {conv_err}. Mencoba memuat langsung berkas asli...")
        temp_cookie = input_cookie

    async with async_playwright() as p:
        # Menjalankan browser Chromium bawaan Playwright
        browser = await p.chromium.launch(headless=True)
        
        # Membuat konteks browser baru dengan storage_state hasil konversi
        context = await browser.new_context(storage_state=temp_cookie)
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
        
        # Beri jeda sejenak agar form metadata termuat
        await asyncio.sleep(3)

        # Masukkan Caption/Deskripsi
        if caption:
            print(f"✍️ Menulis deskripsi video: {caption}")
            try:
                # Mencoba beberapa selektor alternatif demi ketahanan DOM TikTok
                selectors = [
                    '[data-e2e="upload-caption-input"]',
                    'div[contenteditable="true"]',
                    '.editor-container div[contenteditable="true"]',
                    'textarea[placeholder*="caption"]',
                    'textarea[placeholder*="deskripsi"]'
                ]
                caption_element = None
                for sel in selectors:
                    try:
                        caption_element = await page.wait_for_selector(sel, timeout=10000)
                        if caption_element:
                            print(f"✅ Menemukan elemen caption dengan selektor: {sel}")
                            break
                    except:
                        continue
                
                if caption_element:
                    # Klik elemen untuk memfokuskan
                    await caption_element.click()
                    
                    # Bersihkan isi teks bawaan (nama file)
                    # Shortcut Keyboard Control+A lalu Backspace
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(1)
                    
                    # Ketikkan caption secara bertahap (human-like typing)
                    await page.keyboard.type(caption, delay=60) # delay 60ms per karakter
                    print("📝 Deskripsi dan Hashtag berhasil diinput.")
                else:
                    print("⚠️ Gagal menemukan elemen input caption. Melanjutkan tanpa deskripsi.")
            except Exception as e:
                print(f"⚠️ Gagal menginput caption: {e}")
        
        print("⏳ Menunggu proses upload dan enkoding video selesai di server TikTok...")
        # Menunggu tombol "Posting" aktif (menandakan video selesai terunggah)
        button_post = await page.wait_for_selector("button:has-text('Post')", timeout=120000)
        
        # Eksekusi klik tombol posting
        print("🎯 Klik tombol posting konten!")
        await button_post.click()
        
        # Beri jeda 5 detik untuk memastikan request selesai dikirim
        await asyncio.sleep(5)
        print("🚀 Video sukses terbit di akun TikTok Anda.")
        
        await browser.close()
        
        # Bersihkan cookie temporer demi keamanan
        if os.path.exists(temp_cookie) and temp_cookie != input_cookie:
            try:
                os.remove(temp_cookie)
            except OSError:
                pass
