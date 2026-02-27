"""
Event Rewards tab — unlock Sims 4 live-event rewards via accountDataDB.package patching.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import InfoCard, RichTextbox, StatusBadge, Tooltip, ask_yes_no

if TYPE_CHECKING:
    from ..app import App


class EventsFrame(ctk.CTkFrame):
    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._busy = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Top section (fixed) ──────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="new", padx=0, pady=0)
        top.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(
            top,
            text="Event Rewards",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, padx=30, pady=(20, 4), sticky="w")

        ctk.CTkLabel(
            top,
            text="Unlock live-event rewards without completing quests",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=1, column=0, padx=30, pady=(0, 12), sticky="w")

        # ── Status card ──────────────────────────────────────────
        self._card = InfoCard(top, fg_color=theme.COLORS["bg_card"])
        self._card.grid(row=2, column=0, padx=30, pady=(0, 10), sticky="ew")
        self._card.grid_columnconfigure(1, weight=1)

        # Row 0: UserSetting.ini path
        ctk.CTkLabel(
            self._card,
            text="UserSetting.ini",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(
            row=0,
            column=0,
            padx=(theme.CARD_PAD_X, 8),
            pady=(theme.CARD_PAD_Y, 4),
            sticky="w",
        )

        self._ini_badge = StatusBadge(self._card, text="Not scanned", style="muted")
        self._ini_badge.grid(row=0, column=1, padx=0, pady=(theme.CARD_PAD_Y, 4), sticky="w")

        # Row 1: Account IDs
        ctk.CTkLabel(
            self._card,
            text="Accounts",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=1, column=0, padx=(theme.CARD_PAD_X, 8), pady=4, sticky="w")

        self._accounts_badge = StatusBadge(self._card, text="...", style="muted")
        self._accounts_badge.grid(row=1, column=1, padx=0, pady=4, sticky="w")

        # Row 2: Current accountDataDB status
        ctk.CTkLabel(
            self._card,
            text="Package Status",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(
            row=2,
            column=0,
            padx=(theme.CARD_PAD_X, 8),
            pady=(4, theme.CARD_PAD_Y),
            sticky="w",
        )

        self._pkg_badge = StatusBadge(self._card, text="...", style="muted")
        self._pkg_badge.grid(row=2, column=1, padx=0, pady=(4, theme.CARD_PAD_Y), sticky="w")

        # ── Action buttons row ───────────────────────────────────
        btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=30, pady=(0, 10), sticky="ew")

        self._unlock_btn = ctk.CTkButton(
            btn_frame,
            text="Unlock Event Rewards",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_unlock,
        )
        self._unlock_btn.pack(side="left", padx=(0, 5))
        Tooltip(
            self._unlock_btn,
            message=(
                "Generate accountDataDB.package with all event rewards unlocked.\n"
                "For live events: claim rewards online.\n"
                "For ended events: works offline only."
            ),
        )

        self._refresh_btn = ctk.CTkButton(
            btn_frame,
            text="Refresh",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_refresh,
        )
        self._refresh_btn.pack(side="left", padx=5)
        Tooltip(self._refresh_btn, message="Re-scan for UserSetting.ini and account IDs")

        self._restore_btn = ctk.CTkButton(
            btn_frame,
            text="Restore Backup",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_restore,
        )
        self._restore_btn.pack(side="left", padx=5)
        Tooltip(
            self._restore_btn,
            message="Restore the original accountDataDB.package from backup",
        )

        # ── Bottom: events list + log ────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_rowconfigure(0, weight=3)
        bottom.grid_rowconfigure(1, weight=2)

        # Events list (scrollable)
        self._events_scroll = ctk.CTkScrollableFrame(
            bottom,
            fg_color=theme.COLORS["bg_deeper"],
            corner_radius=theme.CORNER_RADIUS_SMALL,
            border_width=1,
            border_color=theme.COLORS["border"],
            label_text="Supported Events (newest first)",
            label_font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            label_fg_color=theme.COLORS["bg_card"],
        )
        self._events_scroll.grid(row=0, column=0, sticky="nsew", padx=30, pady=(0, 8))
        self._events_scroll.grid_columnconfigure(0, weight=1)

        self._build_events_list()

        # ── Log viewer ───────────────────────────────────────────
        log_container = ctk.CTkFrame(bottom, fg_color="transparent")
        log_container.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 15))
        log_container.grid_columnconfigure(0, weight=1)
        log_container.grid_rowconfigure(1, weight=1)

        header_row = ctk.CTkFrame(log_container, fg_color="transparent")
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
            height=24,
            width=60,
            corner_radius=4,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._clear_log,
        ).grid(row=0, column=1, sticky="e")

        self._log_box = RichTextbox(log_container)
        self._log_box.grid(row=1, column=0, sticky="nsew")

        # State
        self._ini_path: Path | None = None
        self._account_ids: list[int] = []
        self._sims4_dir: Path | None = None

    # ── Events list ──────────────────────────────────────────────

    def _build_events_list(self):
        from ...events.unlocker import KNOWN_EVENTS

        for i, event in enumerate(KNOWN_EVENTS):
            row = ctk.CTkFrame(
                self._events_scroll,
                fg_color=theme.COLORS["bg_card"],
                corner_radius=6,
            )
            row.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
            row.grid_columnconfigure(1, weight=1)

            # Event name
            ctk.CTkLabel(
                row,
                text=event.name,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=theme.COLORS["text"],
            ).grid(row=0, column=0, padx=(12, 8), pady=(8, 2), sticky="w")

            # Status badge
            if event.status == "live":
                badge_text, badge_style = "Live!", "success"
            elif event.status == "base_game":
                badge_text, badge_style = "Base Game", "info"
            else:
                badge_text, badge_style = "Ended", "muted"

            badge = StatusBadge(row, text=badge_text, style=badge_style)
            badge.grid(row=0, column=2, padx=(4, 12), pady=(8, 2), sticky="e")

            # Date + note
            detail = event.date
            if event.note:
                detail += f" \u2014 {event.note}"
            ctk.CTkLabel(
                row,
                text=detail,
                font=ctk.CTkFont(*theme.FONT_SMALL),
                text_color=theme.COLORS["text_muted"],
                wraplength=500,
                anchor="w",
            ).grid(row=1, column=0, columnspan=3, padx=(12, 12), pady=(0, 8), sticky="w")

    # ── Logging ──────────────────────────────────────────────────

    def _log(self, message: str, style: str = ""):
        self._log_box.add_line(message, style=style)

    def _enqueue_log(self, msg: str, style: str = ""):
        self.app._enqueue_gui(self._log, msg, style)

    def _clear_log(self):
        self._log_box.clear()

    # ── Status Refresh ───────────────────────────────────────────

    def on_show(self):
        if not self._busy:
            self._refresh()

    def _on_refresh(self):
        self._refresh()

    def _refresh(self):
        from ...events.unlocker import find_sims4_user_dir, find_user_setting_ini, parse_account_ids

        def _bg():
            sims4_dir = find_sims4_user_dir()
            ini_path = find_user_setting_ini(sims4_dir)
            account_ids = parse_account_ids(ini_path) if ini_path else []
            pkg_exists = (sims4_dir / "accountDataDB.package").is_file() if sims4_dir else False
            bak_exists = (sims4_dir / "accountDataDB.package.bak").is_file() if sims4_dir else False
            return sims4_dir, ini_path, account_ids, pkg_exists, bak_exists

        def _done(result):
            sims4_dir, ini_path, account_ids, pkg_exists, bak_exists = result
            self._sims4_dir = sims4_dir
            self._ini_path = ini_path
            self._account_ids = account_ids

            # Update badges
            if ini_path:
                self._ini_badge.set_status(str(ini_path), "success")
            else:
                self._ini_badge.set_status("Not found \u2014 run the game first", "warning")

            if account_ids:
                ids_str = ", ".join(str(a) for a in account_ids)
                self._accounts_badge.set_status(
                    f"{len(account_ids)} account(s): {ids_str}", "success"
                )
            else:
                self._accounts_badge.set_status("No accounts found", "warning")

            if pkg_exists:
                suffix = " (backup available)" if bak_exists else ""
                self._pkg_badge.set_status(f"Installed{suffix}", "success")
            else:
                self._pkg_badge.set_status("Not installed", "muted")

            # Enable/disable buttons
            has_data = bool(ini_path and account_ids)
            self._unlock_btn.configure(state="normal" if has_data else "disabled")
            self._restore_btn.configure(state="normal" if bak_exists else "disabled")

        def _err(e):
            self._ini_badge.set_status("Error scanning", "error")
            self._log(f"Error: {e}", style="error")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Unlock action ────────────────────────────────────────────

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._unlock_btn.configure(state=state)
        self._refresh_btn.configure(state=state)
        self._restore_btn.configure(state=state)

    def _on_unlock(self):
        if self._busy:
            return
        if not self._ini_path or not self._account_ids:
            self.app.show_toast("No accounts found. Run the game first.", "warning")
            return

        confirmed = ask_yes_no(
            self.app,
            title="Unlock Event Rewards",
            message=(
                f"This will generate an accountDataDB.package for "
                f"{len(self._account_ids)} account(s).\n\n"
                "For live events: claim rewards while online.\n"
                "For ended events: rewards work offline only.\n\n"
                "An existing file will be backed up automatically.\n\n"
                "Continue?"
            ),
        )
        if not confirmed:
            return

        self._set_busy(True)
        self._log("--- Unlocking Event Rewards ---", style="header")

        ini_path = self._ini_path

        def _bg():
            from ...events.unlocker import unlock_events

            return unlock_events(
                ini_path=ini_path,
                progress=lambda msg: self._enqueue_log(msg),
            )

        def _done(result):
            self._set_busy(False)
            self._log(f"Output: {result.output_path}", style="success")
            if result.backup_path:
                self._log(f"Backup: {result.backup_path}", style="info")
            self._log(
                f"Unlocked for {len(result.account_ids)} account(s).",
                style="success",
            )
            self.app.show_toast(
                f"Event rewards unlocked for {len(result.account_ids)} account(s)!",
                "success",
            )
            self.app.telemetry.track_event(
                "event_rewards_unlocked",
                {"account_count": len(result.account_ids)},
            )
            self._refresh()

        def _err(e):
            self._set_busy(False)
            self._log(f"Error: {e}", style="error")
            self.app.show_toast(f"Failed: {e}", "error")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Restore backup ───────────────────────────────────────────

    def _on_restore(self):
        if self._busy or not self._sims4_dir:
            return

        bak_path = self._sims4_dir / "accountDataDB.package.bak"
        pkg_path = self._sims4_dir / "accountDataDB.package"

        if not bak_path.is_file():
            self.app.show_toast("No backup found.", "warning")
            return

        confirmed = ask_yes_no(
            self.app,
            title="Restore Backup",
            message=(
                "Restore the original accountDataDB.package from backup?\n\n"
                "This will overwrite the current event rewards file."
            ),
        )
        if not confirmed:
            return

        self._set_busy(True)
        self._log("--- Restoring Backup ---", style="header")

        def _bg():
            import shutil

            shutil.copy2(bak_path, pkg_path)

        def _done(_):
            self._set_busy(False)
            self._log("Backup restored successfully.", style="success")
            self.app.show_toast("Backup restored.", "success")
            self._refresh()

        def _err(e):
            self._set_busy(False)
            self._log(f"Restore failed: {e}", style="error")
            self.app.show_toast(f"Restore failed: {e}", "error")

        self.app.run_async(_bg, on_done=_done, on_error=_err)
