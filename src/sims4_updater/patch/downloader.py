"""
Download manager with resume, progress callbacks, MD5 verification, and cancellation.
"""

from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import requests
import requests.adapters
import ssl
import urllib3

from .manifest import FileEntry
from ..core.exceptions import DownloadError, IntegrityError


# Type alias for progress callbacks: (bytes_downloaded, total_bytes, filename)
ProgressCallback = Callable[[int, int, str], None]

CHUNK_SIZE = 65536
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 60


@dataclass
class DownloadResult:
    """Result of a single file download."""

    entry: FileEntry
    path: Path
    verified: bool = False
    resumed: bool = False
    bytes_downloaded: int = 0


class Downloader:
    """Manages file downloads with resume, verification, and cancellation."""

    def __init__(
        self,
        download_dir: str | Path,
        cancel_event: threading.Event | None = None,
        rate_limiter: "TokenBucketRateLimiter | None" = None,
    ):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._cancel = cancel_event or threading.Event()
        self._session: requests.Session | None = None
        self._rate_limiter = rate_limiter

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = _create_session()
        return self._session

    def cancel(self):
        """Signal cancellation of all ongoing downloads."""
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def download_file(
        self,
        entry: FileEntry,
        progress: ProgressCallback | None = None,
        subdir: str = "",
    ) -> DownloadResult:
        """Download a single file with resume support and MD5 verification.

        Args:
            entry: FileEntry describing the download.
            progress: Optional callback(bytes_downloaded, total_bytes, filename).
            subdir: Optional subdirectory within download_dir.

        Returns:
            DownloadResult with the local path.

        Raises:
            DownloadError: On network or I/O errors.
            IntegrityError: If MD5 verification fails.
        """
        if self.cancelled:
            raise DownloadError("Download cancelled.")

        dest_dir = self.download_dir / subdir if subdir else self.download_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        final_path = dest_dir / entry.filename
        partial_path = final_path.with_suffix(final_path.suffix + ".partial")

        # If final file exists and MD5 matches, skip download
        if final_path.is_file() and entry.md5:
            if _verify_md5(final_path, entry.md5):
                if progress:
                    progress(entry.size, entry.size, entry.filename)
                return DownloadResult(
                    entry=entry,
                    path=final_path,
                    verified=True,
                    resumed=False,
                    bytes_downloaded=0,
                )

        # Resume support
        resume_from = 0
        if partial_path.is_file():
            resume_from = partial_path.stat().st_size

        try:
            headers = {}
            if resume_from > 0:
                headers["Range"] = f"bytes={resume_from}-"

            resp = self.session.get(
                entry.url,
                headers=headers,
                stream=True,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            resp.raise_for_status()

            # Determine total size and write mode
            if resp.status_code == 206:
                # Partial content — resume
                content_range = resp.headers.get("Content-Range", "")
                if "/" in content_range:
                    total_size = int(content_range.rsplit("/", 1)[1])
                else:
                    total_size = resume_from + int(
                        resp.headers.get("Content-Length", 0)
                    )
                mode = "ab"
                resumed = True
            else:
                # Full download (200 or server doesn't support Range)
                total_size = int(resp.headers.get("Content-Length", 0)) or entry.size
                mode = "wb"
                resume_from = 0
                resumed = False

            downloaded = resume_from
            if progress:
                progress(downloaded, total_size, entry.filename)

            with open(partial_path, mode) as f:
                for chunk in resp.iter_content(CHUNK_SIZE):
                    if self.cancelled:
                        raise DownloadError("Download cancelled.")
                    f.write(chunk)
                    if self._rate_limiter:
                        self._rate_limiter.acquire(len(chunk))
                    downloaded += len(chunk)
                    if progress:
                        progress(downloaded, total_size, entry.filename)

        except DownloadError:
            raise
        except requests.RequestException as e:
            raise DownloadError(
                f"Failed to download {entry.filename}: {e}"
            ) from e
        except OSError as e:
            raise DownloadError(
                f"I/O error writing {entry.filename}: {e}"
            ) from e

        # Verify MD5 if provided
        verified = False
        if entry.md5:
            if not _verify_md5(partial_path, entry.md5):
                partial_path.unlink(missing_ok=True)
                raise IntegrityError(
                    f"MD5 mismatch for {entry.filename}.\n"
                    f"Expected: {entry.md5}\n"
                    f"The file may be corrupted or tampered with."
                )
            verified = True

        # Rename partial to final
        partial_path.replace(final_path)

        return DownloadResult(
            entry=entry,
            path=final_path,
            verified=verified,
            resumed=resumed,
            bytes_downloaded=downloaded - resume_from,
        )

    def download_files(
        self,
        entries: list[FileEntry],
        progress: ProgressCallback | None = None,
        subdir: str = "",
    ) -> list[DownloadResult]:
        """Download multiple files sequentially.

        The progress callback receives cumulative bytes across all files.
        """
        total_size = sum(e.size for e in entries)
        cumulative = 0
        results = []

        for entry in entries:
            if self.cancelled:
                raise DownloadError("Download cancelled.")

            base = cumulative

            def file_progress(downloaded: int, file_total: int, filename: str):
                if progress:
                    progress(base + downloaded, total_size, filename)

            result = self.download_file(entry, progress=file_progress, subdir=subdir)
            cumulative += entry.size
            results.append(result)

        return results

    def close(self):
        """Close the HTTP session."""
        if self._session:
            self._session.close()
            self._session = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _create_session() -> requests.Session:
    """Create a requests session with retry, timeout, and legacy TLS support."""
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT

    session = requests.Session()
    retry = requests.adapters.Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = _TimeoutSSLAdapter(ctx, retry=retry)
    session.mount("https://", adapter)
    session.mount("http://", requests.adapters.HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "Sims4Updater/2.0"
    return session


class _TimeoutSSLAdapter(requests.adapters.HTTPAdapter):
    """HTTPAdapter with custom SSL context and default timeout."""

    def __init__(self, ssl_context, **kwargs):
        self._ssl_context = ssl_context
        super().__init__(**kwargs)

    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = (CONNECT_TIMEOUT, READ_TIMEOUT)
        return super().send(request, **kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        self.poolmanager = urllib3.poolmanager.PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=self._ssl_context,
        )


def _verify_md5(path: Path, expected: str) -> bool:
    """Verify a file's MD5 hash."""
    m = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            m.update(chunk)
    return m.hexdigest().upper() == expected.upper()
