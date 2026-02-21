"""
DLC download manager — downloads, extracts, and registers individual DLC packs.

Each DLC goes through a 3-phase pipeline:
  1. Download: HTTP with resume + MD5 verification (reuses patch Downloader)
  2. Extract: standard zip → game directory
  3. Register: enable in crack config via DLCManager

ParallelDLCDownloader adds concurrent execution using a thread pool with
a shared token-bucket rate limiter for global speed control.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from ..patch.downloader import Downloader, ProgressCallback
from ..patch.manifest import DLCDownloadEntry
from ..core.exceptions import DownloadError
from ..core.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


class DLCDownloadState(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    REGISTERING = "registering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DLCDownloadTask:
    """Tracks the state of a single DLC download."""

    entry: DLCDownloadEntry
    state: DLCDownloadState = DLCDownloadState.PENDING
    progress_bytes: int = 0
    total_bytes: int = 0
    error: str = ""


# Callback: (dlc_id, state, progress_bytes, total_bytes, message)
DLCStatusCallback = Callable[
    [str, DLCDownloadState, int, int, str], None
]


class DLCDownloader:
    """Orchestrates downloading, extracting, and registering DLC packs."""

    def __init__(
        self,
        download_dir: str | Path,
        game_dir: str | Path,
        dlc_manager,  # DLCManager — avoids circular import
        cancel_event: threading.Event | None = None,
        downloader: Downloader | None = None,
        register_lock: threading.Lock | None = None,
    ):
        self.download_dir = Path(download_dir) / "dlcs"
        self.game_dir = Path(game_dir)
        self._dlc_manager = dlc_manager
        self._cancel = cancel_event or threading.Event()
        self._register_lock = register_lock
        self._downloader = downloader or Downloader(
            download_dir=self.download_dir,
            cancel_event=self._cancel,
        )

    def cancel(self):
        self._cancel.set()
        self._downloader.cancel()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    # ── Single DLC ──────────────────────────────────────────────

    def download_dlc(
        self,
        entry: DLCDownloadEntry,
        progress: DLCStatusCallback | None = None,
    ) -> DLCDownloadTask:
        """Download, extract, and register a single DLC."""
        task = DLCDownloadTask(entry=entry, total_bytes=entry.size)

        try:
            # Phase 1: Download
            task.state = DLCDownloadState.DOWNLOADING
            if progress:
                progress(
                    entry.dlc_id, task.state, 0, entry.size,
                    f"Downloading {entry.dlc_id}...",
                )

            file_entry = entry.to_file_entry()

            def dl_progress(downloaded: int, total: int, filename: str):
                task.progress_bytes = downloaded
                task.total_bytes = total
                if progress:
                    progress(
                        entry.dlc_id, DLCDownloadState.DOWNLOADING,
                        downloaded, total, filename,
                    )

            result = self._downloader.download_file(
                file_entry, progress=dl_progress,
            )

            if self.cancelled:
                task.state = DLCDownloadState.CANCELLED
                return task

            # Phase 2: Extract to game directory
            task.state = DLCDownloadState.EXTRACTING
            if progress:
                progress(
                    entry.dlc_id, task.state, 0, 0,
                    f"Extracting {entry.dlc_id}...",
                )

            self._extract_zip(result.path, entry.dlc_id)

            # Validate extraction — ensure required files exist
            expected = self.game_dir / entry.dlc_id / "SimulationFullBuild0.package"
            if not expected.is_file():
                raise DownloadError(
                    f"{entry.dlc_id} extraction incomplete: "
                    f"SimulationFullBuild0.package not found"
                )

            if self.cancelled:
                task.state = DLCDownloadState.CANCELLED
                return task

            # Phase 3: Register in crack config
            task.state = DLCDownloadState.REGISTERING
            if progress:
                progress(
                    entry.dlc_id, task.state, 0, 0,
                    f"Registering {entry.dlc_id}...",
                )

            registered = self._register_dlc(entry.dlc_id)

            task.state = DLCDownloadState.COMPLETED
            if registered:
                msg = f"{entry.dlc_id} installed successfully"
            else:
                msg = (
                    f"{entry.dlc_id} extracted but registration failed "
                    f"\u2014 use Apply Changes to register manually"
                )
            if progress:
                progress(
                    entry.dlc_id, task.state, entry.size, entry.size, msg,
                )

        except DownloadError as e:
            task.state = DLCDownloadState.FAILED
            task.error = str(e)
            if progress:
                progress(entry.dlc_id, task.state, 0, 0, str(e))
        except Exception as e:
            task.state = DLCDownloadState.FAILED
            task.error = str(e)
            logger.exception("DLC download failed for %s", entry.dlc_id)
            if progress:
                progress(entry.dlc_id, task.state, 0, 0, str(e))

        return task

    # ── Multiple DLCs ───────────────────────────────────────────

    def download_multiple(
        self,
        entries: list[DLCDownloadEntry],
        progress: DLCStatusCallback | None = None,
    ) -> list[DLCDownloadTask]:
        """Download multiple DLCs sequentially."""
        results = []
        for entry in entries:
            if self.cancelled:
                break
            task = self.download_dlc(entry, progress=progress)
            results.append(task)
            # Stop on failure unless cancelled
            if task.state == DLCDownloadState.FAILED:
                continue  # try next DLC anyway
        return results

    # ── Extraction ──────────────────────────────────────────────

    def _extract_zip(self, archive_path: Path, dlc_id: str):
        """Extract a standard zip archive to the game directory."""
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                game_dir_resolved = self.game_dir.resolve()
                for member in zf.namelist():
                    if self.cancelled:
                        raise DownloadError("Extraction cancelled.")
                    # Path traversal protection
                    target = (self.game_dir / member).resolve()
                    if not str(target).startswith(str(game_dir_resolved)):
                        logger.warning("Skipping unsafe zip path: %s", member)
                        continue
                    zf.extract(member, self.game_dir)
        except zipfile.BadZipFile as e:
            raise DownloadError(
                f"Corrupt archive for {dlc_id}: {e}"
            ) from e
        except OSError as e:
            raise DownloadError(
                f"Extraction failed for {dlc_id}: {e}"
            ) from e

    # ── Registration ────────────────────────────────────────────

    def _register_dlc(self, dlc_id: str) -> bool:
        """Enable the DLC in the crack config. Returns True on success.

        If a ``register_lock`` was provided at construction, the lock is
        held for the entire read-modify-write cycle to prevent concurrent
        workers from clobbering each other's config writes.
        """
        lock = self._register_lock
        if lock:
            lock.acquire()
        try:
            states = self._dlc_manager.get_dlc_states(self.game_dir)
            enabled_set = set()
            for state in states:
                if state.enabled is True:
                    enabled_set.add(state.dlc.id)
                elif state.dlc.id == dlc_id and state.installed:
                    enabled_set.add(dlc_id)
            self._dlc_manager.apply_changes(self.game_dir, enabled_set)
            return True
        except Exception as e:
            # Registration failure is non-fatal — files are on disk
            logger.warning("Could not register DLC %s: %s", dlc_id, e)
            return False
        finally:
            if lock:
                lock.release()

    # ── Cleanup ─────────────────────────────────────────────────

    def close(self):
        self._downloader.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ParallelDLCDownloader:
    """Orchestrates parallel DLC downloads with shared rate limiting.

    Each worker thread gets its own ``Downloader`` (and ``requests.Session``)
    but shares a single ``TokenBucketRateLimiter`` for global speed control
    and a ``threading.Lock`` for serialising crack-config writes.
    """

    def __init__(
        self,
        download_dir: str | Path,
        game_dir: str | Path,
        dlc_manager,
        cancel_event: threading.Event | None = None,
        max_workers: int = 3,
        speed_limit_bytes: int = 0,
    ):
        self._download_dir = Path(download_dir)
        self._dlcs_dir = self._download_dir / "dlcs"
        self._game_dir = Path(game_dir)
        self._dlc_manager = dlc_manager
        self._cancel = cancel_event or threading.Event()
        self._max_workers = max(1, min(max_workers, 10))
        self._rate_limiter = TokenBucketRateLimiter(speed_limit_bytes)
        self._register_lock = threading.Lock()

    def set_speed_limit(self, bytes_per_sec: int) -> None:
        """Update the global speed limit at runtime."""
        self._rate_limiter.set_limit(bytes_per_sec)

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def download_parallel(
        self,
        entries: list[DLCDownloadEntry],
        progress: DLCStatusCallback | None = None,
    ) -> list[DLCDownloadTask]:
        """Download multiple DLCs concurrently using a thread pool.

        Returns a list of ``DLCDownloadTask`` objects (one per entry),
        including any that failed or were cancelled.
        """
        results: list[DLCDownloadTask] = []
        results_lock = threading.Lock()

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self._max_workers,
        ) as pool:
            future_to_entry: dict[concurrent.futures.Future, DLCDownloadEntry] = {}
            for entry in entries:
                if self._cancel.is_set():
                    break
                future = pool.submit(self._download_one, entry, progress)
                future_to_entry[future] = entry

            for future in concurrent.futures.as_completed(future_to_entry):
                entry = future_to_entry[future]
                try:
                    task = future.result()
                except Exception as e:
                    task = DLCDownloadTask(
                        entry=entry,
                        state=DLCDownloadState.FAILED,
                        error=str(e),
                    )
                    if progress:
                        progress(
                            entry.dlc_id, DLCDownloadState.FAILED,
                            0, 0, str(e),
                        )
                with results_lock:
                    results.append(task)

        return results

    def _download_one(
        self,
        entry: DLCDownloadEntry,
        progress: DLCStatusCallback | None,
    ) -> DLCDownloadTask:
        """Download a single DLC in its own thread."""
        # Each worker gets its own Downloader + Session (not thread-safe to share)
        dl = Downloader(
            download_dir=self._dlcs_dir,
            cancel_event=self._cancel,
            rate_limiter=self._rate_limiter,
        )
        worker = DLCDownloader(
            download_dir=self._download_dir,
            game_dir=self._game_dir,
            dlc_manager=self._dlc_manager,
            cancel_event=self._cancel,
            downloader=dl,
            register_lock=self._register_lock,
        )
        try:
            return worker.download_dlc(entry, progress=progress)
        finally:
            dl.close()

    def close(self) -> None:
        """No persistent resources to clean up (workers close their own)."""
