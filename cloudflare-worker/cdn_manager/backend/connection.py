"""Shared connection manager — SFTP pool and Cloudflare KV helpers for all frames."""

from __future__ import annotations

import contextlib
import functools
import json
import logging
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

SEEDBOX_BASE_DIR = "files/sims4"
CDN_DOMAIN = "https://cdn.hyperabyss.com"

# Cached SSH host keys file (alongside cdn_config.json)
_KNOWN_HOSTS_FILE = Path(__file__).resolve().parent.parent.parent / "known_hosts"
# SSH key for native scp uploads (auto-generated, alongside cdn_config.json)
_SSH_KEY_FILE = Path(__file__).resolve().parent.parent.parent / "cdn_manager_key"


def _get_host_keys_policy():
    """Return a paramiko host key policy that uses a local known_hosts file.

    On first connection, the host key is saved (trust-on-first-use / TOFU).
    Subsequent connections verify against the saved key.
    """
    import paramiko

    class TOFUPolicy(paramiko.MissingHostKeyPolicy):
        """Trust-on-first-use: save the key on first connect, reject changes."""

        def missing_host_key(self, client, hostname, key):
            # Save the key to our known_hosts file
            host_keys = client.get_host_keys()
            host_keys.add(hostname, key.get_name(), key)
            with contextlib.suppress(OSError):
                host_keys.save(str(_KNOWN_HOSTS_FILE))

    return TOFUPolicy()


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

        # Create new connection via SSHClient (host key verification)
        client = paramiko.SSHClient()
        if _KNOWN_HOSTS_FILE.is_file():
            client.load_host_keys(str(_KNOWN_HOSTS_FILE))
        client.set_missing_host_key_policy(_get_host_keys_policy())
        client.connect(
            hostname=self._config["whatbox_host"],
            port=self._config.get("whatbox_port", 22),
            username=self._config["whatbox_user"],
            password=self._config["whatbox_pass"],
        )
        transport = client.get_transport()
        transport.default_window_size = paramiko.common.MAX_WINDOW_SIZE
        sftp = client.open_sftp()
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
        if _KNOWN_HOSTS_FILE.is_file():
            client.load_host_keys(str(_KNOWN_HOSTS_FILE))
        client.set_missing_host_key_policy(_get_host_keys_policy())
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

    def _ensure_ssh_key(self) -> Path | None:
        """Ensure an SSH key exists for native scp uploads.

        Generates a key pair on first use and installs the public key on the
        seedbox.  Returns the private key path, or None on failure.
        """
        if _SSH_KEY_FILE.exists():
            return _SSH_KEY_FILE
        try:
            import paramiko as _pm

            key = _pm.RSAKey.generate(4096)
            key.write_private_key_file(str(_SSH_KEY_FILE))
            pub = f"{key.get_name()} {key.get_base64()} cdn_manager"
            _SSH_KEY_FILE.with_suffix(".pub").write_text(pub)

            # Install on seedbox
            transport, sftp = self.connect_sftp()
            try:
                chan = transport.open_session()
                chan.exec_command(
                    f'mkdir -p ~/.ssh && echo "{pub}" >> ~/.ssh/authorized_keys '
                    f"&& chmod 600 ~/.ssh/authorized_keys"
                )
                chan.recv_exit_status()
                chan.close()
            finally:
                self.release_sftp(transport, sftp)
            logger.info("Generated SSH key and installed on seedbox")
            return _SSH_KEY_FILE
        except Exception:
            logger.debug("SSH key setup failed, will use paramiko", exc_info=True)
            _SSH_KEY_FILE.unlink(missing_ok=True)
            _SSH_KEY_FILE.with_suffix(".pub").unlink(missing_ok=True)
            return None

    def _ensure_remote_dirs(self, sftp, remote_path: str) -> None:
        """Create remote directories for a file path."""
        parts = remote_path.split("/")
        current = ""
        for part in parts[:-1]:
            current = f"{current}/{part}" if current else part
            try:
                sftp.stat(current)
            except FileNotFoundError:
                with contextlib.suppress(OSError):
                    sftp.mkdir(current)

    def _upload_native_scp(
        self, local_path: Path, remote_path: str, *, max_retries: int = 5
    ) -> bool:
        """Upload via native scp (7x faster than paramiko). Returns True on success."""
        scp_bin = shutil.which("scp")
        if not scp_bin:
            return False
        key_path = self._ensure_ssh_key()
        if not key_path:
            return False

        host = self._config["whatbox_host"]
        user = self._config["whatbox_user"]
        port = str(self._config.get("whatbox_port", 22))

        # Ensure remote directories exist (scp can't create them)
        transport, sftp = self.connect_sftp()
        try:
            self._ensure_remote_dirs(sftp, remote_path)
        finally:
            self.release_sftp(transport, sftp)

        retry_base = 5
        for attempt in range(1, max_retries + 1):
            try:
                result = subprocess.run(
                    [
                        scp_bin,
                        "-P",
                        port,
                        "-i",
                        str(key_path),
                        "-o",
                        "StrictHostKeyChecking=no",
                        "-o",
                        "BatchMode=yes",
                        str(local_path),
                        f"{user}@{host}:{remote_path}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3600,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode == 0:
                    return True
                logger.debug("scp attempt %d failed: %s", attempt, result.stderr.strip())
            except Exception as e:
                logger.debug("scp attempt %d error: %s", attempt, e)
            if attempt < max_retries:
                time.sleep(retry_base * (2 ** (attempt - 1)))
        return False

    def upload_sftp(
        self,
        local_path: Path,
        remote_path: str,
        *,
        progress_cb=None,
        max_retries: int = 5,
    ) -> None:
        """Upload a file to the seedbox.

        Uses native scp when available (~5 MB/s) with automatic SSH key setup.
        Falls back to paramiko SFTP (~0.6 MB/s) if scp is unavailable.

        progress_cb(sent_bytes, total_bytes) is called during upload (paramiko only).
        """
        file_size = local_path.stat().st_size

        # Try native scp first (7x faster than paramiko)
        if self._upload_native_scp(local_path, remote_path, max_retries=max_retries):
            if progress_cb is not None:
                progress_cb(file_size, file_size)
            # Verify size
            transport, sftp = self.connect_sftp()
            try:
                remote_stat = sftp.stat(remote_path)
                if remote_stat.st_size != file_size:
                    raise OSError(
                        f"Size mismatch: local {file_size} vs remote {remote_stat.st_size}"
                    )
            finally:
                self.release_sftp(transport, sftp)
            return

        # Fallback: paramiko SFTP with pipelining
        logger.info("Native scp unavailable, falling back to paramiko SFTP")
        retry_base = 5
        for attempt in range(1, max_retries + 1):
            try:
                transport, sftp = self.connect_sftp()
                try:
                    self._ensure_remote_dirs(sftp, remote_path)
                    with open(local_path, "rb") as fl, sftp.file(remote_path, "wb") as fr:
                        fr.set_pipelined(True)
                        sent = 0
                        while True:
                            data = fl.read(1 << 20)
                            if not data:
                                break
                            fr.write(data)
                            sent += len(data)
                            if progress_cb is not None:
                                progress_cb(sent, file_size)
                    # Verify size on server
                    remote_stat = sftp.stat(remote_path)
                    if remote_stat.st_size != file_size:
                        raise OSError(
                            f"Size mismatch: local {file_size} vs remote {remote_stat.st_size}"
                        )
                    self.release_sftp(transport, sftp)
                    return
                except Exception:
                    try:
                        sftp.close()
                        transport.close()
                    except Exception:
                        pass
                    raise
            except Exception as e:
                if attempt == max_retries:
                    raise ConnectionError(f"Upload failed after {max_retries} attempts: {e}") from e
                time.sleep(retry_base * (2 ** (attempt - 1)))

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

    def file_size_sftp(self, remote_path: str) -> int:
        """Return remote file size in bytes, or -1 if not found."""
        try:
            transport, sftp = self.connect_sftp()
            try:
                attr = sftp.stat(remote_path)
                self.release_sftp(transport, sftp)
                return attr.st_size or 0
            except FileNotFoundError:
                self.release_sftp(transport, sftp)
                return -1
            except Exception:
                try:
                    sftp.close()
                    transport.close()
                except Exception:
                    pass
                return -1
        except Exception:
            return -1

    def md5_remote_sftp(self, remote_path: str) -> str | None:
        """Stream a remote file and return its MD5 hex digest, or None on error."""
        import hashlib

        try:
            transport, sftp = self.connect_sftp()
            try:
                h = hashlib.md5()
                with sftp.open(remote_path, "rb") as fh:
                    fh.prefetch()
                    while True:
                        chunk = fh.read(1024 * 1024)
                        if not chunk:
                            break
                        h.update(chunk)
                self.release_sftp(transport, sftp)
                return h.hexdigest()
            except Exception:
                try:
                    sftp.close()
                    transport.close()
                except Exception:
                    pass
                return None
        except Exception:
            return None

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

    @_retry(max_retries=2, base_delay=3)
    def kv_put_bulk(self, entries: list[dict]) -> None:
        """Write multiple KV entries in one API call (up to 10,000 pairs).

        Each entry: {"key": "cdn/path", "value": "seedbox/path"}.
        Uses the bulk write endpoint which has separate (higher) rate limits.
        """
        import requests

        if not entries:
            return
        url = f"{self._kv_base_url()}/bulk"
        resp = requests.put(
            url,
            headers={**self._kv_headers(), "Content-Type": "application/json"},
            json=entries,
            timeout=60,
        )
        if resp.status_code == 200 and resp.json().get("success"):
            return
        raise RuntimeError(f"KV bulk write failed: {resp.status_code} {resp.text}")

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
                url,
                headers=self._kv_headers(),
                params=params,
                timeout=30,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"KV list failed: {resp.status_code} {resp.text[:200]}")
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
                json.dumps(current, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass  # Don't fail the publish if backup fails

        self.upload_to_cdn(local_path, "manifest.json", force=True)

    # -- File checks ---------------------------------------------------------

    def sftp_stat(self, remote_path: str) -> tuple[bool, int]:
        """Check if a file exists on the seedbox via SFTP.

        Returns (exists, size_bytes).  Falls back to (False, 0) on error.
        """
        try:
            transport, sftp = self.connect_sftp()
            try:
                attr = sftp.stat(remote_path)
                self.release_sftp(transport, sftp)
                return True, attr.st_size or 0
            except FileNotFoundError:
                self.release_sftp(transport, sftp)
                return False, 0
            except Exception:
                try:
                    sftp.close()
                    transport.close()
                except Exception:
                    pass
                return False, 0
        except Exception:
            return False, 0

    @staticmethod
    def cdn_url_to_seedbox_path(url: str) -> str | None:
        """Convert a CDN URL to the corresponding seedbox path.

        E.g. https://cdn.hyperabyss.com/dlc/EP01.zip → files/sims4/dlc/EP01.zip
        """
        prefix = f"{CDN_DOMAIN}/"
        if url.startswith(prefix):
            cdn_path = url[len(prefix) :]
            return f"{SEEDBOX_BASE_DIR}/{cdn_path}"
        return None

    @staticmethod
    def head_check(url: str, timeout: int = 20) -> tuple[int, int]:
        """HEAD request a URL. Returns (status_code, content_length).

        NOTE: This will fail with HTTP 400 on protected CDN paths that
        require JWT auth.  Prefer sftp_stat() for audit operations.
        """
        import requests

        try:
            resp = requests.head(url, timeout=timeout, allow_redirects=True)
            size = int(resp.headers.get("Content-Length", 0))
            return resp.status_code, size
        except Exception:
            return 0, 0
