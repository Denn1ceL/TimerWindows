import json
import os
from pathlib import Path
import subprocess
import sys

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "config.json"
SFX_DIR = BASE_DIR / "SFX"

#Theme presets are applied when the theme changes and can be customized afterwards.
THEME_PRESETS = {
    "dark": {
        "color_bg":      [20, 27, 39],
        "color_text":    [238, 242, 247],
        "color_primary": [37, 99, 235],
        "color_accent":  [194, 65, 12],
        "color_success": [22, 101, 52],
    },
    "light": {
        "color_bg":      [245, 247, 250],
        "color_text":    [31, 41, 55],
        "color_primary": [37, 99, 235],
        "color_accent":  [180, 83, 9],
        "color_success": [21, 128, 61],
    }
}

LEGACY_THEME_PRESETS = {
    "dark": {
        "color_bg": [24, 24, 28],
        "color_text": [240, 240, 240],
        "color_primary": [58, 134, 255],
        "color_accent": [255, 149, 0],
        "color_success": [46, 204, 113],
    },
    "light": {
        "color_bg": [245, 245, 248],
        "color_text": [20, 20, 24],
        "color_primary": [58, 134, 255],
        "color_accent": [230, 126, 34],
        "color_success": [39, 174, 96],
    },
    "system": {
        "color_bg": [24, 24, 28],
        "color_text": [240, 240, 240],
        "color_primary": [58, 134, 255],
        "color_accent": [255, 149, 0],
        "color_success": [46, 204, 113],
    },
}

DEFAULT_CONFIG = {
    "theme": "dark",
    **THEME_PRESETS["dark"],
    "clock_style": "digital",

    "auto_off_seconds": 30,
    "fade_in": True,
    "fade_in_seconds": 5,
    "max_volume": 1.0,
    "loop_if_short": True,
    "snooze_minutes": 5,
    "sound_file": "",

    "music_dirs": [],
    "autostart": False,
    "vibration_enabled": False,
    "show_vibration_ticker": False,
}


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SFX_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_dirs()
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        theme = cfg.get("theme")
        legacy = LEGACY_THEME_PRESETS.get(theme)
        if theme == "system":
            matching_theme = next(
                (
                    name for name, palette in THEME_PRESETS.items()
                    if all(cfg.get(key) == value for key, value in palette.items())
                ),
                None,
            )
            if matching_theme:
                cfg["theme"] = matching_theme
            elif legacy and all(cfg.get(key) == value for key, value in legacy.items()):
                cfg.update(THEME_PRESETS["dark"])
                cfg["theme"] = "dark"
            else:
                cfg["theme"] = "light"
        elif legacy and all(cfg.get(key) == value for key, value in legacy.items()):
            cfg.update(THEME_PRESETS[theme])
        return cfg
    except Exception:
        return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg: dict):
    ensure_dirs()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def set_autostart(enabled: bool):
    """Create or remove the current user's Windows startup entry."""
    if os.name != "nt":
        raise OSError("Windows startup settings are only available on Windows.")

    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "TimerWindows"
    if getattr(sys, "frozen", False):
        command = subprocess.list2cmdline([sys.executable])
    else:
        command = subprocess.list2cmdline([sys.executable, str(BASE_DIR / "main.py")])

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        if enabled:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass