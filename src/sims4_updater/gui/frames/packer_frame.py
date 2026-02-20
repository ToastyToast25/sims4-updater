"""
DLC Packer frame — pack DLC folders into distributable ZIP archives,
generate manifest JSON, and import archives into the game directory.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ...config import get_app_dir
from ...dlc.packer import DLCPacker, PackResult

if TYPE_CHECKING:
    from ..app import App


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.1f} GB"
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.0f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


class PackerFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._packer = DLCPacker(app.updater._dlc_manager.catalog)

        self._dlc_vars: dict[str, ctk.BooleanVar] = {}
        self._dlc_sizes: dict[str, int] = {}  # dlc_id -> folder size in bytes
        self._dlc_rows: list[ctk.CTkFrame] = []
        self._busy = False

        self._output_dir = get_app_dir() / "packed_dlcs"

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Header ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=30, pady=(20, 4), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="DLC Packer",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Pack DLC files for distribution or import archives",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))

        # ── Top bar: Select All / Deselect All + Pack buttons ──
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, padx=30, pady=(0, 5), sticky="ew")
        bar.grid_columnconfigure(2, weight=1)

        self._select_all_btn = ctk.CTkButton(
            bar,
            text="Select All",
            font=ctk.CTkFont(size=11),
            height=theme.BUTTON_HEIGHT_SMALL,
            width=90,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card"],
            hover_color=theme.COLORS["card_hover"],
            command=self._select_all,
        )
        self._select_all_btn.grid(row=0, column=0, padx=(0, 4))

        self._deselect_all_btn = ctk.CTkButton(
            bar,
            text="Deselect All",
            font=ctk.CTkFont(size=11),
            height=theme.BUTTON_HEIGHT_SMALL,
            width=90,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card"],
            hover_color=theme.COLORS["card_hover"],
            command=self._deselect_all,
        )
        self._deselect_all_btn.grid(row=0, column=1, padx=(0, 8))

        # Spacer
        ctk.CTkFrame(bar, fg_color="transparent", height=1).grid(
            row=0, column=2, sticky="ew"
        )

        self._pack_selected_btn = ctk.CTkButton(
            bar,
            text="Pack Selected",
            font=ctk.CTkFont(size=12),
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_pack_selected,
        )
        self._pack_selected_btn.grid(row=0, column=3, padx=(0, 4))

        self._pack_all_btn = ctk.CTkButton(
            bar,
            text="Pack All",
            font=ctk.CTkFont(size=12),
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["success"],
            hover_color="#3ae882",
            text_color="#1a1a2e",
            command=self._on_pack_all,
        )
        self._pack_all_btn.grid(row=0, column=4)

        # ── Scrollable DLC list ──
        self._scroll_frame = ctk.CTkScrollableFrame(
            self,
            corner_radius=8,
            scrollbar_button_color=theme.COLORS["separator"],
            scrollbar_button_hover_color=theme.COLORS["accent"],
        )
        self._scroll_frame.grid(row=2, column=0, padx=30, pady=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        # ── Empty state ──
        self._empty_label = ctk.CTkLabel(
            self._scroll_frame,
            text="No game directory found. Set it in Settings.",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        )

        # ── Import section ──
        import_frame = ctk.CTkFrame(
            self,
            fg_color=theme.COLORS["bg_card"],
            corner_radius=theme.CORNER_RADIUS_SMALL,
            border_width=1,
            border_color=theme.COLORS["border"],
        )
        import_frame.grid(row=3, column=0, padx=30, pady=(10, 0), sticky="ew")
        import_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            import_frame,
            text="Import Archive",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=0, column=0, padx=(15, 8), pady=10, sticky="w")

        ctk.CTkLabel(
            import_frame,
            text="Extract a ZIP or RAR into the game directory",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=0, column=1, pady=10, sticky="w")

        self._import_btn = ctk.CTkButton(
            import_frame,
            text="Browse & Import...",
            font=ctk.CTkFont(size=12),
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_import,
        )
        self._import_btn.grid(row=0, column=2, padx=(8, 15), pady=10, sticky="e")

        # ── Progress + Status bar ──
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=4, column=0, padx=30, pady=(8, 12), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        self._progress_bar = ctk.CTkProgressBar(
            bottom,
            height=6,
            corner_radius=3,
            progress_color=theme.COLORS["accent"],
        )
        self._progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self._progress_bar.set(0)

        self._status_label = ctk.CTkLabel(
            bottom,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._status_label.grid(row=1, column=0, sticky="w")

        output_row = ctk.CTkFrame(bottom, fg_color="transparent")
        output_row.grid(row=1, column=0, sticky="e")

        ctk.CTkLabel(
            output_row,
            text=f"Output: {self._output_dir}",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_dim"],
        ).pack(side="left", padx=(0, 6))

        self._open_folder_btn = ctk.CTkButton(
            output_row,
            text="Open Folder",
            font=ctk.CTkFont(size=10),
            height=22,
            width=80,
            corner_radius=4,
            fg_color=theme.COLORS["bg_card"],
            hover_color=theme.COLORS["card_hover"],
            command=self._open_output_folder,
        )
        self._open_folder_btn.pack(side="left")

    # ── Lifecycle ─────────────────────────────────────────────────

    def on_show(self):
        self._load_installed_dlcs()

    def _load_installed_dlcs(self):
        self._status_label.configure(text="Scanning installed DLCs...")
        self.app.run_async(
            self._scan_bg,
            on_done=self._on_scan_done,
            on_error=self._on_scan_error,
        )

    def _scan_bg(self):
        game_dir = self.app.updater.find_game_dir()
        if not game_dir:
            return None
        return self._packer.get_installed_dlcs(Path(game_dir))

    def _on_scan_done(self, results):
        # Clear existing rows
        for row in self._dlc_rows:
            row.destroy()
        self._dlc_rows.clear()
        self._dlc_vars.clear()
        self._dlc_sizes.clear()

        if results is None:
            self._empty_label.grid(row=0, column=0, padx=10, pady=20)
            self._status_label.configure(text="")
            return

        self._empty_label.grid_remove()

        for i, (dlc, file_count, folder_size) in enumerate(results):
            self._dlc_sizes[dlc.id] = folder_size
            self._build_dlc_row(i, dlc, file_count, folder_size)

        total = len(results)
        self._status_label.configure(text=f"{total} installed DLC(s) found")

    def _on_scan_error(self, error):
        self._status_label.configure(
            text=f"Error: {error}",
            text_color=theme.COLORS["error"],
        )

    # ── Row Building ──────────────────────────────────────────────

    def _build_dlc_row(self, idx, dlc, file_count, folder_size):
        bg = theme.COLORS["bg_card"] if idx % 2 == 0 else theme.COLORS["bg_card_alt"]
        row = ctk.CTkFrame(
            self._scroll_frame,
            fg_color=bg,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            border_width=1,
            border_color=theme.COLORS["border"],
        )
        row.grid(row=idx, column=0, padx=4, pady=2, sticky="ew")
        row.grid_columnconfigure(1, weight=1)

        var = ctk.BooleanVar(value=True)
        cb = ctk.CTkCheckBox(
            row,
            text=f"{dlc.id} \u2014 {dlc.get_name()}",
            variable=var,
            font=ctk.CTkFont(size=12),
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=4,
        )
        cb.grid(row=0, column=0, padx=(10, 0), pady=6, sticky="w", columnspan=2)

        size_text = f"{file_count} files, {_format_size(folder_size)}"
        ctk.CTkLabel(
            row,
            text=size_text,
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=0, column=2, padx=(0, 12), pady=6, sticky="e")

        self._dlc_vars[dlc.id] = var
        self._dlc_rows.append(row)

    # ── Selection ─────────────────────────────────────────────────

    def _select_all(self):
        for var in self._dlc_vars.values():
            var.set(True)

    def _deselect_all(self):
        for var in self._dlc_vars.values():
            var.set(False)

    # ── Pack Actions ──────────────────────────────────────────────

    def _on_pack_selected(self):
        selected = [dlc_id for dlc_id, var in self._dlc_vars.items() if var.get()]
        if not selected:
            self.app.show_toast("No DLCs selected", "warning")
            return
        self._start_pack(selected)

    def _on_pack_all(self):
        all_ids = list(self._dlc_vars.keys())
        if not all_ids:
            self.app.show_toast("No DLCs available to pack", "warning")
            return
        self._start_pack(all_ids)

    def _start_pack(self, dlc_ids: list[str]):
        if self._busy:
            return

        # Estimate total size and check disk space
        import shutil
        estimated_size = sum(self._dlc_sizes.get(d, 0) for d in dlc_ids)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        try:
            free_space = shutil.disk_usage(self._output_dir).free
        except OSError:
            free_space = 0

        if free_space > 0 and estimated_size > free_space:
            answer = tk.messagebox.askyesno(
                "Low Disk Space",
                f"Estimated pack size: {_format_size(estimated_size)}\n"
                f"Available disk space: {_format_size(free_space)}\n\n"
                f"You may run out of space. Continue anyway?",
                parent=self,
            )
            if not answer:
                return
        elif free_space > 0 and estimated_size > free_space * 0.9:
            # Warn if packing would use more than 90% of remaining space
            self.app.show_toast(
                f"Warning: packing will use ~{_format_size(estimated_size)} "
                f"of {_format_size(free_space)} free",
                "warning",
            )

        # Check which zips already exist
        catalog = self._packer._catalog
        existing = []
        for dlc_id in dlc_ids:
            dlc = catalog.get_by_id(dlc_id)
            if dlc and self._packer.get_zip_path(dlc, self._output_dir).is_file():
                existing.append(dlc_id)

        if existing:
            names = ", ".join(existing)
            answer = tk.messagebox.askyesnocancel(
                "Overwrite Existing?",
                f"The following DLC zips already exist:\n{names}\n\n"
                "Yes = Overwrite existing\n"
                "No = Skip existing, pack the rest\n"
                "Cancel = Abort",
                parent=self,
            )
            if answer is None:
                # Cancel
                return
            if not answer:
                # No — skip existing
                dlc_ids = [d for d in dlc_ids if d not in existing]
                if not dlc_ids:
                    self.app.show_toast("All selected DLCs already packed", "success")
                    return

        self._busy = True
        self._set_buttons_state("disabled")
        self._progress_bar.set(0)
        self._status_label.configure(
            text=f"Packing 0/{len(dlc_ids)} DLCs...",
            text_color=theme.COLORS["text_muted"],
        )

        self.app.run_async(
            self._pack_bg, dlc_ids,
            on_done=self._on_pack_done,
            on_error=self._on_pack_error,
        )

    def _pack_bg(self, dlc_ids: list[str]):
        game_dir = self.app.updater.find_game_dir()
        if not game_dir:
            raise RuntimeError("No game directory found")

        game_dir = Path(game_dir)
        catalog = self._packer._catalog

        dlcs = []
        for dlc_id in dlc_ids:
            dlc = catalog.get_by_id(dlc_id)
            if dlc:
                dlcs.append(dlc)

        def progress_cb(idx, total, dlc_id, msg):
            pct = idx / total if total > 0 else 0
            self.app._enqueue_gui(self._update_pack_progress, idx, total, dlc_id, pct)

        results = self._packer.pack_multiple(game_dir, dlcs, self._output_dir, progress_cb)

        # Generate manifest
        if results:
            self._packer.generate_manifest(results, self._output_dir)

        return results

    def _update_pack_progress(self, idx, total, dlc_id, pct):
        self._progress_bar.set(pct)
        if dlc_id:
            self._status_label.configure(text=f"Packing {idx + 1}/{total}: {dlc_id}")
        else:
            self._status_label.configure(text=f"Packing {idx}/{total}...")

    def _on_pack_done(self, results: list[PackResult]):
        self._busy = False
        self._set_buttons_state("normal")
        self._progress_bar.set(1.0)

        if not results:
            self._status_label.configure(text="No DLCs were packed")
            self.app.show_toast("No DLCs were packed", "warning")
            return

        total_size = sum(r.size for r in results)
        self._status_label.configure(
            text=f"Packed {len(results)} DLC(s), {_format_size(total_size)} total. "
                 f"Manifest saved to {self._output_dir}",
        )
        self.app.show_toast(
            f"Packed {len(results)} DLC(s) successfully", "success",
        )

    def _on_pack_error(self, error):
        self._busy = False
        self._set_buttons_state("normal")
        self._progress_bar.set(0)
        self._status_label.configure(
            text=f"Error: {error}",
            text_color=theme.COLORS["error"],
        )
        self.app.show_toast(f"Pack error: {error}", "error")

    # ── Import ────────────────────────────────────────────────────

    def _on_import(self):
        if self._busy:
            return

        file_path = filedialog.askopenfilename(
            title="Select DLC Archive",
            filetypes=[
                ("Archives", "*.zip *.rar"),
                ("ZIP files", "*.zip"),
                ("RAR files", "*.rar"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        game_dir = self.app.updater.find_game_dir()
        if not game_dir:
            self.app.show_toast("No game directory found", "error")
            return

        filename = Path(file_path).name
        confirm = tk.messagebox.askyesno(
            "Import DLC Archive",
            f"Extract \"{filename}\" into:\n{game_dir}\n\nContinue?",
            parent=self,
        )
        if not confirm:
            return

        self._busy = True
        self._set_buttons_state("disabled")
        self._status_label.configure(text=f"Importing {filename}...")
        self._progress_bar.set(0)

        self.app.run_async(
            self._import_bg, file_path, game_dir,
            on_done=self._on_import_done,
            on_error=self._on_import_error,
        )

    def _import_bg(self, archive_path: str, game_dir: str):
        return self._packer.import_archive(Path(archive_path), Path(game_dir))

    def _on_import_done(self, found_dlc_ids: list[str]):
        self._busy = False
        self._set_buttons_state("normal")
        self._progress_bar.set(1.0)

        if not found_dlc_ids:
            self._status_label.configure(text="Import complete (no DLC folders detected)")
            self.app.show_toast("Archive extracted", "success")
            return

        dlc_list = ", ".join(found_dlc_ids)
        self._status_label.configure(text=f"Imported: {dlc_list}")
        self.app.show_toast(f"Imported {len(found_dlc_ids)} DLC(s): {dlc_list}", "success")

        # Ask if user wants to register the DLCs
        register = tk.messagebox.askyesno(
            "Register DLCs",
            f"The following DLCs were extracted:\n{dlc_list}\n\n"
            "Enable them in the crack config?",
            parent=self,
        )
        if register:
            self.app.run_async(
                self._register_bg, found_dlc_ids,
                on_done=lambda _: self.app.show_toast("DLCs registered", "success"),
                on_error=lambda e: self.app.show_toast(f"Registration error: {e}", "error"),
            )

    def _register_bg(self, dlc_ids: list[str]):
        game_dir = self.app.updater.find_game_dir()
        if not game_dir:
            return
        mgr = self.app.updater._dlc_manager
        states = mgr.get_dlc_states(game_dir)
        enabled_set = set()
        for state in states:
            if state.enabled is True:
                enabled_set.add(state.dlc.id)
            elif state.dlc.id in dlc_ids and state.installed:
                enabled_set.add(state.dlc.id)
        mgr.apply_changes(game_dir, enabled_set)

    def _on_import_error(self, error):
        self._busy = False
        self._set_buttons_state("normal")
        self._progress_bar.set(0)
        self._status_label.configure(
            text=f"Import error: {error}",
            text_color=theme.COLORS["error"],
        )
        self.app.show_toast(f"Import failed: {error}", "error")

    # ── Helpers ───────────────────────────────────────────────────

    def _open_output_folder(self):
        """Open the packed DLCs output folder in the system file explorer."""
        import os
        self._output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self._output_dir)

    def _set_buttons_state(self, state: str):
        for btn in (
            self._select_all_btn,
            self._deselect_all_btn,
            self._pack_selected_btn,
            self._pack_all_btn,
            self._import_btn,
        ):
            btn.configure(state=state)
