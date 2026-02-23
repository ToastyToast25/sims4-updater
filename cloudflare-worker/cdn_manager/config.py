"""
CDN Manager configuration — persistent settings stored as JSON.

Credentials are read from cdn_config.json (gitignored, single source of truth).
Non-credential settings are stored in cdn_manager_config.json (also gitignored).
Credentials are NEVER written to cdn_manager_config.json.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _resolve_config_dir() -> Path:
    """Resolve the config directory.

    - Source mode: cloudflare-worker/ (parent of cdn_manager/)
    - Frozen (exe) mode: directory containing the exe
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


CONFIG_DIR = _resolve_config_dir()
CONFIG_FILE = CONFIG_DIR / "cdn_manager_config.json"
CDN_CONFIG_FILE = CONFIG_DIR / "cdn_config.json"

# Keys that live in cdn_config.json — never saved to cdn_manager_config.json
_CREDENTIAL_KEYS = {
    "whatbox_host",
    "whatbox_port",
    "whatbox_user",
    "whatbox_pass",
    "cloudflare_account_id",
    "cloudflare_api_token",
    "cloudflare_kv_namespace_id",
}


@dataclass
class ManagerConfig:
    # Seedbox (loaded from cdn_config.json)
    whatbox_host: str = "spirit.whatbox.ca"
    whatbox_port: int = 22
    whatbox_user: str = ""
    whatbox_pass: str = ""

    # Cloudflare (loaded from cdn_config.json)
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_kv_namespace_id: str = ""

    # Paths
    game_dir: str = r"C:\Program Files (x86)\Steam\steamapps\common\The Sims 4"
    patcher_dir: str = ""  # defaults to ../patcher/ relative to repo root
    output_dir: str = ""  # temp dir for packing

    # Upload
    default_workers: int = 0  # 0 = auto (speedtest)
    upload_chunk_size: int = 65536

    # Logging
    max_log_lines: int = 5000

    # Window
    window_geometry: str = ""

    # Version registry for patch creation
    version_registry: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls) -> ManagerConfig:
        """Load config: credentials from cdn_config.json, settings from cdn_manager_config.json."""
        config = cls()

        # 1. Load credentials from cdn_config.json (single source of truth)
        if CDN_CONFIG_FILE.is_file():
            try:
                data = json.loads(CDN_CONFIG_FILE.read_text(encoding="utf-8"))
                config.whatbox_host = data.get("whatbox_host", config.whatbox_host)
                config.whatbox_port = data.get("whatbox_port", config.whatbox_port)
                config.whatbox_user = data.get("whatbox_user", config.whatbox_user)
                config.whatbox_pass = data.get("whatbox_pass", config.whatbox_pass)
                config.cloudflare_account_id = data.get(
                    "cloudflare_account_id",
                    config.cloudflare_account_id,
                )
                config.cloudflare_api_token = data.get(
                    "cloudflare_api_token",
                    config.cloudflare_api_token,
                )
                config.cloudflare_kv_namespace_id = data.get(
                    "cloudflare_kv_namespace_id",
                    config.cloudflare_kv_namespace_id,
                )
            except (json.JSONDecodeError, OSError):
                pass

        # 2. Load non-credential settings from cdn_manager_config.json
        if CONFIG_FILE.is_file():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                for key, value in data.items():
                    if hasattr(config, key) and key not in _CREDENTIAL_KEYS:
                        setattr(config, key, value)
            except (json.JSONDecodeError, OSError):
                pass

        # Default patcher dir
        if not config.patcher_dir:
            repo_root = CONFIG_DIR.parent
            patcher = repo_root.parent / "patcher"
            if patcher.is_dir():
                config.patcher_dir = str(patcher)

        return config

    def save(self):
        """Persist non-credential settings to cdn_manager_config.json."""
        data = {k: v for k, v in asdict(self).items() if k not in _CREDENTIAL_KEYS}
        CONFIG_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def save_credentials(self):
        """Persist credentials to cdn_config.json with restrictive permissions.

        The file is gitignored and stored locally alongside the application.
        File permissions are set to owner-only (600) to limit exposure.
        """
        data = {
            "whatbox_host": self.whatbox_host,
            "whatbox_port": self.whatbox_port,
            "whatbox_user": self.whatbox_user,
            "whatbox_pass": self.whatbox_pass,
            "cloudflare_account_id": self.cloudflare_account_id,
            "cloudflare_api_token": self.cloudflare_api_token,
            "cloudflare_kv_namespace_id": self.cloudflare_kv_namespace_id,
        }
        CDN_CONFIG_FILE.write_text(  # lgtm[py/clear-text-storage-sensitive-data]
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        # Restrict file permissions to owner-only read/write
        with contextlib.suppress(OSError):
            os.chmod(CDN_CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)

    def to_cdn_config(self) -> dict:
        """Convert to the dict format expected by ConnectionManager."""
        return {
            "whatbox_host": self.whatbox_host,
            "whatbox_port": self.whatbox_port,
            "whatbox_user": self.whatbox_user,
            "whatbox_pass": self.whatbox_pass,
            "cloudflare_account_id": self.cloudflare_account_id,
            "cloudflare_api_token": self.cloudflare_api_token,
            "cloudflare_kv_namespace_id": self.cloudflare_kv_namespace_id,
        }
