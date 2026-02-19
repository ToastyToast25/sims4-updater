import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path


def _get_settings_dir():
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        return Path(local) / "anadius" / "sims4_updater"
    return Path.home() / ".config" / "sims4_updater"


SETTINGS_PATH = _get_settings_dir() / "settings.json"


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
