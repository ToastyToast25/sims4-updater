"""Depot Downloader frame — download game versions, batch patch pipeline."""

from __future__ import annotations

import contextlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from tkinter import filedialog
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import InfoCard, LogPanel, StatusBadge

if TYPE_CHECKING:
    from ..app import CDNManagerApp

SIMS4_APP_ID = "1222670"
DEFAULT_DEPOT_ID = "1222671"


def _fmt_size(size_bytes: int | float) -> str:
    """Format bytes into human-readable size string."""
    size_bytes = int(size_bytes)
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.2f} GB"
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def _fmt_eta(seconds: float) -> str:
    """Format seconds into a human-readable ETA string."""
    if seconds <= 0 or seconds > 86400:
        return ""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s:02d}s"
    h, remainder = divmod(int(seconds), 3600)
    m = remainder // 60
    return f"{h}h {m:02d}m"


class DepotFrame(ctk.CTkFrame):
    def __init__(self, parent, app: CDNManagerApp):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._busy = False
        self._cancel_event = Event()
        self._pause_event = Event()
        self._registry: list[dict] = []
        self._registry_rows: dict[str, dict] = {}
        self._pipeline_rows: list[dict] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self,
            text="Depot Downloader",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        ).grid(row=0, column=0, padx=theme.SECTION_PAD, pady=(20, 15), sticky="w")

        # Tabs
        self._tabview = ctk.CTkTabview(
            self,
            fg_color=theme.COLORS["bg_card"],
            segmented_button_fg_color=theme.COLORS["bg_card_alt"],
            segmented_button_selected_color=theme.COLORS["accent"],
            segmented_button_selected_hover_color=theme.COLORS["accent_hover"],
            segmented_button_unselected_color=theme.COLORS["bg_card_alt"],
            segmented_button_unselected_hover_color=theme.COLORS["card_hover"],
        )
        self._tabview.grid(
            row=2,
            column=0,
            padx=theme.SECTION_PAD,
            pady=(0, 4),
            sticky="nsew",
        )

        self._build_download_tab()
        self._build_pipeline_tab()
        self._build_registry_tab()

        # Log
        self._log = LogPanel(self)
        self._log.grid(row=3, column=0, padx=theme.SECTION_PAD, pady=(4, 15), sticky="nsew")

    # ══════════════════════════════════════════════════════════════════════
    # Tab 1: Download (single version)
    # ══════════════════════════════════════════════════════════════════════

    def _build_download_tab(self):
        tab = self._tabview.add("Download")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=1)

        # Left column: Auth + Download Settings
        left = ctk.CTkFrame(tab, fg_color="transparent")
        left.grid(row=0, column=0, padx=(6, 3), pady=6, sticky="nsew")
        left.grid_columnconfigure(1, weight=1)

        # -- Auth Card --
        auth_card = InfoCard(left, fg_color=theme.COLORS["bg_card_alt"])
        auth_card.pack(fill="x", pady=(0, 8))
        auth_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            auth_card,
            text="Steam Authentication",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="w")

        ctk.CTkLabel(auth_card, text="Username:", font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, padx=(12, 6), pady=3, sticky="w"
        )
        self._dl_username = ctk.CTkEntry(auth_card, height=28, font=ctk.CTkFont(size=11))
        self._dl_username.grid(row=1, column=1, padx=(0, 12), pady=3, sticky="ew")

        ctk.CTkLabel(auth_card, text="Password:", font=ctk.CTkFont(size=11)).grid(
            row=2, column=0, padx=(12, 6), pady=(3, 6), sticky="w"
        )
        self._dl_password = ctk.CTkEntry(auth_card, height=28, font=ctk.CTkFont(size=11), show="*")
        self._dl_password.grid(row=2, column=1, padx=(0, 12), pady=(3, 6), sticky="ew")

        ctk.CTkLabel(
            auth_card,
            text="Steam Guard / 2FA will be prompted automatically if needed",
            font=ctk.CTkFont(size=9),
            text_color=theme.COLORS["text_dim"],
        ).grid(row=3, column=0, columnspan=2, padx=12, pady=(0, 10), sticky="w")

        # -- Depot Config Card --
        depot_card = InfoCard(left, fg_color=theme.COLORS["bg_card_alt"])
        depot_card.pack(fill="x", pady=(0, 8))
        depot_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            depot_card,
            text="Depot Configuration",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="w")

        ctk.CTkLabel(depot_card, text="App ID:", font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, padx=(12, 6), pady=3, sticky="w"
        )
        self._dl_app_id = ctk.CTkEntry(depot_card, height=28, font=ctk.CTkFont("Consolas", 11))
        self._dl_app_id.grid(row=1, column=1, padx=(0, 12), pady=3, sticky="ew")
        self._dl_app_id.insert(0, SIMS4_APP_ID)

        ctk.CTkLabel(depot_card, text="Depot ID:", font=ctk.CTkFont(size=11)).grid(
            row=2, column=0, padx=(12, 6), pady=3, sticky="w"
        )
        self._dl_depot_id = ctk.CTkEntry(depot_card, height=28, font=ctk.CTkFont("Consolas", 11))
        self._dl_depot_id.grid(row=2, column=1, padx=(0, 12), pady=3, sticky="ew")
        self._dl_depot_id.insert(0, self.app.config_data.depot_default_depot_id)

        ctk.CTkLabel(depot_card, text="Manifest:", font=ctk.CTkFont(size=11)).grid(
            row=3, column=0, padx=(12, 6), pady=3, sticky="w"
        )
        self._dl_manifest_id = ctk.CTkEntry(
            depot_card,
            height=28,
            font=ctk.CTkFont("Consolas", 11),
            placeholder_text="Paste manifest ID from SteamDB",
        )
        self._dl_manifest_id.grid(row=3, column=1, padx=(0, 12), pady=3, sticky="ew")

        ctk.CTkLabel(depot_card, text="Version:", font=ctk.CTkFont(size=11)).grid(
            row=4, column=0, padx=(12, 6), pady=(3, 10), sticky="w"
        )
        self._dl_version = ctk.CTkEntry(
            depot_card,
            height=28,
            font=ctk.CTkFont("Consolas", 11),
            placeholder_text="e.g. 1.99.305.1020 (auto-detect after download)",
        )
        self._dl_version.grid(row=4, column=1, padx=(0, 12), pady=(3, 10), sticky="ew")

        # Right column: Output + Actions
        right = ctk.CTkFrame(tab, fg_color="transparent")
        right.grid(row=0, column=1, padx=(3, 6), pady=6, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        # -- Output Card --
        out_card = InfoCard(right, fg_color=theme.COLORS["bg_card_alt"])
        out_card.pack(fill="x", pady=(0, 8))
        out_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            out_card,
            text="Output",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="w")

        dir_frame = ctk.CTkFrame(out_card, fg_color="transparent")
        dir_frame.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 6), sticky="ew")
        dir_frame.grid_columnconfigure(0, weight=1)

        self._dl_output_dir = ctk.CTkEntry(
            dir_frame,
            height=28,
            font=ctk.CTkFont(size=11),
            placeholder_text="Download directory...",
        )
        self._dl_output_dir.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        ctk.CTkButton(
            dir_frame,
            text="Browse",
            width=70,
            height=28,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._browse_output_dir,
        ).grid(row=0, column=1)

        self._dl_auto_register = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            out_card,
            text="Auto-register in Version Registry",
            variable=self._dl_auto_register,
            font=ctk.CTkFont(size=11),
            height=20,
            checkbox_width=16,
            checkbox_height=16,
        ).grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 6), sticky="w")

        self._dl_add_to_registry = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            out_card,
            text="Save to Depot Registry",
            variable=self._dl_add_to_registry,
            font=ctk.CTkFont(size=11),
            height=20,
            checkbox_width=16,
            checkbox_height=16,
        ).grid(row=3, column=0, columnspan=2, padx=12, pady=(0, 10), sticky="w")

        # -- Clipboard parse button --
        ctk.CTkButton(
            right,
            text="Paste from Clipboard",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._paste_from_clipboard,
        ).pack(fill="x", pady=(0, 8))

        # -- Action Buttons --
        btn_frame = ctk.CTkFrame(right, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 8))

        self._dl_download_btn = ctk.CTkButton(
            btn_frame,
            text="Download Version",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._start_download,
        )
        self._dl_download_btn.pack(side="left", padx=(0, 6))

        self._dl_install_btn = ctk.CTkButton(
            btn_frame,
            text="Install Tool",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._install_tool,
        )
        self._dl_install_btn.pack(side="left", padx=(0, 6))

        self._dl_cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            command=self._cancel_download,
        )

        # -- Tool status --
        self._dl_tool_badge = StatusBadge(right)
        self._dl_tool_badge.pack(anchor="w", pady=(0, 4))

    # ══════════════════════════════════════════════════════════════════════
    # Tab 2: Batch Pipeline
    # ══════════════════════════════════════════════════════════════════════

    def _build_pipeline_tab(self):
        tab = self._tabview.add("Batch Pipeline")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        # Top: scrollable queue
        self._pipe_scroll = ctk.CTkScrollableFrame(
            tab,
            fg_color=theme.COLORS["bg_dark"],
            corner_radius=theme.CORNER_RADIUS,
            border_width=1,
            border_color=theme.COLORS["border"],
        )
        self._pipe_scroll.grid(row=0, column=0, pady=(6, 4), sticky="nsew")
        for col, w in [(0, 30), (1, 140), (2, 0), (3, 90)]:
            self._pipe_scroll.grid_columnconfigure(col, weight=1 if w == 0 else 0, minsize=w)

        self._pipe_placeholder = ctk.CTkLabel(
            self._pipe_scroll,
            text="No versions queued. Use 'Load Versions' to add from registry or file.",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._pipe_placeholder.grid(row=0, column=0, columnspan=4, pady=30)

        # Options row
        opts = ctk.CTkFrame(tab, fg_color="transparent")
        opts.grid(row=1, column=0, pady=(4, 4), sticky="ew")

        ctk.CTkLabel(opts, text="Direction:", font=ctk.CTkFont(size=11, weight="bold")).pack(
            side="left", padx=(0, 4)
        )

        self._pipe_direction = ctk.StringVar(value="Both")
        for text in ("Forward", "Backward", "Both"):
            ctk.CTkRadioButton(
                opts,
                text=text,
                variable=self._pipe_direction,
                value=text,
                font=ctk.CTkFont(size=11),
                height=20,
                radiobutton_width=16,
                radiobutton_height=16,
            ).pack(side="left", padx=(0, 10))

        # Checkboxes
        checks = ctk.CTkFrame(tab, fg_color="transparent")
        checks.grid(row=2, column=0, pady=(0, 4), sticky="ew")

        self._pipe_skip_existing = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            checks,
            text="Skip existing CDN patches",
            variable=self._pipe_skip_existing,
            font=ctk.CTkFont(size=11),
            height=20,
            checkbox_width=16,
            checkbox_height=16,
        ).pack(side="left", padx=(0, 12))

        self._pipe_auto_upload = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            checks,
            text="Auto-upload to CDN",
            variable=self._pipe_auto_upload,
            font=ctk.CTkFont(size=11),
            height=20,
            checkbox_width=16,
            checkbox_height=16,
        ).pack(side="left", padx=(0, 12))

        self._pipe_auto_manifest = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            checks,
            text="Auto-update manifest",
            variable=self._pipe_auto_manifest,
            font=ctk.CTkFont(size=11),
            height=20,
            checkbox_width=16,
            checkbox_height=16,
        ).pack(side="left", padx=(0, 12))

        self._pipe_cleanup_patches = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            checks,
            text="Delete patches after upload",
            variable=self._pipe_cleanup_patches,
            font=ctk.CTkFont(size=11),
            height=20,
            checkbox_width=16,
            checkbox_height=16,
        ).pack(side="left")

        # Progress section
        self._pipe_progress_frame = ctk.CTkFrame(tab, fg_color="transparent")

        self._pipe_progress_bar = ctk.CTkProgressBar(
            self._pipe_progress_frame,
            height=16,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            progress_color=theme.COLORS["accent"],
        )
        self._pipe_progress_bar.pack(fill="x", pady=(0, 2))
        self._pipe_progress_bar.set(0)

        self._pipe_progress_label = ctk.CTkLabel(
            self._pipe_progress_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=theme.COLORS["text_muted"],
        )
        self._pipe_progress_label.pack(anchor="w")

        self._pipe_speed_label = ctk.CTkLabel(
            self._pipe_progress_frame,
            text="",
            font=ctk.CTkFont("Consolas", 11),
            text_color=theme.COLORS["accent"],
        )
        self._pipe_speed_label.pack(anchor="w")

        self._pipe_upload_label = ctk.CTkLabel(
            self._pipe_progress_frame,
            text="",
            font=ctk.CTkFont("Consolas", 11),
            text_color=theme.COLORS["success"],
        )
        self._pipe_upload_label.pack(anchor="w")

        # Buttons
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=4, column=0, pady=(4, 6), sticky="ew")

        self._pipe_load_btn = ctk.CTkButton(
            btn_frame,
            text="Load Versions...",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._load_pipeline_versions,
        )
        self._pipe_load_btn.pack(side="left", padx=(0, 6))

        self._pipe_start_btn = ctk.CTkButton(
            btn_frame,
            text="Start Pipeline",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._start_pipeline,
        )
        self._pipe_start_btn.pack(side="left", padx=(0, 6))

        self._pipe_pause_btn = ctk.CTkButton(
            btn_frame,
            text="Pause",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["warning"],
            hover_color="#e6a817",
            command=self._toggle_pause_pipeline,
        )

        self._pipe_cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            command=self._cancel_pipeline,
        )

    # ══════════════════════════════════════════════════════════════════════
    # Tab 3: Depot Registry
    # ══════════════════════════════════════════════════════════════════════

    def _build_registry_tab(self):
        tab = self._tabview.add("Depot Registry")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(3, weight=1)  # table row gets all extra space

        self._filter_text = ""
        self._select_all_var = ctk.BooleanVar(value=False)

        # -- SteamDB row --
        steamdb_frame = ctk.CTkFrame(tab, fg_color="transparent")
        steamdb_frame.grid(row=0, column=0, pady=(6, 2), sticky="ew")

        ctk.CTkLabel(
            steamdb_frame,
            text="SteamDB:",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="left", padx=(0, 6))

        # Dynamic bundled count
        from ..backend.steamdb import load_bundled_manifests

        bundled = load_bundled_manifests()
        bundled_count = len(bundled)

        self._load_bundled_btn = ctk.CTkButton(
            steamdb_frame,
            text=f"Load Bundled ({bundled_count})",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._load_bundled_manifests,
        )
        self._load_bundled_btn.pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            steamdb_frame,
            text="Fetch Live",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._fetch_steamdb,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            steamdb_frame,
            text="Open SteamDB",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._open_steamdb,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            steamdb_frame,
            text="Import Clipboard",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._import_clipboard_manifests,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            steamdb_frame,
            text="Copy JS Snippet",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._copy_js_snippet,
        ).pack(side="left")

        self._reg_status = ctk.CTkLabel(
            steamdb_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_dim"],
        )
        self._reg_status.pack(side="right", padx=(8, 0))

        # -- Data management row --
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=1, column=0, pady=(2, 4), sticky="ew")

        ctk.CTkButton(
            btn_frame,
            text="Add Entry",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._add_registry_entry,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            btn_frame,
            text="Import JSON",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._import_registry,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            btn_frame,
            text="Remove Selected",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            command=self._remove_registry_entries,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            btn_frame,
            text="Export",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._export_registry,
        ).pack(side="left")

        self._reg_count_label = ctk.CTkLabel(
            btn_frame,
            text="0 entries",
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_dim"],
        )
        self._reg_count_label.pack(side="right", padx=(8, 0))

        # -- Search bar --
        self._reg_search = ctk.CTkEntry(
            tab,
            height=28,
            font=ctk.CTkFont(size=11),
            placeholder_text="Search by date, manifest ID...",
            fg_color=theme.COLORS["bg_dark"],
            border_color=theme.COLORS["border"],
        )
        self._reg_search.grid(row=2, column=0, pady=(0, 4), sticky="ew")
        self._reg_search.bind("<KeyRelease>", lambda _: self._filter_registry())

        # -- Registry table --
        self._reg_scroll = ctk.CTkScrollableFrame(
            tab,
            fg_color=theme.COLORS["bg_dark"],
            corner_radius=theme.CORNER_RADIUS,
            border_width=1,
            border_color=theme.COLORS["border"],
        )
        self._reg_scroll.grid(row=3, column=0, pady=(0, 6), sticky="nsew")
        # Columns: checkbox, date, depot, manifest_id, date_added, status
        for col, w in [(0, 30), (1, 100), (2, 60), (3, 0), (4, 90), (5, 110)]:
            self._reg_scroll.grid_columnconfigure(col, weight=1 if w == 0 else 0, minsize=w)

        self._reg_placeholder = ctk.CTkLabel(
            self._reg_scroll,
            text=(
                "No depot manifests registered.\n"
                "Click 'Load Bundled' to import manifests from SteamDB,\n"
                "or 'Add Entry' to add one manually."
            ),
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._reg_placeholder.grid(row=0, column=0, columnspan=6, pady=30)

        # Context menu
        self._reg_context_menu = self._build_registry_context_menu()

    # ══════════════════════════════════════════════════════════════════════
    # Lifecycle
    # ══════════════════════════════════════════════════════════════════════

    def on_show(self):
        self._load_registry()
        self._update_tool_status()
        # Pre-fill username from config
        if self.app.config_data.steam_username and not self._dl_username.get():
            self._dl_username.insert(0, self.app.config_data.steam_username)
        # Pre-fill output dir from config
        if self.app.config_data.depot_download_dir and not self._dl_output_dir.get():
            self._dl_output_dir.insert(0, self.app.config_data.depot_download_dir)

    # ══════════════════════════════════════════════════════════════════════
    # Download Tab Actions
    # ══════════════════════════════════════════════════════════════════════

    def _browse_output_dir(self):
        path = filedialog.askdirectory(title="Select Download Directory")
        if path:
            self._dl_output_dir.delete(0, "end")
            self._dl_output_dir.insert(0, path)

    def _paste_from_clipboard(self):
        """Parse DepotDownloader args from clipboard."""
        try:
            text = self.clipboard_get()
        except Exception:
            self.app.show_toast("Nothing on clipboard", "warning")
            return

        import re

        app_match = re.search(r"-app\s+(\d+)", text)
        depot_match = re.search(r"-depot\s+(\d+)", text)
        manifest_match = re.search(r"-manifest\s+(\d+)", text)

        filled = 0
        if app_match:
            self._dl_app_id.delete(0, "end")
            self._dl_app_id.insert(0, app_match.group(1))
            filled += 1
        if depot_match:
            self._dl_depot_id.delete(0, "end")
            self._dl_depot_id.insert(0, depot_match.group(1))
            filled += 1
        if manifest_match:
            self._dl_manifest_id.delete(0, "end")
            self._dl_manifest_id.insert(0, manifest_match.group(1))
            filled += 1

        if filled:
            self.app.show_toast(f"Filled {filled} field(s) from clipboard", "success")
        else:
            self.app.show_toast("No -app/-depot/-manifest found in clipboard", "warning")

    def _update_tool_status(self):
        from ..backend.depot_ops import DepotDownloader
        from ..config import CONFIG_DIR

        tool_dir = CONFIG_DIR / "tools" / "DepotDownloader"
        dl = DepotDownloader(tool_dir)
        if dl.is_tool_installed():
            self._dl_tool_badge.set_status("Tool Installed", "success")
            self._dl_install_btn.configure(state="disabled")
        else:
            self._dl_tool_badge.set_status("Tool Not Installed", "warning")
            self._dl_install_btn.configure(state="normal")

    def _install_tool(self):
        if self._busy:
            return
        self._busy = True
        self._dl_install_btn.configure(state="disabled")
        self._log.log("Installing DepotDownloader...")

        def _bg():
            from ..backend.depot_ops import DepotDownloader
            from ..config import CONFIG_DIR

            tool_dir = CONFIG_DIR / "tools" / "DepotDownloader"
            dl = DepotDownloader(tool_dir)

            def log(msg, level="info"):
                self.app._enqueue_gui(self._log.log, msg, level)

            return dl.install_tool(log=log)

        def _done(success):
            self._busy = False
            self._update_tool_status()
            if success:
                self.app.show_toast("DepotDownloader installed", "success")
            else:
                self.app.show_toast("Installation failed", "error")

        self.app.run_async(
            _bg,
            on_done=_done,
            on_error=lambda e: (
                setattr(self, "_busy", False),
                self._log.log(f"Install error: {e}", "error"),
            ),
        )

    def _start_download(self):
        if self._busy:
            self.app.show_toast("Operation in progress", "warning")
            return

        username = self._dl_username.get().strip()
        manifest_id = self._dl_manifest_id.get().strip()
        output_dir = self._dl_output_dir.get().strip()

        if not username:
            self.app.show_toast("Enter Steam username", "warning")
            return
        if not manifest_id:
            self.app.show_toast("Enter manifest ID", "warning")
            return
        if not output_dir:
            self.app.show_toast("Select output directory", "warning")
            return

        # Save username for next time
        self.app.config_data.steam_username = username
        self.app.config_data.depot_download_dir = output_dir

        version = self._dl_version.get().strip() or f"manifest-{manifest_id[:8]}"
        version_dir = Path(output_dir) / version

        self._busy = True
        self._cancel_event.clear()
        self._dl_download_btn.configure(state="disabled")
        self._dl_cancel_btn.pack(side="left", padx=(0, 6))
        self._log.log(f"Starting download: manifest {manifest_id[:16]}...")

        Thread(
            target=self._bg_download,
            args=(
                username,
                self._dl_password.get(),
                self._dl_app_id.get().strip(),
                self._dl_depot_id.get().strip(),
                manifest_id,
                version_dir,
                version,
            ),
            daemon=True,
        ).start()

    def _bg_download(
        self,
        username,
        password,
        app_id,
        depot_id,
        manifest_id,
        version_dir,
        version,
    ):
        from ..backend.depot_ops import DepotDownloader
        from ..config import CONFIG_DIR

        tool_dir = CONFIG_DIR / "tools" / "DepotDownloader"
        dl = DepotDownloader(tool_dir, cancel_event=self._cancel_event)

        def log(msg, level="info"):
            self.app._enqueue_gui(self._log.log, msg, level)

        result = dl.download_version(
            username=username,
            password=password or None,
            auth_code=None,
            app_id=app_id,
            depot_id=depot_id,
            manifest_id=manifest_id,
            output_dir=version_dir,
            log=log,
            ask_password=self._ask_password_dialog,
            ask_auth_code=self._ask_auth_code_dialog,
        )

        # Auto-detect actual game version if version looks like a manifest ID
        if result.success and version.replace("-", "").isdigit():
            try:
                from ..backend.patch_ops import detect_version_fingerprint

                detected, confidence = detect_version_fingerprint(str(version_dir))
                if detected and confidence >= 0.5:
                    log(f"Detected version: {detected} (was {version})", "success")
                    version = detected
                else:
                    # Fingerprint failed — try bundled SteamDB manifest lookup
                    from ..backend.steamdb import load_bundled_manifests

                    raw_id = version.removeprefix("manifest-")
                    for m in load_bundled_manifests():
                        if m.version and (
                            m.manifest_id == raw_id
                            or m.manifest_id.startswith(raw_id)
                            or m.manifest_id == manifest_id
                        ):
                            log(
                                f"Resolved version from SteamDB: {m.version} (was {version})",
                                "success",
                            )
                            version = m.version
                            break
                    else:
                        log(
                            f"Could not auto-detect version for {version} "
                            "(no fingerprint or SteamDB data)",
                            "warning",
                        )
            except Exception as e:
                log(f"Version detection failed: {e}", "warning")

        def finish():
            self._busy = False
            self._dl_download_btn.configure(state="normal")
            self._dl_cancel_btn.pack_forget()

            if result.success:
                self.app.show_toast("Download completed", "success")

                # Save to depot registry
                if self._dl_add_to_registry.get():
                    self._save_to_depot_registry(version, depot_id, manifest_id, str(version_dir))

                # Auto-register in version registry
                if self._dl_auto_register.get():
                    self._log.log(f"Auto-registering {version} in version registry...")
                    self.app.run_async(
                        self._bg_auto_register,
                        str(version_dir),
                        version,
                        on_done=lambda _: self._log.log(f"Registered {version}", "success"),
                        on_error=lambda e: self._log.log(f"Registration failed: {e}", "warning"),
                    )
            else:
                if not self._cancel_event.is_set():
                    self.app.show_toast(f"Download failed: {result.error}", "error")

        self.app._enqueue_gui(finish)

    def _bg_auto_register(self, directory: str, version: str):
        from ..backend.patch_ops import register_version
        from ..config import CONFIG_FILE

        registry = []
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            registry = data.get("version_registry", [])
        except Exception:
            data = {}

        register_version(directory, version, registry)

        # Re-read to avoid clobbering concurrent changes, fallback to current data
        with contextlib.suppress(Exception):
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        data["version_registry"] = registry
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _cancel_download(self):
        self._cancel_event.set()
        self._log.log("Cancellation requested...", "warning")
        self._dl_cancel_btn.configure(state="disabled")

    # -- Interactive Auth Dialogs (thread-safe) ----------------------------

    def _ask_password_dialog(self) -> str | None:
        """Show a password dialog on the GUI thread, block until answered."""
        return self._show_input_dialog(
            title="Steam Password",
            prompt="Enter your Steam password:",
            show="*",
        )

    def _ask_auth_code_dialog(self) -> str | None:
        """Show a 2FA dialog on the GUI thread, block until answered."""
        return self._show_input_dialog(
            title="Steam Guard Code",
            prompt="Enter the Steam Guard / 2FA code\nsent to your email or authenticator app:",
            show="",
        )

    def _show_input_dialog(self, title: str, prompt: str, show: str = "") -> str | None:
        """Thread-safe: schedule a dialog on the GUI thread, block until user responds."""
        result: list[str | None] = [None]
        done = Event()

        def _open():
            dialog = ctk.CTkInputDialog(
                text=prompt,
                title=title,
            )
            if show:
                # Mask input for passwords
                with contextlib.suppress(Exception):
                    for widget in dialog.winfo_children():
                        if isinstance(widget, ctk.CTkEntry):
                            widget.configure(show=show)
            value = dialog.get_input()
            result[0] = value if value else None
            done.set()

        self.app._enqueue_gui(_open)
        done.wait(timeout=300)  # 5 min max wait
        return result[0]

    # ══════════════════════════════════════════════════════════════════════
    # Pipeline Tab Actions
    # ══════════════════════════════════════════════════════════════════════

    def _load_pipeline_versions(self):
        """Load versions from depot registry into the pipeline queue."""
        if not self._registry:
            self.app.show_toast("Depot registry is empty", "warning")
            return

        self._pipeline_rows.clear()
        for widget in self._pipe_scroll.winfo_children():
            widget.destroy()

        # Header
        for col, text in enumerate(["", "Version", "Manifest ID", "Status"]):
            ctk.CTkLabel(
                self._pipe_scroll,
                text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=col, padx=4, pady=(4, 6), sticky="w")

        for i, entry in enumerate(self._registry):
            row = i + 1
            var = ctk.BooleanVar(value=True)

            ctk.CTkCheckBox(
                self._pipe_scroll,
                text="",
                variable=var,
                width=20,
                height=20,
                checkbox_width=16,
                checkbox_height=16,
            ).grid(row=row, column=0, padx=4, pady=2)

            ctk.CTkLabel(
                self._pipe_scroll,
                text=entry.get("version", ""),
                font=ctk.CTkFont("Consolas", 11),
            ).grid(row=row, column=1, padx=4, pady=2, sticky="w")

            mid = entry.get("manifest_id", "")
            display_mid = mid[:20] + "..." if len(mid) > 20 else mid
            ctk.CTkLabel(
                self._pipe_scroll,
                text=display_mid,
                font=ctk.CTkFont("Consolas", 10),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=2, padx=4, pady=2, sticky="w")

            badge = StatusBadge(self._pipe_scroll)
            badge.set_status("Queued", "muted")
            badge.grid(row=row, column=3, padx=4, pady=2, sticky="e")

            self._pipeline_rows.append(
                {
                    "var": var,
                    "entry": entry,
                    "badge": badge,
                }
            )

        self._log.log(f"Loaded {len(self._registry)} versions into pipeline queue")

    def _start_pipeline(self):
        if self._busy:
            self.app.show_toast("Operation in progress", "warning")
            return

        # Collect selected versions
        selected = [r["entry"] for r in self._pipeline_rows if r["var"].get()]
        if not selected:
            self.app.show_toast("No versions selected", "warning")
            return

        username = self._dl_username.get().strip()
        if not username:
            self.app.show_toast("Enter Steam username in Download tab first", "warning")
            return

        versions = [e["version"] for e in selected]
        manifest_ids = {e["version"]: e["manifest_id"] for e in selected}

        self._busy = True
        self._cancel_event.clear()
        self._pause_event.clear()
        self._pipe_start_btn.configure(state="disabled")
        self._pipe_load_btn.configure(state="disabled")
        self._pipe_pause_btn.pack(side="left", padx=(0, 6))
        self._pipe_cancel_btn.pack(side="left", padx=(0, 6))

        # Show progress
        self._pipe_progress_frame.grid(row=3, column=0, padx=0, pady=(4, 0), sticky="ew")
        self._pipe_progress_bar.set(0)
        self._pipe_progress_label.configure(text="Starting pipeline...")
        self._pipe_speed_label.configure(text="")
        self._pipe_upload_label.configure(text="")

        download_dir = self._dl_output_dir.get().strip()
        if not download_dir:
            download_dir = str(Path.home() / "Sims4Versions")

        self._log.log(
            f"Starting batch pipeline: {len(versions)} versions, "
            f"direction={self._pipe_direction.get().lower()}",
            "info",
        )

        Thread(
            target=self._bg_pipeline,
            args=(
                versions,
                manifest_ids,
                username,
                self._dl_password.get() or None,
                self._dl_depot_id.get().strip(),
                download_dir,
            ),
            daemon=True,
        ).start()

    def _bg_pipeline(
        self,
        versions,
        manifest_ids,
        username,
        password,
        depot_id,
        download_dir,
    ):
        from ..backend.depot_ops import BatchPipeline, DepotDownloader
        from ..config import CONFIG_DIR

        tool_dir = CONFIG_DIR / "tools" / "DepotDownloader"
        dl = DepotDownloader(tool_dir, cancel_event=self._cancel_event)

        def log(msg, level="info"):
            self.app._enqueue_gui(self._log.log, msg, level)

        last_phase = [""]

        def progress(phase, current, total):
            if total <= 0:
                return
            if phase == "Uploading":
                # Upload progress goes to the dedicated upload label (from worker thread)
                self.app._enqueue_gui(
                    lambda c=current, t=total: self._pipe_upload_label.configure(
                        text=f"Uploading: {c}/{t}"
                    )
                )
            else:
                pct = current / total
                self.app._enqueue_gui(self._pipe_progress_bar.set, pct)
                self.app._enqueue_gui(
                    lambda p=phase, c=current, t=total: self._pipe_progress_label.configure(
                        text=f"{p}: {c}/{t}"
                    )
                )
                # Reset speed tracking when switching phases
                if phase != last_phase[0]:
                    last_phase[0] = phase
                    dl_samples.clear()
                    self.app._enqueue_gui(lambda: self._pipe_speed_label.configure(text=""))

        def on_version_status(version, status):
            self.app._enqueue_gui(self._update_pipeline_badge, version, status)

        # -- Live download progress tracking (rolling window for ETA) --
        dl_samples: list[tuple[float, float]] = []  # (time, pct)

        def on_download_progress(pct: float, detail: str):
            now = time.monotonic()
            # Clear stale samples when a new download starts (pct drops)
            if dl_samples and pct < dl_samples[-1][1] - 5:
                dl_samples.clear()
            dl_samples.append((now, pct))
            # Keep only last 10 samples
            if len(dl_samples) > 10:
                dl_samples.pop(0)

            # Compute rate from rolling window
            eta_text = ""
            if len(dl_samples) >= 2:
                dt = dl_samples[-1][0] - dl_samples[0][0]
                dp = dl_samples[-1][1] - dl_samples[0][1]
                if dt > 0.5 and dp > 0:
                    rate = dp / dt  # %/sec
                    remaining = 100.0 - pct
                    eta_secs = remaining / rate
                    eta_text = f"ETA: {_fmt_eta(eta_secs)}"

            # Truncate file name for display
            file_name = detail.strip()
            # Strip the percentage prefix (e.g. "  45.23% path/file")
            m = re.match(r"\s*\d+\.?\d*%\s*(.*)", file_name)
            if m:
                file_name = m.group(1)
            if len(file_name) > 50:
                file_name = "..." + file_name[-47:]

            parts = [f"{pct:.1f}%"]
            if eta_text:
                parts.append(eta_text)
            if file_name:
                parts.append(file_name)
            speed_text = " \u2014 ".join(parts)

            self.app._enqueue_gui(lambda s=speed_text: self._pipe_speed_label.configure(text=s))
            # Also update the sub-progress bar within the current item
            if pct > 0:
                self.app._enqueue_gui(self._pipe_progress_bar.set, min(pct / 100.0, 1.0))

        # -- Live upload progress tracking (rolling window for speed) --
        ul_samples: list[tuple[float, int]] = []  # (time, bytes_sent)

        def on_upload_progress(sent_bytes: int, total_bytes: int):
            now = time.monotonic()
            # Clear stale samples when a new upload starts (bytes drop)
            if ul_samples and sent_bytes < ul_samples[-1][1]:
                ul_samples.clear()
            ul_samples.append((now, sent_bytes))
            if len(ul_samples) > 10:
                ul_samples.pop(0)

            pct = (sent_bytes / total_bytes * 100) if total_bytes > 0 else 0

            # Compute speed from rolling window
            speed_text = ""
            if len(ul_samples) >= 2:
                dt = ul_samples[-1][0] - ul_samples[0][0]
                db = ul_samples[-1][1] - ul_samples[0][1]
                if dt > 0.3:
                    speed_bps = db / dt
                    speed_text = f"{_fmt_size(speed_bps)}/s"
                    remaining_bytes = total_bytes - sent_bytes
                    if speed_bps > 0:
                        eta_secs = remaining_bytes / speed_bps
                        speed_text += f" \u2014 ETA: {_fmt_eta(eta_secs)}"

            parts = [
                f"{pct:.1f}%",
                f"{_fmt_size(sent_bytes)} / {_fmt_size(total_bytes)}",
            ]
            if speed_text:
                parts.append(speed_text)
            label = " \u2014 ".join(parts)

            self.app._enqueue_gui(lambda s=label: self._pipe_upload_label.configure(text=s))

        pipeline = BatchPipeline(
            downloader=dl,
            config_dir=CONFIG_DIR,
            cancel_event=self._cancel_event,
            log=log,
            progress=progress,
            pause_event=self._pause_event,
            on_version_status=on_version_status,
            on_download_progress=on_download_progress,
            on_upload_progress=on_upload_progress,
        )

        try:
            result = pipeline.run(
                versions=versions,
                manifest_ids=manifest_ids,
                steam_username=username,
                steam_password=password,
                steam_auth_code=None,
                depot_id=depot_id,
                download_base_dir=Path(download_dir),
                direction=self._pipe_direction.get().lower(),
                skip_existing=self._pipe_skip_existing.get(),
                auto_upload=self._pipe_auto_upload.get(),
                auto_manifest=self._pipe_auto_manifest.get(),
                ask_password=self._ask_password_dialog,
                ask_auth_code=self._ask_auth_code_dialog,
                patcher_dir=self.app.config_data.patcher_dir,
                cleanup_patches=self._pipe_cleanup_patches.get(),
            )
        except Exception as exc:
            import traceback

            tb = traceback.format_exc()
            err_msg = str(exc)
            log(f"Pipeline crashed: {err_msg}", "error")
            log(tb, "error")

            def finish_error(msg=err_msg):
                self._busy = False
                self._pipe_start_btn.configure(state="normal")
                self._pipe_load_btn.configure(state="normal")
                self._pipe_pause_btn.pack_forget()
                self._pipe_cancel_btn.pack_forget()
                self._pipe_progress_frame.grid_forget()
                self._pipe_upload_label.configure(text="")
                self.app.show_toast(f"Pipeline error: {msg}", "error")

            self.app._enqueue_gui(finish_error)
            return

        def finish():
            self._busy = False
            self._pipe_start_btn.configure(state="normal")
            self._pipe_load_btn.configure(state="normal")
            self._pipe_pause_btn.pack_forget()
            self._pipe_cancel_btn.pack_forget()
            self._pipe_progress_frame.grid_forget()
            self._pipe_upload_label.configure(text="")

            if result.cancelled:
                self._log.log("Pipeline cancelled", "warning")
                self.app.show_toast("Pipeline cancelled", "warning")
            elif result.errors:
                self._log.log(f"Pipeline finished with {len(result.errors)} error(s)", "warning")
                self.app.show_toast(
                    f"Pipeline done: {result.patches_uploaded} uploaded, "
                    f"{len(result.errors)} errors",
                    "warning",
                )
            else:
                self._log.log(
                    f"Pipeline complete: {result.downloads} downloaded, "
                    f"{result.patches_created} patches, "
                    f"{result.patches_uploaded} uploaded",
                    "success",
                )
                self.app.show_toast("Pipeline completed successfully", "success")

        self.app._enqueue_gui(finish)

    def _toggle_pause_pipeline(self):
        if self._pause_event.is_set():
            # Currently paused → resume
            self._pause_event.clear()
            self._pipe_pause_btn.configure(text="Pause", fg_color=theme.COLORS["warning"])
            self._log.log("Resuming pipeline...", "info")
        else:
            # Currently running → pause
            self._pause_event.set()
            self._pipe_pause_btn.configure(text="Resume", fg_color=theme.COLORS["accent"])
            self._log.log("Pausing pipeline after current item...", "warning")

    def _cancel_pipeline(self):
        self._cancel_event.set()
        self._pause_event.clear()  # Unpause so cancel can take effect
        self._log.log("Pipeline cancellation requested...", "warning")
        self._pipe_cancel_btn.configure(state="disabled")
        self._pipe_pause_btn.configure(state="disabled")

    def _update_pipeline_badge(self, version: str, status: str):
        """Update the pipeline row badge for a given version."""
        status_map = {
            "downloading": ("Downloading", "info"),
            "done": ("Done", "success"),
            "failed": ("Failed", "error"),
            "patching": ("Patching", "info"),
            "uploading": ("Uploading", "info"),
        }
        label, style = status_map.get(status, (status.title(), "muted"))
        for row in self._pipeline_rows:
            if row["entry"].get("version") == version:
                row["badge"].set_status(label, style)
                break

    # ══════════════════════════════════════════════════════════════════════
    # Registry Tab Actions — SteamDB
    # ══════════════════════════════════════════════════════════════════════

    def _load_bundled_manifests(self):
        """Load the bundled SteamDB manifest database into the registry."""
        from ..backend.steamdb import load_bundled_manifests

        manifests = load_bundled_manifests()
        if not manifests:
            self.app.show_toast("Bundled manifest database not found", "error")
            return

        existing_mids = {e["manifest_id"] for e in self._registry}
        added = 0
        for m in manifests:
            if m.manifest_id not in existing_mids:
                self._registry.append(
                    {
                        "version": m.version or m.date or f"manifest-{m.manifest_id[:8]}",
                        "depot_id": m.depot_id,
                        "manifest_id": m.manifest_id,
                        "date_added": m.date,
                        "download_dir": "",
                        "downloaded": False,
                    }
                )
                existing_mids.add(m.manifest_id)
                added += 1

        if added:
            self._save_registry()
            self._refresh_registry_ui()
            self._log.log(f"Loaded {added} manifests from bundled database", "success")
            self.app.show_toast(f"Added {added} manifests", "success")
        else:
            self.app.show_toast("All bundled manifests already in registry", "info")

        self._reg_status.configure(text=f"{len(self._registry)} entries")

    def _fetch_steamdb(self):
        """Attempt live HTTP scrape of SteamDB (best-effort)."""
        if self._busy:
            self.app.show_toast("Operation in progress", "warning")
            return

        self._busy = True
        self._reg_status.configure(text="Fetching...")
        self._log.log("Attempting SteamDB live scrape (may be blocked by Cloudflare)...")

        def _bg():
            from ..backend.steamdb import scrape_steamdb_manifests

            return scrape_steamdb_manifests(DEFAULT_DEPOT_ID)

        def _done(result):
            self._busy = False
            manifests, error = result
            if error:
                self._reg_status.configure(text="Fetch failed")
                self._log.log(f"SteamDB: {error}", "warning")
                self.app.show_toast("SteamDB fetch failed — try clipboard import", "warning")
                return

            existing_mids = {e["manifest_id"] for e in self._registry}
            added = 0
            for m in manifests:
                if m.manifest_id not in existing_mids:
                    self._registry.append(
                        {
                            "version": m.version or m.date or f"manifest-{m.manifest_id[:8]}",
                            "depot_id": m.depot_id,
                            "manifest_id": m.manifest_id,
                            "date_added": m.date,
                            "download_dir": "",
                            "downloaded": False,
                        }
                    )
                    existing_mids.add(m.manifest_id)
                    added += 1

            if added:
                self._save_registry()
                self._refresh_registry_ui()

            self._reg_status.configure(text=f"{len(self._registry)} entries")
            self._log.log(f"SteamDB: fetched {len(manifests)} manifests, {added} new", "success")
            self.app.show_toast(f"Fetched {len(manifests)}, added {added} new", "success")

        self.app.run_async(
            _bg,
            on_done=_done,
            on_error=lambda e: (
                setattr(self, "_busy", False),
                self._reg_status.configure(text="Fetch error"),
                self._log.log(f"SteamDB fetch error: {e}", "error"),
            ),
        )

    def _open_steamdb(self):
        """Open the SteamDB depot manifests page in the system browser."""
        import webbrowser

        depot_id = self.app.config_data.depot_default_depot_id or DEFAULT_DEPOT_ID
        url = f"https://steamdb.info/depot/{depot_id}/manifests/"
        webbrowser.open(url)
        self._log.log(f"Opened {url}")

    def _import_clipboard_manifests(self):
        """Parse manifest data from clipboard (JSON, DepotDownloader, plain IDs)."""
        try:
            text = self.clipboard_get()
        except Exception:
            self.app.show_toast("Nothing on clipboard", "warning")
            return

        if not text or not text.strip():
            self.app.show_toast("Clipboard is empty", "warning")
            return

        from ..backend.steamdb import parse_clipboard_text

        manifests = parse_clipboard_text(text)
        if not manifests:
            self.app.show_toast("No manifest IDs found in clipboard data", "warning")
            self._log.log("Clipboard parse: no manifests found", "warning")
            return

        existing_mids = {e["manifest_id"] for e in self._registry}
        added = 0
        for m in manifests:
            if m.manifest_id not in existing_mids:
                self._registry.append(
                    {
                        "version": m.version or m.date or f"manifest-{m.manifest_id[:8]}",
                        "depot_id": m.depot_id,
                        "manifest_id": m.manifest_id,
                        "date_added": m.date or datetime.now().strftime("%Y-%m-%d"),
                        "download_dir": "",
                        "downloaded": False,
                    }
                )
                existing_mids.add(m.manifest_id)
                added += 1

        if added:
            self._save_registry()
            self._refresh_registry_ui()
            self._log.log(
                f"Imported {added} manifests from clipboard "
                f"({len(manifests)} parsed, {len(manifests) - added} duplicates)",
                "success",
            )
            self.app.show_toast(f"Imported {added} manifests from clipboard", "success")
        else:
            self.app.show_toast("All clipboard manifests already in registry", "info")

        self._reg_status.configure(text=f"{len(self._registry)} entries")

    def _copy_js_snippet(self):
        """Copy the SteamDB browser console JS snippet to clipboard."""
        from ..backend.steamdb import STEAMDB_JS_SNIPPET

        self.clipboard_clear()
        self.clipboard_append(STEAMDB_JS_SNIPPET)
        self.app.show_toast("JS snippet copied — paste in SteamDB browser console", "success")
        self._log.log(
            "Copied JS snippet to clipboard. Open SteamDB depot page, "
            "press F12 → Console, paste and press Enter.",
        )

    # ══════════════════════════════════════════════════════════════════════
    # Registry Tab Actions — Data Management
    # ══════════════════════════════════════════════════════════════════════

    def _load_registry(self):
        from ..backend.depot_ops import load_depot_registry
        from ..config import CONFIG_FILE

        raw = load_depot_registry(CONFIG_FILE)
        self._registry = [
            {
                "version": e.version,
                "depot_id": e.depot_id,
                "manifest_id": e.manifest_id,
                "date_added": e.date_added,
                "download_dir": e.download_dir,
                "downloaded": e.downloaded,
            }
            for e in raw
        ]
        self._refresh_registry_ui()

    def _save_registry(self):
        from ..backend.depot_ops import DepotManifestEntry, save_depot_registry
        from ..config import CONFIG_FILE

        entries = [
            DepotManifestEntry(
                version=e["version"],
                depot_id=e.get("depot_id", DEFAULT_DEPOT_ID),
                manifest_id=e["manifest_id"],
                date_added=e.get("date_added", ""),
                download_dir=e.get("download_dir", ""),
                downloaded=e.get("downloaded", False),
            )
            for e in self._registry
        ]
        save_depot_registry(CONFIG_FILE, entries)
        # Sync in-memory config
        self.app.config_data.depot_manifest_registry = list(self._registry)

    def _filter_registry(self):
        """Update filter text and refresh the registry table."""
        self._filter_text = self._reg_search.get().strip().lower()
        self._refresh_registry_ui()

    def _get_filtered_entries(self) -> list[dict]:
        """Return registry entries matching the current search filter."""
        if not self._filter_text:
            return list(self._registry)
        return [
            e
            for e in self._registry
            if self._filter_text in e.get("version", "").lower()
            or self._filter_text in e.get("manifest_id", "").lower()
            or self._filter_text in e.get("date_added", "").lower()
            or self._filter_text in e.get("depot_id", "").lower()
        ]

    def _toggle_select_all(self):
        """Toggle all visible entry checkboxes to match Select All state."""
        state = self._select_all_var.get()
        for row_data in self._registry_rows.values():
            row_data["var"].set(state)
        self._update_selection_count()

    def _on_entry_select(self):
        """Called when any individual entry checkbox changes."""
        self._update_selection_count()
        # Sync select-all state
        if not self._registry_rows:
            return
        all_checked = all(r["var"].get() for r in self._registry_rows.values())
        none_checked = not any(r["var"].get() for r in self._registry_rows.values())
        if all_checked:
            self._select_all_var.set(True)
        elif none_checked:
            self._select_all_var.set(False)

    def _update_selection_count(self):
        """Update the count label with selection info."""
        total = len(self._registry)
        visible = len(self._registry_rows)
        selected = sum(1 for r in self._registry_rows.values() if r["var"].get())
        if selected > 0:
            if self._filter_text:
                self._reg_count_label.configure(
                    text=f"{selected} selected / {visible} of {total} entries"
                )
            else:
                self._reg_count_label.configure(text=f"{selected} selected / {total} entries")
        elif self._filter_text:
            self._reg_count_label.configure(text=f"{visible} of {total} entries")
        else:
            self._reg_count_label.configure(text=f"{total} entries")

    def _copy_manifest_id(self, manifest_id: str):
        """Copy a manifest ID to clipboard."""
        self.clipboard_clear()
        self.clipboard_append(manifest_id)
        self.app.show_toast("Manifest ID copied", "success")

    def _show_entry_context_menu(self, event, entry: dict):
        """Show right-click context menu for a registry entry."""
        self._ctx_entry = entry
        self._reg_context_menu.tk_popup(event.x_root, event.y_root)

    def _build_registry_context_menu(self):
        """Create the right-click context menu for registry entries."""
        import tkinter as tk

        menu = tk.Menu(self, tearoff=0, bg="#1a2744", fg="#eaeaea", activebackground="#143a6e")
        menu.add_command(label="Copy Manifest ID", command=self._ctx_copy_manifest)
        menu.add_command(label="Download This Version", command=self._ctx_download_version)
        menu.add_separator()
        menu.add_command(label="Remove", command=self._ctx_remove_entry)
        return menu

    def _ctx_copy_manifest(self):
        if hasattr(self, "_ctx_entry"):
            self._copy_manifest_id(self._ctx_entry.get("manifest_id", ""))

    def _ctx_download_version(self):
        """Fill in Download tab fields and switch to it."""
        if not hasattr(self, "_ctx_entry"):
            return
        entry = self._ctx_entry
        # Fill manifest ID
        self._dl_manifest_id.delete(0, "end")
        self._dl_manifest_id.insert(0, entry.get("manifest_id", ""))
        # Fill version
        self._dl_version.delete(0, "end")
        self._dl_version.insert(0, entry.get("version", ""))
        # Switch to Download tab
        self._tabview.set("Download")
        self.app.show_toast("Fields filled — ready to download", "info")

    def _ctx_remove_entry(self):
        """Remove the right-clicked entry from registry."""
        if not hasattr(self, "_ctx_entry"):
            return
        entry = self._ctx_entry
        self._registry[:] = [e for e in self._registry if e is not entry]
        self._save_registry()
        self._refresh_registry_ui()
        self._log.log(f"Removed entry: {entry.get('version', '')}", "success")

    def _refresh_registry_ui(self):
        for widget in self._reg_scroll.winfo_children():
            widget.destroy()
        self._registry_rows.clear()

        filtered = self._get_filtered_entries()

        if not self._registry:
            self._update_selection_count()
            self._reg_placeholder = ctk.CTkLabel(
                self._reg_scroll,
                text=(
                    "No depot manifests registered.\n"
                    "Click 'Load Bundled' to import manifests from SteamDB,\n"
                    "or 'Add Entry' to add one manually."
                ),
                font=ctk.CTkFont(*theme.FONT_SMALL),
                text_color=theme.COLORS["text_muted"],
            )
            self._reg_placeholder.grid(row=0, column=0, columnspan=6, pady=30)
            return

        if not filtered:
            self._update_selection_count()
            ctk.CTkLabel(
                self._reg_scroll,
                text="No entries match your search.",
                font=ctk.CTkFont(*theme.FONT_SMALL),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=0, columnspan=6, pady=30)
            return

        # Header row — Select All checkbox + column labels
        self._select_all_var.set(False)
        ctk.CTkCheckBox(
            self._reg_scroll,
            text="",
            variable=self._select_all_var,
            command=self._toggle_select_all,
            width=20,
            height=20,
            checkbox_width=16,
            checkbox_height=16,
        ).grid(row=0, column=0, padx=4, pady=(4, 6))

        for col, text in [
            (1, "Date"),
            (2, "Depot"),
            (3, "Manifest ID"),
            (4, "Added"),
            (5, "Status"),
        ]:
            ctk.CTkLabel(
                self._reg_scroll,
                text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=col, padx=4, pady=(4, 6), sticky="w")

        for i, entry in enumerate(filtered):
            row = i + 1
            version = entry["version"]

            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(
                self._reg_scroll,
                text="",
                variable=var,
                command=self._on_entry_select,
                width=20,
                height=20,
                checkbox_width=16,
                checkbox_height=16,
            ).grid(row=row, column=0, padx=4, pady=2)

            # Date / version label
            ctk.CTkLabel(
                self._reg_scroll,
                text=version,
                font=ctk.CTkFont("Consolas", 11),
            ).grid(row=row, column=1, padx=4, pady=2, sticky="w")

            # Depot ID
            ctk.CTkLabel(
                self._reg_scroll,
                text=entry.get("depot_id", DEFAULT_DEPOT_ID),
                font=ctk.CTkFont("Consolas", 10),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=2, padx=4, pady=2, sticky="w")

            # Manifest ID — full, click-to-copy
            mid = entry.get("manifest_id", "")
            mid_label = ctk.CTkLabel(
                self._reg_scroll,
                text=mid,
                font=ctk.CTkFont("Consolas", 10),
                text_color=theme.COLORS["text_muted"],
                cursor="hand2",
            )
            mid_label.grid(row=row, column=3, padx=4, pady=2, sticky="w")
            mid_label.bind("<Button-1>", lambda _, m=mid: self._copy_manifest_id(m))
            mid_label.bind("<Button-3>", lambda e, ent=entry: self._show_entry_context_menu(e, ent))

            # Date added
            ctk.CTkLabel(
                self._reg_scroll,
                text=entry.get("date_added", ""),
                font=ctk.CTkFont(size=10),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=4, padx=4, pady=2, sticky="w")

            # Status badge
            badge = StatusBadge(self._reg_scroll)
            if entry.get("downloaded"):
                badge.set_status("Downloaded", "success")
            else:
                badge.set_status("Not DL'd", "muted")
            badge.grid(row=row, column=5, padx=4, pady=2, sticky="e")

            # Right-click on any cell in this row
            for col_idx in range(5):
                widgets = self._reg_scroll.grid_slaves(row=row, column=col_idx)
                for w in widgets:
                    if not isinstance(w, ctk.CTkCheckBox):
                        w.bind(
                            "<Button-3>",
                            lambda e, ent=entry: self._show_entry_context_menu(e, ent),
                        )

            self._registry_rows[version] = {"var": var, "entry": entry}

        self._update_selection_count()

    def _add_registry_entry(self):
        dialog = _AddDepotEntryDialog(self)
        self.wait_window(dialog)
        if not dialog.version or not dialog.manifest_id:
            return

        # Check for duplicate
        for e in self._registry:
            if e["version"] == dialog.version:
                self.app.show_toast(f"Version {dialog.version} already exists", "warning")
                return

        self._registry.append(
            {
                "version": dialog.version,
                "depot_id": dialog.depot_id,
                "manifest_id": dialog.manifest_id,
                "date_added": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "download_dir": "",
                "downloaded": False,
            }
        )
        self._save_registry()
        self._refresh_registry_ui()
        self._log.log(f"Added depot entry: {dialog.version}", "success")

    def _remove_registry_entries(self):
        selected = [v for v, r in self._registry_rows.items() if r["var"].get()]
        if not selected:
            self.app.show_toast("No entries selected", "warning")
            return

        self._registry[:] = [e for e in self._registry if e["version"] not in selected]
        self._save_registry()
        self._refresh_registry_ui()
        self._log.log(f"Removed {len(selected)} entry/entries", "success")

    def _import_registry(self):
        """Import depot manifest entries from a JSON file."""
        path = filedialog.askopenfilename(
            title="Import Depot Registry",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            entries = data if isinstance(data, list) else data.get("entries", [])
            added = 0
            existing_versions = {e["version"] for e in self._registry}

            for item in entries:
                if not isinstance(item, dict):
                    continue
                version = item.get("version", "")
                manifest_id = item.get("manifest_id", "")
                if version and manifest_id and version not in existing_versions:
                    self._registry.append(
                        {
                            "version": version,
                            "depot_id": item.get("depot_id", DEFAULT_DEPOT_ID),
                            "manifest_id": manifest_id,
                            "date_added": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "download_dir": "",
                            "downloaded": False,
                        }
                    )
                    existing_versions.add(version)
                    added += 1

            self._save_registry()
            self._refresh_registry_ui()
            self._log.log(f"Imported {added} entries from {Path(path).name}", "success")
            self.app.show_toast(f"Imported {added} entries", "success")
        except Exception as e:
            self._log.log(f"Import failed: {e}", "error")
            self.app.show_toast("Import failed", "error")

    def _export_registry(self):
        if not self._registry:
            self.app.show_toast("Nothing to export", "warning")
            return

        path = filedialog.asksaveasfilename(
            title="Export Depot Registry",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile="depot_registry.json",
        )
        if not path:
            return

        try:
            Path(path).write_text(
                json.dumps(self._registry, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._log.log(f"Exported {len(self._registry)} entries", "success")
            self.app.show_toast("Registry exported", "success")
        except Exception as e:
            self._log.log(f"Export failed: {e}", "error")

    def _save_to_depot_registry(
        self, version: str, depot_id: str, manifest_id: str, download_dir: str
    ):
        """Add a download result to the depot registry."""
        for e in self._registry:
            if e["version"] == version:
                e["download_dir"] = download_dir
                e["downloaded"] = True
                self._save_registry()
                self._refresh_registry_ui()
                return

        self._registry.append(
            {
                "version": version,
                "depot_id": depot_id,
                "manifest_id": manifest_id,
                "date_added": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "download_dir": download_dir,
                "downloaded": True,
            }
        )
        self._save_registry()
        self._refresh_registry_ui()
        self._log.log(f"Saved {version} to depot registry", "success")


# -- Dialogs ------------------------------------------------------------------


class _AddDepotEntryDialog(ctk.CTkToplevel):
    """Dialog to add a depot manifest entry."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add Depot Entry")
        self.geometry("480x220")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.version: str = ""
        self.depot_id: str = DEFAULT_DEPOT_ID
        self.manifest_id: str = ""

        self.configure(fg_color=theme.COLORS["bg_card"])
        self.grid_columnconfigure(1, weight=1)

        # Version
        ctk.CTkLabel(
            self,
            text="Version:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, padx=(20, 6), pady=(20, 4), sticky="w")

        self._ver_entry = ctk.CTkEntry(
            self,
            height=32,
            font=ctk.CTkFont("Consolas", 12),
            placeholder_text="e.g. 1.99.305.1020",
        )
        self._ver_entry.grid(row=0, column=1, padx=(0, 20), pady=(20, 4), sticky="ew")

        # Depot ID
        ctk.CTkLabel(
            self,
            text="Depot ID:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=1, column=0, padx=(20, 6), pady=4, sticky="w")

        self._depot_entry = ctk.CTkEntry(
            self,
            height=32,
            font=ctk.CTkFont("Consolas", 12),
        )
        self._depot_entry.grid(row=1, column=1, padx=(0, 20), pady=4, sticky="ew")
        self._depot_entry.insert(0, DEFAULT_DEPOT_ID)

        # Manifest ID
        ctk.CTkLabel(
            self,
            text="Manifest ID:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=2, column=0, padx=(20, 6), pady=4, sticky="w")

        self._manifest_entry = ctk.CTkEntry(
            self,
            height=32,
            font=ctk.CTkFont("Consolas", 12),
            placeholder_text="19-digit numeric ID from SteamDB",
        )
        self._manifest_entry.grid(row=2, column=1, padx=(0, 20), pady=4, sticky="ew")
        self._manifest_entry.bind("<Return>", lambda _: self._ok())

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2, padx=20, pady=(12, 15), sticky="ew")

        ctk.CTkButton(
            btn_frame,
            text="Add",
            width=80,
            height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._ok,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=80,
            height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self.destroy,
        ).pack(side="right")

    def _ok(self):
        version = self._ver_entry.get().strip()
        manifest_id = self._manifest_entry.get().strip()
        depot_id = self._depot_entry.get().strip()
        if version and manifest_id:
            self.version = version
            self.manifest_id = manifest_id
            self.depot_id = depot_id or DEFAULT_DEPOT_ID
            self.destroy()
