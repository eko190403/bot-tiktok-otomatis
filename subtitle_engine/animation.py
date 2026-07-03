"""
subtitle_engine/animation.py
Pop Animation Engine — Efek scale CapCut-style untuk setiap kata aktif subtitle.
Bekerja pada canvas mini (bbox), bukan full-frame 1080x1920.
"""
from PIL import Image


class SubtitleAnimator:
    @staticmethod
    def apply_pop_animation(
        frame: Image.Image,
        progress: float,
        center_coords: tuple = None,
    ) -> Image.Image:
        """
        Efek Pop Scale CapCut-style: 70% → 115% → 100% dalam rentang progress [0, 1].

        Args:
            frame:          Canvas PIL (RGBA) yang akan dianimasikan.
            progress:       Posisi animasi [0.0 - 1.0], di mana 0 = awal kata, 1 = akhir fase pop.
            center_coords:  Titik pusat skala (cx, cy) dalam koordinat frame.
                            Jika None, digunakan pusat frame.

        Returns:
            Frame PIL baru dengan efek pop yang diterapkan.
        """
        if progress <= 0.0:
            # Belum mulai — kembalikan frame transparan kecil sebagai placeholder
            return Image.new("RGBA", frame.size, (0, 0, 0, 0))

        if progress >= 1.0:
            # Sudah selesai animasi — kembalikan frame apa adanya
            return frame

        # ── Kurva Skala CapCut: naik cepat → overshoot → settle ────────────
        if progress < 0.30:
            # Fase pop-in: 70% → 115%
            scale = 0.70 + (0.45 * (progress / 0.30))
        elif progress < 0.60:
            # Fase overshoot & balik: 115% → 100%
            scale = 1.15 - (0.18 * ((progress - 0.30) / 0.30))
        else:
            # Fase settle: 97% → 100%
            scale = 0.97 + (0.03 * ((progress - 0.60) / 0.40))

        scale = max(0.1, min(scale, 1.5))   # Klem agar tidak overflow

        w, h = frame.size
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))

        # Tentukan titik pusat pembesaran
        if center_coords is not None:
            cx, cy = int(center_coords[0]), int(center_coords[1])
        else:
            cx, cy = w // 2, h // 2

        # Scale menggunakan interpolasi LANCZOS (kualitas tinggi)
        scaled = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Buat canvas transparan seukuran frame asli
        output = Image.new("RGBA", (w, h), (0, 0, 0, 0))

        # Paste agar pusat pembesaran tetap di posisi cx, cy
        paste_x = cx - (new_w // 2)
        paste_y = cy - (new_h // 2)
        output.paste(scaled, (paste_x, paste_y), scaled)

        return output
