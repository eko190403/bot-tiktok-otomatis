import json
import os
import asyncio
from playwright.async_api import async_playwright

async def main():
    print("====================================================")
    print(" YouTube Cookie Refresher (Playwright)")
    print("====================================================")
    print("Skrip ini akan membuka browser agar Anda bisa login.")
    print("Setelah login berhasil, cookies terbaru akan disimpan.")
    print("====================================================\n")
    
    async with async_playwright() as p:
        # Jalankan browser Chromium secara visual (headless=False)
        # Jalankan browser Chromium secara visual dengan mode anti-deteksi bot
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print(" Membuka halaman login YouTube Studio...")
        await page.goto("https://studio.youtube.com/", timeout=60000)
        
        print("\n SILAKAN LOGIN DI JENDELA BROWSER YANG TERBUKA.")
        print(" Lakukan login Google/YouTube Anda seperti biasa.")
        print(" Setelah berhasil masuk ke dashboard YouTube Studio, silakan")
        input("   kembali ke terminal ini dan tekan [ENTER] untuk menyimpan cookies...")
        
        print("\n Mengambil cookies aktif dari browser...")
        cookies = await context.cookies()
        
        if not cookies:
            print(" Eror: Tidak ada cookies yang ditemukan. Apakah Anda sudah login?")
            await browser.close()
            return
            
        # Tambahkan atribut expirationDate untuk kompatibilitas penuh
        for c in cookies:
            if "expires" in c and c["expires"] is not None:
                c["expirationDate"] = c["expires"]
                
        output_file = "youtube_cookies.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=4, ensure_ascii=False)
            
        print(f" Cookies berhasil disimpan ke: {output_file}")
        print(" Selesai! Browser akan ditutup secara otomatis.")
        await browser.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n Proses dibatalkan oleh pengguna.")
