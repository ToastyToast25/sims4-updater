"""Language upload frame — scan, list, and upload language packs."""

from __future__ import annotations

import time
from pathlib import Path
from threading import Event, Thread
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import StatusBadge, LogPanel

if TYPE_CHECKING:
    from ..app import CDNManagerApp


class LanguageFrame(ctk.CTkFrame):
    def __init__(self, parent, app: CDNManagerApp):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._busy = False
        self._cancel_event = Event()
        self._lang_rows: dict[str, dict] = {}
        self._cdn_statuses: dict[str, str] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Language Upload",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        ).grid(row=0, column=0, padx=theme.SECTION_PAD, pady=(20, 15), sticky="w")

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=1, column=0, padx=theme.SECTION_PAD, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        path_frame = ctk.CTkFrame(header, fg_color="transparent")
        path_frame.grid(row=0, column=0, sticky="ew")
        path_frame.grid_columnconfigure(0, weight=1)

        self._game_dir_entry = ctk.CTkEntry(
            path_frame, font=ctk.CTkFont(size=12), height=36,
            placeholder_text="Game directory...",
        )
        self._game_dir_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        if self.app.config_data.game_dir:
            self._game_dir_entry.insert(0, self.app.config_data.game_dir)

        ctk.CTkButton(
            path_frame, text="Browse", height=36, width=80,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            command=self._browse,
        ).grid(row=0, column=1)

        # Buttons
        btn_row = ctk.CTkFrame(header, fg_color="transparent")
        btn_row.grid(row=1, column=0, pady=(8, 0), sticky="ew")

        self._scan_btn = ctk.CTkButton(
            btn_row, text="Scan", height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._scan,
        )
        self._scan_btn.pack(side="left", padx=(0, 4))

        self._upload_btn = ctk.CTkButton(
            btn_row, text="Upload Selected", height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["success"],
            hover_color="#3ae882",
            text_color="#1a1a2e",
            command=self._upload_selected,
            state="disabled",
        )
        self._upload_btn.pack(side="left", padx=(0, 4))

        self._cancel_btn = ctk.CTkButton(
            btn_row, text="Cancel", height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            command=self._cancel_upload,
        )

        ctk.CTkButton(
            btn_row, text="All", height=28, width=50,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            font=ctk.CTkFont(size=11),
            command=self._select_all,
        ).pack(side="left", padx=(12, 2))

        ctk.CTkButton(
            btn_row, text="Missing", height=28, width=65,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            font=ctk.CTkFont(size=11),
            command=self._select_missing,
        ).pack(side="left", padx=(0, 2))

        ctk.CTkButton(
            btn_row, text="None", height=28, width=50,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            font=ctk.CTkFont(size=11),
            command=self._select_none,
        ).pack(side="left")

        self._force_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            btn_row, text="Force", variable=self._force_var,
            font=ctk.CTkFont(size=11), height=28, width=60,
            checkbox_width=16, checkbox_height=16,
        ).pack(side="left", padx=(12, 0))

        # Progress
        self._progress_frame = ctk.CTkFrame(self, fg_color="transparent", height=40)
        self._progress_bar = ctk.CTkProgressBar(
            self._progress_frame, height=16,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            progress_color=theme.COLORS["accent"],
        )
        self._progress_bar.pack(fill="x", pady=(0, 2))
        self._progress_bar.set(0)
        self._progress_label = ctk.CTkLabel(
            self._progress_frame, text="",
            font=ctk.CTkFont(size=11), text_color=theme.COLORS["text_muted"],
        )
        self._progress_label.pack(anchor="w")

        # Language list
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=theme.COLORS["bg_dark"],
            corner_radius=theme.CORNER_RADIUS,
            border_width=1, border_color=theme.COLORS["border"],
        )
        self._scroll.grid(row=2, column=0, padx=theme.SECTION_PAD, pady=(10, 4), sticky="nsew")
        for col, w in [(0, 30), (1, 60), (2, 0), (3, 60), (4, 80), (5, 90)]:
            self._scroll.grid_columnconfigure(col, weight=1 if w == 0 else 0, minsize=w)

        ctk.CTkLabel(
            self._scroll, text="Click 'Scan' to detect installed languages",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=0, column=0, columnspan=6, pady=40)

        # Log
        self._log = LogPanel(self)
        self._log.grid(row=3, column=0, padx=theme.SECTION_PAD, pady=(4, 15), sticky="nsew")

    def on_show(self):
        pass

    def _browse(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Select Sims 4 Game Directory")
        if path:
            self._game_dir_entry.delete(0, "end")
            self._game_dir_entry.insert(0, path)

    # -- Scan ----------------------------------------------------------------

    def _scan(self):
        game_dir = self._game_dir_entry.get().strip()
        if not game_dir:
            self.app.show_toast("Enter a game directory first", "warning")
            return
        self._log.log("Scanning for installed languages...")
        self._scan_btn.configure(state="disabled")
        self.app.run_async(
            self._bg_scan, game_dir,
            on_done=self._on_scan_done,
            on_error=self._on_scan_error,
        )

    def _bg_scan(self, game_dir: str):
        from ..backend.lang_ops import scan_installed_languages, LANGUAGES
        from ..backend.dlc_ops import fmt_size
        from ..backend.connection import ConnectionManager

        game_path = Path(game_dir)
        installed = scan_installed_languages(game_path)

        lang_info = []
        for locale_code in sorted(installed):
            paths = installed[locale_code]
            total_size = sum(p.stat().st_size for p in paths)
            lang_info.append({
                "locale": locale_code,
                "name": LANGUAGES.get(locale_code, locale_code),
                "file_count": len(paths),
                "size": total_size,
                "size_str": fmt_size(total_size),
            })

        # Check CDN
        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        cdn_keys = conn.kv_list()
        cdn_langs = {
            k.replace("language/", "").replace(".zip", "")
            for k in cdn_keys if k.startswith("language/")
        }

        statuses = {}
        for info in lang_info:
            statuses[info["locale"]] = "uploaded" if info["locale"] in cdn_langs else "missing"

        return lang_info, statuses

    def _on_scan_done(self, result):
        lang_info, statuses = result
        self._cdn_statuses = statuses
        self._scan_btn.configure(state="normal")

        for widget in self._scroll.winfo_children():
            widget.destroy()
        self._lang_rows.clear()

        if not lang_info:
            ctk.CTkLabel(
                self._scroll, text="No languages found",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=0, columnspan=6, pady=40)
            self._log.log("No languages found", "warning")
            return

        for col, text in enumerate(["", "Code", "Language", "Files", "Size", "Status"]):
            ctk.CTkLabel(
                self._scroll, text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=col, padx=4, pady=(4, 6), sticky="w")

        for i, info in enumerate(lang_info):
            row = i + 1
            locale = info["locale"]
            status = statuses.get(locale, "unknown")

            var = ctk.BooleanVar(value=(status == "missing"))
            ctk.CTkCheckBox(
                self._scroll, text="", variable=var,
                width=20, height=20, checkbox_width=16, checkbox_height=16,
            ).grid(row=row, column=0, padx=4, pady=2)

            ctk.CTkLabel(
                self._scroll, text=locale,
                font=ctk.CTkFont("Consolas", 11),
            ).grid(row=row, column=1, padx=4, pady=2, sticky="w")

            ctk.CTkLabel(
                self._scroll, text=info["name"],
                font=ctk.CTkFont(size=11),
            ).grid(row=row, column=2, padx=4, pady=2, sticky="w")

            ctk.CTkLabel(
                self._scroll, text=str(info["file_count"]),
                font=ctk.CTkFont(size=11), text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=3, padx=4, pady=2, sticky="e")

            ctk.CTkLabel(
                self._scroll, text=info["size_str"],
                font=ctk.CTkFont(size=11), text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=4, padx=4, pady=2, sticky="e")

            badge = StatusBadge(self._scroll)
            if status == "uploaded":
                badge.set_status("Uploaded", "success")
            else:
                badge.set_status("Missing", "warning")
            badge.grid(row=row, column=5, padx=4, pady=2, sticky="e")

            self._lang_rows[locale] = {"var": var, "badge": badge}

        uploaded = sum(1 for s in statuses.values() if s == "uploaded")
        missing = sum(1 for s in statuses.values() if s == "missing")
        self._log.log(
            f"Found {len(lang_info)} languages: {uploaded} uploaded, {missing} missing",
            "success",
        )
        self._upload_btn.configure(state="normal")

    def _on_scan_error(self, error):
        self._scan_btn.configure(state="normal")
        self._log.log(f"Scan failed: {error}", "error")

    # -- Selection -----------------------------------------------------------

    def _select_all(self):
        for row in self._lang_rows.values():
            row["var"].set(True)

    def _select_missing(self):
        for locale, row in self._lang_rows.items():
            row["var"].set(self._cdn_statuses.get(locale) == "missing")

    def _select_none(self):
        for row in self._lang_rows.values():
            row["var"].set(False)

    # -- Upload --------------------------------------------------------------

    def _upload_selected(self):
        selected = [loc for loc, r in self._lang_rows.items() if r["var"].get()]
        if not selected:
            self.app.show_toast("No languages selected", "warning")
            return
        game_dir = self._game_dir_entry.get().strip()
        if not game_dir:
            self.app.show_toast("Enter a game directory first", "warning")
            return

        self._busy = True
        self._cancel_event.clear()
        self._scan_btn.configure(state="disabled")
        self._upload_btn.configure(state="disabled")
        self._cancel_btn.pack(side="left", padx=(4, 0))
        self.app.begin_operation(f"Uploading {len(selected)} languages")

        self._progress_frame.grid(
            row=2, column=0, padx=theme.SECTION_PAD, pady=(10, 0), sticky="ew",
        )
        self._scroll.grid(
            row=2, column=0, padx=theme.SECTION_PAD, pady=(50, 4), sticky="nsew",
        )
        self._progress_bar.set(0)
        self._progress_label.configure(text=f"0/{len(selected)} languages")
        self._log.log(f"Starting upload of {len(selected)} languages...")

        force = self._force_var.get()

        Thread(
            target=self._bg_upload,
            args=(game_dir, selected, force),
            daemon=True,
        ).start()

    def _bg_upload(self, game_dir: str, locales: list[str], force: bool):
        from ..backend.lang_ops import process_language
        from ..backend.dlc_ops import fmt_size
        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        game_path = Path(game_dir)
        output_dir = Path(__file__).resolve().parent.parent.parent / "lang_packed_temp"

        total = len(locales)
        completed = 0
        uploaded = 0
        uploaded_bytes = 0
        failed = []
        uploaded_entries: dict[str, dict] = {}  # locale -> manifest entry
        start_time = time.time()

        def log(msg, level="info"):
            self.app._enqueue_gui(self._log.log, msg, level)

        for locale in locales:
            if self._cancel_event.is_set():
                break

            entry = process_language(
                game_path, locale, conn, output_dir,
                force=force,
                cancel_event=self._cancel_event,
                log_cb=log,
            )
            completed += 1

            if entry:
                if entry.get("size", 0) > 0:
                    uploaded += 1
                    uploaded_bytes += entry["size"]
                    uploaded_entries[locale] = entry
                self.app._enqueue_gui(
                    self._update_badge, locale, "uploaded",
                )
            elif not self._cancel_event.is_set():
                failed.append(locale)

            progress = completed / total
            elapsed = time.time() - start_time
            self.app._enqueue_gui(
                self._update_progress, progress, completed, total, elapsed,
            )

        # Auto-update manifest with new language entries
        if uploaded_entries and not self._cancel_event.is_set():
            from ..backend.manifest_ops import merge_language_entries_and_publish
            merge_language_entries_and_publish(conn, uploaded_entries, log_cb=log)

        total_time = time.time() - start_time

        def finish():
            self._busy = False
            self._scan_btn.configure(state="normal")
            self._upload_btn.configure(state="normal")
            self._cancel_btn.pack_forget()
            self._progress_frame.grid_forget()
            self._scroll.grid(
                row=2, column=0,
                padx=theme.SECTION_PAD, pady=(10, 4), sticky="nsew",
            )
            self.app.end_operation()
            msg = f"Upload complete: {uploaded} uploaded"
            if failed:
                msg += f", {len(failed)} failed"
            msg += f" in {total_time:.0f}s"
            if uploaded_bytes > 0:
                msg += f" ({fmt_size(uploaded_bytes)})"
            self._log.log(msg, "success" if not failed else "warning")
            self.app.show_toast(msg, "success" if not failed else "warning")

        self.app._enqueue_gui(finish)

    def _update_badge(self, locale: str, status: str):
        row = self._lang_rows.get(locale)
        if row:
            if status == "uploaded":
                row["badge"].set_status("Uploaded", "success")
            row["var"].set(False)

    def _update_progress(self, progress: float, completed: int, total: int, elapsed: float):
        self._progress_bar.set(progress)
        if elapsed > 0 and completed > 0:
            remaining = elapsed / completed * (total - completed)
            self._progress_label.configure(
                text=f"{completed}/{total} languages  |  {elapsed:.0f}s  |  ~{remaining:.0f}s remaining",
            )
        else:
            self._progress_label.configure(text=f"{completed}/{total} languages")

    def _cancel_upload(self):
        self._cancel_event.set()
        self._log.log("Cancellation requested...", "warning")
        self._cancel_btn.configure(state="disabled")
