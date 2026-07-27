import os
import re
import time
import json
import logging
import asyncio
import datetime
import requests
import urllib.parse

logger = logging.getLogger("ai_video_engine")



# ============================================================
#  TEXT-TO-IMAGE: Tier 1 — Pollinations.ai (GRATIS, tanpa key)
# ============================================================

async def generate_image_pollinations(prompt: str, width: int = 576, height: int = 1024, seed: int = None) -> str:
    """
    Generate gambar via Pollinations.ai — 100% GRATIS, tanpa API key.
    Endpoint: https://image.pollinations.ai/prompt/{prompt}
    Model: Flux (default) — kualitas baik untuk gaya Pixar/kartun.
    """
    loop = asyncio.get_running_loop()

    if seed is None:
        seed = int(time.time()) % 99999

    # Bersihkan & encode prompt
    clean_prompt = re.sub(r'[^\w\s,.\-!?()]', '', prompt)[:400]
    encoded = urllib.parse.quote(clean_prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&seed={seed}&model=flux&nologo=true&enhance=false"
    )

    try:
        logger.info(f" [T2I Pollinations] Requesting: {url[:80]}...")
        response = await loop.run_in_executor(
            None, lambda: requests.get(url, timeout=60, stream=True)
        )
        if response.status_code == 200 and "image" in response.headers.get("Content-Type", ""):
            # Simpan gambar lokal lalu kembalikan path
            img_path = f"/tmp/pollinations_{seed}.jpg"
            with open(img_path, "wb") as f:
                for chunk in response.iter_content(1024 * 64):
                    if chunk:
                        f.write(chunk)
            file_size = os.path.getsize(img_path)
            if file_size > 5000:  # setidaknya 5KB
                logger.info(f" [T2I Pollinations] Berhasil! {file_size // 1024}KB -> {img_path}")
                return img_path  # path lokal
        logger.warning(f" [T2I Pollinations] Gagal: status={response.status_code}")
    except Exception as e:
        logger.warning(f" [T2I Pollinations] Error: {e}")

    return None


# ============================================================
#  TEXT-TO-IMAGE: Tier 2 — Hugging Face Inference API (gratis)
# ============================================================

async def generate_image_huggingface(prompt: str, width: int = 576, height: int = 1024) -> str:
    """
    Generate gambar via Hugging Face Inference API — gratis dengan rotasi 8 token.
    Model: black-forest-labs/FLUX.1-schnell
    Secrets yang diperlukan: HF_API_KEY_1 sampai HF_API_KEY_8
    """
    loop = asyncio.get_running_loop()
    url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
    payload = {
        "inputs": prompt[:500],
        "parameters": {
            "width": width,
            "height": height,
            "num_inference_steps": 4,
            "guidance_scale": 0.0
        }
    }

    for attempt in range(1, 9):
        hf_key = os.getenv(f"HF_API_KEY_{attempt}")
        if not hf_key:
            continue

        headers = {
            "Authorization": f"Bearer {hf_key}",
            "Content-Type": "application/json"
        }

        try:
            logger.info(f" [T2I HuggingFace] Mencoba Key {attempt} (FLUX.1-schnell)...")
            response = await loop.run_in_executor(
                None, lambda h=headers: requests.post(url, json=payload, headers=h, timeout=90)
            )

            if response.status_code == 200:
                content_type = response.headers.get("Content-Type", "")
                if "image" in content_type:
                    img_path = f"/tmp/hf_{attempt}_{int(time.time())}.jpg"
                    with open(img_path, "wb") as f:
                        f.write(response.content)
                    file_size = os.path.getsize(img_path)
                    if file_size > 5000:
                        logger.info(f" [T2I HuggingFace] Key {attempt} berhasil! {file_size // 1024}KB -> {img_path}")
                        return img_path

            elif response.status_code == 429:
                logger.warning(f" [T2I HuggingFace] Key {attempt} rate limited. Coba key berikutnya.")
                continue

            elif response.status_code == 503:
                logger.warning(f" [T2I HuggingFace] Key {attempt}: Model loading (503). Tunggu 10 detik...")
                await asyncio.sleep(10)
                # Retry sekali dengan key yang sama
                response2 = await loop.run_in_executor(
                    None, lambda h=headers: requests.post(url, json=payload, headers=h, timeout=90)
                )
                if response2.status_code == 200 and "image" in response2.headers.get("Content-Type", ""):
                    img_path = f"/tmp/hf_{attempt}_retry_{int(time.time())}.jpg"
                    with open(img_path, "wb") as f:
                        f.write(response2.content)
                    if os.path.getsize(img_path) > 5000:
                        logger.info(f" [T2I HuggingFace] Key {attempt} retry berhasil -> {img_path}")
                        return img_path
                continue

            else:
                logger.warning(f" [T2I HuggingFace] Key {attempt} error {response.status_code}: {response.text[:150]}")
                continue

        except Exception as e:
            logger.warning(f" [T2I HuggingFace] Key {attempt} exception: {e}")
            continue

    logger.warning(" [T2I HuggingFace] Semua HF key (1-8) gagal/rate limited.")
    return None


# ============================================================



# ============================================================

# ============================================================
# ============================================================
#  IMAGE-TO-VIDEO: Local FFmpeg (100% GRATIS)
# ============================================================

import subprocess

async def animate_local_ffmpeg(image_path: str, output_path: str, duration: int = 6) -> str:
    """
    100% gratis: Menganimasikan gambar statis dengan efek zoom (Ken Burns) via FFmpeg lokal.
    Durasi default 6 detik (cukup untuk dicut di video_builder.py).
    """
    loop = asyncio.get_running_loop()
    
    if not image_path or not os.path.exists(image_path):
        logger.warning(" [I2V Local] Gambar sumber tidak ditemukan.")
        return None
        
    logger.info(" [I2V Local] Membuat animasi zoom-in lokal (FFmpeg)...")
    # Efek Ken Burns presisi tinggi vertikal
    filter_complex = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,zoompan=z='min(zoom+0.0015,1.5)':d=25*{duration}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=720x1280,framerate=25"
    
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", image_path,
        "-vf", filter_complex,
        "-c:v", "libx264", "-t", str(duration), "-pix_fmt", "yuv420p",
        output_path
    ]
    
    try:
        process = await loop.run_in_executor(
            None, lambda: subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        )
        if process.returncode == 0 and os.path.exists(output_path):
            logger.info(f" [I2V Local] Berhasil membuat animasi Ken Burns: {output_path}")
            return output_path
        else:
            err = process.stderr.decode('utf-8') if process.stderr else "Unknown error"
            logger.warning(f" [I2V Local] FFmpeg gagal: {err[:200]}")
    except Exception as e:
        logger.warning(f" [I2V Local] Error jalankan FFmpeg: {e}")
        
    return None


# ============================================================
#  ORCHESTRATOR UTAMA — 100% Free Local Strategy
# ============================================================

async def run_ai_video_workflow(image_prompts: list, target_count: int, output_dir: str = "assets/fallback") -> list:
    """
    Pipeline AI Video 100% Gratis:
    === T2I (Gambar): ===
      Tier 1: Pollinations.ai (GRATIS 100%, tanpa key)
      Tier 2: Hugging Face Inference API (gratis dengan token)
      
    === I2V (Animasi): ===
      Lokal FFmpeg Ken Burns Effect (100% GRATIS)
    """
    os.makedirs(output_dir, exist_ok=True)

    generated_videos = []
    prompts_to_process = image_prompts[:target_count]
    default_prompt = "beautiful landscape, highly detailed, vivid colors, 4k"
    while len(prompts_to_process) < target_count:
        prompts_to_process.append(default_prompt)

    for i, raw_prompt in enumerate(prompts_to_process):
        logger.info(f" ===== Scene {i+1}/{target_count} =====")
        seed = int(time.time()) % 99999 + i * 100

        # ── STEP 1: Text-to-Image (Pollinations -> HF) ──
        logger.info(f" [Step 1] T2I untuk Scene {i+1}...")
        local_path = None

        # Tier 1: Pollinations (gratis)
        local_path = await generate_image_pollinations(raw_prompt, width=720, height=1280, seed=seed)
        if local_path:
            logger.info(f" Scene {i+1}: Gambar dari Pollinations.ai ✓")
        else:
            # Tier 2: HuggingFace (gratis dengan token)
            logger.info(f" Scene {i+1}: Pollinations gagal, coba HuggingFace...")
            local_path = await generate_image_huggingface(raw_prompt, width=720, height=1280)
            if local_path:
                logger.info(f" Scene {i+1}: Gambar dari HuggingFace ✓")

        if not local_path or not os.path.exists(local_path):
            logger.warning(f" Scene {i+1}: Semua T2I gagal. Scene dilewati.")
            continue

        # ── STEP 2: Image-to-Video (FFmpeg Lokal) ──
        logger.info(f" [Step 2] I2V Scene {i+1} via FFmpeg Lokal...")
        output_filename = os.path.join(output_dir, f"scene_{i+1}_ffmpeg_{int(time.time())}.mp4")

        video_path = await animate_local_ffmpeg(local_path, output_filename, duration=6)

        if video_path and os.path.exists(video_path):
            logger.info(f" Scene {i+1}: Animasi berhasil → {video_path}")
            generated_videos.append(video_path)
        else:
            logger.warning(f" Scene {i+1}: FFmpeg I2V gagal. Scene dilewati.")

    logger.info(f" Pipeline selesai: {len(generated_videos)}/{target_count} scene berhasil.")
    return generated_videos
