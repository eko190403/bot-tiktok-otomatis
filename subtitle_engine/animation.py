from PIL import Image

class SubtitleAnimator:
    @staticmethod
    def apply_pop_animation(frame: Image.Image, progress: float, center_coords: tuple = None) -> Image.Image:
        """
        Memberikan efek Pop Scale dinamis pada frame (70% -> 130% -> 100%)
        berdasarkan progress waktu kata tersebut diucapkan.
        """
        # Jika progress sudah lewat dari fase pop (0.18 detik pertama), kembalikan frame asli
        if progress > 1.0:
            return frame

        # Kurva skala animasi CapCut: Naik cepat, memantul sedikit, lalu stabil
        if progress < 0.3:
            # Fase 1: Membesar cepat dari 70% ke 130%
            scale = 0.7 + (0.6 * (progress / 0.3))
        elif progress < 0.6:
            # Fase 2: Memantul turun sedikit dari 130% ke 95%
            scale = 1.3 - (0.35 * ((progress - 0.3) / 0.3))
        else:
            # Fase 3: Stabil menuju ukuran normal 100%
            scale = 0.95 + (0.05 * ((progress - 0.6) / 0.4))

        width, height = frame.size
        
        # Tentukan titik pusat pembesaran (default: tengah kanvas video)
        if center_coords is None:
            cx, cy = width // 2, height // 2
        else:
            cx, cy = center_coords

        # Kalkulasi dimensi baru berdasarkan skala animasi
        new_w = int(width * scale)
        new_h = int(height * scale)
        
        # Pastikan ukuran tidak ganjil atau nol
        new_w = max(1, new_w)
        new_h = max(1, new_h)

        # Lakukan scaling pada frame teks menggunakan interpolasi berkualitas tinggi
        scaled_frame = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Buat kanvas transparan baru seukuran layar asli untuk menampung hasil scale
        output_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        
        # Hitung koordinat penempatan agar posisi teks tetap berada di pusat koordinat asal
        paste_x = cx - (new_w // 2)
        paste_y = cy - (new_h // 2)

        output_canvas.paste(scaled_frame, (paste_x, paste_y), scaled_frame)
        return output_canvas
