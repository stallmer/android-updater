import os
from pathlib import Path


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "android-updater"
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / "android-updater"
APK_DIR = CACHE_DIR / "apks"
INDEX_FILE = CACHE_DIR / "index-v2.json"
WATCHLIST_FILE = CONFIG_DIR / "config.toml"
