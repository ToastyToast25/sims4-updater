"""
DLC Downloader tab — parallel download of DLC packs with progress,
speed limiting, and an activity log.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import InfoCard, StatusBadge

if TYPE_CHECKING:
    from ..app import App

from ...dlc.downloader import DLCDownloadState, DLCDownloadTask
from ...patch.manifest import DLCDownloadEntry


# ── helpers ────────────────────────────────────────────────────────

def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.1f} GB"
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.0f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


# DLC pack-type display order
_TYPE_ORDER = ["expansion", "game_pack", "stuff_pack", "kit", "free_pack", "other"]
_TYPE_LABELS = {
    "expansion": "Expansion Packs",
    "game_pack": "Game Packs",
    "stuff_pack": "Stuff Packs",
    "kit": "Kits",
    "free_pack": "Free Packs",
    "other": "Other",
}


class DownloaderFrame(ctk.CTkFrame):
    """Dedicated DLC download tab with parallel downloads, speed control, and log."""

    def __init__(self, parent, app: "App"):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        # State
        self._busy = False
        self._cancel_event = threading.Event()
        self._dlc_downloads: dict[str, DLCDownloadEntry] = {}
        self._installed_ids: set[str] = set()
        self._cached_ids: set[str] = set()
        self._dlc_vars: dict[str, ctk.BooleanVar] = {}
        self._row_widgets: dict[str, dict] = {}
        self._download_thread: threading.Thread | None = None
        self._game_dir: str | None = None
        self._last_progress_time: dict[str, float] = {}
        self._total_to_download = 0
        self._completed_count = 0
        self._failed_count = 0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # scroll area stretches

        self._build_ui()

    # ── UI Construction ───────────────────────────────────────────

    def _build_ui(self):
        # Row 0 — Header + settings
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=theme.SECTION_PAD, pady=(20, 0))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top, text="DLC Downloader",
            font=ctk.CTkFont(*theme.FONT_HEADING),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            top, text="Download and install DLC content packs",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))

        # Settings card
        card = InfoCard(top, fg_color=theme.COLORS["bg_card"])
        card.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text="Parallel Downloads",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, padx=(theme.CARD_PAD_X, 8), pady=(theme.CARD_PAD_Y, 4), sticky="w")

        self._concurrency_var = ctk.StringVar(value=str(self.app.settings.download_concurrency))
        ctk.CTkOptionMenu(
            card,
            values=["1", "2", "3", "4", "5"],
            variable=self._concurrency_var,
            width=70,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            button_color=theme.COLORS["bg_card_alt"],
            button_hover_color=theme.COLORS["card_hover"],
        ).grid(row=0, column=1, padx=0, pady=(theme.CARD_PAD_Y, 4), sticky="w")

        ctk.CTkLabel(
            card, text="Speed Limit",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text"],
        ).grid(row=1, column=0, padx=(theme.CARD_PAD_X, 8), pady=(4, theme.CARD_PAD_Y), sticky="w")

        speed_frame = ctk.CTkFrame(card, fg_color="transparent")
        speed_frame.grid(row=1, column=1, padx=0, pady=(4, theme.CARD_PAD_Y), sticky="w")

        self._speed_var = ctk.StringVar(value=str(self.app.settings.download_speed_limit))
        ctk.CTkEntry(
            speed_frame,
            textvariable=self._speed_var,
            width=70,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            border_color=theme.COLORS["border"],
            placeholder_text="0",
        ).pack(side="left")

        ctk.CTkLabel(
            speed_frame, text="MB/s  (0 = unlimited)",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).pack(side="left", padx=(6, 0))

        # Row 1 — Action bar
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=theme.SECTION_PAD, pady=(8, 4))
        bar.grid_columnconfigure(2, weight=1)

        btn_kw = dict(
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
        )

        self._select_all_btn = ctk.CTkButton(
            bar, text="Select All",
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._select_all,
            **btn_kw,
        )
        self._select_all_btn.grid(row=0, column=0, padx=(0, 4))

        self._deselect_all_btn = ctk.CTkButton(
            bar, text="Deselect All",
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._deselect_all,
            **btn_kw,
        )
        self._deselect_all_btn.grid(row=0, column=1, padx=(0, 4))

        self._download_btn = ctk.CTkButton(
            bar, text="Download Selected",
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_download_selected,
            **btn_kw,
        )
        self._download_btn.grid(row=0, column=3, padx=(4, 0))

        self._cancel_btn = ctk.CTkButton(
            bar, text="Cancel",
            fg_color=theme.COLORS["error"],
            hover_color="#cc3a47",
            command=self._on_cancel,
            **btn_kw,
        )
        self._cancel_btn.grid(row=0, column=4, padx=(4, 0))
        self._cancel_btn.grid_remove()  # hidden until downloading

        # Row 2 — Scrollable DLC list
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color=theme.COLORS["bg_dark"],
            corner_radius=theme.CORNER_RADIUS,
            border_width=1,
            border_color=theme.COLORS["border"],
        )
        self._scroll_frame.grid(
            row=2, column=0, sticky="nsew",
            padx=theme.SECTION_PAD, pady=(4, 4),
        )
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        # Placeholder labels
        self._no_manifest_label = ctk.CTkLabel(
            self._scroll_frame,
            text="Configure a manifest URL in Settings to see available DLCs.",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        )
        self._loading_label = ctk.CTkLabel(
            self._scroll_frame,
            text="Loading DLC list...",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        )
        self._empty_label = ctk.CTkLabel(
            self._scroll_frame,
            text="No DLCs available for download in the manifest.",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        )

        # Row 3 — Overall progress
        prog_frame = ctk.CTkFrame(self, fg_color="transparent")
        prog_frame.grid(row=3, column=0, sticky="ew", padx=theme.SECTION_PAD, pady=(4, 2))
        prog_frame.grid_columnconfigure(0, weight=1)

        self._overall_progress = ctk.CTkProgressBar(
            prog_frame,
            height=6,
            corner_radius=3,
            progress_color=theme.COLORS["accent"],
            fg_color=theme.COLORS["bg_card_alt"],
        )
        self._overall_progress.grid(row=0, column=0, sticky="ew")
        self._overall_progress.set(0)

        self._overall_label = ctk.CTkLabel(
            prog_frame,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._overall_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Row 4 — Activity log
        log_section = ctk.CTkFrame(self, fg_color="transparent")
        log_section.grid(row=4, column=0, sticky="nsew", padx=theme.SECTION_PAD, pady=(2, 12))
        log_section.grid_columnconfigure(0, weight=1)
        log_section.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(4, weight=0, minsize=140)

        header_row = ctk.CTkFrame(log_section, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        header_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_row, text="Activity Log",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header_row, text="Clear", width=50,
            height=theme.BUTTON_HEIGHT_SMALL - 4,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            font=ctk.CTkFont(*theme.FONT_SMALL),
            command=self._clear_log,
        ).grid(row=0, column=1, sticky="e")

        self._log_box = ctk.CTkTextbox(
            log_section,
            font=ctk.CTkFont(*theme.FONT_MONO),
            fg_color=theme.COLORS["bg_deeper"],
            text_color=theme.COLORS["text_muted"],
            corner_radius=theme.CORNER_RADIUS_SMALL,
            state="disabled",
            wrap="word",
            height=120,
        )
        self._log_box.grid(row=1, column=0, sticky="nsew")

    # ── Frame lifecycle ───────────────────────────────────────────

    def on_show(self):
        """Called when frame becomes visible — trigger data load."""
        if not self._busy:
            self._load_data()

    def _load_data(self):
        """Fetch manifest + scan game dir in background."""
        if not self.app.settings.manifest_url:
            self._hide_placeholders()
            self._no_manifest_label.grid(row=0, column=0, pady=40)
            return

        self._hide_placeholders()
        self._loading_label.grid(row=0, column=0, pady=40)
        self.app.run_async(self._scan_bg, on_done=self._on_scan_done, on_error=self._on_scan_error)

    def _scan_bg(self):
        """Background: fetch manifest, get DLC states, detect cached archives."""
        game_dir = self.app.updater.find_game_dir()

        manifest = self.app.updater.patch_client.fetch_manifest()
        dlc_downloads = manifest.dlc_downloads

        # Get installed DLC IDs
        installed_ids: set[str] = set()
        if game_dir:
            states = self.app.updater._dlc_manager.get_dlc_states(game_dir)
            for s in states:
                if s.installed and s.complete:
                    installed_ids.add(s.dlc.id)

        # Detect cached (fully downloaded) archives
        cached_ids: set[str] = set()
        dlcs_dir = self.app.updater._download_dir / "dlcs"
        if dlcs_dir.is_dir():
            existing_files = {f.name for f in dlcs_dir.iterdir() if f.is_file() and f.suffix != ".partial"}
            for dlc_id, entry in dlc_downloads.items():
                fname = entry.filename or entry.url.rsplit("/", 1)[-1].split("?")[0]
                if fname in existing_files:
                    cached_ids.add(dlc_id)

        return dlc_downloads, installed_ids, cached_ids, game_dir

    def _on_scan_done(self, result):
        self._dlc_downloads, self._installed_ids, self._cached_ids, self._game_dir = result
        self._hide_placeholders()

        if not self._dlc_downloads:
            self._empty_label.grid(row=0, column=0, pady=40)
            return

        self._rebuild_rows()

    def _on_scan_error(self, error):
        self._hide_placeholders()
        self._log(f"[{_timestamp()}] Error loading DLC list: {error}")
        self.app.show_toast(f"Failed to load DLC list: {error}", "error")

    def _hide_placeholders(self):
        self._no_manifest_label.grid_remove()
        self._loading_label.grid_remove()
        self._empty_label.grid_remove()

    # ── DLC List Building ─────────────────────────────────────────

    def _rebuild_rows(self):
        """Destroy and recreate all DLC rows."""
        for w in self._scroll_frame.winfo_children():
            if w not in (self._no_manifest_label, self._loading_label, self._empty_label):
                w.destroy()

        self._dlc_vars.clear()
        self._row_widgets.clear()

        catalog = self.app.updater._dlc_manager.catalog

        # Group DLCs by pack type
        grouped: dict[str, list[tuple[str, DLCDownloadEntry]]] = {}
        for dlc_id, entry in self._dlc_downloads.items():
            info = catalog.get_by_id(dlc_id)
            ptype = info.pack_type if info else "other"
            grouped.setdefault(ptype, []).append((dlc_id, entry))

        grid_row = 0
        for ptype in _TYPE_ORDER:
            items = grouped.get(ptype)
            if not items:
                continue

            # Section header
            label_text = _TYPE_LABELS.get(ptype, ptype.upper())
            count_installed = sum(1 for did, _ in items if did in self._installed_ids)
            header = ctk.CTkLabel(
                self._scroll_frame,
                text=f"  {label_text}  ({count_installed}/{len(items)} installed)",
                font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
                text_color=theme.COLORS["text_muted"],
            )
            header.grid(row=grid_row, column=0, sticky="w", pady=(10, 4), padx=4)
            grid_row += 1

            for idx, (dlc_id, entry) in enumerate(sorted(items, key=lambda x: x[0])):
                self._build_dlc_row(dlc_id, entry, grid_row, idx)
                grid_row += 1

        # Update overall label
        avail = len(self._dlc_downloads) - len(self._installed_ids & set(self._dlc_downloads))
        self._overall_label.configure(text=f"{avail} DLC(s) available for download")

    def _build_dlc_row(self, dlc_id: str, entry: DLCDownloadEntry, grid_row: int, idx: int):
        catalog = self.app.updater._dlc_manager.catalog
        info = catalog.get_by_id(dlc_id)
        name = info.name_en if info else dlc_id

        is_installed = dlc_id in self._installed_ids
        is_cached = dlc_id in self._cached_ids

        bg = theme.COLORS["bg_card"] if idx % 2 == 0 else theme.COLORS["bg_card_alt"]

        row_frame = ctk.CTkFrame(
            self._scroll_frame,
            fg_color=bg,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            border_width=1,
            border_color=theme.COLORS["border"],
            height=42,
        )
        row_frame.grid(row=grid_row, column=0, sticky="ew", padx=2, pady=1)
        row_frame.grid_columnconfigure(1, weight=1)

        # Checkbox
        var = ctk.BooleanVar(value=is_installed or is_cached)
        cb = ctk.CTkCheckBox(
            row_frame,
            text=f"{dlc_id} \u2014 {name}",
            variable=var,
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text"],
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            border_color=theme.COLORS["text_muted"],
            checkmark_color=theme.COLORS["text"],
        )
        cb.grid(row=0, column=0, padx=(12, 4), pady=6, sticky="w")

        if is_installed:
            cb.configure(state="disabled")
            var.set(True)

        self._dlc_vars[dlc_id] = var

        # Status badge
        if is_installed:
            badge = StatusBadge(row_frame, text="Installed", style="success")
        elif is_cached:
            badge = StatusBadge(row_frame, text="Cached", style="info")
        else:
            badge = StatusBadge(row_frame, text="Available", style="muted")
        badge.grid(row=0, column=2, padx=4, pady=6)

        # Size label
        size_text = _format_size(entry.size) if entry.size > 0 else ""
        size_lbl = ctk.CTkLabel(
            row_frame, text=size_text,
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_dim"],
            width=60,
        )
        size_lbl.grid(row=0, column=3, padx=(4, 8), pady=6, sticky="e")

        # Per-DLC progress bar (hidden until download starts)
        prog = ctk.CTkProgressBar(
            row_frame,
            height=4, corner_radius=2, width=120,
            progress_color=theme.COLORS["accent"],
            fg_color=theme.COLORS["bg_deeper"],
        )
        prog.set(0)
        prog.grid(row=0, column=4, padx=4, pady=6)
        prog.grid_remove()

        # State/speed label (hidden until download starts)
        state_lbl = ctk.CTkLabel(
            row_frame, text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
            width=90,
        )
        state_lbl.grid(row=0, column=5, padx=(0, 12), pady=6, sticky="e")
        state_lbl.grid_remove()

        self._row_widgets[dlc_id] = {
            "row_frame": row_frame,
            "checkbox": cb,
            "badge": badge,
            "progress_bar": prog,
            "state_label": state_lbl,
        }

    # ── Selection ─────────────────────────────────────────────────

    def _select_all(self):
        for dlc_id, var in self._dlc_vars.items():
            if dlc_id not in self._installed_ids:
                var.set(True)

    def _deselect_all(self):
        for dlc_id, var in self._dlc_vars.items():
            if dlc_id not in self._installed_ids:
                var.set(False)

    # ── Download Orchestration ────────────────────────────────────

    def _on_download_selected(self):
        if self._busy:
            return

        selected = [
            dlc_id for dlc_id, var in self._dlc_vars.items()
            if var.get() and dlc_id not in self._installed_ids
        ]
        if not selected:
            self.app.show_toast("No DLCs selected for download", "warning")
            return

        if not self._game_dir:
            self.app.show_toast("No game directory configured", "error")
            return

        entries = [self._dlc_downloads[d] for d in selected if d in self._dlc_downloads]
        self._start_downloads(entries)

    def _start_downloads(self, entries: list[DLCDownloadEntry]):
        self._busy = True
        self._cancel_event.clear()
        self._set_buttons_state("disabled")
        self._cancel_btn.grid()
        self._cancel_btn.configure(state="normal", text="Cancel")

        self._completed_count = 0
        self._failed_count = 0
        self._total_to_download = len(entries)
        self._last_progress_time.clear()
        self._overall_progress.set(0)

        # Show per-DLC progress UI
        for entry in entries:
            rw = self._row_widgets.get(entry.dlc_id)
            if rw:
                rw["progress_bar"].set(0)
                rw["progress_bar"].grid()
                rw["state_label"].configure(text="Waiting...")
                rw["state_label"].grid()
                rw["badge"].set_status("Pending", "muted")

        self._log(f"[{_timestamp()}] Starting download of {len(entries)} DLC(s)")

        # Save settings
        try:
            self.app.settings.download_concurrency = int(self._concurrency_var.get())
        except ValueError:
            pass
        try:
            self.app.settings.download_speed_limit = int(self._speed_var.get() or "0")
        except ValueError:
            pass
        self.app.settings.save()

        self._download_thread = threading.Thread(
            target=self._download_bg, args=(entries,), daemon=True,
        )
        self._download_thread.start()

    def _download_bg(self, entries: list[DLCDownloadEntry]):
        """Background thread: run parallel downloads."""
        max_workers = int(self._concurrency_var.get() or "3")
        try:
            speed_mb = int(self._speed_var.get() or "0")
        except ValueError:
            speed_mb = 0
        speed_bytes = speed_mb * 1_048_576

        downloader = self.app.updater.create_parallel_dlc_downloader(
            game_dir=self._game_dir,
            max_workers=max_workers,
            speed_limit_bytes=speed_bytes,
        )

        def progress_cb(dlc_id, state, downloaded, total, message):
            # Throttle per-DLC progress updates to avoid GUI flooding
            now = time.monotonic()
            last = self._last_progress_time.get(dlc_id, 0)
            is_state_change = state not in (DLCDownloadState.DOWNLOADING,)
            if is_state_change or (now - last) >= 0.15:
                self._last_progress_time[dlc_id] = now
                self.app._enqueue_gui(
                    self._update_dlc_progress, dlc_id, state, downloaded, total, message,
                )

        try:
            results = downloader.download_parallel(entries, progress=progress_cb)
            self.app._enqueue_gui(self._on_downloads_done, results)
        except Exception as e:
            self.app._enqueue_gui(self._on_downloads_error, e)
        finally:
            downloader.close()

    def _update_dlc_progress(self, dlc_id, state, downloaded, total, message):
        """GUI thread: update a single DLC row's progress."""
        rw = self._row_widgets.get(dlc_id)
        if not rw:
            return

        prog_bar = rw["progress_bar"]
        state_lbl = rw["state_label"]
        badge = rw["badge"]

        if state == DLCDownloadState.DOWNLOADING:
            if total > 0:
                prog_bar.set(downloaded / total)
            dl_text = _format_size(downloaded)
            tot_text = _format_size(total) if total > 0 else "?"
            state_lbl.configure(text=f"{dl_text}/{tot_text}")
            badge.set_status("Downloading", "info")

        elif state == DLCDownloadState.EXTRACTING:
            prog_bar.set(1.0)
            state_lbl.configure(text="Extracting...")
            badge.set_status("Extracting", "warning")
            self._log(f"[{_timestamp()}] Extracting {dlc_id}...")

        elif state == DLCDownloadState.REGISTERING:
            state_lbl.configure(text="Registering...")
            badge.set_status("Registering", "warning")

        elif state == DLCDownloadState.COMPLETED:
            prog_bar.set(1.0)
            state_lbl.configure(text="Done")
            badge.set_status("Installed", "success")
            rw["checkbox"].configure(state="disabled")
            self._completed_count += 1
            self._installed_ids.add(dlc_id)
            self._log(f"[{_timestamp()}] Completed: {dlc_id}")

        elif state == DLCDownloadState.FAILED:
            state_lbl.configure(text="Failed")
            badge.set_status("Failed", "error")
            self._failed_count += 1
            self._log(f"[{_timestamp()}] FAILED: {dlc_id} \u2014 {message}")

        elif state == DLCDownloadState.CANCELLED:
            state_lbl.configure(text="Cancelled")
            badge.set_status("Cancelled", "muted")
            self._log(f"[{_timestamp()}] Cancelled: {dlc_id}")

        elif state == DLCDownloadState.PENDING:
            pass  # handled at start

        # Log first download byte
        if state == DLCDownloadState.DOWNLOADING and downloaded == 0:
            self._log(f"[{_timestamp()}] Downloading {dlc_id}...")

        # Update overall progress
        done = self._completed_count + self._failed_count
        if self._total_to_download > 0:
            self._overall_progress.set(done / self._total_to_download)
        self._overall_label.configure(
            text=f"{done}/{self._total_to_download} processed  "
                 f"({self._completed_count} OK, {self._failed_count} failed)"
        )

    def _on_downloads_done(self, results: list[DLCDownloadTask]):
        self._busy = False
        self._cancel_btn.grid_remove()
        self._set_buttons_state("normal")
        self._overall_progress.set(1.0)

        completed = sum(1 for r in results if r.state == DLCDownloadState.COMPLETED)
        failed = sum(1 for r in results if r.state == DLCDownloadState.FAILED)
        cancelled = sum(1 for r in results if r.state == DLCDownloadState.CANCELLED)

        parts = []
        if completed:
            parts.append(f"{completed} installed")
        if failed:
            parts.append(f"{failed} failed")
        if cancelled:
            parts.append(f"{cancelled} cancelled")
        summary = ", ".join(parts) or "No DLCs processed"

        self._log(f"[{_timestamp()}] Finished: {summary}")

        if failed == 0 and cancelled == 0:
            self.app.show_toast(f"Downloaded {completed} DLC(s) successfully", "success")
        elif cancelled > 0:
            self.app.show_toast(f"Download cancelled. {summary}", "warning")
        else:
            self.app.show_toast(summary, "warning")

    def _on_downloads_error(self, error):
        self._busy = False
        self._cancel_btn.grid_remove()
        self._set_buttons_state("normal")
        self._log(f"[{_timestamp()}] Error: {error}")
        self.app.show_toast(f"Download error: {error}", "error")

    def _on_cancel(self):
        self._cancel_event.set()
        # Also signal through the updater's shared cancel event
        self.app.updater._cancel.set()
        self._cancel_btn.configure(state="disabled", text="Cancelling...")
        self._log(f"[{_timestamp()}] Cancellation requested...")

    # ── Button state management ───────────────────────────────────

    def _set_buttons_state(self, state: str):
        for btn in (
            self._select_all_btn,
            self._deselect_all_btn,
            self._download_btn,
        ):
            btn.configure(state=state)

    # ── Logging ───────────────────────────────────────────────────

    def _log(self, message: str):
        """Append a line to the activity log (must be called on GUI thread)."""
        self._log_box.configure(state="normal")
        self._log_box.insert("end", message + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _enqueue_log(self, msg: str):
        """Thread-safe log append."""
        self.app._enqueue_gui(self._log, msg)

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
