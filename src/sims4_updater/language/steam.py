"""
Steam language pack downloader using DepotDownloader.

Downloads Strings_*.package files from Steam depots for users
who own The Sims 4 on Steam. DepotDownloader is auto-downloaded
from GitHub on first use (~32MB).
"""

from __future__ import annotations

import logging
import os
import queue
import re
import shutil
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import urllib.request
import json

from ..core.subprocess_ import Popen2

logger = logging.getLogger(__name__)

SIMS4_APP_ID = "1222670"
DEPOT_DOWNLOADER_REPO = "SteamRE/DepotDownloader"
DEPOT_DOWNLOADER_ASSET = "DepotDownloader-windows-x64.zip"

# Strings file filter for DepotDownloader -filelist
_FILELIST_CONTENT = r"regex:Data[\\/]Client[\\/]Strings_.*\.package"

# Map Sims 4 locale codes to Steam language names.
# Steam uses these names for the -language flag in DepotDownloader.
# Each language's Strings file lives in a language-specific depot config,
# so we must download each language separately.
LOCALE_TO_STEAM_LANG = {
    "cs_CZ": "czech",
    "da_DK": "danish",
    "de_DE": "german",
    "en_US": "english",
    "es_ES": "spanish",
    "fi_FI": "finnish",
    "fr_FR": "french",
    "it_IT": "italian",
    "ja_JP": "japanese",
    "ko_KR": "koreana",
    "nl_NL": "dutch",
    "no_NO": "norwegian",
    "pl_PL": "polish",
    "pt_BR": "brazilian",
    "ru_RU": "russian",
    "sv_SE": "swedish",
    "zh_CN": "schinese",
    "zh_TW": "tchinese",
}

LogCallback = Callable[[str], None]


@dataclass
class SteamDownloadResult:
    """Result of a Steam language download operation."""

    success: bool
    installed_locales: list[str] = field(default_factory=list)
    error: str = ""


class SteamLanguageDownloader:
    """Downloads language Strings files from Steam using DepotDownloader."""

    def __init__(
        self,
        app_dir: Path,
        game_dir: Path,
        cancel_event=None,
    ):
        self._app_dir = app_dir
        self._game_dir = game_dir
        self._cancel_event = cancel_event
        self._tool_dir = app_dir / "tools" / "DepotDownloader"

    # ── Tool Management ───────────────────────────────────────────

    def get_tool_path(self) -> Path:
        return self._tool_dir / "DepotDownloader.exe"

    def is_tool_installed(self) -> bool:
        return self.get_tool_path().is_file()

    def install_tool(
        self,
        log: LogCallback | None = None,
    ) -> bool:
        """Download DepotDownloader from GitHub releases.

        Returns True on success.
        """
        if log is None:
            log = lambda msg: None

        log("Fetching latest DepotDownloader release from GitHub...")

        try:
            # Get latest release info
            api_url = (
                f"https://api.github.com/repos/{DEPOT_DOWNLOADER_REPO}"
                f"/releases/latest"
            )
            req = urllib.request.Request(
                api_url,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                release = json.loads(resp.read().decode("utf-8"))

            # Find the windows-x64 asset
            download_url = None
            asset_size = 0
            for asset in release.get("assets", []):
                if DEPOT_DOWNLOADER_ASSET in asset["name"]:
                    download_url = asset["browser_download_url"]
                    asset_size = asset.get("size", 0)
                    break

            if not download_url:
                log(f"ERROR: Could not find {DEPOT_DOWNLOADER_ASSET} in release.")
                return False

            version = release.get("tag_name", "unknown")
            size_mb = asset_size / (1024 * 1024)
            log(f"Downloading DepotDownloader {version} ({size_mb:.1f} MB)...")

            # Download to temp file
            with tempfile.NamedTemporaryFile(
                suffix=".zip", delete=False,
            ) as tmp:
                tmp_path = Path(tmp.name)

            try:
                urllib.request.urlretrieve(download_url, tmp_path)
            except Exception as e:
                tmp_path.unlink(missing_ok=True)
                log(f"ERROR: Download failed: {e}")
                return False

            # Extract
            log("Extracting DepotDownloader...")
            self._tool_dir.mkdir(parents=True, exist_ok=True)

            try:
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    zf.extractall(self._tool_dir)
            except zipfile.BadZipFile as e:
                log(f"ERROR: Corrupt download: {e}")
                return False
            finally:
                tmp_path.unlink(missing_ok=True)

            if not self.is_tool_installed():
                log("ERROR: DepotDownloader.exe not found after extraction.")
                return False

            log(f"DepotDownloader {version} installed successfully.")
            return True

        except Exception as e:
            log(f"ERROR: Failed to install DepotDownloader: {e}")
            return False

    # ── Download ──────────────────────────────────────────────────

    def download_languages(
        self,
        username: str,
        password: str | None = None,
        auth_code: str | None = None,
        log: LogCallback | None = None,
        ask_password: Callable[[], str | None] | None = None,
        ask_auth_code: Callable[[], str | None] | None = None,
        locale_codes: list[str] | None = None,
    ) -> SteamDownloadResult:
        """Download language Strings files from Steam.

        Steam serves language files from language-specific depot configs,
        so we run DepotDownloader once per language with the ``-language``
        flag.  After the first run authenticates (password + 2FA), the
        ``-remember-password`` flag caches the session so subsequent runs
        are automatic.

        Args:
            username: Steam username.
            password: Steam password (None to use cached auth).
            auth_code: Steam Guard / 2FA code (None if not needed).
            log: Logging callback.
            ask_password: Callback to ask user for password.
            ask_auth_code: Callback to ask user for 2FA code.
            locale_codes: Specific locale codes to download.  If None,
                downloads all 18 languages.

        Returns:
            SteamDownloadResult with success status and installed locales.
        """
        if log is None:
            log = lambda msg: None

        if not self.is_tool_installed():
            return SteamDownloadResult(
                success=False,
                error="DepotDownloader not installed.",
            )

        # Determine which languages to download
        if locale_codes is None:
            locale_codes = list(LOCALE_TO_STEAM_LANG.keys())

        # Filter to only locales we have a Steam language mapping for
        targets = []
        for lc in locale_codes:
            steam_lang = LOCALE_TO_STEAM_LANG.get(lc)
            if steam_lang:
                targets.append((lc, steam_lang))
            else:
                log(f"WARNING: No Steam language mapping for {lc}, skipping.")

        if not targets:
            return SteamDownloadResult(
                success=False, error="No languages to download.",
            )

        # Create filelist for Strings filtering
        filelist_path = self._build_filelist()

        # Download directory
        download_dir = self._app_dir / "downloads" / "steam_lang"
        download_dir.mkdir(parents=True, exist_ok=True)

        all_installed: list[str] = []
        errors: list[str] = []
        first_run = True

        try:
            log(f"Downloading {len(targets)} language(s) from Steam...")
            log(f"Username: {username}")
            log("")

            for i, (locale_code, steam_lang) in enumerate(targets, 1):
                if self._cancel_event and self._cancel_event.is_set():
                    log("Download cancelled.")
                    break

                from .changer import LANGUAGES
                lang_name = LANGUAGES.get(locale_code, locale_code)
                log(f"[{i}/{len(targets)}] Downloading {lang_name} ({steam_lang})...")

                args = [
                    str(self.get_tool_path()),
                    "-app", SIMS4_APP_ID,
                    "-username", username,
                    "-remember-password",
                    "-language", steam_lang,
                    "-filelist", str(filelist_path),
                    "-dir", str(download_dir),
                ]

                # Only pass interactive auth callbacks on the first run.
                # After that, -remember-password caches the session.
                exit_code, output = self._run_depot_downloader(
                    args,
                    password=password if first_run else None,
                    auth_code=auth_code if first_run else None,
                    log=log,
                    ask_password=ask_password if first_run else None,
                    ask_auth_code=ask_auth_code if first_run else None,
                )
                first_run = False

                if self._cancel_event and self._cancel_event.is_set():
                    log("Download cancelled.")
                    break

                if exit_code != 0:
                    output_lower = output.lower()
                    if "not available from this account" in output_lower:
                        error = (
                            "The Sims 4 is not available on this Steam "
                            "account."
                        )
                        log(f"ERROR: {error}")
                        return SteamDownloadResult(
                            success=False,
                            installed_locales=all_installed,
                            error=error,
                        )
                    elif "invalid password" in output_lower:
                        log("ERROR: Invalid Steam password.")
                        return SteamDownloadResult(
                            success=False,
                            installed_locales=all_installed,
                            error="Invalid Steam password.",
                        )
                    else:
                        msg = f"{lang_name}: exit code {exit_code}"
                        log(f"WARNING: {msg}")
                        errors.append(msg)
                        continue

                # Copy any downloaded Strings files to game directory
                installed = self._copy_strings_to_game(download_dir, log)
                all_installed.extend(installed)
                log("")

            # Summary
            if all_installed:
                log(
                    f"Successfully installed {len(all_installed)} "
                    f"language pack(s)."
                )
                if errors:
                    log(f"{len(errors)} language(s) failed: "
                        + ", ".join(errors))
                return SteamDownloadResult(
                    success=True, installed_locales=all_installed,
                )
            else:
                error = "No language files were downloaded."
                if errors:
                    error += f" {len(errors)} failed: " + ", ".join(errors)
                log(f"WARNING: {error}")
                return SteamDownloadResult(success=False, error=error)

        finally:
            filelist_path.unlink(missing_ok=True)

    # ── Internal ──────────────────────────────────────────────────

    def _build_filelist(self) -> Path:
        """Create a temporary filelist file for DepotDownloader filtering."""
        filelist_path = self._app_dir / "downloads" / "steam_filelist.txt"
        filelist_path.parent.mkdir(parents=True, exist_ok=True)
        filelist_path.write_text(_FILELIST_CONTENT, encoding="utf-8")
        return filelist_path

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
    ) -> tuple[int, str]:
        """Run DepotDownloader, handling interactive auth prompts.

        Uses background reader threads for stdout and stderr so the
        main loop never blocks on pipe reads. This is critical because
        DepotDownloader writes interactive prompts (password, 2FA)
        without a trailing newline — a blocking read would deadlock.

        Returns (exit_code, combined_output).
        """
        if log is None:
            log = lambda msg: None

        proc = Popen2(args)
        output_lines: list[str] = []
        password_sent = False
        auth_code_sent = False
        buf = b""
        stall_cycles = 0

        # Start background reader threads for stdout and stderr.
        # This ensures peek()/read() blocking never stalls our main loop.
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
                    proc.interrupt()
                    return (-1, "Cancelled")

                # Drain both queues into our buffer (non-blocking)
                got_data = False
                while not stdout_q.empty():
                    try:
                        buf += stdout_q.get_nowait()
                        got_data = True
                    except queue.Empty:
                        break
                while not stderr_q.empty():
                    try:
                        buf += stderr_q.get_nowait()
                        got_data = True
                    except queue.Empty:
                        break

                if got_data:
                    stall_cycles = 0
                else:
                    stall_cycles += 1

                # Process complete lines (terminated by \n)
                while b"\n" in buf:
                    line_bytes, buf = buf.split(b"\n", 1)
                    line_bytes = line_bytes.replace(b"\r", b"")
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if line:
                        output_lines.append(line)
                        self._handle_output_line(line, log)

                # Check partial buffer for interactive prompts that
                # don't end with a newline (e.g. "Password: ").
                # Wait a few stall cycles (~300ms) to be sure no more
                # data is coming before treating it as a prompt.
                if buf and stall_cycles >= 3:
                    partial = buf.decode("utf-8", errors="replace").strip()
                    partial_lower = partial.lower()

                    handled = False

                    # Password prompt
                    if not password_sent and "password" in partial_lower:
                        output_lines.append(partial)
                        log(partial)
                        buf = b""
                        handled = True

                        if password:
                            pw = password
                        elif ask_password:
                            log("Steam is requesting your password...")
                            pw = ask_password()
                        else:
                            pw = None

                        if pw is None:
                            log("No password provided. Cancelling...")
                            proc.interrupt()
                            return (-1, "No password provided")

                        proc.stdin.write((pw + "\n").encode("utf-8"))
                        proc.stdin.flush()
                        password_sent = True
                        log("Password submitted.")
                        stall_cycles = 0

                    # 2FA / Steam Guard prompt
                    elif not auth_code_sent and any(
                        kw in partial_lower for kw in (
                            "steam guard", "two-factor", "2fa",
                            "authentication code", "auth code",
                        )
                    ):
                        output_lines.append(partial)
                        log(partial)
                        buf = b""
                        handled = True

                        if auth_code:
                            code = auth_code
                        elif ask_auth_code:
                            log("Steam Guard / 2FA code required...")
                            code = ask_auth_code()
                        else:
                            code = None

                        if code is None:
                            log("No auth code provided. Cancelling...")
                            proc.interrupt()
                            return (-1, "No auth code provided")

                        proc.stdin.write((code + "\n").encode("utf-8"))
                        proc.stdin.flush()
                        auth_code_sent = True
                        log("Auth code submitted.")
                        stall_cycles = 0

                    if handled:
                        continue

                time.sleep(0.1)

            # Process any remaining data in the buffer
            for chunk in buf.replace(b"\r\n", b"\n").split(b"\n"):
                line = chunk.decode("utf-8", errors="replace").strip()
                if line:
                    output_lines.append(line)
                    self._handle_output_line(line, log)

            exit_code = proc.wait()

        except Exception as e:
            logger.exception("DepotDownloader error")
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                pass
            return (-1, f"Process error: {e}")

        return (exit_code, "\n".join(output_lines))

    @staticmethod
    def _handle_output_line(line: str, log: LogCallback):
        """Process a single complete output line from DepotDownloader."""
        line_lower = line.lower()

        # Progress lines
        if re.search(r"\d+\.?\d*%", line):
            log(f"Progress: {line}")
            return

        # Auth success
        if "logged in" in line_lower:
            log("Successfully logged into Steam.")
            return

        # General depot/download output
        if any(kw in line_lower for kw in (
            "downloading", "depot", "manifest", "validating",
            "got depot", "downloaded", "total",
        )):
            log(line)
            return

        # Log other notable output
        if len(line) > 3:
            log(line)

    def _copy_strings_to_game(
        self, download_dir: Path, log: LogCallback,
    ) -> list[str]:
        """Copy downloaded Strings files to the game's Data/Client/ directory.

        Returns list of locale codes that were installed.
        """
        from .changer import LOCALE_TO_STRINGS

        # Reverse mapping: "ENG_US" -> "en_US"
        strings_to_locale = {v: k for k, v in LOCALE_TO_STRINGS.items()}

        dest_dir = self._game_dir / "Data" / "Client"
        dest_dir.mkdir(parents=True, exist_ok=True)

        installed_locales = []

        # Search download directory recursively for Strings_*.package
        for f in download_dir.rglob("Strings_*.package"):
            if not f.is_file():
                continue

            filename = f.name
            # Extract suffix like "ENG_US" from "Strings_ENG_US.package"
            if not filename.startswith("Strings_") or not filename.endswith(".package"):
                continue

            suffix = filename[len("Strings_"):-len(".package")]
            locale = strings_to_locale.get(suffix)

            dest_path = dest_dir / filename
            try:
                shutil.copy2(f, dest_path)
                code_str = f" ({locale})" if locale else ""
                log(f"Installed: {filename}{code_str}")
                if locale:
                    installed_locales.append(locale)
            except OSError as e:
                log(f"ERROR: Failed to copy {filename}: {e}")

        return installed_locales
