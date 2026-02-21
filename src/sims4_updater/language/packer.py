"""
Language Pack Packer — pack Strings_XXX_XX.package files into distributable
ZIP archives and generate manifest JSON for language_downloads.

Each language pack ZIP contains the Strings file inside Data/Client/ so it
can be extracted directly into the game directory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .changer import LANGUAGES, LOCALE_TO_STRINGS, STRINGS_CHECK_DIRS

logger = logging.getLogger(__name__)

# Callback: (current_index, total_count, locale_code, message)
LangPackProgressCallback = Callable[[int, int, str, str], None]


# Reverse mapping: "ENG_US" -> "en_US"
_STRINGS_TO_LOCALE = {v: k for k, v in LOCALE_TO_STRINGS.items()}


@dataclass
class LangPackResult:
    """Result of packing a single language pack."""

    locale_code: str
    language_name: str
    filename: str
    path: Path
    size: int
    md5: str


class LanguagePacker:
    """Packs language Strings files into distributable ZIP archives."""

    def get_installed_packs(
        self, game_dir: Path,
    ) -> list[tuple[str, str, str, int]]:
        """Scan game dir for installed Strings_*.package files.

        Returns list of (locale_code, language_name, package_filename, file_size).
        """
        results = []
        seen_codes = set()

        for check_dir_rel in STRINGS_CHECK_DIRS:
            check_dir = game_dir / check_dir_rel.replace("/", os.sep)
            if not check_dir.is_dir():
                continue

            for f in check_dir.iterdir():
                if not f.is_file():
                    continue
                name = f.name
                # Match Strings_XXX_XX.package
                if not name.startswith("Strings_") or not name.endswith(".package"):
                    continue

                # Extract the suffix like "ENG_US" from "Strings_ENG_US.package"
                suffix = name[len("Strings_"):-len(".package")]
                locale_code = _STRINGS_TO_LOCALE.get(suffix)
                if not locale_code or locale_code in seen_codes:
                    continue

                seen_codes.add(locale_code)
                lang_name = LANGUAGES.get(locale_code, locale_code)
                size = f.stat().st_size
                results.append((locale_code, lang_name, name, size))

        # Sort by language name
        results.sort(key=lambda x: x[1])
        return results

    @staticmethod
    def get_zip_filename(locale_code: str) -> str:
        """Get the expected ZIP filename for a language pack."""
        lang_name = LANGUAGES.get(locale_code, locale_code)
        # Use ASCII-safe name
        safe_name = lang_name.encode("ascii", "ignore").decode()
        safe_name = safe_name.replace(" ", "_").replace("(", "").replace(")", "")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in "_-")
        if not safe_name:
            safe_name = locale_code
        return f"Sims4_Lang_{locale_code}_{safe_name}.zip"

    def get_zip_path(self, locale_code: str, output_dir: Path) -> Path:
        return output_dir / self.get_zip_filename(locale_code)

    def _find_strings_file(
        self, game_dir: Path, locale_code: str,
    ) -> Path | None:
        """Find the Strings_XXX_XX.package for a locale code."""
        suffix = LOCALE_TO_STRINGS.get(locale_code)
        if not suffix:
            return None
        filename = f"Strings_{suffix}.package"

        for check_dir_rel in STRINGS_CHECK_DIRS:
            path = game_dir / check_dir_rel.replace("/", os.sep) / filename
            if path.is_file():
                return path
        return None

    def pack_single(
        self,
        game_dir: Path,
        locale_code: str,
        output_dir: Path,
    ) -> LangPackResult:
        """Pack a single language Strings file into a ZIP archive.

        The ZIP preserves the Data/Client/ directory structure so it can
        be extracted directly into the game directory.
        """
        strings_file = self._find_strings_file(game_dir, locale_code)
        if strings_file is None:
            raise FileNotFoundError(
                f"Strings file not found for {locale_code}"
            )

        output_dir.mkdir(parents=True, exist_ok=True)

        zip_name = self.get_zip_filename(locale_code)
        zip_path = output_dir / zip_name

        # Store with relative path Data/Client/Strings_XXX_XX.package
        rel_path = strings_file.relative_to(game_dir)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(strings_file, str(rel_path).replace("\\", "/"))

        size = zip_path.stat().st_size
        md5 = _hash_file(zip_path)

        return LangPackResult(
            locale_code=locale_code,
            language_name=LANGUAGES.get(locale_code, locale_code),
            filename=zip_name,
            path=zip_path,
            size=size,
            md5=md5,
        )

    def pack_multiple(
        self,
        game_dir: Path,
        locale_codes: list[str],
        output_dir: Path,
        progress_cb: LangPackProgressCallback | None = None,
    ) -> list[LangPackResult]:
        """Pack multiple language packs sequentially."""
        results = []
        for i, code in enumerate(locale_codes):
            if progress_cb:
                progress_cb(i, len(locale_codes), code, f"Packing {code}...")
            try:
                result = self.pack_single(game_dir, code, output_dir)
                results.append(result)
            except (FileNotFoundError, OSError) as e:
                logger.warning("Failed to pack language %s: %s", code, e)

        if progress_cb:
            progress_cb(len(locale_codes), len(locale_codes), "", "Done")

        return results

    def generate_manifest(
        self,
        results: list[LangPackResult],
        output_dir: Path,
        url_prefix: str = "<UPLOAD_URL>",
    ) -> Path:
        """Generate manifest JSON for language_downloads section.

        Returns path to the generated manifest file.
        """
        manifest = {}
        for r in results:
            manifest[r.locale_code] = {
                "url": f"{url_prefix}/{r.filename}",
                "size": r.size,
                "md5": r.md5,
                "filename": r.filename,
            }

        manifest_path = output_dir / "manifest_language_downloads.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return manifest_path


def _hash_file(path: Path) -> str:
    """Compute uppercase hex MD5 hash of a file."""
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            md5.update(chunk)
    return md5.hexdigest().upper()
