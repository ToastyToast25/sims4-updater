"""
Language Changer tab — change The Sims 4 game language.

Shows all 18 languages with clear Installed/Missing status badges,
per-language download buttons for missing packs, and a bulk
"Download All Missing" action. Writes language changes to
anadius.cfg + registry + RldOrigin.ini.
"""

from __future__ import annotations

import tkinter as tk
import tkinter.simpledialog
import threading
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import InfoCard, StatusBadge, get_animator

if TYPE_CHECKING:
    from ..app import App


# Row status colors
_INSTALLED_COLOR = theme.COLORS["success"]
_MISSING_COLOR = theme.COLORS["error"]
_UNAVAIL_COLOR = theme.COLORS["text_muted"]


class LanguageFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._busy = False
        self._animator = get_animator()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=3)  # pack list gets more space
        self.grid_rowconfigure(2, weight=2)  # log gets less

        # State
        from ...language.changer import LANGUAGES

        self._languages = LANGUAGES  # {code: name}
        self._installed_langs: dict[str, bool] = {}
        self._lang_downloads: dict = {}  # {locale_code: LanguageDownloadEntry}
        self._row_widgets: dict[str, dict] = {}  # code -> widget refs

        # ── Top section ───────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="new", padx=0, pady=0)
        top.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(
            top,
            text="Language Changer",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, padx=30, pady=(20, 4), sticky="w")

        ctk.CTkLabel(
            top,
            text="Change game language and download missing language packs",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=1, column=0, padx=30, pady=(0, 12), sticky="w")

        # ── Status card (compact) ────────────────────────────────
        self._card = InfoCard(top, fg_color=theme.COLORS["bg_card"])
        self._card.grid(row=2, column=0, padx=30, pady=(0, 10), sticky="ew")
        self._card.grid_columnconfigure(1, weight=1)

        # Current language
        ctk.CTkLabel(
            self._card, text="Current",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(
            row=0, column=0,
            padx=(theme.CARD_PAD_X, 8),
            pady=(theme.CARD_PAD_Y, 4), sticky="w",
        )

        self._current_badge = StatusBadge(
            self._card, text="Detecting...", style="muted",
        )
        self._current_badge.grid(
            row=0, column=1, padx=0,
            pady=(theme.CARD_PAD_Y, 4), sticky="w",
        )

        # Packs summary
        ctk.CTkLabel(
            self._card, text="Packs",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(
            row=1, column=0,
            padx=(theme.CARD_PAD_X, 8),
            pady=(4, theme.CARD_PAD_Y), sticky="w",
        )

        self._packs_badge = StatusBadge(
            self._card, text="...", style="muted",
        )
        self._packs_badge.grid(
            row=1, column=1, padx=0,
            pady=(4, theme.CARD_PAD_Y), sticky="w",
        )

        # ── Language selector + buttons ──────────────────────────
        controls = ctk.CTkFrame(top, fg_color="transparent")
        controls.grid(row=3, column=0, padx=30, pady=(0, 10), sticky="ew")
        controls.grid_columnconfigure(0, weight=1)

        lang_values = [f"{name}  ({code})" for code, name in LANGUAGES.items()]
        self._lang_var = ctk.StringVar()

        self._lang_dropdown = ctk.CTkComboBox(
            controls,
            values=lang_values,
            variable=self._lang_var,
            font=ctk.CTkFont(size=13),
            height=36,
            state="readonly",
            dropdown_font=ctk.CTkFont(size=12),
        )
        self._lang_dropdown.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self._apply_btn = ctk.CTkButton(
            controls,
            text="Apply Language",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_apply,
        )
        self._apply_btn.grid(row=0, column=1, padx=(0, 6), sticky="ew")

        self._dl_all_btn = ctk.CTkButton(
            controls,
            text="Download All Missing",
            font=ctk.CTkFont(size=13),
            height=36,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["success"],
            hover_color="#3ae882",
            text_color="#1a1a2e",
            command=self._on_download_all,
        )
        self._dl_all_btn.grid(row=0, column=2, padx=(0, 6), sticky="ew")

        self._steam_dl_btn = ctk.CTkButton(
            controls,
            text="Download from Steam",
            font=ctk.CTkFont(size=13),
            height=36,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color="#1b2838",
            hover_color="#2a475e",
            text_color="#c7d5e0",
            command=self._on_steam_download,
        )
        self._steam_dl_btn.grid(row=0, column=3, padx=(0, 6), sticky="ew")

        self._refresh_btn = ctk.CTkButton(
            controls,
            text="Refresh",
            font=ctk.CTkFont(size=13),
            height=36,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._refresh_status,
        )
        self._refresh_btn.grid(row=0, column=4, sticky="ew")

        # ── Language Packs list (scrollable) ─────────────────────
        pack_section = ctk.CTkFrame(self, fg_color="transparent")
        pack_section.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 8))
        pack_section.grid_columnconfigure(0, weight=1)
        pack_section.grid_rowconfigure(1, weight=1)

        pack_header = ctk.CTkFrame(pack_section, fg_color="transparent")
        pack_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        pack_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            pack_header,
            text="Language Packs",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, sticky="w")

        self._pack_count_label = ctk.CTkLabel(
            pack_header,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._pack_count_label.grid(row=0, column=1, sticky="e")

        self._pack_scroll = ctk.CTkScrollableFrame(
            pack_section,
            corner_radius=8,
            fg_color=theme.COLORS["bg_deeper"],
            border_width=1,
            border_color=theme.COLORS["border"],
            scrollbar_button_color=theme.COLORS["separator"],
            scrollbar_button_hover_color=theme.COLORS["accent"],
        )
        self._pack_scroll.grid(row=1, column=0, sticky="nsew")
        self._pack_scroll.grid_columnconfigure(0, weight=1)

        # ── Log viewer ───────────────────────────────────────────
        log_section = ctk.CTkFrame(self, fg_color="transparent")
        log_section.grid(row=2, column=0, sticky="nsew", padx=30, pady=(0, 15))
        log_section.grid_columnconfigure(0, weight=1)
        log_section.grid_rowconfigure(1, weight=1)

        header_row = ctk.CTkFrame(log_section, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_row,
            text="Activity Log",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header_row,
            text="Clear",
            font=ctk.CTkFont(size=11),
            height=24, width=60,
            corner_radius=4,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._clear_log,
        ).grid(row=0, column=1, sticky="e")

        self._log_box = ctk.CTkTextbox(
            log_section,
            font=ctk.CTkFont(*theme.FONT_MONO),
            fg_color=theme.COLORS["bg_deeper"],
            text_color=theme.COLORS["text_muted"],
            border_width=1,
            border_color=theme.COLORS["border"],
            corner_radius=theme.CORNER_RADIUS_SMALL,
            state="disabled",
            wrap="word",
        )
        self._log_box.grid(row=1, column=0, sticky="nsew")

    # ── Logging ──────────────────────────────────────────────────

    def _log(self, message: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", message + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _enqueue_log(self, msg: str):
        self.app._enqueue_gui(self._log, msg)

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # ── Status ───────────────────────────────────────────────────

    def on_show(self):
        self._refresh_status()

    def _refresh_status(self):
        from ...language.changer import (
            get_current_language, LANGUAGES, get_installed_languages,
        )

        def _bg():
            game_dir = self.app.settings.game_path or None
            code = get_current_language(game_dir=game_dir)
            name = LANGUAGES.get(code, "Unknown")

            # Check if game dir exists
            game_dir_valid = False
            if game_dir:
                from pathlib import Path
                game_dir_valid = Path(game_dir).is_dir()

            # Check which language packs are installed
            installed_langs = {}
            if game_dir and game_dir_valid:
                installed_langs = get_installed_languages(game_dir)

            # Fetch manifest for language download entries
            lang_downloads = {}
            try:
                manifest_url = self.app.settings.manifest_url
                if manifest_url:
                    updater = self.app.updater
                    manifest = updater.patch_client.fetch_manifest()
                    lang_downloads = manifest.language_downloads
            except Exception:
                pass  # Manifest fetch failure is non-fatal

            return {
                "code": code,
                "name": name,
                "game_dir": game_dir,
                "game_dir_valid": game_dir_valid,
                "installed_langs": installed_langs,
                "lang_downloads": lang_downloads,
            }

        def _done(info):
            code = info["code"]
            name = info["name"]
            self._installed_langs = info["installed_langs"]
            self._lang_downloads = info["lang_downloads"]

            self._current_badge.set_status(f"{name}  ({code})", "info")

            # Set dropdown to match current
            for display_code, display_name in self._languages.items():
                if display_code == code:
                    self._lang_var.set(f"{display_name}  ({display_code})")
                    break

            # Packs summary badge
            installed_count = sum(
                1 for v in self._installed_langs.values() if v
            )
            missing_count = len(self._languages) - installed_count
            gd = info["game_dir"]

            if not gd or not info["game_dir_valid"]:
                self._packs_badge.set_status(
                    "Set game directory in Settings", "warning",
                )
            elif missing_count == 0:
                self._packs_badge.set_status(
                    f"All {installed_count} packs installed", "success",
                )
            else:
                self._packs_badge.set_status(
                    f"{installed_count} installed, {missing_count} missing",
                    "error",
                )

            # Build / update the language pack list
            self._rebuild_pack_rows()

            # Update Download All button
            has_downloads = bool(self._lang_downloads)
            downloadable_missing = sum(
                1 for code in self._languages
                if not self._installed_langs.get(code, False)
                and code in self._lang_downloads
            )
            if has_downloads and downloadable_missing > 0:
                self._dl_all_btn.configure(
                    text=f"Download All Missing ({downloadable_missing})",
                    state="normal" if not self._busy else "disabled",
                )
            else:
                self._dl_all_btn.configure(
                    text="Download All Missing",
                    state="disabled",
                )

        def _err(e):
            self._current_badge.set_status("Error", "error")
            self._enqueue_log(f"Detection failed: {e}")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Language Packs List ──────────────────────────────────────

    def _rebuild_pack_rows(self):
        """Destroy and rebuild all language pack rows."""
        # Destroy old rows
        for rw in self._row_widgets.values():
            rw["frame"].destroy()
        self._row_widgets.clear()

        installed_count = sum(1 for v in self._installed_langs.values() if v)
        missing_count = len(self._languages) - installed_count
        self._pack_count_label.configure(
            text=f"{installed_count} installed / {missing_count} missing"
        )

        # Build rows — missing packs first, then installed
        row_idx = 0
        missing_codes = []
        installed_codes = []

        for code in self._languages:
            if self._installed_langs.get(code, False):
                installed_codes.append(code)
            else:
                missing_codes.append(code)

        # Missing packs header (if any)
        if missing_codes:
            hdr = ctk.CTkFrame(self._pack_scroll, fg_color="transparent")
            hdr.grid(row=row_idx, column=0, padx=8, pady=(8, 4), sticky="ew")
            ctk.CTkLabel(
                hdr,
                text=f"MISSING ({len(missing_codes)})",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=_MISSING_COLOR,
            ).pack(side="left")
            self._row_widgets["__missing_hdr"] = {"frame": hdr}
            row_idx += 1

            for code in missing_codes:
                self._build_pack_row(code, row_idx, installed=False)
                row_idx += 1

        # Installed packs header (if any)
        if installed_codes:
            hdr = ctk.CTkFrame(self._pack_scroll, fg_color="transparent")
            hdr.grid(row=row_idx, column=0, padx=8, pady=(12, 4), sticky="ew")
            ctk.CTkLabel(
                hdr,
                text=f"INSTALLED ({len(installed_codes)})",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=_INSTALLED_COLOR,
            ).pack(side="left")
            self._row_widgets["__installed_hdr"] = {"frame": hdr}
            row_idx += 1

            for code in installed_codes:
                self._build_pack_row(code, row_idx, installed=True)
                row_idx += 1

    def _build_pack_row(self, code: str, grid_row: int, installed: bool):
        """Build a single language pack row."""
        name = self._languages.get(code, code)
        has_download = code in self._lang_downloads

        # Alternating background
        bg = theme.COLORS["bg_card"] if grid_row % 2 == 0 else theme.COLORS["bg_card_alt"]

        row_frame = ctk.CTkFrame(
            self._pack_scroll,
            fg_color=bg,
            corner_radius=6,
            border_width=1,
            border_color=theme.COLORS["border"],
            height=36,
        )
        row_frame.grid(row=grid_row, column=0, padx=5, pady=2, sticky="ew")
        row_frame.grid_columnconfigure(1, weight=1)
        row_frame.grid_propagate(False)

        # Status dot
        dot_color = _INSTALLED_COLOR if installed else _MISSING_COLOR
        ctk.CTkLabel(
            row_frame,
            text="\u25cf",
            font=ctk.CTkFont(size=10),
            text_color=dot_color,
            width=16,
        ).grid(row=0, column=0, padx=(12, 0), pady=6)

        # Language name and code
        ctk.CTkLabel(
            row_frame,
            text=f"{name}  ({code})",
            font=ctk.CTkFont(size=12),
            text_color=theme.COLORS["text"] if installed else theme.COLORS["text"],
            anchor="w",
        ).grid(row=0, column=1, padx=(4, 0), pady=6, sticky="w")

        # Status pill
        if installed:
            pill_text = "Installed"
            pill_color = _INSTALLED_COLOR
        else:
            pill_text = "Missing"
            pill_color = _MISSING_COLOR

        pill = ctk.CTkFrame(
            row_frame,
            corner_radius=10,
            border_width=1,
            border_color=pill_color,
            fg_color="transparent",
            height=22,
        )
        pill.grid(row=0, column=2, padx=(4, 0), pady=6, sticky="e")
        ctk.CTkLabel(
            pill,
            text=pill_text,
            font=ctk.CTkFont(size=9),
            text_color=pill_color,
        ).pack(padx=8, pady=2)

        # Download button or progress label (for missing packs only)
        download_btn = None
        dl_progress_label = None

        if not installed:
            if has_download:
                download_btn = ctk.CTkButton(
                    row_frame,
                    text="Download",
                    width=70,
                    height=24,
                    font=ctk.CTkFont(size=11),
                    fg_color=theme.COLORS["success"],
                    hover_color="#3ae882",
                    text_color="#1a1a2e",
                    corner_radius=4,
                    command=lambda c=code: self._on_download_pack(c),
                )
                download_btn.grid(row=0, column=3, padx=(6, 8), pady=6, sticky="e")
                if self._busy:
                    download_btn.configure(state="disabled")
            else:
                ctk.CTkLabel(
                    row_frame,
                    text="Not in manifest",
                    font=ctk.CTkFont(size=9),
                    text_color=_UNAVAIL_COLOR,
                ).grid(row=0, column=3, padx=(6, 8), pady=6, sticky="e")

            # Progress label (hidden, shown during download)
            dl_progress_label = ctk.CTkLabel(
                row_frame,
                text="",
                font=ctk.CTkFont(size=9),
                text_color=theme.COLORS["accent"],
                width=70,
            )
            # Not gridded — shown during download

        # Hover effect
        def on_enter(e, rf=row_frame):
            self._animator.cancel_all(rf, tag="row_hover")
            self._animator.animate_color(
                rf, "border_color",
                theme.COLORS["border"], theme.COLORS["accent"],
                theme.ANIM_FAST, tag="row_hover",
            )

        def on_leave(e, rf=row_frame):
            self._animator.cancel_all(rf, tag="row_hover")
            self._animator.animate_color(
                rf, "border_color",
                theme.COLORS["accent"], theme.COLORS["border"],
                theme.ANIM_NORMAL, tag="row_hover",
            )

        row_frame.bind("<Enter>", on_enter)
        row_frame.bind("<Leave>", on_leave)
        for child in row_frame.winfo_children():
            child.bind("<Enter>", on_enter)
            child.bind("<Leave>", on_leave)

        self._row_widgets[code] = {
            "frame": row_frame,
            "download_btn": download_btn,
            "dl_progress_label": dl_progress_label,
        }

    # ── Apply ────────────────────────────────────────────────────

    def _get_selected_code(self) -> str | None:
        """Extract language code from the dropdown selection."""
        display = self._lang_var.get()
        if not display:
            return None
        # Format: "English  (en_US)"
        if "(" in display and display.endswith(")"):
            return display.rsplit("(", 1)[1].rstrip(")")
        return None

    def _on_apply(self):
        if self._busy:
            return

        code = self._get_selected_code()
        if not code:
            self.app.show_toast("Please select a language.", "warning")
            return

        name = self._languages.get(code, code)
        game_dir = self.app.settings.game_path or None

        # Check if language pack is installed
        if game_dir and self._installed_langs and not self._installed_langs.get(code, False):
            from ...language.changer import get_strings_filename
            filename = get_strings_filename(code) or code

            # If a download is available in the manifest, offer to download it
            if code in self._lang_downloads:
                answer = tk.messagebox.askyesnocancel(
                    "Language Pack Missing",
                    f"The language pack for {name} ({filename}) is not installed.\n"
                    f"The game will not display in {name} without it.\n\n"
                    f"A download is available in the manifest.\n\n"
                    f"Yes = Download the pack now\n"
                    f"No = Apply config change anyway (game stays in current language)\n"
                    f"Cancel = Do nothing",
                    parent=self,
                )
                if answer is None:
                    # Cancel — do nothing
                    return
                if answer:
                    # Yes — download first, then apply language on success
                    self._download_then_apply(code)
                    return
                # No — fall through to apply config without download
            else:
                # No download available — warn and let user decide
                proceed = tk.messagebox.askyesno(
                    "Language Pack Missing",
                    f"The language pack for {name} ({filename}) is not installed "
                    f"and no download is available in the manifest.\n\n"
                    f"The config will be updated but the game will stay in the "
                    f"current language until the pack is installed.\n\n"
                    f"Continue anyway?",
                    parent=self,
                )
                if not proceed:
                    return

        self._apply_language(code)

    def _apply_language(self, code: str):
        """Apply the language config change (anadius.cfg, registry, RldOrigin.ini)."""
        name = self._languages.get(code, code)
        game_dir = self.app.settings.game_path or None

        self._set_busy(True)
        self._log(f"--- Changing language to {name} ({code}) ---")

        from ...language.changer import set_language

        def _bg():
            result = set_language(
                code, game_dir=game_dir, log=self._enqueue_log,
            )

            if not game_dir:
                self._enqueue_log(
                    "No game directory set — skipped crack config updates. "
                    "Set game directory in Settings."
                )

            # Save to settings
            self.app.settings.language = code
            self.app.settings.save()
            self._enqueue_log("Language preference saved to settings.")

            return result

        def _done(result):
            self._set_busy(False)
            if result.success:
                parts = []
                if result.anadius_updated:
                    parts.append(f"{len(result.anadius_updated)} anadius config(s)")
                if result.registry_ok:
                    parts.append("registry")
                if result.rld_updated:
                    parts.append(f"{len(result.rld_updated)} RldOrigin config(s)")
                detail = ", ".join(parts)
                self._log(f"Language changed to {name} ({code})! Updated: {detail}")
                self._log("Restart the game for the language change to take effect.")
                self.app.show_toast(
                    f"Language changed to {name}! Restart the game.", "success",
                )
            else:
                self._log(
                    "Could not update any config. "
                    "Run as Administrator and ensure game directory is set."
                )
                self.app.show_toast(
                    "Language change failed — no configs could be updated.",
                    "error",
                )
            self._refresh_status()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Failed: {e}")
            self.app.show_toast(f"Language change failed: {e}", "error")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    def _download_then_apply(self, code: str):
        """Download the language pack, then apply the language change on success."""
        name = self._languages.get(code, code)
        game_dir = self.app.settings.game_path
        entry = self._lang_downloads.get(code)
        if not entry or not game_dir:
            return

        self._set_busy(True)

        # Update row UI to show downloading state
        rw = self._row_widgets.get(code)
        if rw:
            if rw.get("download_btn"):
                rw["download_btn"].grid_remove()
            if rw.get("dl_progress_label"):
                lbl = rw["dl_progress_label"]
                lbl.configure(text="Downloading...")
                lbl.grid(row=0, column=3, padx=(6, 8), pady=6, sticky="e")

        self._log(f"--- Downloading {name} ({code}) then applying language ---")

        def _bg():
            downloader = self.app.updater.create_language_downloader(game_dir)
            try:
                return downloader.download_language(entry, log=self._enqueue_log)
            finally:
                downloader.close()

        def _done(success):
            if success:
                self._enqueue_log(f"{name} pack installed. Applying language change...")
                self.app.show_toast(
                    f"{name} language pack installed!", "success",
                )
                # Now apply the language config
                self._refresh_status()
                self._apply_language(code)
            else:
                self._set_busy(False)
                self.app.show_toast(
                    f"Download failed for {name}. Language not changed.", "error",
                )
                self._refresh_status()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Download failed: {e}")
            self.app.show_toast(f"Download failed: {e}", "error")
            self._refresh_status()

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Download ─────────────────────────────────────────────────

    def _on_download_pack(self, code: str):
        """Download the language pack for a specific language."""
        if self._busy:
            return

        game_dir = self.app.settings.game_path
        if not game_dir:
            self.app.show_toast(
                "Set game directory in Settings first.", "warning",
            )
            return

        entry = self._lang_downloads.get(code)
        if not entry:
            self.app.show_toast(
                f"No download available for {code}.", "warning",
            )
            return

        if self._installed_langs.get(code, False):
            self.app.show_toast(f"{code} is already installed.", "info")
            return

        name = self._languages.get(code, code)
        self._set_busy(True)

        # Update row UI to show downloading state
        rw = self._row_widgets.get(code)
        if rw:
            if rw.get("download_btn"):
                rw["download_btn"].grid_remove()
            if rw.get("dl_progress_label"):
                lbl = rw["dl_progress_label"]
                lbl.configure(text="Downloading...")
                lbl.grid(row=0, column=3, padx=(6, 8), pady=6, sticky="e")

        self._log(f"--- Downloading: {name} ({code}) ---")

        def _bg():
            downloader = self.app.updater.create_language_downloader(game_dir)
            try:
                return downloader.download_language(entry, log=self._enqueue_log)
            finally:
                downloader.close()

        def _done(success):
            self._set_busy(False)
            if success:
                self.app.show_toast(
                    f"{name} language pack installed!", "success",
                )
            else:
                self.app.show_toast(
                    f"Download failed for {name}.", "error",
                )
            self._refresh_status()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Download failed: {e}")
            self.app.show_toast(f"Download failed: {e}", "error")
            self._refresh_status()

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    def _on_download_all(self):
        """Download all missing language packs."""
        if self._busy:
            return

        game_dir = self.app.settings.game_path
        if not game_dir:
            self.app.show_toast(
                "Set game directory in Settings first.", "warning",
            )
            return

        if not self._lang_downloads:
            self.app.show_toast(
                "No language packs available in manifest.", "warning",
            )
            return

        # Count how many are actually missing and downloadable
        missing = {
            code: entry for code, entry in self._lang_downloads.items()
            if not self._installed_langs.get(code, False)
        }
        if not missing:
            self.app.show_toast("All language packs are already installed.", "info")
            return

        self._set_busy(True)

        # Update all missing rows to show waiting state
        for code in missing:
            rw = self._row_widgets.get(code)
            if rw:
                if rw.get("download_btn"):
                    rw["download_btn"].grid_remove()
                if rw.get("dl_progress_label"):
                    lbl = rw["dl_progress_label"]
                    lbl.configure(text="Waiting...")
                    lbl.grid(row=0, column=3, padx=(6, 8), pady=6, sticky="e")

        self._log(f"--- Downloading {len(missing)} missing language pack(s) ---")

        def _bg():
            downloader = self.app.updater.create_language_downloader(game_dir)
            try:
                return downloader.download_all_missing(
                    self._lang_downloads,
                    self._installed_langs,
                    log=self._enqueue_log,
                )
            finally:
                downloader.close()

        def _done(results):
            self._set_busy(False)
            succeeded = sum(1 for v in results.values() if v)
            failed = sum(1 for v in results.values() if not v)
            if failed == 0 and succeeded > 0:
                self.app.show_toast(
                    f"All {succeeded} language pack(s) installed!", "success",
                )
            elif succeeded > 0:
                self.app.show_toast(
                    f"{succeeded} installed, {failed} failed.", "warning",
                )
            else:
                self.app.show_toast("All downloads failed.", "error")
            self._refresh_status()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Download failed: {e}")
            self.app.show_toast(f"Download failed: {e}", "error")
            self._refresh_status()

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Steam Download ────────────────────────────────────────────

    def _on_steam_download(self):
        """Download all language packs from Steam using DepotDownloader."""
        if self._busy:
            return

        game_dir = self.app.settings.game_path
        if not game_dir:
            self.app.show_toast(
                "Set game directory in Settings first.", "warning",
            )
            return

        from ...language.steam import SteamLanguageDownloader
        from ...config import get_app_dir

        app_dir = get_app_dir()
        from pathlib import Path as _Path
        downloader = SteamLanguageDownloader(
            app_dir=app_dir,
            game_dir=_Path(game_dir),
        )

        # Check if DepotDownloader is installed
        if not downloader.is_tool_installed():
            install = tk.messagebox.askyesno(
                "DepotDownloader Required",
                "DepotDownloader is needed to download language packs from Steam.\n\n"
                "It will be downloaded from GitHub (~32 MB).\n\n"
                "Download and install DepotDownloader?",
                parent=self,
            )
            if not install:
                return

            # Install DepotDownloader in background
            self._set_busy(True)
            self._log("--- Installing DepotDownloader ---")

            def _install_bg():
                return downloader.install_tool(log=self._enqueue_log)

            def _install_done(success):
                if success:
                    self._log("DepotDownloader installed. Proceeding with download...")
                    self._set_busy(False)
                    # Now proceed with the actual download
                    self._start_steam_download(downloader)
                else:
                    self._set_busy(False)
                    self.app.show_toast(
                        "Failed to install DepotDownloader.", "error",
                    )

            def _install_err(e):
                self._set_busy(False)
                self._enqueue_log(f"Install failed: {e}")
                self.app.show_toast(f"Install failed: {e}", "error")

            self.app.run_async(
                _install_bg, on_done=_install_done, on_error=_install_err,
            )
            return

        # Tool already installed, proceed
        self._start_steam_download(downloader)

    def _start_steam_download(self, downloader):
        """Prompt for Steam username and start the download."""
        # Ask for Steam username (pre-filled from settings)
        saved_username = self.app.settings.steam_username or ""
        username = tk.simpledialog.askstring(
            "Steam Username",
            "Enter your Steam username.\n"
            "You must own The Sims 4 on this account.\n\n"
            "Steam Username:",
            initialvalue=saved_username,
            parent=self,
        )
        if not username or not username.strip():
            return
        username = username.strip()

        # Save username for next time
        self.app.settings.steam_username = username
        self.app.settings.save()

        self._set_busy(True)
        self._log(f"--- Downloading language packs from Steam ---")

        # Thread-safe auth dialog helpers using threading.Event
        _auth_result = {"value": None}
        _auth_event = threading.Event()

        def _ask_password():
            _auth_event.clear()
            _auth_result["value"] = None

            def _show_dialog():
                pw = tk.simpledialog.askstring(
                    "Steam Password",
                    f"Enter the password for Steam account '{username}':",
                    show="*",
                    parent=self,
                )
                _auth_result["value"] = pw
                _auth_event.set()

            self.app._enqueue_gui(_show_dialog)
            _auth_event.wait(timeout=300)  # 5 minute timeout
            return _auth_result["value"]

        def _ask_auth_code():
            _auth_event.clear()
            _auth_result["value"] = None

            def _show_dialog():
                code = tk.simpledialog.askstring(
                    "Steam Guard Code",
                    "Enter your Steam Guard / 2FA code:",
                    parent=self,
                )
                _auth_result["value"] = code
                _auth_event.set()

            self.app._enqueue_gui(_show_dialog)
            _auth_event.wait(timeout=300)
            return _auth_result["value"]

        # Only download languages that are missing
        missing_codes = [
            code for code, installed in self._installed_langs.items()
            if not installed
        ]

        def _bg():
            return downloader.download_languages(
                username=username,
                log=self._enqueue_log,
                ask_password=_ask_password,
                ask_auth_code=_ask_auth_code,
                locale_codes=missing_codes or None,
            )

        def _done(result):
            self._set_busy(False)
            if result.success:
                count = len(result.installed_locales)
                self._log(
                    f"Steam download complete! "
                    f"{count} language pack(s) installed."
                )
                self.app.show_toast(
                    f"{count} language pack(s) downloaded from Steam!",
                    "success",
                )
            else:
                self._log(f"Steam download failed: {result.error}")
                self.app.show_toast(
                    f"Steam download failed: {result.error}", "error",
                )
            self._refresh_status()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Steam download failed: {e}")
            self.app.show_toast(f"Steam download failed: {e}", "error")
            self._refresh_status()

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Busy state ───────────────────────────────────────────────

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._apply_btn.configure(state=state)
        self._refresh_btn.configure(state=state)
        self._dl_all_btn.configure(state=state)
        self._steam_dl_btn.configure(state=state)

        # Disable/enable per-row download buttons
        for rw in self._row_widgets.values():
            btn = rw.get("download_btn")
            if btn:
                btn.configure(state=state)
