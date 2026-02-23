"""Shared connection manager — SFTP pool and Cloudflare KV helpers for all frames."""

from __future__ import annotations

import functools
import json
import time
import urllib.request
from pathlib import Path
from threading import Lock
from typing import Any

SEEDBOX_BASE_DIR = "files/sims4"
CDN_DOMAIN = "https://cdn.hyperabyss.com"


def _retry(max_retries: int = 3, base_delay: float = 2):
    """Decorator: retry with exponential backoff on any exception."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception:
                    if attempt == max_retries:
                        raise
                    time.sleep(base_delay * (2 ** (attempt - 1)))
        return wrapper
    return decorator


class SFTPPool:
    """Reusable SFTP connection pool.

    Keeps up to `max_idle` idle connections. Expired connections (>60s idle)
    are pruned on acquire. Thread-safe.
    """

    IDLE_TIMEOUT = 60  # seconds

    def __init__(self, config: dict, max_idle: int = 2):
        self._config = config
        self._max_idle = max_idle
        self._idle: list[tuple[Any, Any, float]] = []  # (transport, sftp, last_used)
        self._lock = Lock()

    def acquire(self):
        """Get an SFTP connection — reuse idle or create new."""
        import paramiko

        with self._lock:
            now = time.time()
            # Prune expired
            valid = []
            for transport, sftp, ts in self._idle:
                if now - ts > self.IDLE_TIMEOUT or not transport.is_active():
                    try:
                        sftp.close()
                        transport.close()
                    except Exception:
                        pass
                else:
                    valid.append((transport, sftp, ts))
            self._idle = valid

            # Return first valid idle
            if self._idle:
                transport, sftp, _ = self._idle.pop(0)
                if transport.is_active():
                    return transport, sftp
                # Stale — close and create new
                try:
                    sftp.close()
                    transport.close()
                except Exception:
                    pass

        # Create new connection
        transport = paramiko.Transport(
            (self._config["whatbox_host"], self._config.get("whatbox_port", 22)),
        )
        transport.default_window_size = paramiko.common.MAX_WINDOW_SIZE
        transport.connect(
            username=self._config["whatbox_user"],
            password=self._config["whatbox_pass"],
        )
        sftp = paramiko.SFTPClient.from_transport(transport)
        return transport, sftp

    def release(self, transport, sftp):
        """Return a connection to the pool (or close if pool is full)."""
        with self._lock:
            try:
                if transport.is_active() and len(self._idle) < self._max_idle:
                    self._idle.append((transport, sftp, time.time()))
                    return
            except Exception:
                pass
        # Pool full or connection dead — close
        try:
            sftp.close()
            transport.close()
        except Exception:
            pass

    def close_all(self):
        """Close all idle connections."""
        with self._lock:
            for transport, sftp, _ in self._idle:
                try:
                    sftp.close()
                    transport.close()
                except Exception:
                    pass
            self._idle.clear()


class ConnectionManager:
    """Shared connection utilities for SFTP and Cloudflare KV.

    Uses an SFTP connection pool to reuse SSH connections across operations.
    Provides retry logic, KV helpers, and SFTP helpers that all
    backend modules use.
    """

    def __init__(self, config_dict: dict):
        self._config = config_dict
        self._lock = Lock()
        self._pool: SFTPPool | None = None

    @property
    def config(self) -> dict:
        return self._config

    def update_config(self, config_dict: dict):
        with self._lock:
            self._config = config_dict
            if self._pool:
                self._pool.close_all()
                self._pool = None

    def _get_pool(self) -> SFTPPool:
        with self._lock:
            if self._pool is None:
                self._pool = SFTPPool(self._config)
            return self._pool

    def close(self):
        """Close all pooled connections."""
        if self._pool:
            self._pool.close_all()

    # -- SFTP ----------------------------------------------------------------

    def connect_sftp(self):
        """Open an SFTP connection from the pool. Caller must call release_sftp()."""
        return self._get_pool().acquire()

    def release_sftp(self, transport, sftp):
        """Return an SFTP connection to the pool."""
        self._get_pool().release(transport, sftp)

    def connect_ssh(self):
        """Open an SSH client. Caller must close it."""
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self._config["whatbox_host"],
            port=self._config.get("whatbox_port", 22),
            username=self._config["whatbox_user"],
            password=self._config["whatbox_pass"],
        )
        return client

    def test_sftp(self) -> bool:
        """Quick SFTP connectivity test."""
        try:
            transport, sftp = self.connect_sftp()
            self.release_sftp(transport, sftp)
            return True
        except Exception:
            return False

    def upload_sftp(
        self,
        local_path: Path,
        remote_path: str,
        *,
        progress_cb=None,
        max_retries: int = 5,
    ) -> None:
        """Upload a file via SFTP with retry and optional progress callback.

        progress_cb(sent_bytes, total_bytes) is called during upload.
        """
        retry_base = 5

        for attempt in range(1, max_retries + 1):
            try:
                transport, sftp = self.connect_sftp()
                try:
                    # Ensure remote directories
                    parts = remote_path.split("/")
                    current = ""
                    for part in parts[:-1]:
                        current = f"{current}/{part}" if current else part
                        try:
                            sftp.stat(current)
                        except FileNotFoundError:
                            try:
                                sftp.mkdir(current)
                            except OSError:
                                pass

                    sftp.put(str(local_path), remote_path, callback=progress_cb)
                    self.release_sftp(transport, sftp)
                    return
                except Exception:
                    # Don't return broken connections to pool
                    try:
                        sftp.close()
                        transport.close()
                    except Exception:
                        pass
                    raise
            except Exception as e:
                if attempt == max_retries:
                    raise ConnectionError(
                        f"Upload failed after {max_retries} attempts: {e}"
                    ) from e
                delay = retry_base * (2 ** (attempt - 1))
                time.sleep(delay)

    def file_exists_sftp(self, remote_path: str) -> bool:
        """Check if a file exists on the seedbox."""
        try:
            transport, sftp = self.connect_sftp()
            try:
                sftp.stat(remote_path)
                self.release_sftp(transport, sftp)
                return True
            except FileNotFoundError:
                self.release_sftp(transport, sftp)
                return False
            except Exception:
                try:
                    sftp.close()
                    transport.close()
                except Exception:
                    pass
                return False
        except Exception:
            return False

    # -- Cloudflare KV -------------------------------------------------------

    def _kv_base_url(self) -> str:
        account_id = self._config["cloudflare_account_id"]
        ns_id = self._config["cloudflare_kv_namespace_id"]
        return (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/storage/kv/namespaces/{ns_id}"
        )

    def _kv_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._config['cloudflare_api_token']}"}

    def test_kv(self) -> bool:
        """Quick KV connectivity test."""
        try:
            url = f"{self._kv_base_url()}/keys?limit=1"
            req = urllib.request.Request(url, headers=self._kv_headers())
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            return data.get("success", False)
        except Exception:
            return False

    @_retry(max_retries=3, base_delay=2)
    def kv_exists(self, key: str) -> bool:
        """Check if a KV key exists."""
        import requests

        url = f"{self._kv_base_url()}/values/{key}"
        resp = requests.get(url, headers=self._kv_headers(), timeout=15)
        return resp.status_code == 200

    @_retry(max_retries=3, base_delay=2)
    def kv_get(self, key: str) -> str | None:
        """Read a KV value. Returns None if key doesn't exist."""
        import requests

        url = f"{self._kv_base_url()}/values/{key}"
        resp = requests.get(url, headers=self._kv_headers(), timeout=15)
        return resp.text if resp.status_code == 200 else None

    @_retry(max_retries=3, base_delay=2)
    def kv_put(self, key: str, value: str) -> None:
        """Write a KV entry."""
        import requests

        url = f"{self._kv_base_url()}/values/{key}"
        resp = requests.put(
            url,
            headers={**self._kv_headers(), "Content-Type": "text/plain"},
            data=value,
            timeout=30,
        )
        if resp.status_code == 200 and resp.json().get("success"):
            return
        raise RuntimeError(f"KV write failed: {resp.status_code} {resp.text}")

    @_retry(max_retries=3, base_delay=2)
    def kv_delete(self, key: str) -> bool:
        """Delete a KV entry. Returns True on success."""
        import requests

        url = f"{self._kv_base_url()}/values/{key}"
        resp = requests.delete(url, headers=self._kv_headers(), timeout=30)
        return resp.status_code == 200

    @_retry(max_retries=2, base_delay=3)
    def kv_list(self) -> list[str]:
        """List all KV keys with pagination."""
        import requests

        url = f"{self._kv_base_url()}/keys"
        all_keys: list[str] = []
        cursor = None

        while True:
            params = {}
            if cursor:
                params["cursor"] = cursor
            resp = requests.get(
                url, headers=self._kv_headers(), params=params, timeout=30,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"KV list failed: {resp.status_code} {resp.text[:200]}"
                )
            data = resp.json()
            all_keys.extend(e.get("name", "") for e in data.get("result", []))
            cursor = data.get("result_info", {}).get("cursor")
            if not cursor:
                break

        return all_keys

    # -- CDN Upload ----------------------------------------------------------

    def upload_to_cdn(
        self,
        local_path: Path,
        cdn_path: str,
        *,
        force: bool = False,
        progress_cb=None,
    ) -> bool:
        """Upload file to seedbox + register KV entry. Returns True if uploaded."""
        cdn_path = cdn_path.strip("/")
        seedbox_path = f"{SEEDBOX_BASE_DIR}/{cdn_path}"

        if not force:
            if self.kv_exists(cdn_path):
                return False
            # File on seedbox but missing KV entry (orphan) — just register KV
            if self.file_exists_sftp(seedbox_path):
                self.kv_put(cdn_path, seedbox_path)
                return True

        self.upload_sftp(local_path, seedbox_path, progress_cb=progress_cb)
        self.kv_put(cdn_path, seedbox_path)
        return True

    # -- Manifest ------------------------------------------------------------

    def fetch_manifest(self) -> dict[str, Any]:
        """Fetch the live manifest from CDN."""
        req = urllib.request.Request(
            f"{CDN_DOMAIN}/manifest.json",
            headers={"User-Agent": "CDNManager/1.0"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode("utf-8"))

    def publish_manifest(self, local_path: Path) -> None:
        """Upload manifest.json to CDN (always overwrites).

        Automatically backs up the current live manifest before overwriting.
        """
        from datetime import datetime

        # Auto-backup current manifest before overwriting
        backup_dir = local_path.parent / "manifest_backups"
        try:
            current = self.fetch_manifest()
            backup_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"manifest_{ts}.json"
            backup_path.write_text(
                json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8",
            )
        except Exception:
            pass  # Don't fail the publish if backup fails

        self.upload_to_cdn(local_path, "manifest.json", force=True)

    # -- HEAD check ----------------------------------------------------------

    @staticmethod
    def head_check(url: str, timeout: int = 20) -> tuple[int, int]:
        """HEAD request a URL. Returns (status_code, content_length)."""
        import requests

        try:
            resp = requests.head(url, timeout=timeout, allow_redirects=True)
            size = int(resp.headers.get("Content-Length", 0))
            return resp.status_code, size
        except Exception:
            return 0, 0
