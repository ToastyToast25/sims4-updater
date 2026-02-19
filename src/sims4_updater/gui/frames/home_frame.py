"""
Home frame — version display, update button, quick status.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme

if TYPE_CHECKING:
    from ..app import App


class HomeFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)

        # ── Title ──
        title = ctk.CTkLabel(
            self,
            text="The Sims 4 Updater",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        )
        title.grid(row=0, column=0, padx=30, pady=(30, 5), sticky="w")

        # ── Info card ──
        self._card = ctk.CTkFrame(self, corner_radius=10)
        self._card.grid(row=1, column=0, padx=30, pady=15, sticky="ew")
        self._card.grid_columnconfigure(1, weight=1)

        # Game directory
        ctk.CTkLabel(
            self._card,
            text="Game Directory:",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=0, column=0, padx=15, pady=(15, 2), sticky="w")

        self._game_dir_label = ctk.CTkLabel(
            self._card,
            text="Detecting...",
            font=ctk.CTkFont(*theme.FONT_BODY),
            anchor="w",
        )
        self._game_dir_label.grid(row=0, column=1, padx=15, pady=(15, 2), sticky="w")

        # Installed version
        ctk.CTkLabel(
            self._card,
            text="Installed Version:",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=1, column=0, padx=15, pady=2, sticky="w")

        self._version_label = ctk.CTkLabel(
            self._card,
            text="...",
            font=ctk.CTkFont(*theme.FONT_BODY),
            anchor="w",
        )
        self._version_label.grid(row=1, column=1, padx=15, pady=2, sticky="w")

        # Latest version
        ctk.CTkLabel(
            self._card,
            text="Latest Version:",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=2, column=0, padx=15, pady=2, sticky="w")

        self._latest_label = ctk.CTkLabel(
            self._card,
            text="...",
            font=ctk.CTkFont(*theme.FONT_BODY),
            anchor="w",
        )
        self._latest_label.grid(row=2, column=1, padx=15, pady=2, sticky="w")

        # DLC summary
        ctk.CTkLabel(
            self._card,
            text="DLCs:",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=3, column=0, padx=15, pady=(2, 15), sticky="w")

        self._dlc_label = ctk.CTkLabel(
            self._card,
            text="...",
            font=ctk.CTkFont(*theme.FONT_BODY),
            anchor="w",
        )
        self._dlc_label.grid(row=3, column=1, padx=15, pady=(2, 15), sticky="w")

        # ── Status message ──
        self._status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._status_label.grid(row=2, column=0, padx=30, pady=(0, 5), sticky="w")

        # ── Buttons ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=30, pady=10, sticky="ew")

        self._update_btn = ctk.CTkButton(
            btn_frame,
            text="Check for Updates",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            corner_radius=8,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_check_updates,
        )
        self._update_btn.pack(side="left", padx=(0, 10))

        self._refresh_btn = ctk.CTkButton(
            btn_frame,
            text="Refresh",
            font=ctk.CTkFont(size=13),
            height=42,
            corner_radius=8,
            fg_color=theme.COLORS["bg_card"],
            command=self.refresh,
        )
        self._refresh_btn.pack(side="left")

    def on_show(self):
        pass

    def refresh(self):
        """Refresh game info in background."""
        self._status_label.configure(text="Scanning...")
        self._update_btn.configure(state="disabled")
        self.app.run_async(self._detect_info, on_done=self._on_info_detected)

    def _detect_info(self):
        """Background: detect game dir and version."""
        updater = self.app.updater

        game_dir = updater.find_game_dir()
        version = None
        dlc_info = None

        if game_dir:
            result = updater.detect_version(game_dir)
            version = result.version

            try:
                states = updater._dlc_manager.get_dlc_states(game_dir)
                total = len(states)
                installed = sum(1 for s in states if s["installed"])
                enabled = sum(1 for s in states if s["enabled"] is True)
                dlc_info = f"{installed}/{total} installed, {enabled} enabled"
            except Exception:
                dlc_info = "Error reading DLCs"

        return {
            "game_dir": game_dir,
            "version": version,
            "dlc_info": dlc_info,
        }

    def _on_info_detected(self, info: dict):
        """GUI thread: update labels with detected info."""
        game_dir = info.get("game_dir")
        version = info.get("version")
        dlc_info = info.get("dlc_info")

        if game_dir:
            # Truncate long paths
            display = str(game_dir)
            if len(display) > 60:
                display = "..." + display[-57:]
            self._game_dir_label.configure(text=display)
        else:
            self._game_dir_label.configure(text="Not found")

        if version:
            self._version_label.configure(text=version)
        else:
            self._version_label.configure(text="Unknown")

        self._latest_label.configure(text="Use 'Check for Updates'")
        self._dlc_label.configure(text=dlc_info or "N/A")
        self._status_label.configure(text="")
        self._update_btn.configure(state="normal")

    def _on_check_updates(self):
        """Check for updates button handler."""
        manifest_url = self.app.settings.manifest_url
        if not manifest_url:
            self.app.show_message(
                "No Manifest URL",
                "Please set a manifest URL in Settings first.",
            )
            return

        self._update_btn.configure(state="disabled")
        self._status_label.configure(text="Checking for updates...")
        self.app.run_async(
            self._check_updates_bg,
            on_done=self._on_updates_checked,
            on_error=self._on_check_error,
        )

    def _check_updates_bg(self):
        """Background: check for updates."""
        return self.app.updater.check_for_updates()

    def _on_updates_checked(self, info):
        """GUI thread: show update results."""
        self._update_btn.configure(state="normal")

        self._latest_label.configure(text=info.latest_version)

        if not info.update_available:
            self._status_label.configure(
                text="You are up to date!",
                text_color=theme.COLORS["success"],
            )
        else:
            from ..patch.client import format_size

            size = format_size(info.total_download_size)
            self._status_label.configure(
                text=f"Update available: {info.step_count} step(s), {size}",
                text_color=theme.COLORS["warning"],
            )

            # Change button to "Update Now"
            self._update_btn.configure(
                text="Update Now",
                command=lambda: self._start_update(info),
            )

    def _on_check_error(self, error):
        self._update_btn.configure(state="normal")
        self._status_label.configure(
            text=f"Error: {error}",
            text_color=theme.COLORS["error"],
        )

    def _start_update(self, info):
        """Start the actual update process."""
        self.app.switch_to_progress()
        progress_frame = self.app._frames.get("progress")
        if progress_frame:
            progress_frame.start_update(info.plan)
