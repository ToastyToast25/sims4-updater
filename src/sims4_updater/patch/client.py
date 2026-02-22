"""
Patch client — orchestrates manifest fetching, update planning, and downloads.

This is the main entry point for the patch subsystem. It coordinates:
  1. Fetching and parsing the manifest from a remote URL
  2. Planning the update path from current to target version
  3. Downloading patch files with progress and cancellation
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .manifest import Manifest, ManifestDLC, PatchEntry, PendingDLC, parse_manifest
from .planner import UpdatePlan, plan_update
from .downloader import Downloader, DownloadResult, ProgressCallback
from ..core.exceptions import ManifestError, DownloadError
from ..core.learned_hashes import LearnedHashDB


# Callback types for status updates: (message: str)
StatusCallback = Callable[[str], None]


@dataclass
class UpdateInfo:
    """Summary of available update."""

    current_version: str
    latest_version: str
    update_available: bool
    plan: UpdatePlan | None = None
    total_download_size: int = 0
    step_count: int = 0
    game_latest_version: str = ""
    game_latest_date: str = ""
    patch_pending: bool = False
    new_dlcs: list[PendingDLC] = field(default_factory=list)


class PatchClient:
    """High-level client for checking and downloading updates.

    Usage:
        client = PatchClient(manifest_url="https://example.com/manifest.json")

        # Check for updates
        info = client.check_update("1.118.257.1020")

        # Download patches
        if info.update_available:
            results = client.download_update(info.plan, progress=my_callback)
    """

    def __init__(
        self,
        manifest_url: str,
        download_dir: str | Path = ".",
        cancel_event: threading.Event | None = None,
        learned_db: LearnedHashDB | None = None,
        dlc_catalog=None,
    ):
        self.manifest_url = manifest_url
        self.download_dir = Path(download_dir)
        self._cancel = cancel_event or threading.Event()
        self._manifest: Manifest | None = None
        self._downloader: Downloader | None = None
        self._learned_db = learned_db
        self._dlc_catalog = dlc_catalog  # DLCCatalog for remote DLC merging

    @property
    def downloader(self) -> Downloader:
        if self._downloader is None:
            self._downloader = Downloader(
                download_dir=self.download_dir,
                cancel_event=self._cancel,
            )
        return self._downloader

    def cancel(self):
        """Cancel any ongoing operations."""
        self._cancel.set()
        if self._downloader:
            self._downloader.cancel()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def fetch_manifest(self, force: bool = False) -> Manifest:
        """Fetch and parse the remote manifest.

        Args:
            force: Re-fetch even if already cached.

        Returns:
            Parsed Manifest object.

        Raises:
            ManifestError on fetch or parse failure.
        """
        if self._manifest and not force:
            return self._manifest

        if not self.manifest_url:
            raise ManifestError(
                "No manifest URL configured.\n"
                "Set the manifest URL in Settings."
            )

        try:
            resp = self.downloader.session.get(self.manifest_url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except json.JSONDecodeError as e:
            raise ManifestError(f"Manifest is not valid JSON: {e}") from e
        except Exception as e:
            raise ManifestError(
                f"Failed to fetch manifest from {self.manifest_url}: {e}"
            ) from e

        self._manifest = parse_manifest(data, source_url=self.manifest_url)

        # Merge fingerprints from manifest into local learned DB
        if self._learned_db and self._manifest.fingerprints:
            self._learned_db.merge(self._manifest.fingerprints)
            self._learned_db.save()

        # Fetch crowd-sourced fingerprints if URL provided
        if self._learned_db and self._manifest.fingerprints_url:
            self._fetch_crowd_fingerprints(self._manifest.fingerprints_url)

        # Merge DLC catalog updates from manifest
        if self._dlc_catalog and self._manifest.dlc_catalog:
            self._dlc_catalog.merge_remote(self._manifest.dlc_catalog)

        return self._manifest

    def load_manifest_from_file(self, path: str | Path) -> Manifest:
        """Load manifest from a local JSON file (for testing/offline use)."""
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ManifestError(f"Failed to load manifest from {path}: {e}") from e

        self._manifest = parse_manifest(data, source_url=str(path))
        return self._manifest

    def check_update(
        self,
        current_version: str,
        target_version: str | None = None,
    ) -> UpdateInfo:
        """Check if an update is available and plan the path.

        Args:
            current_version: Currently installed version.
            target_version: Desired version (defaults to manifest.latest).

        Returns:
            UpdateInfo with plan details including patch_pending state.
        """
        manifest = self.fetch_manifest()
        target = target_version or manifest.latest

        # DLC-only manifest (no patches) — no update available
        if not target:
            return UpdateInfo(
                current_version=current_version,
                latest_version="",
                update_available=False,
                new_dlcs=list(manifest.new_dlcs),
            )

        game_latest = manifest.game_latest or manifest.latest
        is_patch_pending = manifest.patch_pending

        # User already at the actual latest game version
        if current_version == game_latest:
            return UpdateInfo(
                current_version=current_version,
                latest_version=target,
                update_available=False,
                game_latest_version=game_latest,
                game_latest_date=manifest.game_latest_date,
                patch_pending=False,
                new_dlcs=list(manifest.new_dlcs),
            )

        # User at the latest patchable version but game has a newer release
        if current_version == target:
            return UpdateInfo(
                current_version=current_version,
                latest_version=target,
                update_available=False,
                game_latest_version=game_latest,
                game_latest_date=manifest.game_latest_date,
                patch_pending=is_patch_pending,
                new_dlcs=list(manifest.new_dlcs),
            )

        update_plan = plan_update(manifest, current_version, target)

        return UpdateInfo(
            current_version=current_version,
            latest_version=target,
            update_available=True,
            plan=update_plan,
            total_download_size=update_plan.total_download_size,
            step_count=update_plan.step_count,
            game_latest_version=game_latest,
            game_latest_date=manifest.game_latest_date,
            patch_pending=is_patch_pending,
            new_dlcs=list(manifest.new_dlcs),
        )

    def download_update(
        self,
        plan: UpdatePlan,
        progress: ProgressCallback | None = None,
        status: StatusCallback | None = None,
    ) -> list[list[DownloadResult]]:
        """Download all files for an update plan.

        Args:
            plan: UpdatePlan from check_update().
            progress: Callback(bytes_downloaded, total_bytes, filename).
            status: Callback(status_message) for step-level updates.

        Returns:
            List of DownloadResult lists, one per update step.
        """
        all_results = []
        grand_total = plan.total_download_size
        grand_downloaded = 0

        for step in plan.steps:
            if self.cancelled:
                raise DownloadError("Download cancelled.")

            patch = step.patch
            step_label = (
                f"Step {step.step_number}/{step.total_steps}: "
                f"{patch.version_from} -> {patch.version_to}"
            )

            if status:
                status(f"Downloading {step_label}")

            # Download patch files
            step_base = grand_downloaded

            def step_progress(downloaded: int, total: int, filename: str):
                if progress:
                    progress(step_base + downloaded, grand_total, filename)

            step_results = []

            # Download main patch files
            for entry in patch.files:
                if self.cancelled:
                    raise DownloadError("Download cancelled.")

                file_base = grand_downloaded

                def file_progress(downloaded: int, total: int, filename: str):
                    if progress:
                        progress(file_base + downloaded, grand_total, filename)

                result = self.downloader.download_file(
                    entry,
                    progress=file_progress,
                    subdir=f"{patch.version_from}_to_{patch.version_to}",
                )
                grand_downloaded += entry.size
                step_results.append(result)

            # Download crack if present
            if patch.crack:
                if self.cancelled:
                    raise DownloadError("Download cancelled.")

                crack_base = grand_downloaded

                def crack_progress(downloaded: int, total: int, filename: str):
                    if progress:
                        progress(crack_base + downloaded, grand_total, filename)

                result = self.downloader.download_file(
                    patch.crack,
                    progress=crack_progress,
                    subdir=f"{patch.version_from}_to_{patch.version_to}",
                )
                grand_downloaded += patch.crack.size
                step_results.append(result)

            all_results.append(step_results)

            if status:
                status(f"Completed {step_label}")

        return all_results

    def get_downloaded_files(self, plan: UpdatePlan) -> list[Path]:
        """List all downloaded patch files for a plan (for feeding to Patcher)."""
        files = []
        for step in plan.steps:
            patch = step.patch
            subdir = self.download_dir / f"{patch.version_from}_to_{patch.version_to}"
            for entry in patch.files:
                path = subdir / entry.filename
                if path.is_file():
                    files.append(path)
        return files

    # ── Hash Learning ─────────────────────────────────────────────

    def _fetch_crowd_fingerprints(self, url: str):
        """Fetch crowd-sourced fingerprints and merge into learned DB (best-effort)."""
        try:
            resp = self.downloader.session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                versions = data.get("versions", data)
                if isinstance(versions, dict):
                    self._learned_db.merge(versions)
                    self._learned_db.save()
        except Exception:
            pass  # non-critical, silently ignore

    def report_hashes(
        self,
        version: str,
        hashes: dict[str, str],
        report_url: str | None = None,
    ):
        """Report learned hashes to the remote API (fire-and-forget).

        Args:
            version: The version string.
            hashes: Dict of {sentinel_path: md5_hash}.
            report_url: URL to POST to. Falls back to manifest's report_url.
        """
        url = report_url
        if not url and self._manifest:
            url = self._manifest.report_url
        if not url:
            return

        def _send():
            try:
                self.downloader.session.post(
                    url,
                    json={"version": version, "hashes": hashes},
                    timeout=10,
                )
            except Exception:
                pass  # fire-and-forget

        thread = threading.Thread(target=_send, daemon=True)
        thread.start()

    def close(self):
        """Clean up resources."""
        if self._downloader:
            self._downloader.close()
            self._downloader = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
