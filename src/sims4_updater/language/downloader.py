"""
Language pack downloader — downloads and installs Strings package files.

Each language pack goes through a 2-phase pipeline:
  1. Download: HTTP with resume + MD5 verification (reuses patch Downloader)
  2. Extract: unzip Strings_XXX_XX.package to game_dir/Data/Client/
"""

from __future__ import annotations

import logging
import os
import threading
import zipfile
from pathlib import Path
from typing import Callable

from ..patch.downloader import Downloader
from ..patch.manifest import LanguageDownloadEntry
from ..core.exceptions import DownloadError

logger = logging.getLogger(__name__)

# Callback: (locale_code, message)
LanguageProgressCallback = Callable[[str, str], None]


class LanguagePackDownloader:
    """Downloads, extracts, and installs language Strings files."""

    def __init__(
        self,
        download_dir: str | Path,
        game_dir: str | Path,
        cancel_event: threading.Event | None = None,
    ):
        self._download_dir = Path(download_dir) / "languages"
        self._game_dir = Path(game_dir)
        self._cancel = cancel_event or threading.Event()
        self._downloader = Downloader(
            download_dir=self._download_dir,
            cancel_event=self._cancel,
        )
        self._strings_dir = self._game_dir / "Data" / "Client"

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self):
        self._cancel.set()
        self._downloader.cancel()

    def download_language(
        self,
        entry: LanguageDownloadEntry,
        log: Callable[[str], None] | None = None,
    ) -> bool:
        """Download and install a single language pack.

        Returns True on success.
        """
        if log is None:
            log = lambda msg: None

        try:
            # Phase 1: Download
            log(f"Downloading {entry.locale_code} ({entry.filename})...")
            file_entry = entry.to_file_entry()

            def _progress(downloaded: int, total: int, filename: str):
                if total > 0:
                    pct = downloaded * 100 // total
                    mb_dl = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    log(f"  {entry.locale_code}: {mb_dl:.1f}/{mb_total:.1f} MB ({pct}%)")

            result = self._downloader.download_file(file_entry, progress=_progress)

            if self.cancelled:
                log(f"{entry.locale_code}: Cancelled.")
                return False

            # Phase 2: Extract to Data/Client/
            log(f"Installing {entry.locale_code}...")
            self._strings_dir.mkdir(parents=True, exist_ok=True)
            self._extract_strings(result.path, entry.locale_code, log)

            log(f"{entry.locale_code}: Installed successfully.")
            return True

        except DownloadError as e:
            log(f"{entry.locale_code}: Download failed — {e}")
            return False
        except Exception as e:
            logger.exception("Language pack download failed for %s", entry.locale_code)
            log(f"{entry.locale_code}: Failed — {e}")
            return False

    def download_all_missing(
        self,
        entries: dict[str, LanguageDownloadEntry],
        installed_langs: dict[str, bool],
        log: Callable[[str], None] | None = None,
    ) -> dict[str, bool]:
        """Download all missing language packs.

        Args:
            entries: Dict of locale_code -> LanguageDownloadEntry from manifest.
            installed_langs: Dict of locale_code -> bool (already installed).
            log: Log callback.

        Returns:
            Dict of locale_code -> success bool for each attempted download.
        """
        if log is None:
            log = lambda msg: None

        results = {}
        missing = [
            (code, entry) for code, entry in entries.items()
            if not installed_langs.get(code, False)
        ]

        if not missing:
            log("All language packs are already installed.")
            return results

        log(f"Downloading {len(missing)} missing language pack(s)...")

        for i, (code, entry) in enumerate(missing, 1):
            if self.cancelled:
                log("Download cancelled.")
                break
            log(f"--- [{i}/{len(missing)}] {code} ---")
            results[code] = self.download_language(entry, log=log)

        succeeded = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v)
        log(f"Done: {succeeded} installed, {failed} failed.")
        return results

    def _extract_strings(
        self,
        archive_path: Path,
        locale_code: str,
        log: Callable[[str], None],
    ):
        """Extract Strings_XXX_XX.package from a zip archive to Data/Client/."""
        filename = archive_path.name.lower()

        if filename.endswith(".zip"):
            self._extract_zip(archive_path, locale_code, log)
        elif filename.endswith(".package"):
            # Direct .package file — just copy it
            import shutil
            dest = self._strings_dir / archive_path.name
            shutil.copy2(archive_path, dest)
            log(f"  Copied {archive_path.name} to Data/Client/")
        else:
            raise DownloadError(
                f"Unknown archive format: {archive_path.name} "
                f"(expected .zip or .package)"
            )

    def _extract_zip(
        self,
        archive_path: Path,
        locale_code: str,
        log: Callable[[str], None],
    ):
        """Extract Strings .package file(s) from a zip to Data/Client/."""
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                strings_dir_resolved = self._strings_dir.resolve()
                extracted = 0

                for member in zf.namelist():
                    if self.cancelled:
                        raise DownloadError("Extraction cancelled.")

                    basename = Path(member).name
                    # Only extract Strings_*.package files
                    if not basename.startswith("Strings_") or not basename.endswith(".package"):
                        continue

                    # Path traversal protection
                    target = (self._strings_dir / basename).resolve()
                    if not str(target).startswith(str(strings_dir_resolved)):
                        logger.warning("Skipping unsafe zip path: %s", member)
                        continue

                    # Extract directly to Data/Client/ (flatten directory structure)
                    data = zf.read(member)
                    target.write_bytes(data)
                    log(f"  Extracted {basename} to Data/Client/")
                    extracted += 1

                if extracted == 0:
                    raise DownloadError(
                        f"No Strings_*.package files found in {archive_path.name}"
                    )

        except zipfile.BadZipFile as e:
            raise DownloadError(
                f"Corrupt archive for {locale_code}: {e}"
            ) from e
        except OSError as e:
            raise DownloadError(
                f"Extraction failed for {locale_code}: {e}"
            ) from e

    def close(self):
        self._downloader.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
