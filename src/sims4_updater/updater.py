"""
Sims4Updater — the main updater engine.

Subclasses the base Patcher to add:
  - Auto version detection
  - Manifest-based update checking
  - Patch downloading with resume
  - DLC auto-toggling after updates
  - Integration with all subsystems
"""

from __future__ import annotations

import os
import sys
import threading
from enum import Enum
from pathlib import Path

# Make the base patcher package importable
_patcher_root = Path(__file__).resolve().parents[3] / "patcher"
if (
    _patcher_root.is_dir()
    and (_patcher_root / "patcher" / "__init__.py").is_file()
    and str(_patcher_root) not in sys.path
):
    sys.path.insert(0, str(_patcher_root))

from patcher.patcher import Patcher as BasePatcher, CallbackType  # noqa: E402

from .core.version_detect import VersionDetector, DetectionResult
from .core.learned_hashes import LearnedHashDB
from .core.exceptions import (
    UpdaterError,
    DownloadError,
    ManifestError,
    NoUpdatePathError,
    VersionDetectionError,
)
from .patch.client import PatchClient, UpdateInfo
from .patch.planner import UpdatePlan
from .dlc.manager import DLCManager
from .dlc.downloader import DLCDownloader
from .config import Settings, get_app_dir


class UpdateState(Enum):
    """Current state of the updater."""

    IDLE = "idle"
    DETECTING = "detecting_version"
    CHECKING = "checking_updates"
    DOWNLOADING = "downloading"
    PATCHING = "patching"
    FINALIZING = "finalizing"
    DONE = "done"
    ERROR = "error"


class Sims4Updater(BasePatcher):
    """The Sims 4 Updater — extends Patcher with download and auto-update capabilities."""

    VERSION = 1
    NAME = "Sims4Updater"

    def __init__(self, ask_question, callback=None, settings: Settings | None = None):
        super().__init__(ask_question, callback)

        self.settings = settings or Settings.load()
        self._learned_db = LearnedHashDB()
        self._detector = VersionDetector(learned_db=self._learned_db)
        self._dlc_manager = DLCManager()
        self._patch_client: PatchClient | None = None
        self._dlc_downloader: DLCDownloader | None = None
        self._cancel = threading.Event()
        self._state = UpdateState.IDLE
        self._download_dir = get_app_dir() / "downloads"

    @property
    def state(self) -> UpdateState:
        return self._state

    @property
    def patch_client(self) -> PatchClient:
        if self._patch_client is None:
            self._patch_client = PatchClient(
                manifest_url=self.settings.manifest_url,
                download_dir=self._download_dir,
                cancel_event=self._cancel,
                learned_db=self._learned_db,
                dlc_catalog=self._dlc_manager.catalog,
            )
        return self._patch_client

    def create_dlc_downloader(self, game_dir: str) -> DLCDownloader:
        """Create a new DLCDownloader for the given game directory."""
        return DLCDownloader(
            download_dir=self._download_dir,
            game_dir=game_dir,
            dlc_manager=self._dlc_manager,
            cancel_event=self._cancel,
        )

    def exiting_extra(self):
        """Cancel downloads and save settings on exit."""
        try:
            self._cancel.set()
            if self._patch_client:
                self._patch_client.cancel()
                self._patch_client.close()
            if self._dlc_downloader:
                self._dlc_downloader.close()
            self.settings.save()
        except Exception:
            # May fail during interpreter shutdown when builtins are gone
            pass

    # ── Version Detection ──────────────────────────────────────────

    def find_game_dir(self) -> str | None:
        """Auto-detect the Sims 4 installation directory."""
        if self.settings.game_path:
            path = self.settings.game_path
            if self._detector.validate_game_dir(path):
                return path

        found = self._detector.find_game_dir()
        if found:
            self.settings.game_path = found
        return found

    def detect_version(
        self, game_dir: str | None = None, progress=None
    ) -> DetectionResult:
        """Detect the installed game version."""
        self._state = UpdateState.DETECTING
        game_dir = game_dir or self.find_game_dir()
        if not game_dir:
            raise VersionDetectionError("Could not find Sims 4 installation.")

        if not self._detector.validate_game_dir(game_dir):
            raise VersionDetectionError(f"Not a valid Sims 4 directory: {game_dir}")

        result = self._detector.detect(game_dir, progress=progress)
        if result.version:
            self.settings.last_known_version = result.version
        return result

    # ── Update Checking ────────────────────────────────────────────

    def check_for_updates(
        self, current_version: str | None = None
    ) -> UpdateInfo:
        """Check if updates are available.

        Args:
            current_version: Override auto-detected version.

        Returns:
            UpdateInfo with plan details.
        """
        self._state = UpdateState.CHECKING
        version = current_version or self.settings.last_known_version

        if not version:
            result = self.detect_version()
            version = result.version
            if not version:
                raise VersionDetectionError(
                    "Could not detect installed version. "
                    "Cannot check for updates."
                )

        return self.patch_client.check_update(version)

    # ── Downloading ────────────────────────────────────────────────

    def download_update(
        self,
        plan: UpdatePlan,
        progress=None,
        status=None,
    ):
        """Download all patch files for an update plan.

        Args:
            plan: UpdatePlan from check_for_updates().
            progress: Callback(bytes_downloaded, total_bytes, filename).
            status: Callback(status_message).

        Returns:
            List of download results per step.
        """
        self._state = UpdateState.DOWNLOADING

        self.callback(CallbackType.HEADER, "Downloading patches")
        self.callback(
            CallbackType.INFO,
            f"Update: {plan.current_version} -> {plan.target_version} "
            f"({plan.step_count} step(s))",
        )

        def download_progress(downloaded, total, filename):
            self.check_exiting()
            self.callback(CallbackType.PROGRESS, downloaded, total)
            if progress:
                progress(downloaded, total, filename)

        def download_status(message):
            self.callback(CallbackType.INFO, message)
            if status:
                status(message)

        return self.patch_client.download_update(
            plan,
            progress=download_progress,
            status=download_status,
        )

    # ── Patching (override Patcher methods) ────────────────────────

    def load_all_metadata(self, types=None):
        """Override: scan download directory instead of CWD for patch ZIPs."""
        if types is None:
            types = ("patch", "dlc")

        from .core import myzipfile

        self.callback(CallbackType.HEADER, "Reading the metadata from files")

        all_metadata = {}

        # Scan download directory and its subdirectories
        search_dirs = [self._download_dir]
        if Path(".").resolve() != self._download_dir.resolve():
            search_dirs.append(Path("."))

        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            for file in search_dir.rglob("*"):
                if not file.is_file():
                    continue

                try:
                    metadata = self.load_metadata(file)
                except myzipfile.BadZipFile:
                    continue

                self.callback(CallbackType.INFO, file)

                if metadata is None or metadata.get("type") not in types:
                    self.callback(CallbackType.FAILURE, "BAD METADATA")
                    continue

                game_name = metadata.get("game_name")
                metadata["extra"] = {"archive_path": str(file)}
                try:
                    all_metadata[game_name].append(metadata)
                except KeyError:
                    all_metadata[game_name] = [metadata]

        if len(all_metadata) == 0:
            from patcher.exceptions import NoPatchesDLCsFoundError

            raise NoPatchesDLCsFoundError("No patch/DLC files found!")

        self._all_metadata = all_metadata
        return tuple(sorted(self._all_metadata.keys()))

    def _get_crack_path(self, crack):
        """Override: look for crack in download directory."""
        filename = crack["filename"]

        # Check download directory and subdirectories
        for path in self._download_dir.rglob(filename):
            if path.is_file():
                return path

        # Fallback to CWD
        cwd_path = Path(filename)
        if cwd_path.is_file():
            return cwd_path

        return cwd_path  # let the base class handle the missing file error

    def do_after_extraction(self, archive, error_occured):
        """Override: log extraction status but don't delete archives."""
        if error_occured:
            self.callback(
                CallbackType.WARNING,
                f'Extraction error for "{archive}". Will retry.',
            )
        else:
            self.callback(CallbackType.INFO, f"Extracted: {archive}")

    # ── Hash Learning ──────────────────────────────────────────────

    def learn_version(self, game_dir: str | Path, version: str):
        """Hash sentinel files and store as a learned version fingerprint.

        Also reports hashes to the remote API if available.

        Args:
            game_dir: Path to the Sims 4 installation.
            version: The known version string.
        """
        from .core.files import hash_file

        game_dir = Path(game_dir)
        hashes = {}
        for sentinel in constants.SENTINEL_FILES:
            file_path = game_dir / sentinel.replace("/", os.sep)
            if file_path.is_file():
                hashes[sentinel] = hash_file(str(file_path))

        if not hashes:
            return

        self._learned_db.add_version(version, hashes)
        self._learned_db.save()

        # Report to remote API (fire-and-forget)
        self.patch_client.report_hashes(version, hashes)

    # ── High-Level Update Orchestration ────────────────────────────

    def update(
        self,
        game_dir: str | None = None,
        progress=None,
        status=None,
    ):
        """Run the full update pipeline.

        1. Detect game version
        2. Check for updates
        3. Download patches
        4. Apply patches (via inherited Patcher.patch())
        5. Auto-toggle DLCs

        Args:
            game_dir: Game installation path (auto-detected if None).
            progress: Download progress callback.
            status: Status message callback.
        """
        try:
            # Step 1: Find game and detect version
            game_dir = game_dir or self.find_game_dir()
            if not game_dir:
                raise UpdaterError("Could not find Sims 4 installation.")

            self.settings.game_path = game_dir

            detection = self.detect_version(game_dir)
            if not detection.version:
                raise VersionDetectionError(
                    "Could not detect installed version."
                )

            if status:
                status(f"Detected version: {detection.version}")

            # Step 2: Check for updates
            info = self.check_for_updates(detection.version)

            if not info.update_available:
                if status:
                    status("Already up to date!")
                self._state = UpdateState.DONE
                return

            if status:
                from .patch.client import format_size

                status(
                    f"Update available: {info.plan.step_count} step(s), "
                    f"{format_size(info.total_download_size)}"
                )

            # Step 3: Download patches
            self.download_update(info.plan, progress=progress, status=status)

            # Step 4: Apply patches using the Patcher pipeline
            self._state = UpdateState.PATCHING

            if status:
                status("Loading patch metadata...")

            game_names = self.load_all_metadata()

            # The Sims 4 should be the only game in the metadata
            game_name = None
            for name in game_names:
                if "sims" in name.lower() or "ts4" in name.lower():
                    game_name = name
                    break
            if game_name is None:
                game_name = game_names[0]

            versions, dlc_count, languages, cached_path = self.pick_game(game_name)

            # Select language
            language = self.settings.language
            if language and language in languages:
                self.select_language(language)
            elif languages:
                self.select_language(languages[0])

            # Check files and get DLC list
            all_dlcs, missing_dlcs = self.check_files_quick(game_dir)

            # Save DLC enabled/disabled states before patching
            # so user's manual toggles are preserved across updates
            saved_dlc_states = self._dlc_manager.export_states(game_dir)

            # Select all available DLCs
            selected_dlcs = [d for d in all_dlcs if d not in missing_dlcs]
            self.patch(selected_dlcs)

            # Step 5: Learn new version hashes + restore DLC states
            self._state = UpdateState.FINALIZING

            # Learn the new version's sentinel hashes
            target_version = info.plan.target_version
            if target_version:
                if status:
                    status("Learning new version hashes...")
                self.learn_version(game_dir, target_version)

            if status:
                status("Restoring DLC states...")

            # Restore previous DLC states, then enable any genuinely new DLCs
            if saved_dlc_states:
                self._dlc_manager.import_states(game_dir, saved_dlc_states)

            # Enable DLCs that are newly installed (not in saved states)
            current_states = self._dlc_manager.get_dlc_states(game_dir)
            new_enabled = set()
            changes = {}
            for state in current_states:
                if state.dlc.id in saved_dlc_states:
                    # Existed before — keep whatever the user had
                    if saved_dlc_states[state.dlc.id]:
                        new_enabled.add(state.dlc.id)
                elif state.installed:
                    # New DLC added by this patch — enable it
                    new_enabled.add(state.dlc.id)
                    changes[state.dlc.id] = True

            if changes:
                self._dlc_manager.apply_changes(game_dir, new_enabled)
                if status:
                    status(f"Enabled {len(changes)} new DLC(s)")

            # Update stored version
            new_detection = self.detect_version(game_dir)
            if new_detection.version:
                self.settings.last_known_version = new_detection.version
                if status:
                    status(f"Updated to: {new_detection.version}")

            self.settings.save()
            self._state = UpdateState.DONE

        except Exception:
            self._state = UpdateState.ERROR
            raise

    # ── Cleanup ────────────────────────────────────────────────────

    def cleanup_downloads(self):
        """Remove downloaded patch files after successful update."""
        import shutil

        if self._download_dir.is_dir():
            shutil.rmtree(self._download_dir, ignore_errors=True)

    def close(self):
        """Clean up all resources."""
        if self._patch_client:
            self._patch_client.close()
            self._patch_client = None
