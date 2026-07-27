import os
import time
import json
import logging
import asyncio
import datetime
import requests
import base64

logger = logging.getLogger("ai_video_engine")

def get_daily_video_provider() -> str:
    """Merotasi penyedia Image-to-Video secara harian berdasarkan tanggal."""
    providers = ["kling", "fal"]
    day_of_year = datetime.datetime.now().timetuple().tm_yday
    selected = providers[day_of_year % len(providers)]
    logger.info(f" Penyedia AI Video hari ini (Day {day_of_year}): {selected.upper()}")
    return selected

def _get_fal_key() -> tuple:
    """Mencari FAL API key yang aktif (belum habis). Kembalikan (index, key)."""
    for attempt in range(1, 9):
        key = os.getenv(f"FAL_API_KEY_{attempt}")
        if key:
            return (attempt, key)
    return (None, None)

def _get_kling_key() -> tuple:
    """Mencari KLING API key yang aktif. Kembalikan (index, key)."""
    for attempt in range(1, 9):
        key = os.getenv(f"KLING_API_KEY_{attempt}")
        if key:
            return (attempt, key)
    return (None, None)

# ============================================================
#  TEXT-TO-IMAGE: Fal.ai (flux/schnell - lebih hemat kredit)
# ============================================================

async def generate_image_fal(prompt: str, width: int = 576, height: int = 1024) -> str:
    """
    Menghasilkan gambar via Fal.ai.
    - Endpoint: fal-ai/flux/schnell (lebih hemat vs flux/dev)
    - Ukuran default 576x1024 (hemat kredit, masih portrait)
    - Return: URL gambar publik atau None jika gagal
    """
    loop = asyncio.get_running_loop()
    # flux/schnell jauh lebih hemat kredit dibanding flux/dev
    url = "https://fal.run/fal-ai/flux/schnell"

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
            "image_size": "portrait_9_16",   # 576x1024 - portrait untuk Shorts
            "num_inference_steps": 4,          # schnell cukup 4 steps
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
                        logger.info(f" [T2I] Gambar berhasil dari Fal Key {attempt}: {image_url[:60]}...")
                        return image_url
            elif response.status_code in [401, 403]:
                logger.warning(f" Fal.ai Key {attempt} tidak valid/diblokir. Coba key berikutnya.")
                continue
            elif response.status_code == 429:
                logger.warning(f" Fal.ai Key {attempt} rate limited. Coba key berikutnya.")
                continue
            else:
                body = response.text[:200]
                if "Exhausted balance" in body or "locked" in body:
                    logger.warning(f" Fal.ai Key {attempt} kehabisan kredit.")
                else:
                    logger.warning(f" Fal.ai Key {attempt} error {response.status_code}: {body}")
                continue
        except Exception as e:
            logger.warning(f" Error Fal T2I Key {attempt}: {e}")
            continue

    logger.error(" Semua FAL key (1-8) gagal/habis kredit untuk T2I.")
    return None


# ============================================================
#  IMAGE-TO-VIDEO: Kling AI (API resmi)
# ============================================================

async def animate_kling(image_url: str, prompt: str, output_path: str) -> str:
    """
    Animasi gambar ke video via Kling AI (I2V) - IMPLEMENTASI NYATA.
    Kling free tier: ~66 kredit, 1 video = ~5-10 kredit.
    Endpoint: https://api.klingai.com/v1/videos/image2video
    Dokumen: https://docs.qingque.cn/d/home/eZQCKaMlDPpAbJXhpZkBAfpPd
    """
    loop = asyncio.get_running_loop()

    for attempt in range(1, 9):
        api_key = os.getenv(f"KLING_API_KEY_{attempt}")
        if not api_key:
            continue

        logger.info(f" [I2V Kling] Mencoba Key {attempt}...")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Step 1: Submit job
        submit_url = "https://api.klingai.com/v1/videos/image2video"
        payload = {
            "model_name": "kling-v1",
            "image": image_url,
            "prompt": prompt,
            "negative_prompt": "ugly, distorted, blurry, low quality",
            "cfg_scale": 0.5,
            "mode": "std",       # std lebih hemat kredit vs pro
            "duration": "5"      # 5 detik per klip
        }

        try:
            submit_resp = await loop.run_in_executor(
                None, lambda h=headers, p=payload: requests.post(submit_url, json=p, headers=h, timeout=30)
            )

            if submit_resp.status_code not in [200, 201]:
                body = submit_resp.text[:200]
                if "insufficient" in body.lower() or "balance" in body.lower():
                    logger.warning(f" Kling Key {attempt} kredit habis. Coba key berikutnya.")
                    continue
                logger.warning(f" Kling Key {attempt} submit error {submit_resp.status_code}: {body}")
                continue

            submit_json = submit_resp.json()
            task_id = (submit_json.get("data", {}) or {}).get("task_id")
            if not task_id:
                logger.warning(f" Kling Key {attempt}: task_id tidak ditemukan di response.")
                continue

            logger.info(f" Kling task_id={task_id} submitted. Polling status...")

            # Step 2: Poll sampai selesai (max 3 menit)
            poll_url = f"https://api.klingai.com/v1/videos/image2video/{task_id}"
            for poll_attempt in range(36):   # 36 × 5s = 3 menit max
                await asyncio.sleep(5)
                try:
                    poll_resp = await loop.run_in_executor(
                        None, lambda h=headers: requests.get(poll_url, headers=h, timeout=20)
                    )
                    if poll_resp.status_code != 200:
                        logger.warning(f" Kling poll error {poll_resp.status_code}")
                        continue

                    poll_json = poll_resp.json()
                    task_status = (poll_json.get("data", {}) or {}).get("task_status", "")
                    logger.info(f" Kling poll {poll_attempt+1}: status={task_status}")

                    if task_status == "succeed":
                        works = (poll_json.get("data", {}) or {}).get("task_result", {}).get("videos", [])
                        if works:
                            video_url = works[0].get("url")
                            if video_url:
                                logger.info(f" Kling video siap diunduh: {video_url[:60]}...")
                                result = await _download_and_save_video(video_url, output_path)
                                return result
                    elif task_status in ["failed", "error"]:
                        logger.warning(f" Kling task gagal pada Key {attempt}.")
                        break
                except Exception as poll_err:
                    logger.warning(f" Error polling Kling: {poll_err}")

            logger.warning(f" Kling Key {attempt} timeout/gagal. Coba key berikutnya.")

        except Exception as e:
            logger.warning(f" Error Kling Key {attempt}: {e}")
            continue

    logger.error(" Semua KLING key (1-8) gagal/habis kredit untuk I2V.")
    return None


# ============================================================
#  IMAGE-TO-VIDEO: Fal.ai (minimax/video-01 atau ltx-video)
# ============================================================

async def animate_fal(image_url: str, prompt: str, output_path: str) -> str:
    """
    Animasi gambar ke video via Fal.ai I2V - IMPLEMENTASI NYATA.
    Model: minimax/video-01 (5 detik, kualitas tinggi, port 9:16)
    Dokumen: https://fal.ai/models/fal-ai/minimax/video-01
    """
    loop = asyncio.get_running_loop()

    for attempt in range(1, 9):
        api_key = os.getenv(f"FAL_API_KEY_{attempt}")
        if not api_key:
            continue

        logger.info(f" [I2V Fal] Mencoba Key {attempt} (minimax/video-01)...")

        headers = {
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json"
        }

        # Step 1: Submit ke fal queue
        submit_url = "https://queue.fal.run/fal-ai/minimax/video-01"
        payload = {
            "prompt": prompt,
            "image_url": image_url,
        }

        try:
            submit_resp = await loop.run_in_executor(
                None, lambda h=headers, p=payload: requests.post(submit_url, json=p, headers=h, timeout=30)
            )

            if submit_resp.status_code not in [200, 201]:
                body = submit_resp.text[:200]
                if "Exhausted balance" in body or "locked" in body:
                    logger.warning(f" Fal I2V Key {attempt} kredit habis. Coba key berikutnya.")
                    continue
                logger.warning(f" Fal I2V Key {attempt} submit error {submit_resp.status_code}: {body}")
                continue

            submit_json = submit_resp.json()
            request_id = submit_json.get("request_id")
            status_url = submit_json.get("status_url")
            response_url = submit_json.get("response_url")

            if not request_id:
                logger.warning(f" Fal I2V Key {attempt}: request_id tidak ditemukan.")
                continue

            logger.info(f" Fal I2V request_id={request_id}. Polling...")

            # Step 2: Poll status
            for poll_attempt in range(36):  # max 3 menit
                await asyncio.sleep(5)
                try:
                    if status_url:
                        poll_resp = await loop.run_in_executor(
                            None, lambda h=headers: requests.get(status_url, headers=h, timeout=20)
                        )
                    else:
                        poll_resp = await loop.run_in_executor(
                            None, lambda h=headers: requests.get(
                                f"https://queue.fal.run/fal-ai/minimax/video-01/requests/{request_id}/status",
                                headers=h, timeout=20
                            )
                        )

                    if poll_resp.status_code != 200:
                        continue

                    poll_json = poll_resp.json()
                    status = poll_json.get("status", "")
                    logger.info(f" Fal I2V poll {poll_attempt+1}: status={status}")

                    if status == "COMPLETED":
                        # Ambil hasil
                        if response_url:
                            result_resp = await loop.run_in_executor(
                                None, lambda h=headers: requests.get(response_url, headers=h, timeout=20)
                            )
                        else:
                            result_resp = await loop.run_in_executor(
                                None, lambda h=headers: requests.get(
                                    f"https://queue.fal.run/fal-ai/minimax/video-01/requests/{request_id}",
                                    headers=h, timeout=20
                                )
                            )
                        if result_resp.status_code == 200:
                            result_json = result_resp.json()
                            video_url = (result_json.get("video") or {}).get("url")
                            if video_url:
                                logger.info(f" Fal I2V video siap: {video_url[:60]}...")
                                result = await _download_and_save_video(video_url, output_path)
                                return result
                        break
                    elif status in ["FAILED", "ERROR"]:
                        logger.warning(f" Fal I2V task gagal pada Key {attempt}.")
                        break
                except Exception as pe:
                    logger.warning(f" Error polling Fal I2V: {pe}")

            logger.warning(f" Fal I2V Key {attempt} timeout/gagal. Coba key berikutnya.")

        except Exception as e:
            logger.warning(f" Error Fal I2V Key {attempt}: {e}")
            continue

    logger.error(" Semua FAL key (1-8) gagal/habis kredit untuk I2V.")
    return None


# ============================================================
#  DOWNLOAD HELPER
# ============================================================

async def _download_and_save_video(url: str, output_path: str):
    """Fungsi utilitas untuk mengunduh video hasil generate."""
    loop = asyncio.get_running_loop()
    try:
        def download():
            r = requests.get(url, stream=True, timeout=120)
            if r.status_code == 200:
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
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


# ============================================================
#  ORCHESTRATOR UTAMA
# ============================================================

async def run_ai_video_workflow(image_prompts: list, target_count: int, output_dir: str = "assets/fallback") -> list:
    """
    Pipeline lengkap AI Video Niche (WonderTales Studio):
    1. Tiap prompt -> generate gambar via Fal T2I (flux/schnell, hemat kredit)
    2. Tiap gambar -> animasikan via Kling atau Fal I2V (video pendek 5 detik)
    3. Tiap scene menggunakan style prefix yang konsisten agar hasil sambung/nyambung
    4. Kembalikan list path video .mp4 yang sudah diunduh
    
    Catatan kredit:
    - flux/schnell T2I: ~1-2 kredit/gambar
    - Kling std I2V  : ~5 kredit/video
    - Fal minimax I2V: ~5-8 kredit/video
    - Free tier 66 kredit -> cukup untuk ~4 scene per run (4 T2I + 4 I2V)
    """
    os.makedirs(output_dir, exist_ok=True)
    provider = get_daily_video_provider()

    generated_videos = []

    # Ambil hanya sesuai target (sudah dibatasi 4 di video_builder)
    prompts_to_process = image_prompts[:target_count]

    # Isi kekurangan prompt jika tidak cukup
    default_prompt = "cute animated character in a colorful magical forest, 3D Pixar style, vibrant colors, soft lighting"
    while len(prompts_to_process) < target_count:
        prompts_to_process.append(default_prompt)

    for i, raw_prompt in enumerate(prompts_to_process):
        logger.info(f" ===== Scene {i+1}/{target_count} =====")

        # === STEP 1: Text-to-Image ===
        logger.info(f" [Step 1] Menghasilkan gambar AI ({i+1}/{target_count})")
        image_url = await generate_image_fal(prompt=raw_prompt, width=576, height=1024)

        if not image_url:
            logger.warning(f" Scene {i+1}: T2I gagal, skip scene ini.")
            continue

        # === STEP 2: Image-to-Video ===
        logger.info(f" [Step 2] Menganimasikan gambar via {provider.upper()}")
        output_filename = os.path.join(output_dir, f"scene_{i+1}_{provider}_{int(time.time())}.mp4")

        # Prompt animasi: konsisten per scene agar klip sambung
        # Pakai gerakan kamera yang halus & cocok untuk konten anak-anak
        anim_prompts = [
            "gentle camera zoom in, warm sunlight, soft animation, colorful and vibrant",
            "slow dolly shot, magical sparkles appear, dreamy atmosphere, Pixar style",
            "smooth pan right, friendly character smiling, lush colorful environment",
            "gentle zoom out revealing landscape, cheerful mood, pastel colors",
        ]
        anim_prompt = anim_prompts[i % len(anim_prompts)]

        video_path = None
        if provider == "kling":
            video_path = await animate_kling(image_url, anim_prompt, output_filename)
            # Jika Kling gagal, coba Fal sebagai fallback
            if not video_path:
                logger.info(f" Scene {i+1}: Kling gagal, mencoba Fal I2V sebagai fallback...")
                video_path = await animate_fal(image_url, anim_prompt, output_filename)
        elif provider == "fal":
            video_path = await animate_fal(image_url, anim_prompt, output_filename)
            # Jika Fal gagal, coba Kling sebagai fallback
            if not video_path:
                logger.info(f" Scene {i+1}: Fal I2V gagal, mencoba Kling sebagai fallback...")
                video_path = await animate_kling(image_url, anim_prompt, output_filename)

        if video_path and os.path.exists(video_path):
            logger.info(f" Scene {i+1}: Video animasi berhasil -> {video_path}")
            generated_videos.append(video_path)
        else:
            logger.warning(f" Scene {i+1}: Semua provider gagal. Scene ini dilewati.")

    logger.info(f" Pipeline selesai: {len(generated_videos)}/{target_count} scene berhasil dianimasi.")
    return generated_videos
