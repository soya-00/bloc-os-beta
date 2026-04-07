import os
import tomli
import tomli_w
from pathlib import Path


DEFAULT_CONFIG = {
    "identity": {
        "owner": "ADMIN",
        "boot_message": "ALL SYSTEMS NOMINAL",
        "callsign": "ADMIN-1",
    },
    "display": {
        "environment": "hud",
        "font_family": "mono",
        "font_size": 16,
        "brightness": 80,
        "auto_dim": True,
        "dim_level": 20,
    },
    "voice": {
        "enabled": True,
        "wake_word": "dispatch",
        "language": "en",
        "auto_punctuate": True,
        "confirm_before_save": False,
    },
    "pulse": {
        "mode": "pomodoro",
        "work_duration": 25,
        "break_duration": 5,
        "long_break": 15,
        "sessions_before_long": 4,
        "sound": True,
    },
    "radar": {
        "enabled": True,
        "city": "london",
        "range_nm": 80,
        "refresh_seconds": 15,
        "color": "green",
        "show_trails": True,
        "show_callsigns": True,
        "auto_switch_minutes": 5,
    },
    "print": {
        "header": "BLOC",
        "show_footer": True,
        "paper_width": 32,
    },
    "sync": {
        "enabled": False,
        "desktop_ip": "",
        "auto_sync": True,
        "interval_seconds": 300,
    },
    "sounds": {
        "ui_sounds": True,
        "voice_chime": True,
        "timer_alert": True,
        "volume": 70,
    },
}


class Config:
    """
    BLOC configuration manager.
    Reads and writes ~/bloc/config/bloc.config (TOML format).
    Falls back to defaults for any missing keys.
    """

    def __init__(self, config_dir: Path):
        self.config_path = config_dir / "bloc.config"
        self.data = {}
        self._load()

    def _load(self):
        """Load config from file, merging with defaults."""
        if not self.config_path.exists():
            self.data = DEFAULT_CONFIG.copy()
            self._write()
            return

        with open(self.config_path, "rb") as f:
            loaded = tomli.load(f)

        # Deep merge loaded over defaults
        self.data = self._merge(DEFAULT_CONFIG, loaded)

    def _merge(self, base: dict, override: dict) -> dict:
        """Recursively merge override into base."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge(result[key], value)
            else:
                result[key] = value
        return result

    def _write(self):
        """Write current config to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "wb") as f:
            tomli_w.dump(self.data, f)

    def get(self, section: str, key: str, fallback=None):
        """Get a config value by section and key."""
        return self.data.get(section, {}).get(key, fallback)

    def set(self, section: str, key: str, value) -> None:
        """Set a config value and save."""
        if section not in self.data:
            self.data[section] = {}
        self.data[section][key] = value
        self._write()

    def reload(self):
        """Reload config from disk."""
        self._load()

    @property
    def owner(self): return self.get("identity", "owner", "ADMIN")

    @property
    def callsign(self): return self.get("identity", "callsign", "ADMIN-1")

    @property
    def environment(self): return self.get("display", "environment", "hud")

    @property
    def wake_word(self): return self.get("voice", "wake_word", "tower")

    @property
    def radar_city(self): return self.get("radar", "city", "london")

    @property
    def radar_range(self): return self.get("radar", "range_nm", 80)

    @property
    def radar_refresh(self): return self.get("radar", "refresh_seconds", 15)