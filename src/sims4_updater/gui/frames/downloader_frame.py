"""
DLC Downloader tab — parallel download of DLC packs with progress,
speed limiting, pause/resume, and an activity log.
"""

from __future__ import annotations

import contextlib
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import InfoCard, StatusBadge

if TYPE_CHECKING:
    from ..app import App

from ...dlc.downloader import (
    DLCDownloadState,
    DLCDownloadTask,
    ParallelDLCDownloader,
)
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


def _format_speed(bps: float) -> str:
    if bps >= 1_048_576:
        return f"{bps / 1_048_576:.1f} MB/s"
    if bps >= 1024:
        return f"{bps / 1024:.0f} KB/s"
    return f"{bps:.0f} B/s"


def _format_eta(seconds: float | None) -> str:
    if seconds is None or seconds <= 0:
        return ""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"ETA {h}h {m}m"
    if m > 0:
        return f"ETA {m}m {s}s"
    return f"ETA {s}s"


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


class _SpeedTracker:
    """Sliding-window speed calculator for download progress."""

    WINDOW = 3.0  # seconds

    def __init__(self) -> None:
        self._samples: list[tuple[float, int]] = []
        self._total_size = 0

    def reset(self, total_size: int = 0) -> None:
        self._samples.clear()
        self._total_size = total_size

    def update(self, cumulative_bytes: int) -> None:
        now = time.monotonic()
        self._samples.append((now, cumulative_bytes))
        cutoff = now - self.WINDOW
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.pop(0)

    @property
    def speed_bps(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        dt = self._samples[-1][0] - self._samples[0][0]
        db = self._samples[-1][1] - self._samples[0][1]
        return db / dt if dt > 0 else 0.0

    @property
    def eta_seconds(self) -> float | None:
        speed = self.speed_bps
        if speed <= 0 or not self._samples:
            return None
        remaining = self._total_size - self._samples[-1][1]
        return max(0, remaining / speed) if remaining > 0 else 0


class DownloaderFrame(ctk.CTkFrame):
    """Dedicated DLC download tab with parallel downloads, speed control, and log."""

    def __init__(self, parent, app: App):
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
        self._extracted_count = 0
        self._active_downloader: ParallelDLCDownloader | None = None
        self._selected_version: str | None = None  # None = latest

        # Speed / timing
        self._overall_tracker = _SpeedTracker()
        self._dlc_bytes: dict[str, int] = {}  # per-DLC cumulative bytes
        self._dlc_start_times: dict[str, float] = {}
        self._download_start_time: float = 0.0
        self._download_entries: list[DLCDownloadEntry] = []
        self._logged_dl_start: set[str] = set()  # DLC IDs already logged "Downloading..."

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
            top,
            text="DLC Downloader",
            font=ctk.CTkFont(*theme.FONT_HEADING),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            top,
            text="Download and install DLC content packs",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))

        # Settings card
        card = InfoCard(top, fg_color=theme.COLORS["bg_card"])
        card.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card,
            text="Parallel Downloads",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text"],
        ).grid(
            row=0,
            column=0,
            padx=(theme.CARD_PAD_X, 8),
            pady=(theme.CARD_PAD_Y, 4),
            sticky="w",
        )

        self._concurrency_var = ctk.StringVar(
            value=str(self.app.settings.download_concurrency),
        )
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
            card,
            text="Speed Limit",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text"],
        ).grid(
            row=1,
            column=0,
            padx=(theme.CARD_PAD_X, 8),
            pady=(4, theme.CARD_PAD_Y),
            sticky="w",
        )

        speed_frame = ctk.CTkFrame(card, fg_color="transparent")
        speed_frame.grid(
            row=1,
            column=1,
            padx=0,
            pady=(4, theme.CARD_PAD_Y),
            sticky="w",
        )

        self._speed_var = ctk.StringVar(
            value=str(self.app.settings.download_speed_limit),
        )
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
            speed_frame,
            text="MB/s  (0 = unlimited)",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).pack(side="left", padx=(6, 0))

        # Content version picker
        ctk.CTkLabel(
            card,
            text="Content Version",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text"],
        ).grid(
            row=2,
            column=0,
            padx=(theme.CARD_PAD_X, 8),
            pady=(4, theme.CARD_PAD_Y),
            sticky="w",
        )

        self._version_var = ctk.StringVar(value="Latest")
        self._version_menu = ctk.CTkOptionMenu(
            card,
            values=["Latest"],
            variable=self._version_var,
            width=220,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            button_color=theme.COLORS["bg_card_alt"],
            button_hover_color=theme.COLORS["card_hover"],
            command=self._on_version_changed,
        )
        self._version_menu.grid(
            row=2,
            column=1,
            padx=0,
            pady=(4, theme.CARD_PAD_Y),
            sticky="w",
        )

        # Row 1 — Action bar
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=theme.SECTION_PAD, pady=(8, 4))
        bar.grid_columnconfigure(2, weight=1)

        btn_kw = dict(
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
        )

        self._select_missing_btn = ctk.CTkButton(
            bar,
            text="Select Missing",
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._select_missing,
            **btn_kw,
        )
        self._select_missing_btn.grid(row=0, column=0, padx=(0, 4))

        self._deselect_all_btn = ctk.CTkButton(
            bar,
            text="Deselect All",
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._deselect_all,
            **btn_kw,
        )
        self._deselect_all_btn.grid(row=0, column=1, padx=(0, 4))

        self._download_btn = ctk.CTkButton(
            bar,
            text="Download Selected",
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_download_selected,
            **btn_kw,
        )
        self._download_btn.grid(row=0, column=3, padx=(4, 0))

        # Pause button (hidden until downloading)
        self._pause_btn = ctk.CTkButton(
            bar,
            text="Pause",
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_pause,
            **btn_kw,
        )
        self._pause_btn.grid(row=0, column=4, padx=(4, 0))
        self._pause_btn.grid_remove()

        # Resume button (hidden until paused)
        self._resume_btn = ctk.CTkButton(
            bar,
            text="Resume",
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_resume,
            **btn_kw,
        )
        self._resume_btn.grid(row=0, column=4, padx=(4, 0))
        self._resume_btn.grid_remove()

        # Cancel button (hidden until downloading)
        self._cancel_btn = ctk.CTkButton(
            bar,
            text="Cancel",
            fg_color=theme.COLORS["error"],
            hover_color="#cc3a47",
            command=self._on_cancel,
            **btn_kw,
        )
        self._cancel_btn.grid(row=0, column=5, padx=(4, 0))
        self._cancel_btn.grid_remove()

        # Row 2 — Scrollable DLC list
        self._scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=theme.COLORS["bg_dark"],
            corner_radius=theme.CORNER_RADIUS,
            border_width=1,
            border_color=theme.COLORS["border"],
        )
        self._scroll_frame.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=theme.SECTION_PAD,
            pady=(4, 4),
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
        prog_frame.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=theme.SECTION_PAD,
            pady=(4, 2),
        )
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
        log_section.grid(
            row=4,
            column=0,
            sticky="nsew",
            padx=theme.SECTION_PAD,
            pady=(2, 12),
        )
        log_section.grid_columnconfigure(0, weight=1)
        log_section.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(4, weight=0, minsize=140)

        header_row = ctk.CTkFrame(log_section, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", pady=(0, 2))
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
            width=50,
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
        self.app.run_async(
            self._scan_bg,
            on_done=self._on_scan_done,
            on_error=self._on_scan_error,
        )

    def _on_version_changed(self, choice: str):
        """Handle version dropdown change — reload DLC list from archived manifest."""
        if choice == "Latest":
            self._selected_version = None
        else:
            # Extract version string (format: "1.121.372.1020 (Feb 2025, 109 DLCs)")
            self._selected_version = choice.split(" (")[0].strip()
        if not self._busy:
            self._load_data()

    def _scan_bg(self):
        """Background: fetch manifest, get DLC states, detect cached archives."""
        game_dir = self.app.updater.find_game_dir()

        client = self.app.updater.patch_client
        # Fetch main manifest first (populates archived_versions)
        main_manifest = client.fetch_manifest()

        # Use archived manifest if a specific version is selected
        if self._selected_version:
            manifest = client.fetch_version_manifest(self._selected_version)
        else:
            manifest = main_manifest

        # Collect available versions for the dropdown
        archived = main_manifest.archived_versions
        version_choices = ["Latest"]
        for ver_str in sorted(
            archived,
            key=lambda v: [int(x) for x in v.split(".")],
            reverse=True,
        ):
            av = archived[ver_str]
            parts = []
            if av.date:
                parts.append(av.date)
            if av.dlc_count:
                parts.append(f"{av.dlc_count} DLCs")
            label = f"{ver_str} ({', '.join(parts)})" if parts else ver_str
            version_choices.append(label)

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
            existing_files = {
                f.name for f in dlcs_dir.iterdir() if f.is_file() and f.suffix != ".partial"
            }
            for dlc_id, entry in dlc_downloads.items():
                fname = entry.filename or entry.url.rsplit("/", 1)[-1].split("?")[0]
                if fname in existing_files:
                    cached_ids.add(dlc_id)

        return dlc_downloads, installed_ids, cached_ids, game_dir, version_choices

    def _on_scan_done(self, result):
        dlc_dl, inst, cached, gdir, ver_choices = result
        self._dlc_downloads = dlc_dl
        self._installed_ids = inst
        self._cached_ids = cached
        self._game_dir = gdir

        # Update version dropdown options
        if ver_choices and len(ver_choices) > 1:
            self._version_menu.configure(values=ver_choices)
        else:
            self._version_menu.configure(values=["Latest"])
        self._hide_placeholders()

        if not self._dlc_downloads:
            self._empty_label.grid(row=0, column=0, pady=40)
            return

        self._rebuild_rows()
        self._select_missing()  # auto-select what needs downloading

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
            if w not in (
                self._no_manifest_label,
                self._loading_label,
                self._empty_label,
            ):
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

        # Update overall label with missing/installed/total counts
        self._update_summary_label()

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
        elif entry.url and entry.size > 0:
            badge = StatusBadge(row_frame, text="On CDN", style="info")
        else:
            badge = StatusBadge(row_frame, text="Not Available", style="muted")
        badge.grid(row=0, column=2, padx=4, pady=6)

        # Size label
        size_text = _format_size(entry.size) if entry.size > 0 else ""
        size_lbl = ctk.CTkLabel(
            row_frame,
            text=size_text,
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_dim"],
            width=60,
        )
        size_lbl.grid(row=0, column=3, padx=(4, 8), pady=6, sticky="e")

        # Per-DLC progress bar (hidden until download starts)
        prog = ctk.CTkProgressBar(
            row_frame,
            height=4,
            corner_radius=2,
            width=120,
            progress_color=theme.COLORS["accent"],
            fg_color=theme.COLORS["bg_deeper"],
        )
        prog.set(0)
        prog.grid(row=0, column=4, padx=4, pady=6)
        prog.grid_remove()

        # State/speed label (hidden until download starts)
        state_lbl = ctk.CTkLabel(
            row_frame,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
            width=130,
        )
        state_lbl.grid(row=0, column=5, padx=(0, 12), pady=6, sticky="e")
        state_lbl.grid_remove()

        self._row_widgets[dlc_id] = {
            "row_frame": row_frame,
            "checkbox": cb,
            "badge": badge,
            "progress_bar": prog,
            "state_label": state_lbl,
            "speed_tracker": _SpeedTracker(),
        }

    # ── Selection ─────────────────────────────────────────────────

    def _select_missing(self):
        """Auto-select only DLCs that are not installed and not cached."""
        for dlc_id, var in self._dlc_vars.items():
            if dlc_id not in self._installed_ids and dlc_id not in self._cached_ids:
                var.set(True)

    def _deselect_all(self):
        for dlc_id, var in self._dlc_vars.items():
            if dlc_id not in self._installed_ids:
                var.set(False)

    def _update_summary_label(self):
        """Update the bottom label with missing/installed/total counts."""
        total = len(self._dlc_downloads)
        installed = len(self._installed_ids & set(self._dlc_downloads))
        missing = total - installed
        self._overall_label.configure(
            text=f"{missing} missing \u00b7 {installed} installed \u00b7 {total} total"
        )

    # ── Download Orchestration ────────────────────────────────────

    def _on_download_selected(self):
        if self._busy:
            return

        selected = [
            dlc_id
            for dlc_id, var in self._dlc_vars.items()
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
        self._pause_btn.grid()
        self._cancel_btn.grid()
        self._cancel_btn.configure(state="normal", text="Cancel")
        self._resume_btn.grid_remove()

        self._completed_count = 0
        self._failed_count = 0
        self._extracted_count = 0
        self._total_to_download = len(entries)
        self._last_progress_time.clear()
        self._overall_progress.set(0)
        self._download_entries = entries
        self._download_start_time = time.monotonic()
        self._dlc_bytes.clear()
        self._dlc_start_times.clear()
        self._logged_dl_start.clear()

        # Reset speed trackers
        total_download_size = sum(e.size for e in entries)
        self._overall_tracker.reset(total_size=total_download_size)

        # Show per-DLC progress UI
        for entry in entries:
            rw = self._row_widgets.get(entry.dlc_id)
            if rw:
                rw["progress_bar"].set(0)
                rw["progress_bar"].grid()
                rw["state_label"].configure(text="Waiting...")
                rw["state_label"].grid()
                rw["badge"].set_status("Pending", "muted")
                rw["speed_tracker"].reset(total_size=entry.size)

        # Build settings description for log
        try:
            workers = int(self._concurrency_var.get())
        except ValueError:
            workers = 3
        try:
            speed_mb = int(self._speed_var.get() or "0")
        except ValueError:
            speed_mb = 0
        speed_desc = f"{speed_mb} MB/s" if speed_mb > 0 else "unlimited"
        self._log(
            f"[{_timestamp()}] Starting download of {len(entries)} DLC(s) "
            f"({workers} workers, {speed_desc})"
        )

        # Save settings
        with contextlib.suppress(ValueError):
            self.app.settings.download_concurrency = int(self._concurrency_var.get())
        with contextlib.suppress(ValueError):
            self.app.settings.download_speed_limit = int(self._speed_var.get() or "0")
        self.app.settings.save()

        self._download_thread = threading.Thread(
            target=self._download_bg,
            args=(entries,),
            daemon=True,
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
        self._active_downloader = downloader

        def progress_cb(dlc_id, state, downloaded, total, message):
            # Throttle per-DLC progress updates to avoid GUI flooding
            now = time.monotonic()
            last = self._last_progress_time.get(dlc_id, 0)
            is_state_change = state not in (DLCDownloadState.DOWNLOADING,)
            if is_state_change or (now - last) >= 0.15:
                self._last_progress_time[dlc_id] = now
                self.app._enqueue_gui(
                    self._update_dlc_progress,
                    dlc_id,
                    state,
                    downloaded,
                    total,
                    message,
                )

        try:
            results = downloader.download_parallel(entries, progress=progress_cb)
            self.app._enqueue_gui(self._on_downloads_done, results)
        except Exception as e:
            self.app._enqueue_gui(self._on_downloads_error, e)
        finally:
            self._active_downloader = None
            downloader.close()

    def _update_dlc_progress(self, dlc_id, state, downloaded, total, message):
        """GUI thread: update a single DLC row's progress."""
        rw = self._row_widgets.get(dlc_id)
        if not rw:
            return

        prog_bar = rw["progress_bar"]
        state_lbl = rw["state_label"]
        badge = rw["badge"]
        tracker = rw["speed_tracker"]

        if state == DLCDownloadState.DOWNLOADING:
            if total > 0:
                prog_bar.set(downloaded / total)

            # Track per-DLC speed
            tracker.update(downloaded)
            self._dlc_bytes[dlc_id] = downloaded

            speed = tracker.speed_bps
            if speed > 0:
                eta = tracker.eta_seconds
                eta_text = _format_eta(eta)
                speed_text = _format_speed(speed)
                state_lbl.configure(text=f"{speed_text}  {eta_text}")
            else:
                dl_text = _format_size(downloaded)
                tot_text = _format_size(total) if total > 0 else "?"
                state_lbl.configure(text=f"{dl_text}/{tot_text}")

            badge.set_status("Downloading", "info")

            # Update overall speed tracker with sum of all DLC bytes
            total_cumulative = sum(self._dlc_bytes.values())
            self._overall_tracker.update(total_cumulative)

        elif state == DLCDownloadState.EXTRACTING:
            prog_bar.set(1.0)
            state_lbl.configure(text="Extracting...")
            badge.set_status("Extracting", "warning")
            self._log(f"[{_timestamp()}] Extracting {dlc_id}...")

        elif state == DLCDownloadState.REGISTERING:
            state_lbl.configure(text="Registering...")
            badge.set_status("Registering", "warning")
            self._log(f"[{_timestamp()}] Registering {dlc_id} in crack config...")

        elif state == DLCDownloadState.COMPLETED:
            prog_bar.set(1.0)
            badge.set_status("Installed", "success")
            rw["checkbox"].configure(state="disabled")
            self._completed_count += 1
            self._installed_ids.add(dlc_id)
            # Record full size for overall progress bar
            entry = self._dlc_downloads.get(dlc_id)
            if entry and entry.size > 0:
                self._dlc_bytes[dlc_id] = entry.size
            # Log with timing
            elapsed = self._dlc_elapsed(dlc_id)
            avg_speed = self._dlc_avg_speed(dlc_id)
            state_lbl.configure(text="Done")
            self._log(f"[{_timestamp()}] Completed {dlc_id} in {elapsed} ({avg_speed})")

        elif state == DLCDownloadState.EXTRACTED:
            prog_bar.set(1.0)
            state_lbl.configure(text="Needs Config")
            badge.set_status("Extracted", "warning")
            self._extracted_count += 1
            entry = self._dlc_downloads.get(dlc_id)
            if entry and entry.size > 0:
                self._dlc_bytes[dlc_id] = entry.size
            elapsed = self._dlc_elapsed(dlc_id)
            self._log(
                f"[{_timestamp()}] WARNING: {dlc_id} extracted but registration "
                f"failed ({elapsed}) \u2014 enable in DLC tab"
            )

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

        # Log download start once per DLC (guard against duplicate callbacks)
        if state == DLCDownloadState.DOWNLOADING and dlc_id not in self._logged_dl_start:
            self._logged_dl_start.add(dlc_id)
            self._dlc_start_times[dlc_id] = time.monotonic()
            catalog = self.app.updater._dlc_manager.catalog
            info = catalog.get_by_id(dlc_id)
            name = info.name_en if info else dlc_id
            entry = self._dlc_downloads.get(dlc_id)
            size_str = _format_size(entry.size) if entry and entry.size > 0 else ""
            size_part = f" ({size_str})" if size_str else ""
            self._log(f"[{_timestamp()}] Downloading {dlc_id} \u2014 {name}{size_part}...")

        # Update overall progress bar using byte-level progress
        total_size = sum(e.size for e in self._download_entries) if self._download_entries else 0
        if total_size > 0:
            self._overall_progress.set(min(1.0, sum(self._dlc_bytes.values()) / total_size))

        done = self._completed_count + self._failed_count + self._extracted_count
        overall_speed = self._overall_tracker.speed_bps
        overall_eta = self._overall_tracker.eta_seconds
        parts = [f"{done}/{self._total_to_download} processed"]
        if overall_speed > 0:
            parts.append(_format_speed(overall_speed))
        if overall_eta is not None and overall_eta > 0:
            parts.append(_format_eta(overall_eta))
        self._overall_label.configure(text=" \u00b7 ".join(parts))

    def _dlc_elapsed(self, dlc_id: str) -> str:
        """Format elapsed time since DLC download started."""
        start = self._dlc_start_times.get(dlc_id)
        if start is None:
            return "?"
        elapsed = time.monotonic() - start
        if elapsed < 60:
            return f"{elapsed:.0f}s"
        m, s = divmod(int(elapsed), 60)
        return f"{m}m {s}s"

    def _dlc_avg_speed(self, dlc_id: str) -> str:
        """Calculate average speed for a completed DLC."""
        start = self._dlc_start_times.get(dlc_id)
        entry = self._dlc_downloads.get(dlc_id)
        if start is None or entry is None or entry.size <= 0:
            return ""
        elapsed = time.monotonic() - start
        if elapsed <= 0:
            return ""
        return f"{_format_speed(entry.size / elapsed)} avg"

    def _on_downloads_done(self, results: list[DLCDownloadTask]):
        self._busy = False
        self._pause_btn.grid_remove()
        self._resume_btn.grid_remove()
        self._cancel_btn.grid_remove()
        self._set_buttons_state("normal")
        self._overall_progress.set(1.0)
        self._active_downloader = None

        completed = sum(1 for r in results if r.state == DLCDownloadState.COMPLETED)
        extracted = sum(1 for r in results if r.state == DLCDownloadState.EXTRACTED)
        failed = sum(1 for r in results if r.state == DLCDownloadState.FAILED)
        cancelled = sum(1 for r in results if r.state == DLCDownloadState.CANCELLED)

        parts = []
        if completed:
            parts.append(f"{completed} installed")
        if extracted:
            parts.append(f"{extracted} extracted")
        if failed:
            parts.append(f"{failed} failed")
        if cancelled:
            parts.append(f"{cancelled} cancelled")
        summary = ", ".join(parts) or "No DLCs processed"

        # Calculate total duration and average speed
        duration = time.monotonic() - self._download_start_time
        total_bytes = sum(
            e.size
            for e in self._download_entries
            if e.dlc_id in self._installed_ids
            or e.dlc_id
            in {r.entry.dlc_id for r in results if r.state == DLCDownloadState.EXTRACTED}
        )
        duration_str = _format_eta(duration).replace("ETA ", "") or f"{duration:.0f}s"
        avg_speed = _format_speed(total_bytes / duration) if duration > 0 else ""

        self._log(f"[{_timestamp()}] Finished: {summary} (total {duration_str})")
        if avg_speed:
            self._log(f"[{_timestamp()}] Average speed: {avg_speed}")

        if failed == 0 and cancelled == 0:
            self.app.show_toast(
                f"Downloaded {completed} DLC(s) successfully",
                "success",
            )
        elif cancelled > 0:
            self.app.show_toast(f"Download cancelled. {summary}", "warning")
        else:
            self.app.show_toast(summary, "warning")

        # Refresh summary counts
        self._update_summary_label()

    def _on_downloads_error(self, error):
        self._busy = False
        self._pause_btn.grid_remove()
        self._resume_btn.grid_remove()
        self._cancel_btn.grid_remove()
        self._set_buttons_state("normal")
        self._active_downloader = None
        self._log(f"[{_timestamp()}] Error: {error}")
        self.app.show_toast(f"Download error: {error}", "error")

    # ── Pause / Resume / Cancel ──────────────────────────────────

    def _on_pause(self):
        dl = self._active_downloader
        if dl:
            dl.pause()
        self._pause_btn.grid_remove()
        self._resume_btn.grid()
        self._log(f"[{_timestamp()}] Downloads paused")

    def _on_resume(self):
        dl = self._active_downloader
        if dl:
            dl.resume()
        self._resume_btn.grid_remove()
        self._pause_btn.grid()
        self._log(f"[{_timestamp()}] Downloads resumed")

    def _on_cancel(self):
        dl = self._active_downloader
        if dl:
            dl.cancel()
        self._cancel_event.set()
        self.app.updater._cancel.set()
        self._cancel_btn.configure(state="disabled", text="Cancelling...")
        self._pause_btn.grid_remove()
        self._resume_btn.grid_remove()
        self._log(f"[{_timestamp()}] Cancellation requested...")

    # ── Button state management ───────────────────────────────────

    def _set_buttons_state(self, state: str):
        for btn in (
            self._select_missing_btn,
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
