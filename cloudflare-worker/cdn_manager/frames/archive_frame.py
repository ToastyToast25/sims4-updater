"""Archive Manager frame — create, verify, delete, promote version archives."""

from __future__ import annotations

import time
from threading import Thread
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import StatusBadge, LogPanel

if TYPE_CHECKING:
    from ..app import CDNManagerApp


class ArchiveFrame(ctk.CTkFrame):
    def __init__(self, parent, app: CDNManagerApp):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._busy = False
        self._archive_rows: dict[str, dict] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Archive Manager",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        ).grid(row=0, column=0, padx=theme.SECTION_PAD, pady=(20, 15), sticky="w")

        # Action buttons
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=1, column=0, padx=theme.SECTION_PAD, sticky="ew")

        self._refresh_btn = ctk.CTkButton(
            header, text="Refresh",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._refresh,
        )
        self._refresh_btn.pack(side="left", padx=(0, 6))

        self._create_btn = ctk.CTkButton(
            header, text="Create Archive",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["success"],
            hover_color="#3ae882",
            text_color="#1a1a2e",
            command=self._create_archive,
        )
        self._create_btn.pack(side="left", padx=(0, 6))

        self._verify_btn = ctk.CTkButton(
            header, text="Verify Selected",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._verify,
        )
        self._verify_btn.pack(side="left", padx=(0, 6))

        self._delete_btn = ctk.CTkButton(
            header, text="Delete Selected",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            command=self._delete,
        )
        self._delete_btn.pack(side="left", padx=(0, 6))

        self._promote_btn = ctk.CTkButton(
            header, text="Promote (Rollback)",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["warning"],
            hover_color="#ffb347",
            text_color="#1a1a2e",
            command=self._promote,
        )
        self._promote_btn.pack(side="left")

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

        # Archive list
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=theme.COLORS["bg_dark"],
            corner_radius=theme.CORNER_RADIUS,
            border_width=1, border_color=theme.COLORS["border"],
        )
        self._scroll.grid(row=2, column=0, padx=theme.SECTION_PAD, pady=(10, 4), sticky="nsew")
        for col, w in [(0, 30), (1, 120), (2, 90), (3, 60), (4, 60), (5, 90)]:
            self._scroll.grid_columnconfigure(col, weight=1 if w == 0 else 0, minsize=w)

        ctk.CTkLabel(
            self._scroll, text="Click 'Refresh' to load archived versions",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=0, column=0, columnspan=6, pady=40)

        # Log
        self._log = LogPanel(self)
        self._log.grid(row=3, column=0, padx=theme.SECTION_PAD, pady=(4, 15), sticky="nsew")

    def on_show(self):
        pass

    # -- Refresh ---------------------------------------------------------------

    def _refresh(self):
        self._log.log("Loading archived versions from manifest...")
        self._refresh_btn.configure(state="disabled")
        self.app.run_async(
            self._bg_refresh,
            on_done=self._on_refresh_done,
            on_error=self._on_refresh_error,
        )

    def _bg_refresh(self):
        from ..backend.archive_ops import list_archives
        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        return list_archives(conn)

    def _on_refresh_done(self, archives: dict):
        self._refresh_btn.configure(state="normal")

        for widget in self._scroll.winfo_children():
            widget.destroy()
        self._archive_rows.clear()

        if not archives:
            ctk.CTkLabel(
                self._scroll, text="No archived versions found",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=0, columnspan=6, pady=40)
            self._log.log("No archived versions in manifest", "warning")
            return

        # Header row
        for col, text in enumerate(["", "Version", "Date", "DLCs", "Langs", "Status"]):
            ctk.CTkLabel(
                self._scroll, text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=col, padx=4, pady=(4, 6), sticky="w")

        for i, (version, info) in enumerate(sorted(archives.items(), reverse=True)):
            row = i + 1

            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(
                self._scroll, text="", variable=var,
                width=20, height=20, checkbox_width=16, checkbox_height=16,
            ).grid(row=row, column=0, padx=4, pady=2)

            ctk.CTkLabel(
                self._scroll, text=version,
                font=ctk.CTkFont("Consolas", 11),
            ).grid(row=row, column=1, padx=4, pady=2, sticky="w")

            ctk.CTkLabel(
                self._scroll, text=info.get("date", "—"),
                font=ctk.CTkFont(size=11), text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=2, padx=4, pady=2, sticky="w")

            ctk.CTkLabel(
                self._scroll, text=str(info.get("dlc_count", 0)),
                font=ctk.CTkFont(size=11), text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=3, padx=4, pady=2, sticky="e")

            ctk.CTkLabel(
                self._scroll, text=str(info.get("language_count", 0)),
                font=ctk.CTkFont(size=11), text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=4, padx=4, pady=2, sticky="e")

            badge = StatusBadge(self._scroll)
            badge.set_status("Archived", "info")
            badge.grid(row=row, column=5, padx=4, pady=2, sticky="e")

            self._archive_rows[version] = {"var": var, "badge": badge, "info": info}

        self._log.log(f"Loaded {len(archives)} archived versions", "success")

    def _on_refresh_error(self, error):
        self._refresh_btn.configure(state="normal")
        self._log.log(f"Refresh failed: {error}", "error")

    # -- Create Archive --------------------------------------------------------

    def _create_archive(self):
        if self._busy:
            self.app.show_toast("Operation in progress", "warning")
            return

        dialog = _VersionInputDialog(self, "Create Archive", "Enter version string:")
        self.wait_window(dialog)
        version = dialog.result
        if not version:
            return

        # Confirm
        existing = [v for v in self._archive_rows if v == version]
        if existing:
            confirm = _ConfirmDialog(
                self, "Overwrite Archive",
                f"Archive {version} already exists. Overwrite?",
            )
            self.wait_window(confirm)
            if not confirm.result:
                return

        self._busy = True
        self._set_buttons_state("disabled")
        self._log.log(f"Creating archive for {version}...")

        Thread(
            target=self._bg_create, args=(version,), daemon=True,
        ).start()

    def _bg_create(self, version: str):
        from ..backend.archive_ops import create_archive
        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())

        def log(msg, level="info"):
            self.app._enqueue_gui(self._log.log, msg, level)

        try:
            ok = create_archive(conn, version, log_cb=log)
        except Exception as e:
            self.app._enqueue_gui(self._log.log, f"Create failed: {e}", "error")
            ok = False

        def finish():
            self._busy = False
            self._set_buttons_state("normal")
            if ok:
                self.app.show_toast(f"Archive {version} created", "success")
                self._refresh()
            else:
                self.app.show_toast("Archive creation failed", "error")

        self.app._enqueue_gui(finish)

    # -- Verify ----------------------------------------------------------------

    def _verify(self):
        selected = self._get_selected()
        if not selected:
            self.app.show_toast("No archives selected", "warning")
            return
        if self._busy:
            self.app.show_toast("Operation in progress", "warning")
            return

        self._busy = True
        self._set_buttons_state("disabled")
        self._show_progress()
        self._log.log(f"Verifying {len(selected)} archive(s)...")

        Thread(
            target=self._bg_verify, args=(selected,), daemon=True,
        ).start()

    def _bg_verify(self, versions: list[str]):
        from ..backend.archive_ops import verify_archive
        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        total_versions = len(versions)

        def log(msg, level="info"):
            self.app._enqueue_gui(self._log.log, msg, level)

        all_ok = True
        for vi, version in enumerate(versions):
            log(f"Verifying archive {version} ({vi + 1}/{total_versions})...")

            def progress_cb(done, total):
                overall = (vi + done / max(total, 1)) / total_versions
                self.app._enqueue_gui(
                    self._update_progress, overall,
                    f"Checking {version}: {done}/{total} URLs",
                )

            try:
                ok_count, broken_count, broken = verify_archive(
                    conn, version, log_cb=log, progress_cb=progress_cb,
                )
            except Exception as e:
                log(f"Verify failed for {version}: {e}", "error")
                self.app._enqueue_gui(
                    self._update_badge, version, "Error", "error",
                )
                all_ok = False
                continue

            if broken_count == 0:
                log(f"Archive {version}: all {ok_count} URLs OK", "success")
                self.app._enqueue_gui(
                    self._update_badge, version, "Verified", "success",
                )
            else:
                log(f"Archive {version}: {broken_count} broken URLs", "error")
                for label, url, status in broken:
                    log(f"  BROKEN [{status}] {label}: {url}", "error")
                self.app._enqueue_gui(
                    self._update_badge, version, f"{broken_count} broken", "error",
                )
                all_ok = False

        def finish():
            self._busy = False
            self._set_buttons_state("normal")
            self._hide_progress()
            if all_ok:
                self.app.show_toast("All archives verified OK", "success")
            else:
                self.app.show_toast("Some archives have broken URLs", "warning")

        self.app._enqueue_gui(finish)

    # -- Delete ----------------------------------------------------------------

    def _delete(self):
        selected = self._get_selected()
        if not selected:
            self.app.show_toast("No archives selected", "warning")
            return
        if self._busy:
            self.app.show_toast("Operation in progress", "warning")
            return

        confirm = _ConfirmDialog(
            self, "Delete Archives",
            f"Delete {len(selected)} archive(s)?\n\n"
            + "\n".join(f"  - {v}" for v in selected)
            + "\n\nThis removes files from seedbox, KV entries, and manifest.",
        )
        self.wait_window(confirm)
        if not confirm.result:
            return

        self._busy = True
        self._set_buttons_state("disabled")
        self._log.log(f"Deleting {len(selected)} archive(s)...")

        Thread(
            target=self._bg_delete, args=(selected,), daemon=True,
        ).start()

    def _bg_delete(self, versions: list[str]):
        from ..backend.archive_ops import delete_archive
        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        deleted = 0

        def log(msg, level="info"):
            self.app._enqueue_gui(self._log.log, msg, level)

        for version in versions:
            try:
                ok = delete_archive(conn, version, log_cb=log)
                if ok:
                    deleted += 1
            except Exception as e:
                log(f"Delete failed for {version}: {e}", "error")

        def finish():
            self._busy = False
            self._set_buttons_state("normal")
            msg = f"Deleted {deleted}/{len(versions)} archive(s)"
            self._log.log(msg, "success" if deleted == len(versions) else "warning")
            self.app.show_toast(msg, "success" if deleted > 0 else "error")
            if deleted > 0:
                self._refresh()

        self.app._enqueue_gui(finish)

    # -- Promote (Rollback) ----------------------------------------------------

    def _promote(self):
        selected = self._get_selected()
        if not selected:
            self.app.show_toast("Select one archive to promote", "warning")
            return
        if len(selected) > 1:
            self.app.show_toast("Select only one archive to promote", "warning")
            return
        if self._busy:
            self.app.show_toast("Operation in progress", "warning")
            return

        version = selected[0]
        confirm = _ConfirmDialog(
            self, "Promote Archive",
            f"Promote (rollback to) archive {version}?\n\n"
            "This will REPLACE the current CDN content with the archived version.\n"
            "All existing DLC and language files will be overwritten.",
        )
        self.wait_window(confirm)
        if not confirm.result:
            return

        self._busy = True
        self._set_buttons_state("disabled")
        self._log.log(f"Promoting archive {version}...")

        Thread(
            target=self._bg_promote, args=(version,), daemon=True,
        ).start()

    def _bg_promote(self, version: str):
        from ..backend.archive_ops import promote_archive
        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())

        def log(msg, level="info"):
            self.app._enqueue_gui(self._log.log, msg, level)

        try:
            ok = promote_archive(conn, version, log_cb=log)
        except Exception as e:
            self.app._enqueue_gui(self._log.log, f"Promote failed: {e}", "error")
            ok = False

        def finish():
            self._busy = False
            self._set_buttons_state("normal")
            if ok:
                self.app.show_toast(f"CDN rolled back to {version}", "success")
            else:
                self.app.show_toast("Promote failed", "error")

        self.app._enqueue_gui(finish)

    # -- Helpers ---------------------------------------------------------------

    def _get_selected(self) -> list[str]:
        return [v for v, r in self._archive_rows.items() if r["var"].get()]

    def _set_buttons_state(self, state: str):
        for btn in (
            self._refresh_btn, self._create_btn,
            self._verify_btn, self._delete_btn, self._promote_btn,
        ):
            btn.configure(state=state)

    def _update_badge(self, version: str, text: str, style: str):
        row = self._archive_rows.get(version)
        if row:
            row["badge"].set_status(text, style)

    def _show_progress(self):
        self._progress_frame.grid(
            row=2, column=0, padx=theme.SECTION_PAD, pady=(10, 0), sticky="ew",
        )
        self._scroll.grid(
            row=2, column=0, padx=theme.SECTION_PAD, pady=(50, 4), sticky="nsew",
        )
        self._progress_bar.set(0)
        self._progress_label.configure(text="")

    def _hide_progress(self):
        self._progress_frame.grid_forget()
        self._scroll.grid(
            row=2, column=0, padx=theme.SECTION_PAD, pady=(10, 4), sticky="nsew",
        )

    def _update_progress(self, progress: float, text: str):
        self._progress_bar.set(progress)
        self._progress_label.configure(text=text)


# -- Dialogs ------------------------------------------------------------------

class _VersionInputDialog(ctk.CTkToplevel):
    """Simple modal dialog to get a version string."""

    def __init__(self, parent, title: str, prompt: str):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x160")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: str = ""

        self.configure(fg_color=theme.COLORS["bg_card"])

        ctk.CTkLabel(
            self, text=prompt,
            font=ctk.CTkFont(*theme.FONT_BODY),
        ).pack(padx=20, pady=(20, 8))

        self._entry = ctk.CTkEntry(
            self, height=36, font=ctk.CTkFont("Consolas", 12),
            placeholder_text="e.g. 1.121.372.1020",
        )
        self._entry.pack(padx=20, fill="x")
        self._entry.focus_set()
        self._entry.bind("<Return>", lambda _: self._ok())

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(padx=20, pady=(12, 15), fill="x")

        ctk.CTkButton(
            btn_frame, text="OK", width=80, height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._ok,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_frame, text="Cancel", width=80, height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self.destroy,
        ).pack(side="right")

    def _ok(self):
        text = self._entry.get().strip()
        if text:
            self.result = text
            self.destroy()


class _ConfirmDialog(ctk.CTkToplevel):
    """Simple modal yes/no confirmation dialog."""

    def __init__(self, parent, title: str, message: str):
        super().__init__(parent)
        self.title(title)
        self.geometry("450x200")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: bool = False

        self.configure(fg_color=theme.COLORS["bg_card"])

        ctk.CTkLabel(
            self, text=message,
            font=ctk.CTkFont(*theme.FONT_BODY),
            wraplength=400, justify="left",
        ).pack(padx=20, pady=(20, 15), anchor="w")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(padx=20, pady=(0, 15), fill="x")

        ctk.CTkButton(
            btn_frame, text="Yes", width=80, height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._yes,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_frame, text="No", width=80, height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self.destroy,
        ).pack(side="right")

    def _yes(self):
        self.result = True
        self.destroy()
