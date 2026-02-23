"""
Packer frame — pack DLC folders and language Strings files into distributable
ZIP archives, generate manifest JSON, and import archives into the game directory.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING

import customtkinter as ctk

from ...config import get_app_dir
from ...dlc.packer import DLCPacker
from ...language.packer import LanguagePacker
from .. import theme

if TYPE_CHECKING:
    from ..app import App

_TYPE_ORDER = ["expansion", "game_pack", "stuff_pack", "kit", "free_pack", "other"]
_TYPE_LABELS = {
    "expansion": "Expansion Packs",
    "game_pack": "Game Packs",
    "stuff_pack": "Stuff Packs",
    "kit": "Kits",
    "free_pack": "Free Packs",
    "other": "Other",
}
_TYPE_COLORS = {
    "expansion": "#e94560",
    "game_pack": "#ffa502",
    "stuff_pack": "#2ed573",
    "kit": "#a0a0b0",
    "free_pack": "#70a1ff",
    "other": "#6a6a8a",
}


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
        self._lang_packer = LanguagePacker()

        self._dlc_vars: dict[str, ctk.BooleanVar] = {}
        self._dlc_sizes: dict[str, int] = {}  # dlc_id -> folder size in bytes
        self._all_widgets: list[ctk.CTkFrame] = []  # all dynamically created widgets

        self._lang_vars: dict[str, ctk.BooleanVar] = {}

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
            text="Packer",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Pack DLC and language files into archives for distribution",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))

        # ── Top bar: Select/Deselect + Import + Pack buttons ──
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, padx=30, pady=(0, 5), sticky="ew")
        bar.grid_columnconfigure(3, weight=1)

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
        self._deselect_all_btn.grid(row=0, column=1, padx=(0, 4))

        self._import_btn = ctk.CTkButton(
            bar,
            text="Import Archive...",
            font=ctk.CTkFont(size=11),
            height=theme.BUTTON_HEIGHT_SMALL,
            width=120,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_import,
        )
        self._import_btn.grid(row=0, column=2, padx=(0, 8))

        # Spacer
        ctk.CTkFrame(bar, fg_color="transparent", height=1).grid(row=0, column=3, sticky="ew")

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
        self._pack_selected_btn.grid(row=0, column=4, padx=(0, 4))

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
        self._pack_all_btn.grid(row=0, column=5)

        # ── Scrollable list (DLCs grouped by type + Languages) ──
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

        # ── Progress + Status bar ──
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=3, column=0, padx=30, pady=(8, 12), sticky="ew")
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

        self._output_path_label = ctk.CTkLabel(
            output_row,
            text=self._short_output_path(),
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_dim"],
        )
        self._output_path_label.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            output_row,
            text="Change",
            font=ctk.CTkFont(size=10),
            height=22,
            width=60,
            corner_radius=4,
            fg_color=theme.COLORS["bg_card"],
            hover_color=theme.COLORS["card_hover"],
            command=self._change_output_folder,
        ).pack(side="left", padx=(0, 4))

        self._open_folder_btn = ctk.CTkButton(
            output_row,
            text="Open",
            font=ctk.CTkFont(size=10),
            height=22,
            width=50,
            corner_radius=4,
            fg_color=theme.COLORS["bg_card"],
            hover_color=theme.COLORS["card_hover"],
            command=self._open_output_folder,
        )
        self._open_folder_btn.pack(side="left")

    # ── Lifecycle ─────────────────────────────────────────────────

    def on_show(self):
        self._load_all()

    def _load_all(self):
        self._status_label.configure(text="Scanning installed DLCs and languages...")
        self.app.run_async(
            self._scan_bg,
            on_done=self._on_scan_done,
            on_error=self._on_scan_error,
        )

    def _scan_bg(self):
        game_dir = self.app.updater.find_game_dir()
        if not game_dir:
            return None
        game_path = Path(game_dir)
        dlcs = self._packer.get_installed_dlcs(game_path)
        langs = self._lang_packer.get_installed_packs(game_path)
        return {"dlcs": dlcs, "langs": langs}

    def _on_scan_done(self, results):
        # Clear all dynamic widgets
        for w in self._all_widgets:
            w.destroy()
        self._all_widgets.clear()
        self._dlc_vars.clear()
        self._dlc_sizes.clear()
        self._lang_vars.clear()

        if results is None:
            self._empty_label.grid(row=0, column=0, padx=10, pady=20)
            self._status_label.configure(text="")
            return

        self._empty_label.grid_remove()

        dlcs = results["dlcs"]
        langs = results["langs"]

        # Group DLCs by pack_type
        grouped: dict[str, list[tuple]] = {}
        for dlc, file_count, folder_size in dlcs:
            ptype = dlc.pack_type or "other"
            grouped.setdefault(ptype, []).append((dlc, file_count, folder_size))

        grid_row = 0
        row_idx = 0  # continuous row index for alternating colors

        # ── DLC sections by type ──
        for ptype in _TYPE_ORDER:
            items = grouped.get(ptype)
            if not items:
                continue

            label_text = _TYPE_LABELS.get(ptype, ptype).upper()
            color = _TYPE_COLORS.get(ptype, theme.COLORS["text_muted"])

            hdr = ctk.CTkFrame(self._scroll_frame, fg_color="transparent")
            hdr.grid(
                row=grid_row,
                column=0,
                padx=8,
                pady=(10 if grid_row > 0 else 8, 4),
                sticky="ew",
            )
            ctk.CTkLabel(
                hdr,
                text=f"{label_text} ({len(items)})",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=color,
            ).pack(side="left")
            self._all_widgets.append(hdr)
            grid_row += 1

            for dlc, file_count, folder_size in items:
                self._dlc_sizes[dlc.id] = folder_size
                self._build_dlc_row(grid_row, row_idx, dlc, file_count, folder_size)
                grid_row += 1
                row_idx += 1

        # ── Language Packs section ──
        if langs:
            sep = ctk.CTkFrame(
                self._scroll_frame,
                height=1,
                fg_color=theme.COLORS["separator"],
            )
            sep.grid(row=grid_row, column=0, padx=5, pady=(12, 0), sticky="ew")
            self._all_widgets.append(sep)
            grid_row += 1

            lang_hdr = ctk.CTkFrame(self._scroll_frame, fg_color="transparent")
            lang_hdr.grid(row=grid_row, column=0, padx=8, pady=(8, 4), sticky="ew")
            ctk.CTkLabel(
                lang_hdr,
                text=f"LANGUAGE PACKS ({len(langs)})",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#70a1ff",
            ).pack(side="left")
            self._all_widgets.append(lang_hdr)
            grid_row += 1

            for locale_code, lang_name, pkg_filename, file_size in langs:
                self._build_lang_row(
                    grid_row,
                    row_idx,
                    locale_code,
                    lang_name,
                    pkg_filename,
                    file_size,
                )
                grid_row += 1
                row_idx += 1

        total_dlcs = len(dlcs)
        total_langs = len(langs)
        self._status_label.configure(
            text=f"{total_dlcs} DLC(s) and {total_langs} language pack(s) found"
        )

    def _on_scan_error(self, error):
        self._status_label.configure(
            text=f"Error: {error}",
            text_color=theme.COLORS["error"],
        )

    # ── Row Building ──────────────────────────────────────────────

    def _build_dlc_row(self, grid_row, row_idx, dlc, file_count, folder_size):
        bg = theme.COLORS["bg_card"] if row_idx % 2 == 0 else theme.COLORS["bg_card_alt"]
        row = ctk.CTkFrame(
            self._scroll_frame,
            fg_color=bg,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            border_width=1,
            border_color=theme.COLORS["border"],
        )
        row.grid(row=grid_row, column=0, padx=4, pady=2, sticky="ew")
        row.grid_columnconfigure(2, weight=1)

        var = ctk.BooleanVar(value=True)
        cb = ctk.CTkCheckBox(
            row,
            text=f"{dlc.id} \u2014 {dlc.get_name()}",
            variable=var,
            font=ctk.CTkFont(size=12),
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=4,
        )
        cb.grid(row=0, column=0, padx=(10, 6), pady=6, sticky="w")

        # Pack type pill
        ptype = dlc.pack_type or "other"
        pill_color = _TYPE_COLORS.get(ptype, theme.COLORS["text_dim"])
        short_label = {
            "expansion": "EP",
            "game_pack": "GP",
            "stuff_pack": "SP",
            "kit": "Kit",
            "free_pack": "Free",
        }.get(ptype, "?")
        pill = ctk.CTkLabel(
            row,
            text=short_label,
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=pill_color,
            width=30,
        )
        pill.grid(row=0, column=1, padx=(0, 4), pady=6)

        size_text = f"{file_count} files, {_format_size(folder_size)}"
        ctk.CTkLabel(
            row,
            text=size_text,
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=0, column=3, padx=(0, 12), pady=6, sticky="e")

        self._dlc_vars[dlc.id] = var
        self._all_widgets.append(row)

    def _build_lang_row(
        self,
        grid_row,
        row_idx,
        locale_code,
        lang_name,
        pkg_filename,
        file_size,
    ):
        bg = theme.COLORS["bg_card"] if row_idx % 2 == 0 else theme.COLORS["bg_card_alt"]
        row = ctk.CTkFrame(
            self._scroll_frame,
            fg_color=bg,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            border_width=1,
            border_color=theme.COLORS["border"],
        )
        row.grid(row=grid_row, column=0, padx=4, pady=2, sticky="ew")
        row.grid_columnconfigure(1, weight=1)

        var = ctk.BooleanVar(value=True)
        cb = ctk.CTkCheckBox(
            row,
            text=f"{lang_name}  ({locale_code})",
            variable=var,
            font=ctk.CTkFont(size=12),
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=4,
        )
        cb.grid(row=0, column=0, padx=(10, 0), pady=6, sticky="w", columnspan=2)

        size_text = f"{pkg_filename}, {_format_size(file_size)}"
        ctk.CTkLabel(
            row,
            text=size_text,
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=0, column=2, padx=(0, 12), pady=6, sticky="e")

        self._lang_vars[locale_code] = var
        self._all_widgets.append(row)

    # ── Selection ─────────────────────────────────────────────────

    def _select_all(self):
        for var in self._dlc_vars.values():
            var.set(True)
        for var in self._lang_vars.values():
            var.set(True)

    def _deselect_all(self):
        for var in self._dlc_vars.values():
            var.set(False)
        for var in self._lang_vars.values():
            var.set(False)

    # ── Pack Actions ──────────────────────────────────────────────

    def _on_pack_selected(self):
        selected_dlcs = [did for did, var in self._dlc_vars.items() if var.get()]
        selected_langs = [code for code, var in self._lang_vars.items() if var.get()]
        if not selected_dlcs and not selected_langs:
            self.app.show_toast("Nothing selected", "warning")
            return
        self._start_pack(selected_dlcs, selected_langs)

    def _on_pack_all(self):
        all_dlcs = list(self._dlc_vars.keys())
        all_langs = list(self._lang_vars.keys())
        if not all_dlcs and not all_langs:
            self.app.show_toast("No DLCs or language packs available", "warning")
            return
        self._start_pack(all_dlcs, all_langs)

    def _start_pack(self, dlc_ids: list[str], lang_codes: list[str]):
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
            self.app.show_toast(
                f"Warning: packing will use ~{_format_size(estimated_size)} "
                f"of {_format_size(free_space)} free",
                "warning",
            )

        # Check which DLC zips already exist
        catalog = self._packer._catalog
        existing_dlcs = []
        for dlc_id in dlc_ids:
            dlc = catalog.get_by_id(dlc_id)
            if dlc and self._packer.get_zip_path(dlc, self._output_dir).is_file():
                existing_dlcs.append(dlc_id)

        # Check which language zips already exist
        existing_langs = []
        for code in lang_codes:
            if self._lang_packer.get_zip_path(code, self._output_dir).is_file():
                existing_langs.append(code)

        existing = existing_dlcs + existing_langs
        if existing:
            names = ", ".join(existing)
            answer = tk.messagebox.askyesnocancel(
                "Overwrite Existing?",
                f"The following archives already exist:\n{names}\n\n"
                "Yes = Overwrite existing\n"
                "No = Skip existing, pack the rest\n"
                "Cancel = Abort",
                parent=self,
            )
            if answer is None:
                return
            if not answer:
                dlc_ids = [d for d in dlc_ids if d not in existing_dlcs]
                lang_codes = [c for c in lang_codes if c not in existing_langs]
                if not dlc_ids and not lang_codes:
                    self.app.show_toast("All selected items already packed", "success")
                    return

        total_items = len(dlc_ids) + len(lang_codes)
        self._busy = True
        self._set_buttons_state("disabled")
        self._progress_bar.set(0)
        self._status_label.configure(
            text=f"Packing 0/{total_items} item(s)...",
            text_color=theme.COLORS["text_muted"],
        )

        self.app.run_async(
            self._pack_bg,
            dlc_ids,
            lang_codes,
            on_done=self._on_pack_done,
            on_error=self._on_pack_error,
        )

    def _pack_bg(self, dlc_ids: list[str], lang_codes: list[str]):
        game_dir = self.app.updater.find_game_dir()
        if not game_dir:
            raise RuntimeError("No game directory found")

        game_path = Path(game_dir)
        catalog = self._packer._catalog
        total = len(dlc_ids) + len(lang_codes)

        # Pack DLCs
        dlcs = []
        for dlc_id in dlc_ids:
            dlc = catalog.get_by_id(dlc_id)
            if dlc:
                dlcs.append(dlc)

        def dlc_progress_cb(idx, count, dlc_id, msg):
            pct = idx / total if total > 0 else 0
            self.app._enqueue_gui(
                self._update_pack_progress,
                idx,
                total,
                dlc_id or msg,
                pct,
            )

        dlc_results = self._packer.pack_multiple(
            game_path,
            dlcs,
            self._output_dir,
            dlc_progress_cb,
        )

        # Pack Languages
        offset = len(dlc_ids)

        def lang_progress_cb(idx, count, code, msg):
            pct = (offset + idx) / total if total > 0 else 0
            label = code or msg
            self.app._enqueue_gui(
                self._update_pack_progress,
                offset + idx,
                total,
                label,
                pct,
            )

        lang_results = self._lang_packer.pack_multiple(
            game_path,
            lang_codes,
            self._output_dir,
            lang_progress_cb,
        )

        # Generate manifests
        if dlc_results:
            self._packer.generate_manifest(dlc_results, self._output_dir)
        if lang_results:
            self._lang_packer.generate_manifest(lang_results, self._output_dir)

        return {"dlc_results": dlc_results, "lang_results": lang_results}

    def _update_pack_progress(self, idx, total, label, pct):
        self._progress_bar.set(pct)
        if label:
            self._status_label.configure(text=f"Packing {idx + 1}/{total}: {label}")
        else:
            self._status_label.configure(text=f"Packing {idx}/{total}...")

    def _on_pack_done(self, results):
        self._busy = False
        self._set_buttons_state("normal")
        self._progress_bar.set(1.0)

        dlc_results = results["dlc_results"]
        lang_results = results["lang_results"]
        total_count = len(dlc_results) + len(lang_results)

        if total_count == 0:
            self._status_label.configure(text="Nothing was packed")
            self.app.show_toast("Nothing was packed", "warning")
            return

        total_size = sum(r.size for r in dlc_results) + sum(r.size for r in lang_results)

        parts = []
        if dlc_results:
            parts.append(f"{len(dlc_results)} DLC(s)")
        if lang_results:
            parts.append(f"{len(lang_results)} language pack(s)")

        self._status_label.configure(
            text=f"Packed {', '.join(parts)}, {_format_size(total_size)} total",
        )
        self.app.show_toast(
            f"Packed {', '.join(parts)} successfully",
            "success",
        )
        self.app.telemetry.track_event("dlc_pack", {
            "dlc_count": total_count,
            "total_size_bytes": total_size,
        })

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
            f'Extract "{filename}" into:\n{game_dir}\n\nContinue?',
            parent=self,
        )
        if not confirm:
            return

        self._busy = True
        self._set_buttons_state("disabled")
        self._status_label.configure(text=f"Importing {filename}...")
        self._progress_bar.set(0)

        self.app.run_async(
            self._import_bg,
            file_path,
            game_dir,
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
            self._status_label.configure(
                text="Import complete (no DLC folders detected)",
            )
            self.app.show_toast("Archive extracted", "success")
            return

        self.app.telemetry.track_event("dlc_import", {
            "dlc_count": len(found_dlc_ids),
        })
        dlc_list = ", ".join(found_dlc_ids)
        self._status_label.configure(text=f"Imported: {dlc_list}")
        self.app.show_toast(
            f"Imported {len(found_dlc_ids)} DLC(s): {dlc_list}",
            "success",
        )

        # Ask if user wants to register the DLCs
        register = tk.messagebox.askyesno(
            "Register DLCs",
            f"The following DLCs were extracted:\n{dlc_list}\n\nEnable them in the crack config?",
            parent=self,
        )
        if register:
            self.app.run_async(
                self._register_bg,
                found_dlc_ids,
                on_done=lambda _: self.app.show_toast("DLCs registered", "success"),
                on_error=lambda e: self.app.show_toast(
                    f"Registration error: {e}",
                    "error",
                ),
            )

    def _register_bg(self, dlc_ids: list[str]):
        game_dir = self.app.updater.find_game_dir()
        if not game_dir:
            return
        mgr = self.app.updater._dlc_manager
        states = mgr.get_dlc_states(game_dir)
        enabled_set = set()
        for state in states:
            if state.enabled is True or (state.dlc.id in dlc_ids and state.installed):
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

    def _short_output_path(self) -> str:
        """Truncated output path for display."""
        s = str(self._output_dir)
        if len(s) > 45:
            return "..." + s[-42:]
        return s

    def _change_output_folder(self):
        """Let user choose a different output folder."""
        new_dir = filedialog.askdirectory(
            title="Select Output Folder",
            initialdir=str(self._output_dir),
        )
        if not new_dir:
            return
        self._output_dir = Path(new_dir)
        self._output_path_label.configure(text=self._short_output_path())
        self.app.show_toast("Output folder changed", "info")

    def _open_output_folder(self):
        """Open the output folder in the system file explorer."""
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
