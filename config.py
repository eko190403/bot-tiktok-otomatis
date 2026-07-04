import os

# Video Settings
WIDTH = 1080
HEIGHT = 1920
FPS = 30

# Typography Settings
FONT_PATH = os.path.join("assets", "fonts", "font.ttf")
FONT_SIZE_HOOK = 68
FONT_SIZE_BODY = 58
STROKE_WIDTH = 5

# Path Directories
DIR_ASSETS = "assets"
DIR_OUTPUT = "output"

import sys
if sys.platform.startswith("win"):
    DIR_TEMP = "temp"
else:
    # Menggunakan RAM Disk (/dev/shm) di Linux (GitHub Actions) untuk mempercepat rendering file I/O
    DIR_TEMP = "/dev/shm/temp" if os.path.exists("/dev/shm") else "temp"

# API Keys - Mendukung rotasi otomatis dari GEMINI_API_KEY_1 sampai GEMINI_API_KEY_8
GEMINI_KEYS = []
for i in range(1, 9): # Mengubah range ke 9 agar mencakup kunci ke-6, 7, dan 8
    key = os.getenv(f"GEMINI_API_KEY_{i}") or os.getenv("GEMINI_API_KEY")
    if key and key not in GEMINI_KEYS:
        GEMINI_KEYS.append(key)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

def get_channel_config(channel_id: str = "ruangpikir") -> dict:
    import json
    json_path = os.path.join("config", "channels.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                channels = data.get("channels", {})
                if channel_id in channels:
                    cfg = channels[channel_id]
                    cfg["id"] = channel_id
                    return cfg
                if channels:
                    first_key = next(iter(channels.keys()))
                    cfg = channels[first_key]
                    cfg["id"] = first_key
                    return cfg
        except Exception as e:
            print(f"⚠️ Gagal membaca config/channels.json: {e}")
            
    # Default fallback
    return {
        "id": "ruangpikir",
        "name": "Ruang Pikir",
        "niche": "dark psychology and human behavior secrets",
        "watermark": "@RuangPikir",
        "aesthetic_query": "dark cinematic cold moody tone",
        "voice_id": "id-ID-ArdiNeural",
        "theme_color": "classic_yellow"
    }

