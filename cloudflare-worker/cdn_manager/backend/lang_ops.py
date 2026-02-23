"""Language operations — scan, pack, upload pipeline for the GUI."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from threading import Event

from .connection import CDN_DOMAIN, SEEDBOX_BASE_DIR, ConnectionManager
from .dlc_ops import fmt_size

LANGUAGES: dict[str, str] = {
    "cs_CZ": "\u010ce\u0161tina",
    "da_DK": "Dansk",
    "de_DE": "Deutsch",
    "en_US": "English",
    "es_ES": "Espa\u00f1ol",
    "fr_FR": "Fran\u00e7ais",
    "it_IT": "Italiano",
    "nl_NL": "Nederlands",
    "no_NO": "Norsk",
    "pl_PL": "Polski",
    "pt_BR": "Portugu\u00eas (Brasil)",
    "fi_FI": "Suomi",
    "sv_SE": "Svenska",
    "ru_RU": "\u0420\u0443\u0441\u0441\u043a\u0438\u0439",
    "ja_JP": "\u65e5\u672c\u8a9e",
    "zh_TW": "\u7e41\u9ad4\u4e2d\u6587",
    "zh_CN": "\u7b80\u4f53\u4e2d\u6587",
    "ko_KR": "\ud55c\uad6d\uc5b4",
}

LOCALE_TO_STRINGS: dict[str, str] = {
    "cs_CZ": "CZE_CZ", "da_DK": "DAN_DK", "de_DE": "GER_DE", "en_US": "ENG_US",
    "es_ES": "SPA_ES", "fr_FR": "FRE_FR", "it_IT": "ITA_IT", "nl_NL": "DUT_NL",
    "no_NO": "NOR_NO", "pl_PL": "POL_PL", "pt_BR": "POR_BR", "fi_FI": "FIN_FI",
    "sv_SE": "SWE_SE", "ru_RU": "RUS_RU", "ja_JP": "JPN_JP", "zh_TW": "CHT_CN",
    "zh_CN": "CHS_CN", "ko_KR": "KOR_KR",
}

STRINGS_SEARCH_DIRS = ["Data/Client", "Delta/Base"]


def scan_installed_languages(game_dir: Path) -> dict[str, list[Path]]:
    """Find installed Strings_XXX_XX.package files for each locale.

    Returns {locale_code: [file_paths]}.
    """
    installed: dict[str, list[Path]] = {}
    for locale_code, strings_suffix in LOCALE_TO_STRINGS.items():
        filename = f"Strings_{strings_suffix}.package"
        found: list[Path] = []
        for search_dir in STRINGS_SEARCH_DIRS:
            candidate = game_dir / search_dir / filename
            if candidate.is_file():
                found.append(candidate)
        if found:
            installed[locale_code] = found
    return installed


def pack_language(game_dir: Path, locale_code: str, output_dir: Path) -> Path:
    """Create a ZIP for a language pack. Returns path to ZIP."""
    strings_suffix = LOCALE_TO_STRINGS.get(locale_code)
    if not strings_suffix:
        raise ValueError(f"Unknown locale code: {locale_code}")

    filename = f"Strings_{strings_suffix}.package"
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{locale_code}.zip"

    files_to_pack: list[tuple[str, Path]] = []
    for search_dir in STRINGS_SEARCH_DIRS:
        candidate = game_dir / search_dir / filename
        if candidate.is_file():
            archive_name = f"{search_dir}/{filename}"
            files_to_pack.append((archive_name, candidate))

    if not files_to_pack:
        raise FileNotFoundError(
            f"No Strings file found for {locale_code} (expected {filename})"
        )

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for archive_name, abs_path in files_to_pack:
            zf.write(abs_path, archive_name)

    return zip_path


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().upper()


def process_language(
    game_dir: Path,
    locale_code: str,
    conn: ConnectionManager,
    output_dir: Path,
    *,
    force: bool = False,
    cancel_event: Event | None = None,
    log_cb=None,
    progress_cb=None,
) -> dict | None:
    """Pack, upload, and register a single language pack.

    Returns manifest entry dict on success, or None on failure/cancel.
    """
    cdn_path = f"language/{locale_code}.zip"
    remote_path = f"{SEEDBOX_BASE_DIR}/{cdn_path}"
    lang_name = LANGUAGES.get(locale_code, locale_code)
    tag = f"[{locale_code}]"

    def log(msg, level="info"):
        if log_cb:
            log_cb(f"{tag} {msg}", level)

    # Check if already on CDN
    if not force and conn.kv_exists(cdn_path):
        log(f"Already on CDN ({lang_name}), skipping")
        return {
            "url": f"{CDN_DOMAIN}/{cdn_path}",
            "size": 0,
            "md5": "",
            "filename": f"{locale_code}.zip",
        }

    if cancel_event and cancel_event.is_set():
        return None

    # Pack
    log(f"Packing {lang_name}...")
    try:
        zip_path = pack_language(game_dir, locale_code, output_dir)
    except FileNotFoundError as e:
        log(f"Skip: {e}", "warning")
        return None

    zip_size = zip_path.stat().st_size
    zip_md5 = md5_file(zip_path)
    log(f"Packed: {fmt_size(zip_size)}, MD5: {zip_md5}")

    if cancel_event and cancel_event.is_set():
        zip_path.unlink(missing_ok=True)
        return None

    # Upload
    log(f"Uploading {fmt_size(zip_size)}...")
    try:
        conn.upload_sftp(zip_path, remote_path, progress_cb=progress_cb)
    except Exception as e:
        log(f"Upload failed: {e}", "error")
        zip_path.unlink(missing_ok=True)
        return None

    if cancel_event and cancel_event.is_set():
        zip_path.unlink(missing_ok=True)
        return None

    # Register KV
    try:
        conn.kv_put(cdn_path, remote_path)
        log(f"Registered in CDN")
    except Exception as e:
        log(f"KV registration failed: {e}", "error")
        zip_path.unlink(missing_ok=True)
        return None

    # Clean up
    zip_path.unlink(missing_ok=True)

    entry = {
        "url": f"{CDN_DOMAIN}/{cdn_path}",
        "size": zip_size,
        "md5": zip_md5,
        "filename": f"{locale_code}.zip",
    }
    log(f"Done ({lang_name}, {fmt_size(zip_size)})", "success")
    return entry
