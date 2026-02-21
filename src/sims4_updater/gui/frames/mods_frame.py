"""
Mods tab — manage bundled and installed game modifications.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import InfoCard, StatusBadge

if TYPE_CHECKING:
    from ..app import App


# Default Documents-based Mods folder
_DEFAULT_MODS_DIR = (
    Path.home() / "Documents" / "Electronic Arts" / "The Sims 4" / "Mods"
)


def _format_size(size_bytes: int) -> str:
    """Format bytes into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class ModsFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._busy = False
        self._manager = None  # Lazy init

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Top section (fixed) ──────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="new", padx=0, pady=0)
        top.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(
            top,
            text="Mods",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, padx=30, pady=(20, 4), sticky="w")

        ctk.CTkLabel(
            top,
            text="Manage game modifications",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=1, column=0, padx=30, pady=(0, 12), sticky="w")

        # ── Status card ──────────────────────────────────────────
        self._card = InfoCard(top, fg_color=theme.COLORS["bg_card"])
        self._card.grid(row=2, column=0, padx=30, pady=(0, 10), sticky="ew")
        self._card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self._card, text="Mods Folder",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, padx=(theme.CARD_PAD_X, 8), pady=(theme.CARD_PAD_Y, 4), sticky="w")

        self._folder_badge = StatusBadge(self._card, text="...", style="muted")
        self._folder_badge.grid(row=0, column=1, padx=0, pady=(theme.CARD_PAD_Y, 4), sticky="w")

        ctk.CTkLabel(
            self._card, text="Status",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=1, column=0, padx=(theme.CARD_PAD_X, 8), pady=4, sticky="w")

        self._status_badge = StatusBadge(self._card, text="Loading...", style="muted")
        self._status_badge.grid(row=1, column=1, padx=0, pady=4, sticky="w")

        ctk.CTkLabel(
            self._card, text="Total Size",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=2, column=0, padx=(theme.CARD_PAD_X, 8), pady=(4, theme.CARD_PAD_Y), sticky="w")

        self._size_badge = StatusBadge(self._card, text="...", style="muted")
        self._size_badge.grid(row=2, column=1, padx=0, pady=(4, theme.CARD_PAD_Y), sticky="w")

        # ── Action buttons row ───────────────────────────────────
        btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=30, pady=(0, 10), sticky="ew")

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
        self._refresh_btn.pack(side="left", padx=(0, 5))

        self._open_folder_btn = ctk.CTkButton(
            btn_frame,
            text="Open Mods Folder",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_open_folder,
        )
        self._open_folder_btn.pack(side="left", padx=5)

        # ── Scrollable content area ──────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_rowconfigure(0, weight=3)
        bottom.grid_rowconfigure(1, weight=2)

        # Mod list (scrollable)
        self._mod_scroll = ctk.CTkScrollableFrame(
            bottom,
            fg_color=theme.COLORS["bg_deeper"],
            corner_radius=theme.CORNER_RADIUS_SMALL,
            border_width=1,
            border_color=theme.COLORS["border"],
        )
        self._mod_scroll.grid(row=0, column=0, sticky="nsew", padx=30, pady=(0, 8))
        self._mod_scroll.grid_columnconfigure(0, weight=1)

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
            height=24, width=60,
            corner_radius=4,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._clear_log,
        ).grid(row=0, column=1, sticky="e")

        self._log_box = ctk.CTkTextbox(
            log_container,
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

        # Track mod row widgets for refresh
        self._mod_rows: list[ctk.CTkFrame] = []

    # ── Manager ──────────────────────────────────────────────────

    def _get_manager(self):
        if self._manager is None:
            from ...mods.manager import ModManager
            self._manager = ModManager(_DEFAULT_MODS_DIR)
        return self._manager

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

    # ── Status Refresh ────────────────────────────────────────────

    def on_show(self):
        self._refresh()

    def _on_refresh(self):
        self._refresh()

    def _refresh(self):
        mgr = self._get_manager()
        mods_dir = mgr.game_mods_dir

        # Update folder badge
        if mods_dir.is_dir():
            self._folder_badge.set_status(str(mods_dir), "info")
        else:
            self._folder_badge.set_status("Not found", "warning")

        def _bg():
            mgr.load_registry()
            bundled, detected = mgr.get_all_mods()
            # Calculate sizes in background thread
            sizes = {}
            for m in bundled:
                sizes[m.name] = mgr.get_mod_size(m)
            for m in detected:
                sizes[m.name] = mgr.get_mod_size(m)
            return bundled, detected, sizes

        def _done(result):
            bundled, detected, sizes = result
            total = sum(1 for m in bundled if mgr.is_installed(m.name)) + len(detected)
            self._status_badge.set_status(
                f"{total} mod(s) installed, {len(bundled)} bundled",
                "success" if total > 0 else "muted",
            )
            total_size = sum(sizes.values())
            self._size_badge.set_status(_format_size(total_size), "info")
            self._rebuild_mod_list(bundled, detected, sizes)

        def _err(e):
            self._status_badge.set_status("Error loading mods", "error")
            self._log(f"Error: {e}")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Mod List UI ───────────────────────────────────────────────

    def _rebuild_mod_list(self, bundled, detected, sizes=None):
        if sizes is None:
            sizes = {}

        # Clear existing rows
        for row in self._mod_rows:
            row.destroy()
        self._mod_rows.clear()

        # ── Bundled Mods section ──
        if bundled:
            header = ctk.CTkLabel(
                self._mod_scroll,
                text="Bundled Mods",
                font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
                text_color=theme.COLORS["accent"],
            )
            header.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
            self._mod_rows.append(header)

            for i, mod in enumerate(bundled):
                row = self._create_bundled_row(mod, i + 1, sizes.get(mod.name, 0))
                self._mod_rows.append(row)

        # ── Detected / Installed Mods section ──
        offset = len(bundled) + 2
        if detected:
            header = ctk.CTkLabel(
                self._mod_scroll,
                text="Installed Mods (Detected)",
                font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
                text_color=theme.COLORS["accent"],
            )
            header.grid(row=offset, column=0, sticky="w", padx=8, pady=(12, 4))
            self._mod_rows.append(header)

            for i, mod in enumerate(detected):
                row = self._create_detected_row(mod, offset + 1 + i, sizes.get(mod.name, 0))
                self._mod_rows.append(row)

        if not bundled and not detected:
            lbl = ctk.CTkLabel(
                self._mod_scroll,
                text="No mods found. Place mod ZIPs in the bundled mods directory or install mods to the game's Mods folder.",
                font=ctk.CTkFont(*theme.FONT_SMALL),
                text_color=theme.COLORS["text_muted"],
                wraplength=500,
            )
            lbl.grid(row=0, column=0, padx=8, pady=20)
            self._mod_rows.append(lbl)

    def _create_bundled_row(self, mod, grid_row: int, size_bytes: int = 0) -> ctk.CTkFrame:
        mgr = self._get_manager()
        installed = mgr.is_installed(mod.name)

        row = ctk.CTkFrame(self._mod_scroll, fg_color=theme.COLORS["bg_card"], corner_radius=6)
        row.grid(row=grid_row, column=0, sticky="ew", padx=4, pady=3)
        row.grid_columnconfigure(1, weight=1)

        # Mod name + size
        name_text = mod.name
        if size_bytes > 0:
            name_text += f"  ({_format_size(size_bytes)})"
        ctk.CTkLabel(
            row, text=name_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, padx=(12, 8), pady=8, sticky="w")

        # Status badge
        if installed and mod.enabled:
            badge_text, badge_style = "Installed", "success"
        elif installed and not mod.enabled:
            badge_text, badge_style = "Disabled", "warning"
        else:
            badge_text, badge_style = "Not Installed", "muted"

        badge = StatusBadge(row, text=badge_text, style=badge_style)
        badge.grid(row=0, column=1, padx=4, pady=8, sticky="w")

        # Buttons
        btn_container = ctk.CTkFrame(row, fg_color="transparent")
        btn_container.grid(row=0, column=2, padx=(4, 8), pady=6, sticky="e")

        if not installed:
            ctk.CTkButton(
                btn_container, text="Install",
                font=ctk.CTkFont(size=11), height=28, width=70,
                corner_radius=4,
                fg_color=theme.COLORS["accent"],
                hover_color=theme.COLORS["accent_hover"],
                command=lambda m=mod.name: self._on_install(m),
            ).pack(side="left", padx=2)
        else:
            if mod.enabled:
                ctk.CTkButton(
                    btn_container, text="Disable",
                    font=ctk.CTkFont(size=11), height=28, width=70,
                    corner_radius=4,
                    fg_color=theme.COLORS["warning"],
                    hover_color="#cc8400",
                    command=lambda m=mod.name: self._on_disable(m),
                ).pack(side="left", padx=2)
            else:
                ctk.CTkButton(
                    btn_container, text="Enable",
                    font=ctk.CTkFont(size=11), height=28, width=70,
                    corner_radius=4,
                    fg_color=theme.COLORS["success"],
                    hover_color="#26b863",
                    command=lambda m=mod.name: self._on_enable(m),
                ).pack(side="left", padx=2)

            ctk.CTkButton(
                btn_container, text="Uninstall",
                font=ctk.CTkFont(size=11), height=28, width=80,
                corner_radius=4,
                fg_color=theme.COLORS["bg_card_alt"],
                hover_color=theme.COLORS["card_hover"],
                command=lambda m=mod.name: self._on_uninstall(m),
            ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_container, text="Delete",
            font=ctk.CTkFont(size=11), height=28, width=60,
            corner_radius=4,
            fg_color=theme.COLORS["error"],
            hover_color="#cc3944",
            command=lambda m=mod.name: self._on_delete(m),
        ).pack(side="left", padx=2)

        return row

    def _create_detected_row(self, mod, grid_row: int, size_bytes: int = 0) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self._mod_scroll, fg_color=theme.COLORS["bg_card"], corner_radius=6)
        row.grid(row=grid_row, column=0, sticky="ew", padx=4, pady=3)
        row.grid_columnconfigure(1, weight=1)

        # Mod name + size
        name_text = mod.name
        if size_bytes > 0:
            name_text += f"  ({_format_size(size_bytes)})"
        ctk.CTkLabel(
            row, text=name_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, padx=(12, 8), pady=8, sticky="w")

        # File count + status
        file_count = len(mod.installed_files)
        status_text = f"{file_count} file(s)"
        if not mod.enabled:
            status_text += " (Disabled)"

        badge_style = "success" if mod.enabled else "warning"
        badge = StatusBadge(row, text=status_text, style=badge_style)
        badge.grid(row=0, column=1, padx=4, pady=8, sticky="w")

        # Buttons
        btn_container = ctk.CTkFrame(row, fg_color="transparent")
        btn_container.grid(row=0, column=2, padx=(4, 8), pady=6, sticky="e")

        if mod.enabled:
            ctk.CTkButton(
                btn_container, text="Disable",
                font=ctk.CTkFont(size=11), height=28, width=70,
                corner_radius=4,
                fg_color=theme.COLORS["warning"],
                hover_color="#cc8400",
                command=lambda m=mod: self._on_disable_detected(m),
            ).pack(side="left", padx=2)
        else:
            ctk.CTkButton(
                btn_container, text="Enable",
                font=ctk.CTkFont(size=11), height=28, width=70,
                corner_radius=4,
                fg_color=theme.COLORS["success"],
                hover_color="#26b863",
                command=lambda m=mod: self._on_enable_detected(m),
            ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_container, text="Uninstall",
            font=ctk.CTkFont(size=11), height=28, width=80,
            corner_radius=4,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=lambda m=mod: self._on_uninstall_detected(m),
        ).pack(side="left", padx=2)

        return row

    # ── Actions (bundled mods) ────────────────────────────────────

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._refresh_btn.configure(state=state)

    def _on_install(self, mod_name: str):
        if self._busy:
            return
        self._set_busy(True)
        self._log(f"--- Installing {mod_name} ---")

        mgr = self._get_manager()

        def _bg():
            return mgr.install_mod(mod_name, log=self._enqueue_log)

        def _done(ok):
            self._set_busy(False)
            if ok:
                self.app.show_toast(f"{mod_name} installed!", "success")
            else:
                self.app.show_toast(f"Failed to install {mod_name}", "error")
            self._refresh()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Install failed: {e}")
            self.app.show_toast(f"Install failed: {e}", "error")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    def _on_uninstall(self, mod_name: str):
        if self._busy:
            return
        confirmed = tk.messagebox.askyesno(
            "Confirm Uninstall",
            f"Uninstall {mod_name}?\n\nThis will remove the mod files from the game's Mods folder.",
            parent=self.winfo_toplevel(),
        )
        if not confirmed:
            return

        self._set_busy(True)
        self._log(f"--- Uninstalling {mod_name} ---")
        mgr = self._get_manager()

        def _bg():
            return mgr.uninstall_mod(mod_name, log=self._enqueue_log)

        def _done(ok):
            self._set_busy(False)
            if ok:
                self.app.show_toast(f"{mod_name} uninstalled.", "success")
            self._refresh()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Uninstall failed: {e}")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    def _on_enable(self, mod_name: str):
        if self._busy:
            return
        self._set_busy(True)
        mgr = self._get_manager()

        def _bg():
            return mgr.enable_mod(mod_name, log=self._enqueue_log)

        def _done(_):
            self._set_busy(False)
            self.app.show_toast(f"{mod_name} enabled.", "success")
            self._refresh()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Enable failed: {e}")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    def _on_disable(self, mod_name: str):
        if self._busy:
            return
        self._set_busy(True)
        mgr = self._get_manager()

        def _bg():
            return mgr.disable_mod(mod_name, log=self._enqueue_log)

        def _done(_):
            self._set_busy(False)
            self.app.show_toast(f"{mod_name} disabled.", "success")
            self._refresh()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Disable failed: {e}")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    def _on_delete(self, mod_name: str):
        if self._busy:
            return
        confirmed = tk.messagebox.askyesno(
            "Confirm Delete",
            f"Delete bundled mod '{mod_name}'?\n\n"
            "This will permanently remove the ZIP file. "
            "Installed mod files in the game will NOT be affected.",
            parent=self.winfo_toplevel(),
        )
        if not confirmed:
            return

        self._set_busy(True)
        self._log(f"--- Deleting {mod_name} ---")
        mgr = self._get_manager()

        def _bg():
            return mgr.delete_bundled_mod(mod_name, log=self._enqueue_log)

        def _done(ok):
            self._set_busy(False)
            if ok:
                self.app.show_toast(f"{mod_name} deleted.", "success")
            self._refresh()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Delete failed: {e}")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Actions (detected mods) ───────────────────────────────────

    def _on_enable_detected(self, mod):
        if self._busy:
            return
        self._set_busy(True)
        mgr = self._get_manager()

        def _bg():
            # Register the detected mod temporarily so enable works
            from ...mods.manager import ModInfo, DISABLED_SUFFIX
            mgr._registry[mod.name] = mod
            mgr.save_registry()
            return mgr.enable_mod(mod.name, log=self._enqueue_log)

        def _done(_):
            self._set_busy(False)
            self.app.show_toast(f"{mod.name} enabled.", "success")
            self._refresh()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Enable failed: {e}")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    def _on_disable_detected(self, mod):
        if self._busy:
            return
        self._set_busy(True)
        mgr = self._get_manager()

        def _bg():
            mgr._registry[mod.name] = mod
            mgr.save_registry()
            return mgr.disable_mod(mod.name, log=self._enqueue_log)

        def _done(_):
            self._set_busy(False)
            self.app.show_toast(f"{mod.name} disabled.", "success")
            self._refresh()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Disable failed: {e}")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    def _on_uninstall_detected(self, mod):
        if self._busy:
            return
        confirmed = tk.messagebox.askyesno(
            "Confirm Uninstall",
            f"Uninstall {mod.name}?\n\nThis will remove {len(mod.installed_files)} file(s) from the Mods folder.",
            parent=self.winfo_toplevel(),
        )
        if not confirmed:
            return

        self._set_busy(True)
        self._log(f"--- Uninstalling {mod.name} ---")
        mgr = self._get_manager()

        def _bg():
            mgr._registry[mod.name] = mod
            mgr.save_registry()
            return mgr.uninstall_mod(mod.name, log=self._enqueue_log)

        def _done(ok):
            self._set_busy(False)
            if ok:
                self.app.show_toast(f"{mod.name} uninstalled.", "success")
            self._refresh()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Uninstall failed: {e}")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Misc ──────────────────────────────────────────────────────

    def _on_open_folder(self):
        mods_dir = self._get_manager().game_mods_dir
        if mods_dir.is_dir():
            import os
            os.startfile(str(mods_dir))
        else:
            self.app.show_toast("Mods folder not found.", "warning")
