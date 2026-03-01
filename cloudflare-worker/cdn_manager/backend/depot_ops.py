"""
Steam Depot Downloader operations — download game versions, batch pipeline.

Wraps the DepotDownloader CLI tool to download specific Sims 4 versions
from Steam depots by manifest ID. Provides a batch pipeline that downloads
versions, creates delta patches, and uploads them to CDN.

Adapted from src/sims4_updater/language/steam.py — reuses the proven
queue-based stream reader and stall-cycle prompt detection patterns.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Event

from .connection import SEEDBOX_BASE_DIR

logger = logging.getLogger(__name__)

SIMS4_APP_ID = "1222670"
DEPOT_DOWNLOADER_REPO = "SteamRE/DepotDownloader"
DEPOT_DOWNLOADER_ASSET = "DepotDownloader-windows-x64.zip"

LogCallback = Callable[[str, str], None]  # (message, level)


# -- Data Classes -----------------------------------------------------------


@dataclass
class DepotManifestEntry:
    """A mapping from game version to Steam depot manifest ID."""

    version: str  # e.g. "1.99.305.1020"
    depot_id: str  # e.g. "1222671"
    manifest_id: str  # e.g. "8923489234812348"
    date_added: str = ""
    download_dir: str = ""  # path where version was downloaded
    downloaded: bool = False
    registered: bool = False  # whether registered in PatchFrame version registry


@dataclass
class DepotDownloadResult:
    """Result of a single depot download."""

    success: bool
    exit_code: int = 0
    output_dir: str = ""
    error: str = ""


@dataclass
class PipelineState:
    """Persistent state for a batch pipeline run, enabling resume."""

    versions: list[str] = field(default_factory=list)
    manifest_ids: dict[str, str] = field(default_factory=dict)
    direction: str = "both"  # "forward", "backward", "both"
    completed_downloads: list[str] = field(default_factory=list)
    completed_patches: list[str] = field(default_factory=list)  # "from->to"
    completed_uploads: list[str] = field(default_factory=list)  # "from->to"
    upload_manifest_entries: list[dict] = field(default_factory=list)
    current_phase: str = "idle"
    current_item: str = ""
    failed_items: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Summary of a completed pipeline run."""

    downloads: int = 0
    patches_created: int = 0
    patches_uploaded: int = 0
    manifest_updated: bool = False
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


@dataclass
class UploadJob:
    """A patch file queued for upload to CDN."""

    pair_key: str  # "from->to"
    patch_path: Path
    from_version: str
    to_version: str


# -- Depot Registry Persistence ---------------------------------------------


def load_depot_registry(config_path: Path) -> list[DepotManifestEntry]:
    """Load the depot manifest registry from the config JSON."""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        raw = data.get("depot_manifest_registry", [])
        entries = []
        for item in raw:
            if isinstance(item, dict) and "version" in item and "manifest_id" in item:
                entries.append(
                    DepotManifestEntry(
                        version=item["version"],
                        depot_id=item.get("depot_id", "1222671"),
                        manifest_id=item["manifest_id"],
                        date_added=item.get("date_added", ""),
                        download_dir=item.get("download_dir", ""),
                        downloaded=item.get("downloaded", False),
                        registered=item.get("registered", False),
                    )
                )
        return entries
    except (json.JSONDecodeError, OSError, KeyError):
        return []


def save_depot_registry(config_path: Path, registry: list[DepotManifestEntry]) -> None:
    """Save the depot manifest registry to the config JSON."""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {}
    data["depot_manifest_registry"] = [asdict(e) for e in registry]
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# -- Pipeline State Persistence ---------------------------------------------


def _pipeline_state_path(config_dir: Path) -> Path:
    return config_dir / "depot_pipeline_state.json"


def load_pipeline_state(config_dir: Path) -> PipelineState | None:
    """Load saved pipeline state for resume. Returns None if no state exists."""
    path = _pipeline_state_path(config_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PipelineState(
            versions=data.get("versions", []),
            manifest_ids=data.get("manifest_ids", {}),
            direction=data.get("direction", "both"),
            completed_downloads=data.get("completed_downloads", []),
            completed_patches=data.get("completed_patches", []),
            completed_uploads=data.get("completed_uploads", []),
            upload_manifest_entries=data.get("upload_manifest_entries", []),
            current_phase=data.get("current_phase", "idle"),
            current_item=data.get("current_item", ""),
            failed_items=data.get("failed_items", []),
        )
    except (json.JSONDecodeError, OSError):
        return None


def save_pipeline_state(config_dir: Path, state: PipelineState) -> None:
    """Persist pipeline state for resume capability."""
    path = _pipeline_state_path(config_dir)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def clear_pipeline_state(config_dir: Path) -> None:
    """Remove pipeline state file after successful completion."""
    _pipeline_state_path(config_dir).unlink(missing_ok=True)


# -- DepotDownloader Wrapper ------------------------------------------------


class DepotDownloader:
    """Manages the DepotDownloader CLI tool and runs game version downloads.

    Adapted from SteamLanguageDownloader — same queue-based stream reader
    and stall-cycle prompt detection, but generalized for depot downloads
    rather than language-specific operations.
    """

    def __init__(self, tool_dir: Path, cancel_event: Event | None = None):
        self._tool_dir = tool_dir
        self._cancel_event = cancel_event

    # -- Tool Management ----------------------------------------------------

    def get_tool_path(self) -> Path:
        return self._tool_dir / "DepotDownloader.exe"

    def is_tool_installed(self) -> bool:
        return self.get_tool_path().is_file()

    def install_tool(self, log: LogCallback | None = None) -> bool:
        """Download DepotDownloader from GitHub releases. Returns True on success."""
        if log is None:

            def log(_msg, _lvl="info"):
                pass

        log("Fetching latest DepotDownloader release from GitHub...", "info")

        try:
            api_url = f"https://api.github.com/repos/{DEPOT_DOWNLOADER_REPO}/releases/latest"
            req = urllib.request.Request(
                api_url,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                release = json.loads(resp.read().decode("utf-8"))

            download_url = None
            asset_size = 0
            for asset in release.get("assets", []):
                if DEPOT_DOWNLOADER_ASSET in asset["name"]:
                    download_url = asset["browser_download_url"]
                    asset_size = asset.get("size", 0)
                    break

            if not download_url:
                log(f"Could not find {DEPOT_DOWNLOADER_ASSET} in release.", "error")
                return False

            if not download_url.startswith("https://"):
                log("Download URL is not HTTPS — aborting for security.", "error")
                return False

            version = release.get("tag_name", "unknown")
            size_mb = asset_size / (1024 * 1024)
            log(f"Downloading DepotDownloader {version} ({size_mb:.1f} MB)...", "info")

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            try:
                urllib.request.urlretrieve(download_url, tmp_path)
            except Exception as e:
                tmp_path.unlink(missing_ok=True)
                log(f"Download failed: {e}", "error")
                return False

            log("Extracting DepotDownloader...", "info")
            self._tool_dir.mkdir(parents=True, exist_ok=True)

            try:
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    tool_resolved = self._tool_dir.resolve()
                    for member in zf.namelist():
                        target = (self._tool_dir / member).resolve()
                        if not target.is_relative_to(tool_resolved):
                            log(f"Skipping unsafe zip path: {member}", "warning")
                            continue
                        zf.extract(member, self._tool_dir)
            except zipfile.BadZipFile as e:
                log(f"Corrupt download: {e}", "error")
                return False
            finally:
                tmp_path.unlink(missing_ok=True)

            if not self.is_tool_installed():
                log("DepotDownloader.exe not found after extraction.", "error")
                return False

            log(f"DepotDownloader {version} installed successfully.", "success")
            return True

        except Exception as e:
            log(f"Failed to install DepotDownloader: {e}", "error")
            return False

    # -- Single Version Download --------------------------------------------

    def download_version(
        self,
        username: str,
        password: str | None = None,
        auth_code: str | None = None,
        app_id: str = SIMS4_APP_ID,
        depot_id: str = "1222671",
        manifest_id: str = "",
        output_dir: Path | None = None,
        *,
        log: LogCallback | None = None,
        ask_password: Callable[[], str | None] | None = None,
        ask_auth_code: Callable[[], str | None] | None = None,
        on_progress: Callable[[float, str], None] | None = None,
    ) -> DepotDownloadResult:
        """Download a specific game version from Steam.

        Args:
            username: Steam username.
            password: Steam password (None to use cached auth).
            auth_code: Steam Guard / 2FA code (None if not needed).
            app_id: Steam app ID (default: Sims 4).
            depot_id: Steam depot ID (default: Sims 4 main depot).
            manifest_id: Steam manifest ID for the specific version.
            output_dir: Directory to download files into.
            log: Logging callback ``(message, level)``.
            ask_password: Callback to ask user for password interactively.
            ask_auth_code: Callback to ask user for 2FA code interactively.
            on_progress: Progress callback ``(pct_0_to_100, detail_text)``.

        Returns:
            DepotDownloadResult with success status.
        """
        if log is None:

            def log(_msg, _lvl="info"):
                pass

        log(f"download_version() called: manifest={manifest_id!r}, user={username!r}", "info")
        log(f"  password={'set' if password else 'not set'}, tool={self.get_tool_path()}", "info")

        if not self.is_tool_installed():
            log("DepotDownloader not installed — click 'Install Tool' first.", "error")
            return DepotDownloadResult(success=False, error="DepotDownloader not installed.")

        if not manifest_id.strip():
            log("Manifest ID is required.", "error")
            return DepotDownloadResult(success=False, error="Manifest ID is required.")

        if output_dir is None:
            log("Output directory is required.", "error")
            return DepotDownloadResult(success=False, error="Output directory is required.")

        log(f"  output_dir={output_dir}", "info")
        output_dir.mkdir(parents=True, exist_ok=True)
        log("  output_dir created OK", "info")

        # If no password provided, ask upfront rather than relying on
        # interactive stdin detection (which fails without a console).
        if not password and ask_password:
            log("Steam password required — opening dialog...", "info")
            password = ask_password()
            if not password:
                log("No password provided.", "warning")
                return DepotDownloadResult(success=False, error="No password provided")
            log("Password received from dialog.", "info")

        args = [
            str(self.get_tool_path()),
            "-app",
            app_id,
            "-depot",
            depot_id,
            "-manifest",
            manifest_id.strip(),
            "-username",
            username,
            "-remember-password",
            "-dir",
            str(output_dir),
        ]

        # Pass password as CLI arg so DepotDownloader doesn't need
        # an interactive prompt (which requires a console).
        if password:
            args.extend(["-password", password])

        log(f"Downloading depot {depot_id} manifest {manifest_id[:16]}...", "info")
        log(f"Output: {output_dir}", "info")
        log(f"Tool: {self.get_tool_path()}", "info")

        exit_code, output = self._run_depot_downloader(
            args,
            password=None,  # Already in CLI args
            auth_code=auth_code,
            log=log,
            ask_password=None,  # Already handled above
            ask_auth_code=ask_auth_code,
            on_progress=on_progress,
        )

        if self._cancel_event and self._cancel_event.is_set():
            return DepotDownloadResult(success=False, exit_code=-1, error="Cancelled")

        if exit_code != 0:
            output_lower = output.lower()
            if "not available from this account" in output_lower:
                error = "Content not available on this Steam account."
            elif "invalid password" in output_lower:
                error = "Invalid Steam password."
            else:
                error = f"DepotDownloader exited with code {exit_code}"
            log(error, "error")
            return DepotDownloadResult(success=False, exit_code=exit_code, error=error)

        log("Download completed successfully.", "success")
        return DepotDownloadResult(
            success=True,
            exit_code=0,
            output_dir=str(output_dir),
        )

    # -- Internal: Subprocess Runner ----------------------------------------

    @staticmethod
    def _stream_reader(stream, data_queue: queue.Queue):
        """Read from a stream in a background thread.

        Uses read1() to read whatever is available (up to 4096 bytes)
        without waiting for a full buffer. Each call does at most one
        raw read on the pipe, so it returns as soon as any data arrives.
        """
        try:
            while True:
                chunk = stream.read1(4096)
                if not chunk:
                    break
                data_queue.put(chunk)
        except (OSError, ValueError):
            pass

    def _run_depot_downloader(
        self,
        args: list[str],
        password: str | None = None,
        auth_code: str | None = None,
        log: LogCallback | None = None,
        ask_password: Callable[[], str | None] | None = None,
        ask_auth_code: Callable[[], str | None] | None = None,
        on_progress: Callable[[float, str], None] | None = None,
    ) -> tuple[int, str]:
        """Run DepotDownloader, handling interactive auth prompts.

        Uses background reader threads for stdout and stderr so the
        main loop never blocks on pipe reads. This is critical because
        DepotDownloader writes interactive prompts (password, 2FA)
        without a trailing newline — a blocking read would deadlock.

        Returns (exit_code, combined_output).
        """
        if log is None:

            def log(_msg, _lvl="info"):
                pass

        # Build Popen kwargs — suppress console window on Windows.
        # Use CREATE_NO_WINDOW (not CREATE_NEW_CONSOLE) so that
        # stdout/stderr/stdin stay connected to the PIPE handles.
        # CREATE_NEW_CONSOLE allocates a separate console which
        # can intercept .NET output away from our pipes.
        popen_kwargs: dict = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.PIPE,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        # Log the command (mask password)
        display_args = list(args)
        for i, a in enumerate(display_args):
            if a == "-password" and i + 1 < len(display_args):
                display_args[i + 1] = "***"
        log(f"Running: {' '.join(display_args)}", "info")

        try:
            proc = subprocess.Popen(args, **popen_kwargs)
        except FileNotFoundError:
            log("DepotDownloader executable not found!", "error")
            return (-1, "DepotDownloader executable not found")
        except OSError as e:
            log(f"Failed to start DepotDownloader: {e}", "error")
            return (-1, f"Process start failed: {e}")

        log(f"Process started (PID {proc.pid})", "info")
        output_lines: list[str] = []
        password_sent = False
        auth_code_sent = False
        buf = b""
        stall_cycles = 0

        # Start background reader threads
        stdout_q: queue.Queue[bytes] = queue.Queue()
        stderr_q: queue.Queue[bytes] = queue.Queue()

        stdout_thread = threading.Thread(
            target=self._stream_reader,
            args=(proc.stdout, stdout_q),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._stream_reader,
            args=(proc.stderr, stderr_q),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        try:
            while proc.poll() is None or not stdout_q.empty() or not stderr_q.empty():
                if self._cancel_event and self._cancel_event.is_set():
                    self._interrupt_process(proc)
                    return (-1, "Cancelled")

                # Drain both queues into buffer (non-blocking)
                got_data = False
                while not stdout_q.empty():
                    with contextlib.suppress(queue.Empty):
                        buf += stdout_q.get_nowait()
                        got_data = True
                while not stderr_q.empty():
                    with contextlib.suppress(queue.Empty):
                        buf += stderr_q.get_nowait()
                        got_data = True

                if got_data:
                    stall_cycles = 0
                else:
                    stall_cycles += 1

                # Process complete lines
                while b"\n" in buf:
                    line_bytes, buf = buf.split(b"\n", 1)
                    line_bytes = line_bytes.replace(b"\r", b"")
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if line:
                        output_lines.append(line)
                        self._handle_output_line(line, log)
                        # Extract download percentage for progress callback
                        if on_progress:
                            m = re.search(r"(\d+\.?\d*)%", line)
                            if m:
                                on_progress(float(m.group(1)), line)

                # Check \r-delimited progress in partial buffer (ANSI
                # progress bars overwrite the line with \r without \n).
                if on_progress and b"\r" in buf:
                    segments = buf.split(b"\r")
                    latest = segments[-1].decode("utf-8", errors="replace").strip()
                    if latest:
                        m = re.search(r"(\d+\.?\d*)%", latest)
                        if m:
                            on_progress(float(m.group(1)), latest)
                    # Keep only the latest segment to avoid re-processing
                    buf = segments[-1]

                # Check partial buffer for interactive prompts without newline.
                # Wait 3 stall cycles (~300ms) before treating as prompt.
                if buf and stall_cycles >= 3:
                    partial = buf.decode("utf-8", errors="replace").strip()
                    partial_lower = partial.lower()

                    handled = False

                    # Password prompt
                    if not password_sent and "password" in partial_lower:
                        output_lines.append(partial)
                        log(partial, "info")
                        buf = b""
                        handled = True

                        pw = password
                        if pw is None and ask_password:
                            log("Steam is requesting your password...", "info")
                            pw = ask_password()

                        if pw is None:
                            log("No password provided. Cancelling...", "warning")
                            self._interrupt_process(proc)
                            return (-1, "No password provided")

                        try:
                            proc.stdin.write((pw + "\n").encode("utf-8"))
                            proc.stdin.flush()
                        except (BrokenPipeError, OSError):
                            return (-1, "DepotDownloader exited unexpectedly")
                        password_sent = True
                        log("Password submitted.", "info")
                        stall_cycles = 0

                    # 2FA / Steam Guard prompt
                    elif not auth_code_sent and any(
                        kw in partial_lower
                        for kw in (
                            "steam guard",
                            "two-factor",
                            "2fa",
                            "authentication code",
                            "auth code",
                        )
                    ):
                        output_lines.append(partial)
                        log(partial, "info")
                        buf = b""
                        handled = True

                        code = auth_code
                        if code is None and ask_auth_code:
                            log("Steam Guard / 2FA code required...", "info")
                            code = ask_auth_code()

                        if code is None:
                            log("No auth code provided. Cancelling...", "warning")
                            self._interrupt_process(proc)
                            return (-1, "No auth code provided")

                        try:
                            proc.stdin.write((code + "\n").encode("utf-8"))
                            proc.stdin.flush()
                        except (BrokenPipeError, OSError):
                            return (-1, "DepotDownloader exited unexpectedly")
                        auth_code_sent = True
                        log("Auth code submitted.", "info")
                        stall_cycles = 0

                    if handled:
                        continue

                time.sleep(0.1)

            # Process remaining buffer
            for chunk in buf.replace(b"\r\n", b"\n").split(b"\n"):
                line = chunk.decode("utf-8", errors="replace").strip()
                if line:
                    output_lines.append(line)
                    self._handle_output_line(line, log)

            exit_code = proc.wait()
            log(f"DepotDownloader exited with code {exit_code}", "info")

        except Exception as e:
            logger.exception("DepotDownloader error")
            with contextlib.suppress(Exception):
                proc.terminate()
                proc.wait(timeout=5)
            return (-1, f"Process error: {e}")

        return (exit_code, "\n".join(output_lines))

    @staticmethod
    def _interrupt_process(proc: subprocess.Popen) -> None:
        """Gracefully interrupt a running DepotDownloader process."""
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            with contextlib.suppress(Exception):
                proc.kill()

    @staticmethod
    def _handle_output_line(line: str, log: LogCallback) -> None:
        """Process a single output line from DepotDownloader."""
        line_lower = line.lower()

        if re.search(r"\d+\.?\d*%", line):
            log(line, "info")
            return

        if "logged in" in line_lower:
            log("Successfully logged into Steam.", "success")
            return

        if any(
            kw in line_lower
            for kw in (
                "downloading",
                "depot",
                "manifest",
                "validating",
                "got depot",
                "downloaded",
                "total",
            )
        ):
            log(line, "info")
            return

        if len(line) > 3:
            log(line, "info")


# -- Upload Worker ----------------------------------------------------------


class UploadWorker:
    """Background thread that uploads patches to CDN as they are produced.

    Consumes ``UploadJob`` items from a ``queue.Queue``. A sentinel ``None``
    signals shutdown — the worker drains remaining items then exits.
    """

    def __init__(
        self,
        conn,
        upload_fn: Callable,
        state: PipelineState,
        result: PipelineResult,
        state_lock: threading.Lock,
        config_dir: Path,
        log: LogCallback,
        cancel: Event,
        pause: Event | None,
        cleanup_patches: bool = False,
        on_upload_progress: Callable[[int, int], None] | None = None,
        progress: Callable[[str, int, int], None] | None = None,
    ):
        self._conn = conn
        self._upload_fn = upload_fn
        self._state = state
        self._result = result
        self._state_lock = state_lock
        self._config_dir = config_dir
        self._log = log
        self._cancel = cancel
        self._pause = pause
        self._cleanup = cleanup_patches
        self._on_upload_progress = on_upload_progress
        self._progress = progress
        self._queue: queue.Queue[UploadJob | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._total_enqueued = 0
        self._completed_count = 0
        self._done_uploads: set[str] = set(state.completed_uploads)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enqueue(self, job: UploadJob) -> None:
        self._total_enqueued += 1
        self._queue.put(job)

    def shutdown_and_wait(self, timeout: float = 120) -> None:
        """Signal shutdown and wait for the worker to drain the queue."""
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while True:
            try:
                job = self._queue.get(timeout=1.0)
            except queue.Empty:
                if self._cancel.is_set():
                    return
                continue

            if job is None:
                # Drain remaining items before exiting
                while not self._queue.empty():
                    remaining = self._queue.get_nowait()
                    if remaining is None:
                        continue
                    if self._cancel.is_set():
                        return
                    self._process_job(remaining)
                return

            if self._cancel.is_set():
                return

            # Respect pause
            if self._pause and self._pause.is_set():
                self._log("Upload paused, waiting...", "warning")
                while self._pause.is_set():
                    if self._cancel.is_set():
                        return
                    time.sleep(0.5)

            self._process_job(job)

    def _process_job(self, job: UploadJob) -> None:
        self._completed_count += 1
        self._log(
            f"[Upload {self._completed_count}/{self._total_enqueued}] Uploading {job.pair_key}...",
            "info",
        )
        if self._progress:
            self._progress("Uploading", self._completed_count, self._total_enqueued)

        entry = self._upload_fn(self._conn, job.patch_path, job.from_version, job.to_version)

        # Retry once with fresh connection on failure
        if entry is None:
            self._log("Retrying upload with fresh connection...", "warning")
            try:
                from ..config import ManagerConfig
                from .connection import ConnectionManager

                self._conn.close()
                cdn_config = ManagerConfig.load().to_cdn_config()
                self._conn = ConnectionManager(cdn_config)
                entry = self._upload_fn(
                    self._conn, job.patch_path, job.from_version, job.to_version
                )
            except Exception as exc:
                self._log(f"Reconnect failed: {exc}", "error")

        with self._state_lock:
            if entry:
                self._state.completed_uploads.append(job.pair_key)
                self._state.upload_manifest_entries.append(entry)
                self._result.patches_uploaded += 1
                self._done_uploads.add(job.pair_key)
                save_pipeline_state(self._config_dir, self._state)

                # Cleanup: delete local patch after verified upload
                if self._cleanup and job.patch_path.is_file():
                    remote_path = f"files/sims4/patches/{job.from_version}_to_{job.to_version}.zip"
                    try:
                        if self._conn.file_exists_sftp(remote_path):
                            job.patch_path.unlink()
                            self._log(f"Cleaned up {job.patch_path.name}", "success")
                    except Exception:
                        pass  # Non-critical
            else:
                self._log(f"Upload failed for {job.pair_key}", "error")
                self._state.failed_items.append(f"upload:{job.pair_key}")
                self._result.errors.append(f"Upload failed: {job.pair_key}")
                save_pipeline_state(self._config_dir, self._state)


# -- Batch Pipeline ---------------------------------------------------------


class BatchPipeline:
    """Orchestrates: download versions -> create patches -> upload to CDN.

    Downloads sequentially (Steam rate-limits), patches immediately when
    adjacent versions are available, and uploads concurrently in a background
    thread. State is persisted after every step for resume capability.
    """

    def __init__(
        self,
        downloader: DepotDownloader,
        config_dir: Path,
        cancel_event: Event,
        log: LogCallback,
        progress: Callable[[str, int, int], None] | None = None,
        pause_event: Event | None = None,
        on_version_status: Callable[[str, str], None] | None = None,
        on_download_progress: Callable[[float, str], None] | None = None,
        on_upload_progress: Callable[[int, int], None] | None = None,
    ):
        self._downloader = downloader
        self._config_dir = config_dir
        self._cancel = cancel_event
        self._log = log
        self._progress = progress  # (phase_label, current, total)
        self._pause = pause_event  # set = paused
        self._on_version_status = on_version_status  # (version, status)
        self._on_download_progress = on_download_progress  # (pct, detail)
        self._on_upload_progress = on_upload_progress  # (sent_bytes, total_bytes)
        self._state_lock = threading.Lock()

    def run(
        self,
        versions: list[str],
        manifest_ids: dict[str, str],
        *,
        steam_username: str,
        steam_password: str | None = None,
        steam_auth_code: str | None = None,
        depot_id: str = "1222671",
        download_base_dir: Path | None = None,
        direction: str = "both",
        skip_existing: bool = True,
        auto_register: bool = True,
        auto_upload: bool = True,
        auto_manifest: bool = True,
        ask_password: Callable[[], str | None] | None = None,
        ask_auth_code: Callable[[], str | None] | None = None,
        patcher_dir: str = "",
        cleanup_patches: bool = False,
        cleanup_versions: bool = False,
    ) -> PipelineResult:
        """Run the streaming batch pipeline.

        Downloads versions sequentially, patches immediately when adjacent
        versions are available, and uploads concurrently via a background
        worker thread. Manifest is updated once after all uploads complete.
        """
        result = PipelineResult()
        upload_worker: UploadWorker | None = None
        conn = None
        max_failures = 5

        if download_base_dir is None:
            download_base_dir = self._config_dir / "depot_downloads"
        download_base_dir.mkdir(parents=True, exist_ok=True)

        # Load or create pipeline state
        state = load_pipeline_state(self._config_dir)
        if state is None or state.versions != versions:
            state = PipelineState(
                versions=list(versions),
                manifest_ids=dict(manifest_ids),
                direction=direction,
            )

        # Deduplicate failed_items from previous resume cycles
        state.failed_items = list(dict.fromkeys(state.failed_items))

        # -- Setup: Pre-compute patch pairs and index by version --
        all_pairs = self._build_patch_pairs(versions, direction)
        pairs_by_version: dict[str, list[tuple[str, str]]] = {}
        for from_v, to_v in all_pairs:
            pairs_by_version.setdefault(from_v, []).append((from_v, to_v))
            pairs_by_version.setdefault(to_v, []).append((from_v, to_v))

        done_downloads = set(state.completed_downloads)
        done_patches = set(state.completed_patches)

        # -- Setup: Connect to CDN + start upload worker --
        if auto_upload:
            try:
                from ..config import ManagerConfig
                from .connection import ConnectionManager

                cdn_config = ManagerConfig.load().to_cdn_config()
                conn = ConnectionManager(cdn_config)

                upload_worker = UploadWorker(
                    conn=conn,
                    upload_fn=self._upload_patch,
                    state=state,
                    result=result,
                    state_lock=self._state_lock,
                    config_dir=self._config_dir,
                    log=self._log,
                    cancel=self._cancel,
                    pause=self._pause,
                    cleanup_patches=cleanup_patches,
                    on_upload_progress=self._on_upload_progress,
                    progress=self._progress,
                )
                upload_worker.start()
                self._log("Upload worker started — uploads will run alongside downloads", "info")
            except Exception as e:
                self._log(f"Cannot connect to CDN: {e} — continuing without uploads", "warning")
                result.errors.append(f"CDN connection failed: {e}")
                upload_worker = None
                conn = None

        # -- Resume: Re-enqueue patches that were created but not uploaded --
        if upload_worker:
            done_uploads = set(state.completed_uploads)
            re_enqueued = 0
            for from_v, to_v in all_pairs:
                pair_key = f"{from_v}->{to_v}"
                if pair_key in done_patches and pair_key not in done_uploads:
                    patch_path = self._config_dir / "patch_output" / f"{from_v}_to_{to_v}.zip"
                    if patch_path.is_file():
                        upload_worker.enqueue(UploadJob(pair_key, patch_path, from_v, to_v))
                        re_enqueued += 1
            if re_enqueued:
                self._log(f"Re-enqueued {re_enqueued} patches from previous run", "info")

        # -- Catch-up: Create patches for already-downloaded pairs --
        # On resume, versions in completed_downloads skip the main loop, so
        # their patches are never retried. This phase catches up on any pair
        # where both versions are downloaded but the patch hasn't been created.
        # Clear old patch failures so they can be retried with the current code.
        old_failed = len(state.failed_items)
        state.failed_items = [f for f in state.failed_items if not f.startswith("patch:")]
        if old_failed != len(state.failed_items):
            self._log(
                f"Cleared {old_failed - len(state.failed_items)} old patch failures for retry",
                "info",
            )
            with self._state_lock:
                save_pipeline_state(self._config_dir, state)
        catchup_count = 0
        for from_v, to_v in all_pairs:
            if self._cancel.is_set():
                break
            pair_key = f"{from_v}->{to_v}"
            if pair_key in done_patches:
                continue
            if from_v not in done_downloads or to_v not in done_downloads:
                continue
            from_dir = download_base_dir / from_v
            to_dir = download_base_dir / to_v
            if not from_dir.is_dir() or not to_dir.is_dir():
                continue

            # Check if patch zip already exists on disk
            existing_zip = self._config_dir / "patch_output" / f"{from_v}_to_{to_v}.zip"
            if existing_zip.is_file():
                self._log(f"Catch-up: {pair_key} (patch exists on disk)", "info")
                with self._state_lock:
                    state.completed_patches.append(pair_key)
                    save_pipeline_state(self._config_dir, state)
                done_patches.add(pair_key)
                result.patches_created += 1
                if upload_worker:
                    upload_worker.enqueue(UploadJob(pair_key, existing_zip, from_v, to_v))
                catchup_count += 1
                if cleanup_versions:
                    self._try_cleanup_versions(
                        {from_v, to_v}, pairs_by_version, done_patches, download_base_dir
                    )
                continue

            catchup_count += 1
            self._log(f"[Catch-up {catchup_count}] Creating {pair_key}...", "info")
            if self._progress:
                self._progress("Patching", catchup_count, catchup_count)

            patch_path = self._create_patch(from_dir, to_dir, from_v, to_v, patcher_dir)
            if patch_path and patch_path.is_file():
                with self._state_lock:
                    state.completed_patches.append(pair_key)
                    save_pipeline_state(self._config_dir, state)
                done_patches.add(pair_key)
                result.patches_created += 1
                if upload_worker:
                    upload_worker.enqueue(UploadJob(pair_key, patch_path, from_v, to_v))
                if cleanup_versions:
                    self._try_cleanup_versions(
                        {from_v, to_v}, pairs_by_version, done_patches, download_base_dir
                    )
            else:
                with self._state_lock:
                    state.failed_items.append(f"patch:{pair_key}")
                    save_pipeline_state(self._config_dir, state)
                result.errors.append(f"Catch-up patch failed: {pair_key}")

        if catchup_count:
            self._log(
                f"Catch-up phase: {catchup_count} patches attempted, "
                f"{result.patches_created} created",
                "info",
            )

        # -- Main loop: Download + patch + enqueue uploads --
        state.current_phase = "downloading"
        with self._state_lock:
            save_pipeline_state(self._config_dir, state)
        total_downloads = len(versions)
        patch_count = 0

        first_download = True
        consecutive_failures = 0
        for i, version in enumerate(versions):
            if self._cancel.is_set():
                result.cancelled = True
                break
            if self._wait_if_paused():
                result.cancelled = True
                break

            if version in done_downloads:
                self._set_status(version, "done")
                self._log(f"Skipping download {version} (already done)", "debug")
                continue

            with self._state_lock:
                state.current_item = version
                save_pipeline_state(self._config_dir, state)

            manifest_id = manifest_ids.get(version, "")
            if not manifest_id:
                self._set_status(version, "failed")
                self._log(f"No manifest ID for {version}, skipping", "warning")
                with self._state_lock:
                    state.failed_items.append(f"download:{version}")
                    save_pipeline_state(self._config_dir, state)
                result.errors.append(f"No manifest ID for {version}")
                continue

            output_dir = download_base_dir / version

            # Skip download if directory already has files and passes hash check
            if skip_existing and output_dir.is_dir() and any(output_dir.iterdir()):
                if self._verify_download(version, output_dir):
                    self._set_status(version, "done")
                    self._log(f"Skipping {version} (exists + hash OK)", "info")
                    with self._state_lock:
                        state.completed_downloads.append(version)
                        save_pipeline_state(self._config_dir, state)
                    done_downloads.add(version)
                    result.downloads += 1
                    if auto_register:
                        self._register_version(version, output_dir)
                    # Check for newly eligible patches after this "download"
                    patch_count = self._patch_and_enqueue(
                        version,
                        versions,
                        pairs_by_version,
                        done_downloads,
                        done_patches,
                        download_base_dir,
                        patcher_dir,
                        state,
                        result,
                        upload_worker,
                        patch_count,
                        cleanup_versions=cleanup_versions,
                    )
                    continue
                self._log(
                    f"Existing {version} failed hash check — re-downloading",
                    "warning",
                )

            self._set_status(version, "downloading")
            self._log(f"[{i + 1}/{total_downloads}] Downloading {version}...", "info")
            if self._progress:
                self._progress("Downloading", i + 1, total_downloads)

            dl_result = self._downloader.download_version(
                username=steam_username,
                password=steam_password if first_download else None,
                auth_code=steam_auth_code if first_download else None,
                app_id=SIMS4_APP_ID,
                depot_id=depot_id,
                manifest_id=manifest_id,
                output_dir=output_dir,
                log=self._log,
                ask_password=ask_password if first_download else None,
                ask_auth_code=ask_auth_code if first_download else None,
                on_progress=self._on_download_progress,
            )

            if dl_result.success:
                first_download = False
                # Verify download integrity via sentinel file hashes
                if not self._verify_download(version, output_dir):
                    self._set_status(version, "failed")
                    self._log(
                        f"Download {version} failed hash verification — "
                        "files may be corrupt or incomplete",
                        "error",
                    )
                    self._delete_version_dir(output_dir, version)
                    with self._state_lock:
                        state.failed_items.append(f"verify:{version}")
                        save_pipeline_state(self._config_dir, state)
                    result.errors.append(f"Hash verification failed: {version}")
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        self._log(f"Stopping: {max_failures} consecutive failures", "error")
                        break
                    continue

                self._set_status(version, "done")
                with self._state_lock:
                    state.completed_downloads.append(version)
                    save_pipeline_state(self._config_dir, state)
                done_downloads.add(version)
                result.downloads += 1
                consecutive_failures = 0

                if auto_register:
                    self._register_version(version, output_dir)

                # Create patches for newly eligible pairs + enqueue uploads
                patch_count = self._patch_and_enqueue(
                    version,
                    versions,
                    pairs_by_version,
                    done_downloads,
                    done_patches,
                    download_base_dir,
                    patcher_dir,
                    state,
                    result,
                    upload_worker,
                    patch_count,
                    cleanup_versions=cleanup_versions,
                )
            else:
                self._set_status(version, "failed")
                self._log(f"Download failed for {version}: {dl_result.error}", "error")
                self._delete_version_dir(output_dir, version)
                with self._state_lock:
                    state.failed_items.append(f"download:{version}")
                    save_pipeline_state(self._config_dir, state)
                result.errors.append(f"Download {version}: {dl_result.error}")

                # Back off before next attempt to avoid Steam rate-limiting
                consecutive_failures += 1
                delay = min(5 * consecutive_failures, 30)
                self._log(f"Waiting {delay}s before next download...", "warning")
                for _ in range(delay * 10):
                    if self._cancel.is_set():
                        break
                    time.sleep(0.1)

        # -- Shutdown upload worker and wait for drain --
        if upload_worker:
            self._log("Downloads complete — waiting for uploads to finish...", "info")
            upload_worker.shutdown_and_wait(timeout=300)

        if result.cancelled:
            if upload_worker:
                upload_worker.shutdown_and_wait(timeout=30)
            with self._state_lock:
                save_pipeline_state(self._config_dir, state)
            self._log_summary(result)
            if conn:
                conn.close()
            return result

        # -- Flush all KV routes (bulk write) --
        # Collect explicit kv_route entries, or reconstruct from from/to fields
        pending_kv = []
        for e in state.upload_manifest_entries:
            if e.get("kv_route"):
                pending_kv.append(e.pop("kv_route"))
            elif e.get("from") and e.get("to"):
                cdn_path = f"patches/{e['from']}_to_{e['to']}.zip"
                pending_kv.append({"key": cdn_path, "value": f"{SEEDBOX_BASE_DIR}/{cdn_path}"})
        if pending_kv:
            self._log(f"Registering {len(pending_kv)} deferred KV routes (bulk)...")
            if conn is None:
                try:
                    from ..config import ManagerConfig
                    from .connection import ConnectionManager

                    cdn_config = ManagerConfig.load().to_cdn_config()
                    conn = ConnectionManager(cdn_config)
                except Exception as e:
                    self._log(f"Cannot connect for KV bulk: {e}", "error")
            if conn:
                try:
                    conn.kv_put_bulk(pending_kv)
                    self._log(f"Registered {len(pending_kv)} KV routes", "success")
                except Exception as e:
                    self._log(f"KV bulk write failed: {e}", "error")
                    result.errors.append(f"KV bulk write: {e}")

        # -- Update manifest --
        if auto_manifest and state.upload_manifest_entries:
            state.current_phase = "manifest"
            with self._state_lock:
                save_pipeline_state(self._config_dir, state)
            if conn is None:
                # No upload worker was started, connect now for manifest only
                try:
                    from ..config import ManagerConfig
                    from .connection import ConnectionManager

                    cdn_config = ManagerConfig.load().to_cdn_config()
                    conn = ConnectionManager(cdn_config)
                except Exception as e:
                    self._log(f"Cannot connect for manifest update: {e}", "error")
                    result.errors.append(f"Manifest connection failed: {e}")
            if conn:
                result.manifest_updated = self._update_manifest(conn, state.upload_manifest_entries)

        # -- Done --
        if conn:
            conn.close()

        if not result.cancelled:
            state.current_phase = "done"
            clear_pipeline_state(self._config_dir)
        else:
            with self._state_lock:
                save_pipeline_state(self._config_dir, state)

        self._log_summary(result)
        return result

    def _patch_and_enqueue(
        self,
        version: str,
        versions: list[str],
        pairs_by_version: dict[str, list[tuple[str, str]]],
        done_downloads: set[str],
        done_patches: set[str],
        download_base_dir: Path,
        patcher_dir: str,
        state: PipelineState,
        result: PipelineResult,
        upload_worker: UploadWorker | None,
        patch_count: int,
        cleanup_versions: bool = False,
    ) -> int:
        """After downloading a version, create eligible patches and enqueue uploads.

        Returns the updated patch_count for logging.
        """
        eligible = pairs_by_version.get(version, [])
        for from_v, to_v in eligible:
            pair_key = f"{from_v}->{to_v}"
            if pair_key in done_patches:
                continue
            # Both versions must be downloaded
            if from_v not in done_downloads or to_v not in done_downloads:
                continue

            if self._cancel.is_set():
                break

            from_dir = download_base_dir / from_v
            to_dir = download_base_dir / to_v
            if not from_dir.is_dir() or not to_dir.is_dir():
                continue

            # Skip if patch zip already exists on disk
            existing_zip = self._config_dir / "patch_output" / f"{from_v}_to_{to_v}.zip"
            if existing_zip.is_file():
                self._log(f"Skipping {pair_key} (patch already exists on disk)", "info")
                with self._state_lock:
                    state.completed_patches.append(pair_key)
                    save_pipeline_state(self._config_dir, state)
                done_patches.add(pair_key)
                result.patches_created += 1
                if upload_worker:
                    upload_worker.enqueue(UploadJob(pair_key, existing_zip, from_v, to_v))
                patch_count += 1
                continue

            patch_count += 1
            with self._state_lock:
                state.current_item = pair_key
                save_pipeline_state(self._config_dir, state)

            self._log(f"[Patch {patch_count}] Creating {pair_key}...", "info")
            if self._progress:
                self._progress("Patching", patch_count, patch_count)

            patch_path = self._create_patch(from_dir, to_dir, from_v, to_v, patcher_dir)

            if patch_path and patch_path.is_file():
                with self._state_lock:
                    state.completed_patches.append(pair_key)
                    save_pipeline_state(self._config_dir, state)
                done_patches.add(pair_key)
                result.patches_created += 1
                if upload_worker:
                    upload_worker.enqueue(UploadJob(pair_key, patch_path, from_v, to_v))
            else:
                self._log(f"Patch creation failed for {pair_key}", "error")
                with self._state_lock:
                    state.failed_items.append(f"patch:{pair_key}")
                    save_pipeline_state(self._config_dir, state)
                result.errors.append(f"Patch failed: {pair_key}")

        # Clean up version directories that have all patches created
        if cleanup_versions and eligible:
            candidates = set()
            for from_v, to_v in eligible:
                candidates.add(from_v)
                candidates.add(to_v)
            self._try_cleanup_versions(
                candidates, pairs_by_version, done_patches, download_base_dir
            )

        return patch_count

    def _try_cleanup_versions(
        self,
        candidates: set[str],
        pairs_by_version: dict[str, list[tuple[str, str]]],
        done_patches: set[str],
        download_base_dir: Path,
    ) -> None:
        """Delete version directories once ALL their patches are created."""
        for version in candidates:
            all_pairs = pairs_by_version.get(version, [])
            if not all_pairs:
                continue
            if all(f"{f}->{t}" in done_patches for f, t in all_pairs):
                version_dir = download_base_dir / version
                if version_dir.is_dir():
                    import shutil

                    shutil.rmtree(version_dir, ignore_errors=True)
                    self._log(f"Cleaned up version directory: {version}", "success")

    def _delete_version_dir(self, version_dir: Path, version: str) -> None:
        """Delete a failed/partial version directory to reclaim preallocated space."""
        if version_dir.is_dir():
            import shutil

            shutil.rmtree(version_dir, ignore_errors=True)
            self._log(f"Deleted partial download: {version}", "info")

    # -- Pipeline Helpers ---------------------------------------------------

    def _log_summary(self, result: PipelineResult) -> None:
        """Log a one-line summary of what the pipeline accomplished."""
        parts = []
        if result.downloads:
            parts.append(f"{result.downloads} downloaded")
        if result.patches_created:
            parts.append(f"{result.patches_created} patches created")
        if result.patches_uploaded:
            parts.append(f"{result.patches_uploaded} uploaded")
        if result.manifest_updated:
            parts.append("manifest updated")
        if result.errors:
            parts.append(f"{len(result.errors)} errors")
        if result.cancelled:
            parts.append("cancelled")
        summary = ", ".join(parts) if parts else "nothing to do"
        self._log(f"Pipeline complete: {summary}", "info")

    # Minimum expected file count for a valid Sims 4 depot download.
    # A full depot has 500+ files; this threshold catches empty or
    # severely incomplete downloads while allowing partial depots.
    _MIN_FILE_COUNT = 50
    # Minimum total size in bytes (~500 MB) — a complete depot is several GB.
    _MIN_TOTAL_SIZE = 500 * 1024 * 1024

    def _verify_download(self, version: str, output_dir: Path) -> bool:
        """Verify a downloaded version via file size + sentinel hash check.

        1. Checks minimum file count and total size (catches incomplete downloads).
        2. Scans for zero-byte files (corrupt/truncated files).
        3. Hashes sentinel game files against version_hashes.json.

        Returns True if all checks pass or if no hash data is available
        (graceful degradation). Returns False on any failure.
        """
        try:
            # -- File count and size check --
            file_count = 0
            total_size = 0
            zero_byte_files = []
            for f in output_dir.rglob("*"):
                if f.is_file():
                    file_count += 1
                    fsize = f.stat().st_size
                    total_size += fsize
                    if fsize == 0:
                        zero_byte_files.append(f.name)

            if file_count < self._MIN_FILE_COUNT:
                self._log(
                    f"Incomplete download for {version}: "
                    f"only {file_count} files (minimum {self._MIN_FILE_COUNT})",
                    "error",
                )
                return False

            if total_size < self._MIN_TOTAL_SIZE:
                from .dlc_ops import fmt_size as _fmt

                self._log(
                    f"Incomplete download for {version}: "
                    f"total size {_fmt(total_size)} (minimum {_fmt(self._MIN_TOTAL_SIZE)})",
                    "error",
                )
                return False

            if zero_byte_files:
                sample = ", ".join(zero_byte_files[:5])
                extra = f" (+{len(zero_byte_files) - 5} more)" if len(zero_byte_files) > 5 else ""
                self._log(
                    f"Warning: {len(zero_byte_files)} zero-byte files in {version}: "
                    f"{sample}{extra}",
                    "warning",
                )

            # -- Sentinel file hash check --
            from .patch_ops import detect_version_fingerprint

            detected, confidence = detect_version_fingerprint(str(output_dir))
            if detected is None:
                from .dlc_ops import fmt_size as _fmt

                self._log(
                    f"No hash data for {version} — size OK "
                    f"({file_count} files, {_fmt(total_size)})",
                    "warning",
                )
                return True

            if detected == version and confidence >= 0.8:
                from .dlc_ops import fmt_size as _fmt

                self._log(
                    f"Verified {version}: {file_count} files, "
                    f"{_fmt(total_size)}, hash {confidence:.0%}",
                    "success",
                )
                return True

            if detected == version:
                self._log(
                    f"Hash check partial for {version} "
                    f"(confidence {confidence:.0%}, expected >=80%)",
                    "warning",
                )
                return True

            # Wrong version detected
            self._log(
                f"Hash check FAILED for {version} — detected {detected} "
                f"(confidence {confidence:.0%})",
                "error",
            )
            return False
        except Exception as e:
            self._log(f"Hash verification error for {version}: {e}", "warning")
            return True  # Don't block pipeline on verification errors

    def _wait_if_paused(self) -> bool:
        """Block while pause event is set. Returns True if cancelled during pause."""
        if self._pause is None or not self._pause.is_set():
            return False
        self._log("Pipeline paused. Click Resume to continue.", "warning")
        while self._pause.is_set():
            if self._cancel.is_set():
                return True
            time.sleep(0.5)
        self._log("Pipeline resumed.", "info")
        return False

    def _set_status(self, version: str, status: str) -> None:
        """Notify the UI of a version's status change."""
        if self._on_version_status:
            self._on_version_status(version, status)

    @staticmethod
    def _build_patch_pairs(
        versions: list[str],
        direction: str,
    ) -> list[tuple[str, str]]:
        """Build list of (from, to) pairs for patch creation."""
        pairs = []
        for i in range(len(versions) - 1):
            if direction in ("forward", "both"):
                pairs.append((versions[i], versions[i + 1]))
            if direction in ("backward", "both"):
                pairs.append((versions[i + 1], versions[i]))
        return pairs

    def _register_version(self, version: str, output_dir: Path) -> None:
        """Auto-register a downloaded version in the patch creator's registry."""
        try:
            from ..config import CONFIG_FILE
            from .patch_ops import register_version

            # Read config once, mutate, then save
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}

            registry_data = data.get("version_registry", [])
            register_version(str(output_dir), version, registry_data)
            data["version_registry"] = registry_data
            CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._log(f"Registered {version} in version registry", "success")
        except Exception as e:
            self._log(f"Failed to register {version}: {e}", "warning")

    def _create_patch(
        self,
        from_dir: Path,
        to_dir: Path,
        from_version: str,
        to_version: str,
        patcher_dir: str,
    ) -> Path | None:
        """Create a delta patch between two version directories."""
        try:
            from .patch_ops import create_patch, get_patcher_dir

            resolved_patcher = get_patcher_dir(patcher_dir)
            if not resolved_patcher:
                self._log("Patcher directory not found", "error")
                return None

            output_dir = self._config_dir / "patch_output"
            output_dir.mkdir(parents=True, exist_ok=True)

            return create_patch(
                str(from_dir),
                str(to_dir),
                from_version,
                to_version,
                resolved_patcher,
                output_dir,
                cancel_event=self._cancel,
                log_cb=self._log,
            )
        except Exception as e:
            self._log(f"Patch creation error: {e}", "error")
            return None

    def _upload_patch(
        self,
        conn,
        patch_path: Path,
        from_version: str,
        to_version: str,
    ) -> dict | None:
        """Upload a patch to CDN and register KV route."""
        try:
            from .patch_ops import upload_patch

            return upload_patch(
                conn,
                patch_path,
                from_version,
                to_version,
                log_cb=self._log,
                progress_cb=self._on_upload_progress,
            )
        except Exception as e:
            self._log(f"Upload error: {e}", "error")
            return None

    def _update_manifest(self, conn, new_entries: list[dict]) -> bool:
        """Batch-update the CDN manifest with new patch entries."""
        try:
            manifest = conn.fetch_manifest()
            patches = manifest.get("patches", [])

            # Merge: replace existing from->to pairs, append new ones
            new_keys = {(e.get("from", ""), e.get("to", "")) for e in new_entries}
            patches = [p for p in patches if (p.get("from", ""), p.get("to", "")) not in new_keys]
            patches.extend(new_entries)
            manifest["patches"] = patches

            # Write and publish
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(manifest, tmp, indent=2)
                tmp_path = Path(tmp.name)

            try:
                conn.publish_manifest(tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)

            self._log(f"Manifest updated with {len(new_entries)} patch entries", "success")
            return True
        except Exception as e:
            self._log(f"Manifest update failed: {e}", "error")
            return False
