"""
Configuration module for Panic Fish Bot
Loads settings from .env and environment variables.
"""

import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(BASE_DIR / ".env")

# Lichess API Settings
LICHESS_API_TOKEN = os.getenv("LICHESS_API_TOKEN", "").strip()

# Engine Settings - auto-detect across Windows, Linux, and Docker
def resolve_stockfish_path() -> str:
    env_path = os.getenv("STOCKFISH_PATH", "").strip()
    if env_path and (os.path.exists(env_path) or shutil.which(env_path)):
        return env_path
    
    local_windows = BASE_DIR / "engine" / "stockfish.exe"
    if local_windows.exists():
        return str(local_windows)
        
    local_linux = BASE_DIR / "engine" / "stockfish"
    if local_linux.exists():
        return str(local_linux)

    system_sf = shutil.which("stockfish")
    if system_sf:
        return system_sf

    for common_path in ["/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish"]:
        if os.path.exists(common_path):
            return common_path

    return str(local_windows)

STOCKFISH_PATH = resolve_stockfish_path()

# Panic Fish Mechanics
STARTING_ELO = int(os.getenv("STARTING_ELO", "3600"))
ELO_DROP_PER_CHECK = int(os.getenv("ELO_DROP_PER_CHECK", "300"))
MIN_ELO = int(os.getenv("MIN_ELO", "0"))

# In-Game Chat Notifications
SEND_CHAT_ALERTS = os.getenv("SEND_CHAT_ALERTS", "true").lower() in ("true", "1", "yes")

# Challenge Filters
ACCEPT_VARIANTS = os.getenv("ACCEPT_VARIANTS", "standard").lower().split(",")
ACCEPT_VARIANTS = [v.strip() for v in ACCEPT_VARIANTS if v.strip()]

# Maximum simultaneous active games (Shared Master Engine supports 5 simultaneous games with <30MB RAM)
MAX_CONCURRENT_GAMES = int(os.getenv("MAX_CONCURRENT_GAMES", "5"))
