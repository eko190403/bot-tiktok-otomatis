import os
import logging
from moviepy import VideoFileClip, TextClip, CompositeVideoClip, vfx

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
        
        # Batasi durasi maksimal 55 detik agar aman untuk Shorts
        if clip.duration > 55:
            logger.info(" Memotong video menjadi 55 detik...")
            clip = clip.subclip(0, 55)
            
        # Terapkan sedikit perubahan kecepatan (1.05x) untuk menghindari deteksi re-upload mentah
        clip = clip.fx(vfx.speedx, 1.05)
        
        # Susun daftar elemen visual
        video_elements = [clip]
        
        if add_watermark and uploader:
            # Membuat teks kredit sumber
            txt_clip = TextClip(
                f"Source: @{uploader}",
                fontsize=30,
                color='white',
                font='Arial-Bold',
                bg_color='black'
            )
            txt_clip = txt_clip.set_opacity(0.6).set_position(("center", "bottom")).set_duration(clip.duration)
            video_elements.append(txt_clip)
            
        # Gabungkan elemen
        final_clip = CompositeVideoClip(video_elements)
        
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
