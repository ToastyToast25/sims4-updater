"""
DLC frame — scrollable checkboxes with collapsible groups and auto-toggle support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import get_animator

if TYPE_CHECKING:
    from ..app import App


class DLCFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._checkboxes: dict[str, ctk.CTkCheckBox] = {}
        self._checkbox_vars: dict[str, ctk.BooleanVar] = {}
        self._pending_dlcs = []
        self._section_frames: dict[str, ctk.CTkFrame] = {}
        self._section_collapsed: dict[str, bool] = {}

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
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        self._auto_btn = ctk.CTkButton(
            btn_frame,
            text="Auto-Toggle",
            font=ctk.CTkFont(size=12),
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_auto_toggle,
        )
        self._auto_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self._apply_btn = ctk.CTkButton(
            btn_frame,
            text="Apply Changes",
            font=ctk.CTkFont(size=12),
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card"],
            command=self._on_apply,
        )
        self._apply_btn.grid(row=0, column=1, sticky="ew")

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
        """GUI thread: build checkbox list with collapsible groups."""
        # Clear existing
        for widget in self._scroll_frame.winfo_children():
            widget.destroy()
        self._checkboxes.clear()
        self._checkbox_vars.clear()
        self._section_frames.clear()

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

            # Count stats for this section
            sec_installed = sum(1 for s in type_states if s["installed"])
            sec_total = len(type_states)

            total += sec_total
            installed += sec_installed
            enabled += sum(1 for s in type_states if s["enabled"] is True)

            # Separator before each section (except the first)
            if row > 0:
                ctk.CTkFrame(
                    self._scroll_frame, height=1,
                    fg_color=theme.COLORS["separator"],
                ).grid(row=row, column=0, padx=5, pady=(8, 0), sticky="ew")
                row += 1

            # Collapsible section header button
            is_collapsed = self._section_collapsed.get(pack_type, False)
            arrow = "\u25b6" if is_collapsed else "\u25bc"
            label_text = type_labels.get(pack_type, pack_type)
            header_text = f"{arrow}  {label_text}  ({sec_installed}/{sec_total})"

            header_btn = ctk.CTkButton(
                self._scroll_frame,
                text=header_text,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=theme.COLORS["accent"],
                fg_color="transparent",
                hover_color=theme.COLORS["sidebar_hover"],
                anchor="w",
                height=30,
                corner_radius=4,
                command=lambda pt=pack_type: self._toggle_section(pt),
            )
            header_btn.grid(row=row, column=0, padx=2, pady=(10, 2), sticky="ew")
            row += 1

            # Content frame for collapsible children
            content_frame = ctk.CTkFrame(self._scroll_frame, fg_color="transparent")
            content_frame.grid(row=row, column=0, sticky="ew")
            content_frame.grid_columnconfigure(0, weight=1)
            self._section_frames[pack_type] = content_frame
            row += 1

            if is_collapsed:
                content_frame.grid_remove()
                continue

            cb_row = 0
            for state in type_states:
                dlc = state["dlc"]
                name = dlc.get_name()
                is_inst = state["installed"]
                is_en = state["enabled"]

                var = ctk.BooleanVar(value=is_en is True)
                self._checkbox_vars[dlc.id] = var

                status_text = "  [MISSING]" if not is_inst else ""

                cb = ctk.CTkCheckBox(
                    content_frame,
                    text=f"{name}{status_text}",
                    variable=var,
                    font=ctk.CTkFont(size=12),
                    height=theme.BUTTON_HEIGHT_SMALL,
                    corner_radius=4,
                )

                if not is_inst:
                    cb.configure(
                        text_color=theme.COLORS["text_muted"],
                        state="disabled",
                    )
                else:
                    # Hover effect on installed checkboxes
                    cb.bind("<Enter>", lambda e, w=cb: w.configure(
                        text_color=theme.COLORS["text"],
                    ))
                    cb.bind("<Leave>", lambda e, w=cb: w.configure(
                        text_color=theme.COLORS["text"] if not hasattr(w, '_is_muted') else theme.COLORS["text_muted"],
                    ))

                cb.grid(row=cb_row, column=0, padx=15, pady=2, sticky="w")
                self._checkboxes[dlc.id] = cb
                cb_row += 1

        # ── Pending DLCs from manifest ──
        if self._pending_dlcs:
            ctk.CTkFrame(
                self._scroll_frame, height=1,
                fg_color=theme.COLORS["separator"],
            ).grid(row=row, column=0, padx=5, pady=(8, 0), sticky="ew")
            row += 1

            ctk.CTkLabel(
                self._scroll_frame,
                text="\u25cf  Pending (Patch Not Yet Available)",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=theme.COLORS["warning"],
            ).grid(row=row, column=0, padx=5, pady=(10, 4), sticky="w")
            row += 1

            for pending in self._pending_dlcs:
                ctk.CTkLabel(
                    self._scroll_frame,
                    text=f"    {pending.name}  [PENDING]",
                    font=ctk.CTkFont(size=12),
                    text_color=theme.COLORS["text_muted"],
                ).grid(row=row, column=0, padx=15, pady=1, sticky="w")
                row += 1

        self._status_label.configure(
            text=f"{installed}/{total} installed, {enabled} enabled"
        )

    def _toggle_section(self, pack_type: str):
        """Toggle a section's collapsed state and refresh."""
        self._section_collapsed[pack_type] = not self._section_collapsed.get(pack_type, False)
        frame = self._section_frames.get(pack_type)
        if frame is None:
            return

        if self._section_collapsed[pack_type]:
            frame.grid_remove()
        else:
            frame.grid()

        # Update header arrow — find the header button and update text
        for widget in self._scroll_frame.winfo_children():
            if isinstance(widget, ctk.CTkButton):
                text = widget.cget("text")
                label = {
                    "expansion": "Expansion Packs",
                    "game_pack": "Game Packs",
                    "stuff_pack": "Stuff Packs",
                    "kit": "Kits",
                    "free_pack": "Free Packs",
                    "other": "Other",
                }.get(pack_type, pack_type)
                if label in text:
                    arrow = "\u25b6" if self._section_collapsed[pack_type] else "\u25bc"
                    # Reconstruct the text keeping the count
                    count_part = text.split("(")[-1] if "(" in text else ""
                    new_text = f"{arrow}  {label}  ({count_part}" if count_part else f"{arrow}  {label}"
                    widget.configure(text=new_text)
                    break

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
            self.app.show_toast(f"Toggled {len(changes)} DLC(s)", "success")
            self._load_dlcs()
        else:
            self.app.show_toast("All DLCs already correctly configured", "success")

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
        self.app.show_toast("Changes applied successfully", "success")

    def set_pending_dlcs(self, pending_dlcs):
        """Store pending DLCs from manifest for display on next refresh."""
        self._pending_dlcs = pending_dlcs

    def _on_dlc_error(self, error):
        self._auto_btn.configure(state="normal")
        self._apply_btn.configure(state="normal")
        self._status_label.configure(
            text=f"Error: {error}",
            text_color=theme.COLORS["error"],
        )
