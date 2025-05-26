import os
import sys
import json
import requests

# 🧭 Obsługa ścieżek zależnie od trybu działania
if getattr(sys, 'frozen', False):  # Aplikacja spakowana (np. PyInstaller)
    BASE_DIR = sys._MEIPASS
else:  # Tryb deweloperski
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 🔧 Wyznacz ścieżkę do config.json
if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
    CONFIG_PATH = sys.argv[1]
else:
    CONFIG_PATH = os.path.join(os.path.dirname(BASE_DIR), "config.json")  # ⬅️ TO SIĘ ZMIENIŁO

# 📥 Wczytanie pliku konfiguracyjnego
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config_data = json.load(f)

CONFIG = config_data["CONFIG"]
REDDIT_TO_ADSPOWER = config_data["REDDIT_TO_ADSPOWER"]
BLOCKED_KEYWORDS = config_data["BLOCKED_KEYWORDS"]
BLOCKED_SUBREDDITS = config_data["BLOCKED_SUBREDDITS"]

# 🔄 Synchronizacja metadanych z API
def sync_metadata():
    response = requests.post(
        "https://api-3vgi.onrender.com/sync_metadata",
        json={
            "email": CONFIG.get("email"),
            "google_sheet": CONFIG.get("google_sheet"),
            "api_key": CONFIG.get("api_key"),
            "adspower_api_url": CONFIG.get("adspower_api_url"),
            "deepseek_api_key": CONFIG.get("deepseek_api_key"),
            "REDDIT_TO_ADSPOWER": REDDIT_TO_ADSPOWER
        },
        timeout=100
    )

sync_metadata()
