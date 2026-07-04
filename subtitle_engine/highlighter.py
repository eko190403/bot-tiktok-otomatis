import re

class KeywordHighlighter:
    """
    Mewarnai kata-kata kunci penting secara otomatis sesuai kategori konten.
    Dioptimasi untuk konten psikologi, mindset, dan edukasi viral Indonesia.
    """
    def __init__(self):
        # ── MERAH: Bahaya, ancaman, emosi negatif, peringatan ──────────────────
        self._danger = re.compile(
            r"\b(BAHAYA|MATI|TAKUT|STRES|DEPRESI|ANXIOUS|GILA|RUGI|TRAUMA|MANIPULASI|"
            r"TOXIC|GAGAL|HANCUR|RACUN|HANCURKAN|NYERI|LUKA|SAKIT|BUNUH|MUSUH|"
            r"ANCAMAN|KORBAN|KEKERASAN|KRISIS|PANIK|PUTUS|BENCI|MARAH|BOHONG|IRI|"
            r"DENGKI|CEMAS|TEGANG|BURUK|JAHAT|PARANOID|NEGATIF|TEKANAN|MENYERAH|"
            r"MENYESAL|SALAH|DOSA|KHIANAT|RAHASIA|RENTAN|LEMAH|BODOH)\b"
        )
        # ── KUNING: Otak, fakta, psikologi, rahasia, ilmu ─────────────────────
        self._mind = re.compile(
            r"\b(OTAK|PIKIRAN|MENTAL|FAKTA|RAHASIA|PSIKOLOGI|MANUSIA|ILMU|SAINS|"
            r"PENELITIAN|STUDI|TERBUKTI|ILMIAH|MEMORI|INGATAN|SADAR|BAWAH|SADAR|"
            r"KONDISI|EFEK|DAMPAK|REALITA|MANIPULASI|PERSEPSI|LOGIKA|INTUISI|"
            r"KEPUTUSAN|IDENTITAS|KARAKTER|KEPRIBADIAN|PERILAKU|GENIUS|PINTAR|"
            r"CERDAS|MEMAHAMI|MENGALAMI|MEMPENGARUHI|ALASAN|CARA|TRIK|TIPS|KUNCI|"
            r"FORMULA|TEORI|FENOMENA|REFLEKSI|FILOSOFI|STOIC|STOIKISME|KONTROL|FOKUS)\b"
        )
        # ── HIJAU: Uang, kesuksesan, kekayaan, karier ─────────────────────────
        self._wealth = re.compile(
            r"\b(UANG|KAYA|SUKSES|BISNIS|UNTUNG|OMSET|INVESTASI|KERJA|PROFIT|"
            r"KEKAYAAN|FINANSIAL|ASET|PENGHASILAN|PENDAPATAN|MODAL|PRODUKTIF|"
            r"DISIPLIN|KONSISTEN|TUJUAN|IMPIAN|TARGET|VISI|KARIER|PRESTASI|"
            r"JUARA|MENANG|UNGGUL|BERKEMBANG|POTENSI|MILIARDER|JUTAWAN|KESEMPATAN|"
            r"PRODUKTIVITAS|AMBISI|KONSISTENSI|USAHA|KEPEMIMPINAN|PEMIMPIN|HEBAT|LUAR|BIASA)\b"
        )
        # ── PINK/MERAH MUDA: Hubungan, emosi, sosial ──────────────────────────
        self._social = re.compile(
            r"\b(CINTA|SAYANG|PASANGAN|PACAR|MENIKAH|HUBUNGAN|KELUARGA|TEMAN|"
            r"KEPERCAYAAN|PERCAYA|SETIA|PENGKHIANATAN|KESEPIAN|EMPATI|DUKUNGAN|"
            r"KOMUNIKASI|KONFLIK|BATAS|RESPECT|HORMATI|PEDULI|NYAMAN|RASA|PERASAAN|"
            r"MENARIK|KHARISMATIK|MENAWAN|SAHABAT|KASIH|INTIM|SOSIAL|MASYARAKAT)\b"
        )

        # Mapping pola ke warna (urutan penting — pertama yang cocok yang dipakai)
        self._rules = [
            (self._danger, "#FF3B30"),   # Merah — Bahaya
            (self._wealth, "#34C759"),   # Hijau — Kekayaan
            (self._social, "#FF2D55"),   # Pink  — Sosial/Hubungan
            (self._mind,   "#FFCC00"),   # Kuning — Pikiran/Fakta
        ]

    def get_word_color(self, word: str, default_color: str = "#FFFFFF") -> str:
        """Memeriksa apakah sebuah kata harus di-highlight dengan warna khusus."""
        clean_word = re.sub(r"[^\w]", "", word.upper()).strip()
        if not clean_word:
            return default_color

        for pattern, color in self._rules:
            if pattern.search(clean_word):
                return color

        return default_color
