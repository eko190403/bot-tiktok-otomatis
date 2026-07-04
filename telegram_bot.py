import os
import asyncio
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Muat file .env jika berjalan di komputer lokal
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8644685615:AAERnJkiFVLR0HhFxmj5HTFmYhsmtytso1A")
GITHUB_TOKEN = os.getenv("GH_PAT_TOKEN")    # Personal Access Token (Classic) dari GitHub
GITHUB_REPO = os.getenv("GH_REPO")          # Format: username/nama-repo

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani perintah /start di Telegram."""
    await update.message.reply_text(
        f"👋 Halo Vio!\n"
        f"Saya adalah sistem otomatisasi Ruang Pikir Engine.\n\n"
        f"Ketik perintah `/generate` untuk memicu pipeline pembuatan video Shorts di GitHub Actions secara otomatis."
    )

async def generate_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memicu GitHub Actions Workflow melalui Repository Dispatch API."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        await update.message.reply_text("❌ Eror: Variabel GH_PAT_TOKEN atau GH_REPO belum dikonfigurasi di server!")
        return

    await update.message.reply_text("🧠 Perintah diterima. Menghubungi API GitHub Actions...")

    # Jalur endpoint resmi GitHub Repository Dispatches
    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    
    # Payload wajib membawa event_type yang sinkron dengan file .yml
    payload = {
        "event_type": "telegram_trigger",
        "client_payload": {
            "chat_id": str(update.effective_chat.id),
            "user": update.effective_user.username
        }
    }

    # Jalankan request HTTP POST secara asynchronous agar tidak memblokir bot
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: requests.post(url, json=payload, headers=headers, timeout=10)
        )
        
        if response.status_code == 204:
            await update.message.reply_text(
                "🚀 Sukses Besar!\n"
                "Workflow GitHub Actions telah berhasil dibangunkan.\n"
                "Video V7.1 kamu sedang diproses di awan, pantau langsung di tab 'Actions' GitHub-mu!"
            )
        else:
            await update.message.reply_text(
                f"❌ GitHub menolak permintaan.\n"
                f"Kode Status: {response.status_code}\n"
                f"Respon: {response.text}"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Terjadi kesalahan koneksi ke GitHub: {e}")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memproses tombol inline untuk upload YouTube/TikTok."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data or not data.startswith("pub:"):
        return
        
    parts = data.split(":")
    if len(parts) < 3:
        return
        
    platform_code = parts[1] # "yt" atau "tt"
    video_id = parts[2]
    
    platform = "YouTube Shorts" if platform_code == "yt" else "TikTok"
    
    # Sunting caption pesan untuk memberikan progres pemrosesan
    current_caption = query.message.caption or ""
    await query.edit_message_caption(
        caption=f"{current_caption}\n\n⏳ <b>Memproses publikasi ke {platform}...</b>",
        parse_mode="HTML"
    )
    
    if not GITHUB_TOKEN or not GITHUB_REPO:
        await query.edit_message_caption(
            caption=f"{current_caption}\n\n❌ <b>Eror: GH_PAT_TOKEN atau GH_REPO tidak diset di server bot!</b>",
            parse_mode="HTML"
        )
        return
        
    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    
    # Kirim Repository Dispatch Event ke GitHub Actions
    payload = {
        "event_type": "telegram_publish",
        "client_payload": {
            "video_id": video_id,
            "platform": "youtube" if platform_code == "yt" else "tiktok",
            "chat_id": str(update.effective_chat.id)
        }
    }
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: requests.post(url, json=payload, headers=headers, timeout=10)
        )
        if response.status_code == 204:
            await query.edit_message_caption(
                caption=f"{current_caption}\n\n🚀 <b>Perintah dikirim ke GitHub!</b> Proses pengunggahan ke {platform} sedang berjalan di cloud.",
                parse_mode="HTML"
            )
        else:
            await query.edit_message_caption(
                caption=f"{current_caption}\n\n❌ <b>Gagal memicu GitHub ({response.status_code}):</b> {response.text}",
                parse_mode="HTML"
            )
    except Exception as e:
        await query.edit_message_caption(
            caption=f"{current_caption}\n\n❌ <b>Eror koneksi ke API GitHub:</b> {e}",
            parse_mode="HTML"
        )


def main():
    """Mengaktifkan daemon bot Telegram."""
    if not TELEGRAM_TOKEN:
        print("❌ Eror Fatal: TELEGRAM_BOT_TOKEN kosong!")
        return

    # Bangun aplikasi bot
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Daftarkan handler perintah chat
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("generate", generate_video))
    application.add_handler(CallbackQueryHandler(button_click))

    print("🤖 Python Telegram Bot aktif mendengarkan perintah /generate dari Vio...")
    application.run_polling()

if __name__ == "__main__":
    main()
