import os
import time
import json
import logging
import asyncio
import datetime
import requests
import base64

logger = logging.getLogger("ai_video_engine")

# API Endpoints (Placeholder documentation URLs or common structures)
# - Fal.ai: https://fal.ai/docs
# - Pika: https://pika.art/docs/api
# - Kling: https://klingai.com/api
# - HaiLuo/MiniMax: https://api.minimax.chat/document/video-generation

def get_daily_video_provider() -> str:
    """Merotasi penyedia Image-to-Video secara harian berdasarkan tanggal."""
    providers = ["kling", "fal"]
    day_of_year = datetime.datetime.now().timetuple().tm_yday
    selected = providers[day_of_year % len(providers)]
    logger.info(f" Penyedia AI Video hari ini (Day {day_of_year}): {selected.upper()}")
    return selected

async def generate_image_fal(prompt: str, width: int = 1080, height: int = 1920) -> str:
    """Menghasilkan gambar awal (Text-to-Image) menggunakan Fal.ai (misal FLUX.1) dengan rotasi 5 key."""
    loop = asyncio.get_running_loop()
    url = "https://queue.fal.run/fal-ai/flux/dev" # Contoh endpoint
    
    for attempt in range(1, 9):
        api_key = os.getenv(f"FAL_API_KEY_{attempt}")
        if not api_key:
            continue
            
        headers = {
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt,
            "image_size": f"{width}x{height}",
            "num_images": 1
        }
        
        try:
            response = await loop.run_in_executor(
                None, lambda h=headers, p=payload: requests.post(url, json=p, headers=h, timeout=30)
            )
            if response.status_code == 200:
                res_json = response.json()
                if "images" in res_json and len(res_json["images"]) > 0:
                    image_url = res_json["images"][0]["url"]
                    logger.info(f" Gambar AI berhasil di-generate via Fal (Key {attempt}): {image_url}")
                    return image_url
            elif response.status_code in [401, 403, 429]:
                logger.warning(f" Fal.ai Key {attempt} limit/error: {response.text}")
                continue
            else:
                logger.warning(f" Gagal generate gambar dengan Key {attempt}: {response.text}")
        except Exception as e:
            logger.warning(f" Error saat memanggil Fal.ai T2I dengan Key {attempt}: {e}")
            continue
            
    logger.error(" Semua key FAL (1-8) gagal, habis limit, atau tidak dikonfigurasi. Menggunakan dummy image.")
    return "dummy_image_url"

async def _download_and_save_video(url: str, output_path: str):
    """Fungsi utilitas untuk mengunduh video hasil generate."""
    loop = asyncio.get_running_loop()
    try:
        def download():
            r = requests.get(url, stream=True, timeout=60)
            if r.status_code == 200:
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        if chunk: f.write(chunk)
                return True
            return False
        
        success = await loop.run_in_executor(None, download)
        if success:
            logger.info(f" Video berhasil diunduh ke {output_path}")
            return output_path
        else:
            logger.error(" Gagal mengunduh video hasil API.")
            return None
    except Exception as e:
        logger.error(f" Error downloading video: {e}")
        return None

async def animate_kling(image_url: str, prompt: str, output_path: str) -> str:
    """Implementasi animasi via Kling AI API (Simulasi/Mock)."""
    logger.info(f" Memanggil Kling API untuk animasi. Prompt: '{prompt}'")
    for attempt in range(1, 9):
        api_key = os.getenv(f"KLING_API_KEY_{attempt}")
        if not api_key: continue
        logger.warning(f" KLING_API_KEY_{attempt} digunakan. Simulasi sukses.")
        await asyncio.sleep(2)
        # BISA IMPLEMENTASI REAL KLING API DISINI
        return None
    logger.warning(" Semua KLING_API_KEY (1-8) gagal/tidak diset. Simulasi sukses (fallback).")
    return None

async def animate_fal(image_url: str, prompt: str, output_path: str) -> str:
    """Implementasi animasi via Fal.ai (LTX / SVD) (Simulasi/Mock)."""
    logger.info(f" Memanggil Fal API (I2V) untuk animasi. Prompt: '{prompt}'")
    for attempt in range(1, 9):
        api_key = os.getenv(f"FAL_API_KEY_{attempt}")
        if not api_key: continue
        logger.warning(f" FAL_API_KEY_{attempt} digunakan. Simulasi sukses.")
        await asyncio.sleep(2)
        # BISA IMPLEMENTASI REAL FAL I2V API DISINI
        return None
    logger.warning(" Semua FAL_API_KEY (1-8) gagal/tidak diset. Simulasi sukses (fallback).")
    return None

# ================= ORCHESTRATOR =================

async def run_ai_video_workflow(image_prompts: list, target_count: int, output_dir: str = "assets/fallback") -> list:
    """
    Orkestrator utama untuk AI Video Niche:
    1. Mengambil naskah/prompt gambar.
    2. Menghasilkan gambar statis (Text-to-Image).
    3. Menganimasikan gambar (Image-to-Video) menggunakan rotasi harian.
    4. Mengunduh hasil MP4.
    """
    os.makedirs(output_dir, exist_ok=True)
    provider = get_daily_video_provider()
    
    generated_videos = []
    
    # Ambil seperlunya sesuai target_count
    prompts_to_process = image_prompts[:target_count]
    while len(prompts_to_process) < target_count:
        prompts_to_process.append("cinematic dark moody abstract scene, high quality")
        
    for i, prompt_data in enumerate(prompts_to_process):
        # 1. Generate Image (Defaulting to Fal)
        logger.info(f" [Step 1] Menghasilkan gambar AI ({i+1}/{target_count})")
        image_url = await generate_image_fal(prompt=prompt_data, width=1080, height=1920)
        
        # 2. Animate Image
        logger.info(f" [Step 2] Menganimasikan gambar via {provider.upper()}")
        output_filename = os.path.join(output_dir, f"ai_anim_{provider}_{int(time.time())}_{i}.mp4")
        
        anim_prompt = "cinematic slow pan, subtle motion, elegant movement"
        
        # Delegasi ke fungsi spesifik
        video_path = None
        if provider == "kling":
            video_path = await animate_kling(image_url, anim_prompt, output_filename)
        elif provider == "fal":
            video_path = await animate_fal(image_url, anim_prompt, output_filename)
            
        if video_path and os.path.exists(video_path):
            generated_videos.append(video_path)
        else:
            logger.warning(f" ⚠️ Provider {provider} gagal merender/unduh video. Coba generate fallback.")
            # Di lingkungan nyata, bisa panggil provider fallback
            
    return generated_videos
