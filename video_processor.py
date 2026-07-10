import os
import logging
from moviepy import VideoFileClip, CompositeVideoClip, vfx
from overlay import apply_text_watermark

logger = logging.getLogger("bot")

def process_hunter_video(raw_filepath: str, uploader: str, output_path: str, add_watermark: bool = True):
    """
    Memproses video mentah hasil unduhan Hunter untuk membuatnya aman monetisasi (Fair Use).
    1. Memotong video jika terlalu panjang.
    2. Menambahkan watermark/kredit kreator asli.
    3. Menerapkan filter visual ringan.
    """
    logger.info(f" 🎬 Memproses video mentah dari @{uploader}...")
    
    try:
        clip = VideoFileClip(raw_filepath)
        
        # SOP: Jika durasi sangat pendek (< 15 detik), lakukan looping agar narasi cukup panjang
        if clip.duration > 0 and clip.duration < 15:
            from moviepy import concatenate_videoclips
            logger.info(f" Durasi video sangat pendek ({clip.duration}s). Melakukan looping...")
            # Hitung butuh berapa loop untuk mencapai setidaknya ~20 detik
            loops_needed = int(20 / clip.duration) + 1
            clip = concatenate_videoclips([clip] * loops_needed)
            logger.info(f" Video di-loop {loops_needed}x. Durasi baru: {clip.duration}s")
            
        # Batasi durasi maksimal 55 detik agar aman untuk Shorts
        if clip.duration > 55:
            logger.info(" Memotong video menjadi 55 detik...")
            clip = clip.subclipped(0, 55)
            
        # Terapkan sedikit perubahan kecepatan (1.05x) untuk menghindari deteksi re-upload mentah
        clip = clip.with_effects([vfx.MultiplySpeed(1.05)])
        
        if add_watermark and uploader:
            # Gunakan fungsi dari overlay.py yang sudah teruji aman (tanpa ImageMagick)
            clip = apply_text_watermark(clip, f"Source: @{uploader}")
            
        final_clip = clip
        
        # Kita tidak langsung merender di sini karena audio (voiceover) akan di-inject oleh video_builder.py
        # Skrip ini bisa dikembangkan lebih jauh untuk Auto-Cutting Matematis (Sebab-Akibat).
        
        logger.info(f" ✅ Video proses siap untuk di-dubbing AI.")
        
        # Tulis hasil sementara tanpa audio (atau simpan saja file sementara)
        final_clip.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            preset="ultrafast",
            audio=False, # Audio asli dibuang, akan diganti TTS
            logger=None
        )
        
        clip.close()
        final_clip.close()
        return True
        
    except Exception as e:
        logger.error(f" ❌ Gagal memproses video Hunter: {e}")
        return False
