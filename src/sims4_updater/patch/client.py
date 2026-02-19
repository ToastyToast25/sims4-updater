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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .manifest import Manifest, PatchEntry, parse_manifest
from .planner import UpdatePlan, plan_update
from .downloader import Downloader, DownloadResult, ProgressCallback
from ..core.exceptions import ManifestError, DownloadError


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
    ):
        self.manifest_url = manifest_url
        self.download_dir = Path(download_dir)
        self._cancel = cancel_event or threading.Event()
        self._manifest: Manifest | None = None
        self._downloader: Downloader | None = None

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
            UpdateInfo with plan details.
        """
        manifest = self.fetch_manifest()
        target = target_version or manifest.latest

        if current_version == target:
            return UpdateInfo(
                current_version=current_version,
                latest_version=target,
                update_available=False,
            )

        update_plan = plan_update(manifest, current_version, target)

        return UpdateInfo(
            current_version=current_version,
            latest_version=target,
            update_available=True,
            plan=update_plan,
            total_download_size=update_plan.total_download_size,
            step_count=update_plan.step_count,
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
