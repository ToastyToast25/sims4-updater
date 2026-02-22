import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

_OLD_DIR_NAME = "anadius"
_NEW_DIR_NAME = "ToastyToast25"


def get_app_dir() -> Path:
    """Return the app data directory, creating it if needed."""
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        p = Path(local) / _NEW_DIR_NAME / "sims4_updater"
    else:
        p = Path.home() / ".config" / "sims4_updater"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _migrate_from_old_dir():
    """One-time migration: copy settings from old anadius dir to new ToastyToast25 dir."""
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return
    old_dir = Path(local) / _OLD_DIR_NAME / "sims4_updater"
    new_dir = Path(local) / _NEW_DIR_NAME / "sims4_updater"
    if not old_dir.is_dir():
        return
    # Only migrate if new dir has no settings yet
    if (new_dir / "settings.json").is_file():
        return
    for name in ("settings.json", "learned_hashes.json"):
        src = old_dir / name
        if src.is_file():
            new_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, new_dir / name)


# Run migration before anything else uses the directory
_migrate_from_old_dir()

SETTINGS_PATH = get_app_dir() / "settings.json"


@dataclass
class Settings:
    game_path: str = ""
    language: str = "English"
    check_updates_on_start: bool = True
    last_known_version: str = ""
    enabled_dlcs: list[str] = field(default_factory=list)
    manifest_url: str = "https://cdn.hyperabyss.com/manifest.json"
    theme: str = "dark"
    download_concurrency: int = 3
    download_speed_limit: int = 0  # MB/s, 0 = unlimited
    steam_username: str = ""  # Steam username for depot downloads (password NOT stored)
    steam_path: str = ""  # Steam installation directory (auto-detected or manual)
    greenluma_archive_path: str = ""  # Path to GreenLuma 7z archive
    greenluma_auto_backup: bool = True  # Backup config.vdf/AppList before modifications
    greenluma_lua_path: str = ""  # Path to .lua manifest file
    greenluma_manifest_dir: str = ""  # Path to directory containing .manifest files
    skip_game_update: bool = False  # DLC-only mode: skip base game updates
    window_geometry: str = ""  # Window size+position as "WxH+X+Y"

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or SETTINGS_PATH
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # Only use keys that exist in the dataclass
            valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in valid_keys}
            return cls(**filtered)
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            return cls()

    def save(self, path: Path | None = None) -> None:
        path = path or SETTINGS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json_tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, path)
