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


def get_daily_video_provider() -> str:
    """Merotasi penyedia Image-to-Video secara harian berdasarkan tanggal."""
    providers = ["kling", "fal"]
    day_of_year = datetime.datetime.now().timetuple().tm_yday
    selected = providers[day_of_year % len(providers)]
    logger.info(f" Penyedia AI Video hari ini (Day {day_of_year}): {selected.upper()}")
    return selected


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
    Generate gambar via Hugging Face Inference API — gratis dengan token.
    Model: black-forest-labs/FLUX.1-schnell
    Secret yang diperlukan: HF_API_KEY
    """
    loop = asyncio.get_running_loop()

    hf_key = os.getenv("HF_API_KEY")
    if not hf_key:
        logger.warning(" [T2I HuggingFace] HF_API_KEY tidak dikonfigurasi. Skip.")
        return None

    url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
    headers = {
        "Authorization": f"Bearer {hf_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": prompt[:500],
        "parameters": {
            "width": width,
            "height": height,
            "num_inference_steps": 4,
            "guidance_scale": 0.0
        }
    }

    try:
        logger.info(f" [T2I HuggingFace] Requesting FLUX.1-schnell...")
        response = await loop.run_in_executor(
            None, lambda: requests.post(url, json=payload, headers=headers, timeout=90)
        )
        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            if "image" in content_type:
                img_path = f"/tmp/hf_{int(time.time())}.jpg"
                with open(img_path, "wb") as f:
                    f.write(response.content)
                file_size = os.path.getsize(img_path)
                if file_size > 5000:
                    logger.info(f" [T2I HuggingFace] Berhasil! {file_size // 1024}KB -> {img_path}")
                    return img_path
        elif response.status_code == 503:
            logger.warning(" [T2I HuggingFace] Model sedang loading. Coba lagi setelah 10 detik...")
            await asyncio.sleep(10)
            # Retry sekali
            response = await loop.run_in_executor(
                None, lambda: requests.post(url, json=payload, headers=headers, timeout=90)
            )
            if response.status_code == 200 and "image" in response.headers.get("Content-Type", ""):
                img_path = f"/tmp/hf_retry_{int(time.time())}.jpg"
                with open(img_path, "wb") as f:
                    f.write(response.content)
                if os.path.getsize(img_path) > 5000:
                    logger.info(f" [T2I HuggingFace] Retry berhasil -> {img_path}")
                    return img_path
        else:
            logger.warning(f" [T2I HuggingFace] Error {response.status_code}: {response.text[:150]}")
    except Exception as e:
        logger.warning(f" [T2I HuggingFace] Error: {e}")

    return None


# ============================================================
#  TEXT-TO-IMAGE: Tier 3 — Fal.ai flux/schnell (last resort)
# ============================================================

async def generate_image_fal(prompt: str, width: int = 576, height: int = 1024) -> str:
    """
    Generate gambar via Fal.ai (flux/schnell) — last resort, berbayar.
    Hanya dipanggil jika Pollinations & HuggingFace keduanya gagal.
    """
    loop = asyncio.get_running_loop()
    url = "https://fal.run/fal-ai/flux/schnell"

    for attempt in range(1, 9):
        api_key = os.getenv(f"FAL_API_KEY_{attempt}")
        if not api_key:
            continue

        headers = {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}
        payload = {
            "prompt": prompt,
            "image_size": "portrait_9_16",
            "num_inference_steps": 4,
            "num_images": 1,
            "enable_safety_checker": True
        }

        try:
            response = await loop.run_in_executor(
                None, lambda h=headers, p=payload: requests.post(url, json=p, headers=h, timeout=60)
            )
            if response.status_code == 200:
                res_json = response.json()
                images = res_json.get("images", [])
                if images:
                    image_url = images[0].get("url")
                    if image_url:
                        logger.info(f" [T2I Fal] Berhasil via Key {attempt}: {image_url[:60]}...")
                        return image_url  # URL eksternal (OK untuk Kling/Fal I2V)
            else:
                body = response.text[:200]
                if "Exhausted balance" in body or "locked" in body:
                    logger.warning(f" Fal Key {attempt} kredit habis.")
                else:
                    logger.warning(f" Fal Key {attempt} error {response.status_code}: {body}")
        except Exception as e:
            logger.warning(f" Fal Key {attempt} exception: {e}")

    logger.error(" [T2I Fal] Semua key habis kredit.")
    return None


# ============================================================
#  HELPER: Upload lokal image ke Pollinations (get public URL)
# ============================================================

async def _get_public_image_url(local_path: str, prompt_hint: str, seed: int) -> str:
    """
    Untuk I2V API (Kling/Fal), kita butuh URL publik.
    Jika gambar dari Pollinations/HF disimpan lokal,
    kita kembalikan URL Pollinations aslinya lewat re-request dengan seed yang sama.
    Atau, upload ke tmpfiles.org / file.io sebagai alternatif sederhana.
    """
    # Coba upload ke file.io (gratis, 14 hari)
    loop = asyncio.get_running_loop()
    try:
        def upload():
            with open(local_path, "rb") as f:
                resp = requests.post(
                    "https://file.io/?expires=1d",
                    files={"file": f},
                    timeout=30
                )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data.get("link")
            return None

        url = await loop.run_in_executor(None, upload)
        if url:
            logger.info(f" Gambar terupload ke file.io: {url}")
            return url
    except Exception as e:
        logger.warning(f" Gagal upload ke file.io: {e}")

    # Fallback: gunakan URL Pollinations langsung
    clean_prompt = re.sub(r'[^\w\s,.\-!?()]', '', prompt_hint)[:300]
    encoded = urllib.parse.quote(clean_prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=576&height=1024&seed={seed}&model=flux&nologo=true"


# ============================================================
#  IMAGE-TO-VIDEO: Kling AI (API resmi)
# ============================================================

async def animate_kling(image_url: str, prompt: str, output_path: str) -> str:
    """Animasi gambar ke video 5 detik via Kling AI I2V."""
    loop = asyncio.get_running_loop()

    for attempt in range(1, 9):
        api_key = os.getenv(f"KLING_API_KEY_{attempt}")
        if not api_key:
            continue

        logger.info(f" [I2V Kling] Mencoba Key {attempt}...")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model_name": "kling-v1",
            "image": image_url,
            "prompt": prompt,
            "negative_prompt": "ugly, distorted, blurry, low quality, scary, violent",
            "cfg_scale": 0.5,
            "mode": "std",
            "duration": "5"
        }

        try:
            submit_resp = await loop.run_in_executor(
                None, lambda h=headers, p=payload: requests.post(
                    "https://api.klingai.com/v1/videos/image2video",
                    json=p, headers=h, timeout=30
                )
            )

            if submit_resp.status_code not in [200, 201]:
                body = submit_resp.text[:200]
                if any(kw in body.lower() for kw in ["insufficient", "balance", "credit", "quota"]):
                    logger.warning(f" Kling Key {attempt} kredit habis. Coba key berikutnya.")
                    continue
                logger.warning(f" Kling Key {attempt} submit error {submit_resp.status_code}: {body}")
                continue

            task_id = submit_resp.json().get("data", {}).get("task_id")
            if not task_id:
                logger.warning(f" Kling Key {attempt}: task_id tidak ditemukan.")
                continue

            logger.info(f" Kling task_id={task_id}. Polling...")
            poll_url = f"https://api.klingai.com/v1/videos/image2video/{task_id}"

            for _ in range(36):  # max 3 menit
                await asyncio.sleep(5)
                poll_resp = await loop.run_in_executor(
                    None, lambda h=headers: requests.get(poll_url, headers=h, timeout=20)
                )
                if poll_resp.status_code != 200:
                    continue

                poll_data = poll_resp.json().get("data", {})
                status = poll_data.get("task_status", "")
                logger.info(f" Kling status: {status}")

                if status == "succeed":
                    videos = poll_data.get("task_result", {}).get("videos", [])
                    if videos:
                        video_url = videos[0].get("url")
                        if video_url:
                            return await _download_and_save_video(video_url, output_path)
                    break
                elif status in ["failed", "error"]:
                    logger.warning(f" Kling task gagal (Key {attempt}).")
                    break

        except Exception as e:
            logger.warning(f" Kling Key {attempt} exception: {e}")

    logger.error(" Semua KLING key gagal untuk I2V.")
    return None


# ============================================================
#  IMAGE-TO-VIDEO: Fal.ai (minimax/video-01)
# ============================================================

async def animate_fal(image_url: str, prompt: str, output_path: str) -> str:
    """Animasi gambar ke video via Fal.ai minimax/video-01."""
    loop = asyncio.get_running_loop()

    for attempt in range(1, 9):
        api_key = os.getenv(f"FAL_API_KEY_{attempt}")
        if not api_key:
            continue

        logger.info(f" [I2V Fal] Mencoba Key {attempt} (minimax/video-01)...")
        headers = {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}
        payload = {"prompt": prompt, "image_url": image_url}

        try:
            submit_resp = await loop.run_in_executor(
                None, lambda h=headers, p=payload: requests.post(
                    "https://queue.fal.run/fal-ai/minimax/video-01",
                    json=p, headers=h, timeout=30
                )
            )

            if submit_resp.status_code not in [200, 201]:
                body = submit_resp.text[:200]
                if "Exhausted balance" in body or "locked" in body:
                    logger.warning(f" Fal I2V Key {attempt} kredit habis.")
                    continue
                logger.warning(f" Fal I2V Key {attempt} error {submit_resp.status_code}: {body}")
                continue

            submit_json = submit_resp.json()
            request_id = submit_json.get("request_id")
            status_url = submit_json.get("status_url")
            response_url = submit_json.get("response_url")
            if not request_id:
                continue

            logger.info(f" Fal I2V request_id={request_id}. Polling...")

            for _ in range(36):
                await asyncio.sleep(5)
                poll_url = status_url or f"https://queue.fal.run/fal-ai/minimax/video-01/requests/{request_id}/status"
                poll_resp = await loop.run_in_executor(
                    None, lambda h=headers: requests.get(poll_url, headers=h, timeout=20)
                )
                if poll_resp.status_code != 200:
                    continue

                status = poll_resp.json().get("status", "")
                logger.info(f" Fal I2V status: {status}")

                if status == "COMPLETED":
                    res_url = response_url or f"https://queue.fal.run/fal-ai/minimax/video-01/requests/{request_id}"
                    result_resp = await loop.run_in_executor(
                        None, lambda h=headers: requests.get(res_url, headers=h, timeout=20)
                    )
                    if result_resp.status_code == 200:
                        video_url = (result_resp.json().get("video") or {}).get("url")
                        if video_url:
                            return await _download_and_save_video(video_url, output_path)
                    break
                elif status in ["FAILED", "ERROR"]:
                    logger.warning(f" Fal I2V task gagal (Key {attempt}).")
                    break

        except Exception as e:
            logger.warning(f" Fal I2V Key {attempt} exception: {e}")

    logger.error(" Semua FAL key gagal untuk I2V.")
    return None


# ============================================================
#  DOWNLOAD HELPER
# ============================================================

async def _download_and_save_video(url: str, output_path: str) -> str:
    loop = asyncio.get_running_loop()
    try:
        def download():
            r = requests.get(url, stream=True, timeout=120)
            if r.status_code == 200:
                with open(output_path, "wb") as f:
                    for chunk in r.iter_content(1024 * 1024):
                        if chunk:
                            f.write(chunk)
                return True
            return False

        if await loop.run_in_executor(None, download):
            logger.info(f" Video diunduh ke {output_path}")
            return output_path
    except Exception as e:
        logger.error(f" Error download video: {e}")
    return None


# ============================================================
#  ORCHESTRATOR UTAMA — Hybrid Strategy
# ============================================================

async def run_ai_video_workflow(image_prompts: list, target_count: int, output_dir: str = "assets/fallback") -> list:
    """
    Pipeline Hybrid AI Video:
    === T2I (Gambar): ===
      Tier 1: Pollinations.ai (GRATIS 100%, tanpa key)
      Tier 2: Hugging Face Inference API (gratis dengan token)
      Tier 3: Fal.ai flux/schnell (last resort, berbayar)

    === I2V (Animasi): ===
      Primary : Kling AI / Fal.ai (rotasi harian)
      Fallback: Provider sebaliknya jika primary gagal

    === Continuity: ===
      - Setiap scene memakai anim_prompt berbeda yang berurutan
      - Gambar disimpan lokal → upload ke file.io → URL publik untuk I2V API
    """
    os.makedirs(output_dir, exist_ok=True)
    provider = get_daily_video_provider()

    generated_videos = []
    prompts_to_process = image_prompts[:target_count]
    default_prompt = "cute animated character in a colorful magical forest, 3D Pixar style, vibrant, wholesome, soft lighting"
    while len(prompts_to_process) < target_count:
        prompts_to_process.append(default_prompt)

    # Prompt animasi berurutan → koneksi antar scene
    anim_prompts = [
        "gentle camera zoom in, warm golden sunlight, soft smooth animation, colorful and vibrant, Pixar style",
        "slow dolly forward, magical sparkles appear, dreamy floating atmosphere, cheerful mood",
        "smooth pan right revealing new area, friendly character smiling, lush colorful environment",
        "gentle zoom out revealing full landscape, joyful moment, pastel rainbow colors, happy ending",
        "soft push in, warm cozy light, character looking at camera, heartwarming expression",
    ]

    for i, raw_prompt in enumerate(prompts_to_process):
        logger.info(f" ===== Scene {i+1}/{target_count} =====")
        seed = int(time.time()) % 99999 + i * 100

        # ── STEP 1: Text-to-Image (Waterfall Free → Berbayar) ──
        logger.info(f" [Step 1] T2I untuk Scene {i+1}...")
        local_path = None
        image_url = None

        # Tier 1: Pollinations (gratis)
        local_path = await generate_image_pollinations(raw_prompt, width=576, height=1024, seed=seed)
        if local_path:
            logger.info(f" Scene {i+1}: Gambar dari Pollinations.ai ✓")
        else:
            # Tier 2: HuggingFace (gratis dengan token)
            logger.info(f" Scene {i+1}: Pollinations gagal, coba HuggingFace...")
            local_path = await generate_image_huggingface(raw_prompt, width=576, height=1024)
            if local_path:
                logger.info(f" Scene {i+1}: Gambar dari HuggingFace ✓")

        if local_path and os.path.exists(local_path):
            # Upload ke file.io untuk dapat URL publik (dibutuhkan oleh Kling/Fal I2V)
            image_url = await _get_public_image_url(local_path, raw_prompt, seed)
        else:
            # Tier 3: Fal.ai (last resort, berbayar)
            logger.info(f" Scene {i+1}: Free tier habis, coba Fal.ai (berbayar)...")
            image_url = await generate_image_fal(raw_prompt, width=576, height=1024)

        if not image_url:
            logger.warning(f" Scene {i+1}: Semua T2I gagal. Scene dilewati.")
            continue

        # ── STEP 2: Image-to-Video ──
        logger.info(f" [Step 2] I2V Scene {i+1} via {provider.upper()}...")
        output_filename = os.path.join(output_dir, f"scene_{i+1}_{provider}_{int(time.time())}.mp4")
        anim_prompt = anim_prompts[i % len(anim_prompts)]

        video_path = None
        if provider == "kling":
            video_path = await animate_kling(image_url, anim_prompt, output_filename)
            if not video_path:
                logger.info(f" Scene {i+1}: Kling gagal → fallback Fal I2V...")
                video_path = await animate_fal(image_url, anim_prompt, output_filename)
        else:
            video_path = await animate_fal(image_url, anim_prompt, output_filename)
            if not video_path:
                logger.info(f" Scene {i+1}: Fal I2V gagal → fallback Kling...")
                video_path = await animate_kling(image_url, anim_prompt, output_filename)

        if video_path and os.path.exists(video_path):
            logger.info(f" Scene {i+1}: Animasi berhasil → {video_path}")
            generated_videos.append(video_path)
        else:
            logger.warning(f" Scene {i+1}: I2V semua provider gagal. Scene dilewati.")

    logger.info(f" Pipeline selesai: {len(generated_videos)}/{target_count} scene berhasil.")
    return generated_videos
