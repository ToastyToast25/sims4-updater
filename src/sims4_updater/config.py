import json
import os
import shutil
from dataclasses import dataclass, field, asdict
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
    manifest_url: str = ""
    theme: str = "dark"

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
