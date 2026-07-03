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


def get_tiktok_username_from_cookies(cookie_path="cookies.json") -> str:
    """Membaca cookies.json dan mengekstrak nilai cookie 'unique_id' atau 'unique_id_d' sebagai username."""
    if not os.path.exists(cookie_path):
        return "@Akun_Tidak_Diketahui"
        
    try:
        with open(cookie_path, "r", encoding="utf-8") as f:
            c_data = json.load(f)
            c_list = c_data.get("cookies", []) if isinstance(c_data, dict) else c_data
            for c in c_list:
                if c.get("name") in ["unique_id", "unique_id_d"]:
                    val = c.get("value", "")
                    if val:
                        import urllib.parse
                        decoded = urllib.parse.unquote(val)
                        # Bersihkan jika ada format JSON/String aneh
                        decoded = decoded.strip('"').strip("'")
                        if not decoded.startswith("@"):
                            decoded = f"@{decoded}"
                        return decoded
    except Exception as e:
        print(f"⚠️ Gagal mengekstrak username dari cookie: {e}")
        
    return "@RuangPikir"


async def upload_to_tiktok(video_path="final_output.mp4", caption="") -> str:
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
        # Jalankan browser Chromium secara headless dengan mode anti-deteksi bot
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        # Membuat konteks browser dengan storage_state hasil konversi dan User Agent manusia
        context = await browser.new_context(
            storage_state=temp_cookie,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})
        
        detected_username = None
        
        try:
            print("🌐 Mengakses halaman TikTok Creator Studio Upload...")
            await page.goto("https://www.tiktok.com/creator-center/upload?lang=id-ID", timeout=60000)
            
            # Cek apakah berhasil masuk atau malah mental ke halaman login biasa
            if "login" in page.url or "signup" in page.url:
                raise RuntimeError("Cookies kedaluwarsa atau tidak valid. TikTok meminta login ulang.")
                
            print("📤 Memilih dan mengunggah berkas video...")
            # Menemukan elemen input file di halaman TikTok Studio dengan state attached (karena input sering disembunyikan secara visual)
            file_input = await page.wait_for_selector("input[type='file']", state="attached", timeout=45000)
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
            # Kita tunggu tombol [data-e2e="post_video_button"] yang tidak memiliki aria-disabled="true"
            button_post = None
            selectors_post = [
                '[data-e2e="post_video_button"]:not([aria-disabled="true"])',
                'button:has-text("Post"):not([disabled]):not([aria-disabled="true"])',
                'button:has-text("Posting"):not([disabled]):not([aria-disabled="true"])',
                'button:has-text("Terbitkan"):not([disabled]):not([aria-disabled="true"])',
                # Fallback jika selektor strict tidak terdeteksi
                '[data-e2e="post_video_button"]',
                'button:has-text("Post")',
                'button:has-text("Posting")'
            ]
            
            for sel in selectors_post:
                try:
                    button_post = await page.wait_for_selector(sel, timeout=10000)
                    if button_post:
                        is_disabled = await button_post.get_attribute("aria-disabled")
                        if is_disabled == "true":
                            continue
                        print(f"✅ Menemukan tombol posting yang aktif: {sel}")
                        break
                except:
                    continue
    
            # Jika setelah iterasi cepat tidak ketemu tombol aktif, mari tunggu tombol resmi yang aktif secara eksplisit
            if not button_post:
                print("⏳ Menunggu tombol posting resmi [data-e2e='post_video_button'] menjadi aktif (maksimal 3 menit)...")
                try:
                    button_post = await page.wait_for_selector('[data-e2e="post_video_button"]:not([aria-disabled="true"])', timeout=180000)
                except Exception as e:
                    print(f"⚠️ Gagal menunggu tombol data-e2e aktif: {e}. Mencoba mencari tombol teks 'Post' secara umum...")
                    try:
                        button_post = await page.wait_for_selector('button:has-text("Post")', timeout=30000)
                    except Exception as e2:
                        raise RuntimeError(f"❌ Tidak dapat menemukan tombol posting aktif di layar: {e2}")
    
            # Klik tombol posting
            print("🎯 Klik tombol posting konten!")
            await button_post.click()
            
            # Menunggu konfirmasi sukses dari TikTok
            print("⏳ Menunggu konfirmasi sukses publikasi dari TikTok Creator Studio...")
            success_selectors = [
                '[data-e2e="upload-success-modal"]',
                'button:has-text("Post another video")',
                'button:has-text("Urus postingan")',
                'button:has-text("Kelola konten")',
                'text="Manage posts"',
                'text="Manage content"',
                'text="Manage your posts"',
                'text="Post another video"',
                'text="Urus postingan"',
                'text="Kelola konten"'
            ]
            
            success_found = False
            # Polling setiap 1 detik selama maksimal 45 detik
            for attempt in range(45):
                for sel in success_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible():
                            print(f"🚀 Konfirmasi Sukses Terdeteksi: '{sel}' terlihat di layar!")
                            success_found = True
                            break
                    except:
                        continue
                if success_found:
                    break
                await asyncio.sleep(1)
                
            if not success_found:
                print("⚠️ Peringatan: Konfirmasi sukses publikasi tidak muncul secara visual dalam 45 detik. Tombol posting sudah diklik, memberikan waktu penyelamatan tambahan 12 detik...")
                await asyncio.sleep(12)
            else:
                print("🚀 Konfirmasi sukses terverifikasi secara visual.")
                await asyncio.sleep(3) # Jeda ekstra agar request selesai dikirim sepenuhnya
                
            # Deteksi username secara dinamis dari visual layar (Body Text) sebelum menutup browser
            try:
                body_text = await page.locator("body").text_content()
                import re
                matches = re.findall(r'@[a-zA-Z0-9_\.]+', body_text)
                for m in matches:
                    clean_m = m.strip()
                    # Filter email dan teks yang tidak valid
                    if len(clean_m) > 2 and len(clean_m) < 30 and "." not in clean_m:
                        detected_username = clean_m
                        print(f"👤 Berhasil mendeteksi username secara visual dari layar: {detected_username}")
                        break
            except Exception as detect_err:
                print(f"⚠️ Gagal mendeteksi username secara visual dari layar: {detect_err}")
                
            if not detected_username:
                detected_username = get_tiktok_username_from_cookies(input_cookie)
                
        except Exception as e:
            # Ambil screenshot jika terjadi kegagalan untuk mempermudah debugging di GitHub Actions
            print(f"📸 Mengambil screenshot kegagalan karena terjadi eror: {e}")
            try:
                os.makedirs("output", exist_ok=True)
                await page.screenshot(path="output/error_screenshot.png", full_page=True)
                print("💾 Screenshot berhasil disimpan ke: output/error_screenshot.png")
            except Exception as screenshot_err:
                print(f"⚠️ Gagal mengambil screenshot: {screenshot_err}")
            raise e
        finally:
            await browser.close()
            
        # Bersihkan cookie temporer demi keamanan
        if os.path.exists(temp_cookie) and temp_cookie != input_cookie:
            try:
                os.remove(temp_cookie)
            except OSError:
                pass
                
        return detected_username
