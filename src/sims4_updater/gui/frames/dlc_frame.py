"""
DLC frame — scrollable checkboxes with auto-toggle support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme

if TYPE_CHECKING:
    from ..app import App


class DLCFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._checkboxes: dict[str, ctk.CTkCheckBox] = {}
        self._checkbox_vars: dict[str, ctk.BooleanVar] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ──
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=30, pady=(20, 10), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_frame,
            text="DLC Management",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, sticky="w")

        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e")

        self._auto_btn = ctk.CTkButton(
            btn_frame,
            text="Auto-Toggle",
            font=ctk.CTkFont(size=12),
            height=32,
            corner_radius=6,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_auto_toggle,
        )
        self._auto_btn.pack(side="left", padx=(0, 5))

        self._apply_btn = ctk.CTkButton(
            btn_frame,
            text="Apply Changes",
            font=ctk.CTkFont(size=12),
            height=32,
            corner_radius=6,
            fg_color=theme.COLORS["bg_card"],
            command=self._on_apply,
        )
        self._apply_btn.pack(side="left")

        # ── Status ──
        self._status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._status_label.grid(row=2, column=0, padx=30, pady=(5, 10), sticky="w")

        # ── Scrollable DLC list ──
        self._scroll_frame = ctk.CTkScrollableFrame(self, corner_radius=8)
        self._scroll_frame.grid(row=1, column=0, padx=30, pady=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

    def on_show(self):
        """Refresh DLC list when frame is shown."""
        self._load_dlcs()

    def _load_dlcs(self):
        """Load DLC states in background."""
        self._status_label.configure(text="Loading DLCs...")
        self.app.run_async(self._get_dlc_states, on_done=self._populate_list)

    def _get_dlc_states(self):
        """Background: fetch DLC states."""
        game_dir = self.app.updater.find_game_dir()
        if not game_dir:
            return None

        from ...language.changer import get_current_language

        locale = get_current_language()
        states = self.app.updater._dlc_manager.get_dlc_states(game_dir, locale)
        return states

    def _populate_list(self, states):
        """GUI thread: build checkbox list."""
        # Clear existing
        for widget in self._scroll_frame.winfo_children():
            widget.destroy()
        self._checkboxes.clear()
        self._checkbox_vars.clear()

        if states is None:
            ctk.CTkLabel(
                self._scroll_frame,
                text="No game directory found. Set it in Settings.",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=0, padx=10, pady=20)
            self._status_label.configure(text="")
            return

        # Group by type
        type_order = [
            "expansion", "game_pack", "stuff_pack", "kit", "free_pack", "other",
        ]
        type_labels = {
            "expansion": "Expansion Packs",
            "game_pack": "Game Packs",
            "stuff_pack": "Stuff Packs",
            "kit": "Kits",
            "free_pack": "Free Packs",
            "other": "Other",
        }

        row = 0
        total = 0
        installed = 0
        enabled = 0

        for pack_type in type_order:
            type_states = [s for s in states if s["dlc"].pack_type == pack_type]
            if not type_states:
                continue

            # Section header
            ctk.CTkLabel(
                self._scroll_frame,
                text=type_labels.get(pack_type, pack_type),
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=theme.COLORS["accent"],
            ).grid(row=row, column=0, padx=5, pady=(12, 4), sticky="w")
            row += 1

            for state in type_states:
                dlc = state["dlc"]
                name = dlc.get_name()
                is_installed = state["installed"]
                is_enabled = state["enabled"]

                total += 1
                if is_installed:
                    installed += 1
                if is_enabled is True:
                    enabled += 1

                var = ctk.BooleanVar(value=is_enabled is True)
                self._checkbox_vars[dlc.id] = var

                # Build display text
                status_text = ""
                if not is_installed:
                    status_text = "  [MISSING]"

                cb = ctk.CTkCheckBox(
                    self._scroll_frame,
                    text=f"{name}{status_text}",
                    variable=var,
                    font=ctk.CTkFont(size=12),
                    height=28,
                    corner_radius=4,
                )

                if not is_installed:
                    cb.configure(
                        text_color=theme.COLORS["text_muted"],
                    )

                cb.grid(row=row, column=0, padx=15, pady=1, sticky="w")
                self._checkboxes[dlc.id] = cb
                row += 1

        self._status_label.configure(
            text=f"{installed}/{total} installed, {enabled} enabled"
        )

    def _on_auto_toggle(self):
        """Auto-enable installed, disable missing."""
        self._auto_btn.configure(state="disabled")
        self._status_label.configure(text="Auto-toggling...")
        self.app.run_async(
            self._auto_toggle_bg,
            on_done=self._on_auto_done,
            on_error=self._on_dlc_error,
        )

    def _auto_toggle_bg(self):
        game_dir = self.app.updater.find_game_dir()
        if not game_dir:
            return {}
        return self.app.updater._dlc_manager.auto_toggle(game_dir)

    def _on_auto_done(self, changes: dict):
        self._auto_btn.configure(state="normal")
        if changes:
            self._status_label.configure(
                text=f"Toggled {len(changes)} DLC(s). Refreshing...",
                text_color=theme.COLORS["success"],
            )
            self._load_dlcs()
        else:
            self._status_label.configure(
                text="All DLCs already correctly configured.",
                text_color=theme.COLORS["success"],
            )

    def _on_apply(self):
        """Apply checkbox selections to crack config."""
        self._apply_btn.configure(state="disabled")
        self._status_label.configure(text="Applying changes...")

        enabled_set = {
            dlc_id for dlc_id, var in self._checkbox_vars.items() if var.get()
        }
        self.app.run_async(
            self._apply_bg,
            enabled_set,
            on_done=self._on_apply_done,
            on_error=self._on_dlc_error,
        )

    def _apply_bg(self, enabled_set):
        game_dir = self.app.updater.find_game_dir()
        if not game_dir:
            return
        self.app.updater._dlc_manager.apply_changes(game_dir, enabled_set)

    def _on_apply_done(self, _):
        self._apply_btn.configure(state="normal")
        self._status_label.configure(
            text="Changes applied successfully.",
            text_color=theme.COLORS["success"],
        )

    def _on_dlc_error(self, error):
        self._auto_btn.configure(state="normal")
        self._apply_btn.configure(state="normal")
        self._status_label.configure(
            text=f"Error: {error}",
            text_color=theme.COLORS["error"],
        )
