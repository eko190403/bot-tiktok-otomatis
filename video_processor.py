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
            
        # Batasi durasi maksimal 70 detik agar aman untuk Shorts
        if clip.duration > 70:
            logger.info(" Memotong video menjadi 70 detik...")
            clip = clip.subclipped(0, 70)
            
        # Terapkan sedikit perubahan kecepatan (1.05x) untuk menghindari deteksi re-upload mentah (KECUALI KOMEDI)
        # clip = clip.with_effects([vfx.MultiplySpeed(1.05)]) # Dinonaktifkan agar gerakan dan audio komedi tetap natural
        
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
            audio=True, # Pertahankan audio asli (Dulu False, sekarang True agar terdengar di Komedi)
            logger=None
        )
        
        clip.close()
        final_clip.close()
        return True
        
    except Exception as e:
        logger.error(f" ❌ Gagal memproses video Hunter: {e}")
        return False

def process_ffmpeg_reposter(input_path: str, watermark_text: str, output_path: str) -> bool:
    """
    Menggunakan FFmpeg mentah untuk menambahkan watermark transparan dan mengubah pitch audio 2%.
    Ini 100x lebih cepat daripada moviepy dan efektif mengecoh bot copyright.
    """
    import subprocess
    import os
    
    # Filter Audio: asetrate=44100*1.02 menaikkan pitch 2% (membuat suara sedikit melengking namun natural)
    # Filter Video: drawtext membuat watermark transparan di pojok kiri bawah
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"drawtext=text='{watermark_text}':fontcolor=white@0.7:fontsize=36:x=30:y=H-th-80:box=1:boxcolor=black@0.3:boxborderw=5",
        "-af", "asetrate=44100*1.02,aresample=44100",
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        output_path
    ]
    
    logger.info(f" 🚀 Memulai render kilat FFmpeg (Bypass Mode) untuk: {input_path}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(" ✅ Render FFmpeg berhasil!")
            return True
        else:
            logger.error(f" ❌ FFmpeg gagal memproses video. Error: {result.stderr[-300:]}")
            return False
    except Exception as e:
        logger.error(f" ❌ Terjadi kesalahan saat menjalankan FFmpeg: {e}")
        return False
