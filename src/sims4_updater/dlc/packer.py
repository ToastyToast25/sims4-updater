"""
DLC Packer — pack DLC folders into distributable ZIP archives,
generate manifest JSON, and import archives into the game directory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..constants import get_tools_dir
from ..core.exceptions import DownloadError
from .catalog import DLCCatalog, DLCInfo

logger = logging.getLogger(__name__)

# Callback: (current_index, total_count, dlc_id, message)
PackProgressCallback = Callable[[int, int, str, str], None]


@dataclass
class PackResult:
    """Result of packing a single DLC."""

    dlc_id: str
    dlc_name: str
    filename: str
    path: Path
    size: int
    md5: str
    file_count: int


class DLCPacker:
    """Packs DLC folders into standard zip archives and imports archives."""

    def __init__(self, catalog: DLCCatalog | None = None):
        self._catalog = catalog or DLCCatalog()

    # ── Packing ──────────────────────────────────────────────────

    @staticmethod
    def get_zip_filename(dlc: DLCInfo) -> str:
        """Get the expected zip filename for a DLC."""
        safe_name = dlc.name_en.encode("ascii", "ignore").decode()
        safe_name = safe_name.replace(" ", "_").replace(":", "").replace("'", "")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in "_-")
        return f"Sims4_DLC_{dlc.id}_{safe_name}.zip"

    def get_zip_path(self, dlc: DLCInfo, output_dir: Path) -> Path:
        """Get the expected zip path for a DLC."""
        return output_dir / self.get_zip_filename(dlc)

    def pack_single(
        self,
        game_dir: Path,
        dlc: DLCInfo,
        output_dir: Path,
        progress_cb: PackProgressCallback | None = None,
    ) -> PackResult:
        """Pack a single DLC into a standard ZIP archive."""
        dlc_dir = game_dir / dlc.id
        if not dlc_dir.is_dir():
            raise FileNotFoundError(f"{dlc.id} not installed at {dlc_dir}")

        output_dir.mkdir(parents=True, exist_ok=True)

        zip_name = self.get_zip_filename(dlc)
        zip_path = output_dir / zip_name

        # Collect files
        files: list[tuple[Path, Path]] = []  # (relative, absolute)
        for path in dlc_dir.rglob("*"):
            if path.is_file():
                files.append((path.relative_to(game_dir), path))

        # Also include __Installer/DLC/{DLC_ID}/ if present
        installer_dir = game_dir / "__Installer" / "DLC" / dlc.id
        if installer_dir.is_dir():
            for path in installer_dir.rglob("*"):
                if path.is_file():
                    files.append((path.relative_to(game_dir), path))

        if not files:
            raise FileNotFoundError(f"{dlc.id} has no files to pack")

        # Create zip
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel_path, abs_path in sorted(files):
                zf.write(abs_path, str(rel_path).replace("\\", "/"))

        # Compute MD5 and size
        size = zip_path.stat().st_size
        md5 = _hash_file(zip_path)

        return PackResult(
            dlc_id=dlc.id,
            dlc_name=dlc.name_en,
            filename=zip_name,
            path=zip_path,
            size=size,
            md5=md5,
            file_count=len(files),
        )

    def pack_multiple(
        self,
        game_dir: Path,
        dlcs: list[DLCInfo],
        output_dir: Path,
        progress_cb: PackProgressCallback | None = None,
    ) -> list[PackResult]:
        """Pack multiple DLCs sequentially."""
        results = []
        for i, dlc in enumerate(dlcs):
            if progress_cb:
                progress_cb(i, len(dlcs), dlc.id, f"Packing {dlc.id}...")
            try:
                result = self.pack_single(game_dir, dlc, output_dir)
                results.append(result)
            except (FileNotFoundError, OSError) as e:
                logger.warning("Failed to pack %s: %s", dlc.id, e)

        if progress_cb:
            progress_cb(len(dlcs), len(dlcs), "", "Done")

        return results

    # ── Manifest Generation ──────────────────────────────────────

    def generate_manifest(
        self,
        results: list[PackResult],
        output_dir: Path,
        url_prefix: str = "<UPLOAD_URL>",
    ) -> Path:
        """Generate manifest JSON for packed DLCs.

        Returns path to the generated manifest file.
        """
        manifest = {}
        for r in results:
            manifest[r.dlc_id] = {
                "url": f"{url_prefix}/{r.filename}",
                "size": r.size,
                "md5": r.md5,
                "filename": r.filename,
            }

        manifest_path = output_dir / "manifest_dlc_downloads.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return manifest_path

    # ── Import / Extract ─────────────────────────────────────────

    def import_archive(
        self,
        archive_path: Path,
        game_dir: Path,
        progress_cb: PackProgressCallback | None = None,
    ) -> list[str]:
        """Extract a ZIP or RAR archive into the game directory.

        Returns list of DLC IDs found in the extracted content.
        """
        ext = archive_path.suffix.lower()
        if ext == ".zip":
            self._extract_zip(archive_path, game_dir)
        elif ext == ".rar":
            self._extract_rar(archive_path, game_dir)
        else:
            raise ValueError(f"Unsupported archive type: {ext}")

        # Scan for DLC directories that now exist
        return self._detect_dlc_dirs(game_dir)

    def _extract_zip(self, archive_path: Path, dest_dir: Path):
        """Extract ZIP with path traversal protection."""
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                dest_resolved = dest_dir.resolve()
                for member in zf.namelist():
                    target = (dest_dir / member).resolve()
                    if not str(target).startswith(str(dest_resolved)):
                        logger.warning("Skipping unsafe zip path: %s", member)
                        continue
                    zf.extract(member, dest_dir)
        except zipfile.BadZipFile as e:
            raise DownloadError(f"Corrupt archive: {e}") from e

    def _extract_rar(self, archive_path: Path, dest_dir: Path):
        """Extract RAR using bundled unrar.exe."""
        unrar = get_tools_dir() / "unrar.exe"
        if not unrar.is_file():
            raise FileNotFoundError(
                "unrar.exe not found. Cannot extract RAR archives."
            )

        result = subprocess.run(
            [
                str(unrar), "x",
                "-p-",          # no password
                "-o+",          # overwrite existing
                str(archive_path),
                str(dest_dir) + "\\",
            ],
            capture_output=True,
            timeout=600,
        )

        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            stdout = result.stdout.decode(errors="replace").strip()
            msg = stderr or stdout or f"unrar exit code {result.returncode}"
            raise DownloadError(f"RAR extraction failed: {msg}")

    def _detect_dlc_dirs(self, game_dir: Path) -> list[str]:
        """Scan game directory for DLC folders that match known IDs."""
        found = []
        for dlc in self._catalog.all_dlcs():
            dlc_dir = game_dir / dlc.id
            if dlc_dir.is_dir():
                found.append(dlc.id)
        return found

    # ── Utilities ────────────────────────────────────────────────

    def get_installed_dlcs(self, game_dir: Path) -> list[tuple[DLCInfo, int, int]]:
        """Get installed DLCs with file count and folder size.

        Returns list of (dlc_info, file_count, folder_size_bytes).
        """
        results = []
        for dlc in self._catalog.all_dlcs():
            dlc_dir = game_dir / dlc.id
            if not dlc_dir.is_dir():
                continue
            file_count = 0
            total_size = 0
            try:
                for f in dlc_dir.rglob("*"):
                    if f.is_file():
                        file_count += 1
                        total_size += f.stat().st_size
            except OSError:
                pass

            # Also count __Installer/DLC/{id} files
            installer_dir = game_dir / "__Installer" / "DLC" / dlc.id
            if installer_dir.is_dir():
                try:
                    for f in installer_dir.rglob("*"):
                        if f.is_file():
                            file_count += 1
                            total_size += f.stat().st_size
                except OSError:
                    pass

            results.append((dlc, file_count, total_size))
        return results


def _hash_file(path: Path) -> str:
    """Compute uppercase hex MD5 hash of a file."""
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            md5.update(chunk)
    return md5.hexdigest().upper()
