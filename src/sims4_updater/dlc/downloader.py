"""
DLC download manager — downloads, extracts, and registers individual DLC packs.

Each DLC goes through a 3-phase pipeline:
  1. Download: HTTP with resume + MD5 verification (reuses patch Downloader)
  2. Extract: standard zip → game directory
  3. Register: enable in crack config via DLCManager

ParallelDLCDownloader adds concurrent execution using a thread pool with
a shared token-bucket rate limiter for global speed control, and supports
pause/resume via a shared ``proceed`` event.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import logging
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..core.exceptions import DownloadError
from ..core.rate_limiter import TokenBucketRateLimiter
from ..patch.downloader import Downloader
from ..patch.manifest import DLCDownloadEntry

logger = logging.getLogger(__name__)


class DLCDownloadState(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    REGISTERING = "registering"
    EXTRACTED = "extracted"
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
DLCStatusCallback = Callable[[str, DLCDownloadState, int, int, str], None]


class DLCDownloader:
    """Orchestrates downloading, extracting, and registering DLC packs."""

    def __init__(
        self,
        download_dir: str | Path,
        game_dir: str | Path,
        dlc_manager,  # DLCManager — avoids circular import
        cancel_event: threading.Event | None = None,
        proceed_event: threading.Event | None = None,
        downloader: Downloader | None = None,
        register_lock: threading.Lock | None = None,
    ):
        self.download_dir = Path(download_dir) / "dlcs"
        self.game_dir = Path(game_dir)
        self._dlc_manager = dlc_manager
        self._cancel = cancel_event or threading.Event()
        self._proceed = proceed_event  # None = no pause support
        self._register_lock = register_lock
        self._downloader = downloader or Downloader(
            download_dir=self.download_dir,
            cancel_event=self._cancel,
            proceed_event=self._proceed,
        )

    def cancel(self):
        self._cancel.set()
        self._downloader.cancel()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def _wait_if_paused(self) -> None:
        """Block until proceed event is set (unpaused). No-op if no event."""
        if self._proceed is not None:
            self._proceed.wait()

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
            self._wait_if_paused()
            if self.cancelled:
                task.state = DLCDownloadState.CANCELLED
                return task

            task.state = DLCDownloadState.DOWNLOADING
            if progress:
                progress(
                    entry.dlc_id,
                    task.state,
                    0,
                    entry.size,
                    f"Downloading {entry.dlc_id}...",
                )

            file_entry = entry.to_file_entry()

            def dl_progress(downloaded: int, total: int, filename: str):
                task.progress_bytes = downloaded
                task.total_bytes = total
                if progress:
                    progress(
                        entry.dlc_id,
                        DLCDownloadState.DOWNLOADING,
                        downloaded,
                        total,
                        filename,
                    )

            result = self._downloader.download_file(
                file_entry,
                progress=dl_progress,
            )

            if self.cancelled:
                task.state = DLCDownloadState.CANCELLED
                return task

            # Phase 2: Extract to game directory
            self._wait_if_paused()
            if self.cancelled:
                task.state = DLCDownloadState.CANCELLED
                return task

            task.state = DLCDownloadState.EXTRACTING
            if progress:
                progress(
                    entry.dlc_id,
                    task.state,
                    0,
                    0,
                    f"Extracting {entry.dlc_id}...",
                )

            extracted_files = self._extract_zip(result.path, entry.dlc_id)

            # Clean up downloaded ZIP to save disk space
            try:
                result.path.unlink(missing_ok=True)
                logger.info("Deleted archive: %s", result.path)
            except OSError as e:
                logger.warning("Could not delete archive %s: %s", result.path, e)

            # Validate extraction — ensure required files exist
            expected = self.game_dir / entry.dlc_id / "SimulationFullBuild0.package"
            if not expected.is_file():
                raise DownloadError(
                    f"{entry.dlc_id} extraction incomplete: SimulationFullBuild0.package not found"
                )

            if self.cancelled:
                self._cleanup_extracted(extracted_files)
                task.state = DLCDownloadState.CANCELLED
                return task

            # Phase 3: Register in crack config
            self._wait_if_paused()
            if self.cancelled:
                task.state = DLCDownloadState.CANCELLED
                return task

            task.state = DLCDownloadState.REGISTERING
            if progress:
                progress(
                    entry.dlc_id,
                    task.state,
                    0,
                    0,
                    f"Registering {entry.dlc_id}...",
                )

            registered = self._register_dlc(entry.dlc_id)

            if registered:
                task.state = DLCDownloadState.COMPLETED
                msg = f"{entry.dlc_id} installed successfully"
            else:
                task.state = DLCDownloadState.EXTRACTED
                msg = f"{entry.dlc_id} extracted but registration failed \u2014 enable in DLC tab"
            if progress:
                progress(
                    entry.dlc_id,
                    task.state,
                    entry.size,
                    entry.size,
                    msg,
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

    def _extract_zip(self, archive_path: Path, dlc_id: str) -> list[Path]:
        """Extract a standard zip archive to the game directory.

        Returns list of extracted file paths for cleanup on cancel.
        """
        extracted: list[Path] = []
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                game_dir_resolved = self.game_dir.resolve()
                for member in zf.namelist():
                    if self.cancelled:
                        self._cleanup_extracted(extracted)
                        raise DownloadError("Extraction cancelled.")
                    # Path traversal protection
                    target = (self.game_dir / member).resolve()
                    if not str(target).startswith(str(game_dir_resolved)):
                        logger.warning("Skipping unsafe zip path: %s", member)
                        continue
                    zf.extract(member, self.game_dir)
                    if target.is_file():
                        extracted.append(target)
        except zipfile.BadZipFile as e:
            raise DownloadError(f"Corrupt archive for {dlc_id}: {e}") from e
        except DownloadError:
            raise
        except OSError as e:
            raise DownloadError(f"Extraction failed for {dlc_id}: {e}") from e
        return extracted

    def _cleanup_extracted(self, files: list[Path]) -> None:
        """Remove extracted files on cancel/failure (best-effort)."""
        for f in reversed(files):
            with contextlib.suppress(OSError):
                f.unlink(missing_ok=True)
        # Remove empty directories left behind
        dirs = sorted(
            {f.parent for f in files},
            key=lambda p: len(p.parts),
            reverse=True,
        )
        for d in dirs:
            try:
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            except OSError:
                pass

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
    but shares a single ``TokenBucketRateLimiter`` for global speed control,
    a ``threading.Lock`` for serialising crack-config writes, and a
    ``proceed`` event for pause/resume control.
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
        self._proceed = threading.Event()
        self._proceed.set()  # start in running (unpaused) state
        self._max_workers = max(1, min(max_workers, 10))
        self._rate_limiter = TokenBucketRateLimiter(speed_limit_bytes)
        self._register_lock = threading.Lock()

    def set_speed_limit(self, bytes_per_sec: int) -> None:
        """Update the global speed limit at runtime."""
        self._rate_limiter.set_limit(bytes_per_sec)

    def pause(self) -> None:
        """Pause all workers at next checkpoint."""
        self._proceed.clear()

    def resume(self) -> None:
        """Resume paused workers."""
        self._proceed.set()

    @property
    def paused(self) -> bool:
        return not self._proceed.is_set()

    def cancel(self) -> None:
        self._cancel.set()
        self._proceed.set()  # unblock any paused workers so they can exit

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
                            entry.dlc_id,
                            DLCDownloadState.FAILED,
                            0,
                            0,
                            str(e),
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
            proceed_event=self._proceed,
        )
        worker = DLCDownloader(
            download_dir=self._download_dir,
            game_dir=self._game_dir,
            dlc_manager=self._dlc_manager,
            cancel_event=self._cancel,
            proceed_event=self._proceed,
            downloader=dl,
            register_lock=self._register_lock,
        )
        try:
            return worker.download_dlc(entry, progress=progress)
        finally:
            dl.close()

    def close(self) -> None:
        """No persistent resources to clean up (workers close their own)."""
