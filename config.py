import os
from dotenv import load_dotenv

# .env faylini yuklash
load_dotenv()

# Tokenlar va kalitlar
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Admin IDs
_admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in _admin_ids_str.split(",") if x.strip().isdigit()]

# Model sozlamalari
GEMINI_AUDIO_MODEL = os.getenv("GEMINI_AUDIO_MODEL", "gemini-3.6-flash")
GEMINI_SALES_MODEL = os.getenv("GEMINI_SALES_MODEL", "gemini-3.6-flash")
GEMINI_MODEL = GEMINI_AUDIO_MODEL  # Moslik uchun

# Fayllar katalogi
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(BASE_DIR, "datasets")
