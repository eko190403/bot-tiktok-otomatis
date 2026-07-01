import os

# Video Settings
WIDTH = 1080
HEIGHT = 1920
FPS = 30

# Typography Settings
FONT_PATH = os.path.join("assets", "fonts", "font.ttf")
FONT_SIZE_HOOK = 68
FONT_SIZE_BODY = 58
STROKE_WIDTH = 5

# Path Directories
DIR_ASSETS = "assets"
DIR_TEMP = "temp"
DIR_OUTPUT = "output"

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
