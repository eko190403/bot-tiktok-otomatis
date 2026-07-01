import re

class KeywordHighlighter:
    def __init__(self):
        # Pemetaan kata kunci ke warna target (Format HEX)
        self.keywords_map = {
            r"\b(BAHAYA|MATI|TAKUT|STRES|DEPRESI|ANXIOUS|GILA|RUGI)\b": "#FF3B30",     # Merah (Danger)
            r"\b(OTAK|PIKIRAN|MENTAL|FAKTA|RAHASIA|PSIKOLOGI|MANUSIA)\b": "#FFCC00", # Kuning (Mind/Fact)
            r"\b(UANG|KAYA|SUKSES|BISNIS|UNTUNG|OMSET|INVESTASI|KERJA)\b": "#34C759", # Hijau (Wealth)
            r"\b(CINTA|SAYANG|PASANGAN|PACAR|MENIKAH|HUBUNGAN)\b": "#FF2D55"          # Pink (Romance)
        }

    def get_word_color(self, word: str, default_color: str = "#FFFFFF") -> str:
        """Memeriksa apakah sebuah kata harus di-highlight dengan warna khusus."""
        clean_word = re.sub(r"[^\w]", "", word.upper())
        
        for pattern, color in self.keywords_map.items():
            if re.search(pattern, clean_word):
                return color
        return default_color
