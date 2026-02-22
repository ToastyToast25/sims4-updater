"""
Home frame — version display, update button, quick status.

Shows patch-pending banners when a new game version exists but
patches aren't available yet, and new DLC notifications.
Also checks for updater self-updates from GitHub Releases.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import InfoCard, StatusBadge, get_animator

if TYPE_CHECKING:
    from ..app import App


class HomeFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._last_update_info = None
        self._app_update_info = None
        self._self_updating = False
        self._entrance_played = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)  # scrollable content expands

        # Layout:
        #   Row 0 = scrollable content (weight=1)
        #   Row 1 = buttons (pinned to bottom, always visible)

        # ── Scrollable content area ──
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=theme.COLORS["separator"],
            scrollbar_button_hover_color=theme.COLORS["accent"],
        )
        self._scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self._scroll.grid_columnconfigure(0, weight=1)

        # ── App update banner (hidden by default) ──
        self._app_update_frame = ctk.CTkFrame(
            self._scroll, corner_radius=8, fg_color=theme.COLORS["accent"],
        )

        # -- Info row: label + button (shown before download starts)
        self._app_update_inner = ctk.CTkFrame(
            self._app_update_frame, fg_color="transparent",
        )
        self._app_update_inner.pack(fill="x", padx=16, pady=10)

        self._app_update_label = ctk.CTkLabel(
            self._app_update_inner,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff",
            anchor="w",
        )
        self._app_update_label.pack(side="left", fill="x", expand=True)

        self._app_update_btn = ctk.CTkButton(
            self._app_update_inner,
            text="Update Now",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=28,
            width=110,
            corner_radius=6,
            fg_color="#ffffff",
            text_color=theme.COLORS["accent"],
            hover_color="#e0e0e0",
            command=self._on_self_update,
        )
        self._app_update_btn.pack(side="right", padx=(10, 0))

        # -- Download progress row (hidden until download starts)
        self._dl_progress_frame = ctk.CTkFrame(
            self._app_update_frame, fg_color="transparent",
        )

        # Top line: "Downloading v2.0.5..." left, "1.2 MB/s" right
        dl_top = ctk.CTkFrame(self._dl_progress_frame, fg_color="transparent")
        dl_top.pack(fill="x", padx=16, pady=(10, 0))
        dl_top.columnconfigure(1, weight=1)

        self._dl_title_label = ctk.CTkLabel(
            dl_top,
            text="Downloading...",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff",
            anchor="w",
        )
        self._dl_title_label.pack(side="left")

        self._dl_speed_label = ctk.CTkLabel(
            dl_top,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="#b3b3b3",
            anchor="e",
        )
        self._dl_speed_label.pack(side="right")

        # Progress bar
        self._dl_progress_bar = ctk.CTkProgressBar(
            self._dl_progress_frame,
            height=8,
            corner_radius=4,
            progress_color="#ffffff",
            fg_color="#4a1a2a",
        )
        self._dl_progress_bar.pack(fill="x", padx=16, pady=(6, 0))
        self._dl_progress_bar.set(0)

        # Bottom line: "12.5 MB / 21.0 MB" left, "58% — ~12s left" right
        dl_bottom = ctk.CTkFrame(self._dl_progress_frame, fg_color="transparent")
        dl_bottom.pack(fill="x", padx=16, pady=(4, 10))

        self._dl_size_label = ctk.CTkLabel(
            dl_bottom,
            text="0 B / 0 B",
            font=ctk.CTkFont(size=10),
            text_color="#b3b3b3",
            anchor="w",
        )
        self._dl_size_label.pack(side="left")

        self._dl_pct_label = ctk.CTkLabel(
            dl_bottom,
            text="0%",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#ffffff",
            anchor="e",
        )
        self._dl_pct_label.pack(side="right")

        # Download speed tracking state
        self._dl_start_time = 0.0
        self._dl_last_bytes = 0
        self._dl_last_time = 0.0

        # ── Title + Subtitle ──
        title_frame = ctk.CTkFrame(self._scroll, fg_color="transparent")
        title_frame.grid(row=1, column=0, padx=theme.SECTION_PAD, pady=(20, 4), sticky="ew")

        self._title = ctk.CTkLabel(
            title_frame,
            text="The Sims 4 Updater",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        )
        self._title.pack(anchor="w")

        self._subtitle = ctk.CTkLabel(
            title_frame,
            text="Keep your game patched and up to date",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._subtitle.pack(anchor="w", pady=(2, 0))

        # ── Info card (with hover glow) ──
        self._card = InfoCard(self._scroll)
        self._card.grid(row=2, column=0, padx=30, pady=15, sticky="ew")
        self._card.grid_columnconfigure(1, weight=1)

        # Game directory
        ctk.CTkLabel(
            self._card,
            text="Game Directory:",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=0, column=0, padx=theme.CARD_PAD_X, pady=(theme.CARD_PAD_Y, theme.CARD_ROW_PAD), sticky="w")

        self._game_dir_label = ctk.CTkLabel(
            self._card,
            text="Detecting...",
            font=ctk.CTkFont(*theme.FONT_BODY),
            anchor="w",
            cursor="hand2",
        )
        self._game_dir_label.grid(row=0, column=1, padx=theme.CARD_PAD_X, pady=(theme.CARD_PAD_Y, theme.CARD_ROW_PAD), sticky="w")
        self._game_dir_label.bind("<Button-1>", self._open_game_dir)

        # Installed version
        ctk.CTkLabel(
            self._card,
            text="Installed Version:",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=1, column=0, padx=theme.CARD_PAD_X, pady=theme.CARD_ROW_PAD, sticky="w")

        self._version_label = ctk.CTkLabel(
            self._card,
            text="...",
            font=ctk.CTkFont(*theme.FONT_BODY),
            anchor="w",
        )
        self._version_label.grid(row=1, column=1, padx=theme.CARD_PAD_X, pady=theme.CARD_ROW_PAD, sticky="w")

        # Latest patchable version
        ctk.CTkLabel(
            self._card,
            text="Latest Patch:",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=2, column=0, padx=theme.CARD_PAD_X, pady=theme.CARD_ROW_PAD, sticky="w")

        self._latest_label = ctk.CTkLabel(
            self._card,
            text="...",
            font=ctk.CTkFont(*theme.FONT_BODY),
            anchor="w",
        )
        self._latest_label.grid(row=2, column=1, padx=theme.CARD_PAD_X, pady=theme.CARD_ROW_PAD, sticky="w")

        # Game latest (actual EA release) — hidden until check
        self._game_latest_row_label = ctk.CTkLabel(
            self._card,
            text="Game Latest:",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        )
        self._game_latest_label = ctk.CTkLabel(
            self._card,
            text="",
            font=ctk.CTkFont(*theme.FONT_BODY),
            anchor="w",
        )

        # DLC summary
        ctk.CTkLabel(
            self._card,
            text="DLCs:",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=4, column=0, padx=theme.CARD_PAD_X, pady=(theme.CARD_ROW_PAD, theme.CARD_PAD_Y), sticky="w")

        self._dlc_label = ctk.CTkLabel(
            self._card,
            text="...",
            font=ctk.CTkFont(*theme.FONT_BODY),
            anchor="w",
        )
        self._dlc_label.grid(row=4, column=1, padx=theme.CARD_PAD_X, pady=(theme.CARD_ROW_PAD, theme.CARD_PAD_Y), sticky="w")

        # ── Pricing Summary Card (hidden until prices load) ──
        self._pricing_card = InfoCard(self._scroll)
        self._pricing_card.grid_columnconfigure(1, weight=1)
        # Hidden initially — shown by update_pricing_card()

        ctk.CTkLabel(
            self._pricing_card,
            text="DLC Pricing Summary",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=theme.COLORS["accent"],
        ).grid(row=0, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=(theme.CARD_PAD_Y, 6), sticky="w")

        self._price_total_label_key = ctk.CTkLabel(
            self._pricing_card, text="Total DLCs:",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        )
        self._price_total_label_key.grid(row=1, column=0, padx=theme.CARD_PAD_X, pady=2, sticky="w")
        self._price_total_label = ctk.CTkLabel(
            self._pricing_card, text="...",
            font=ctk.CTkFont(*theme.FONT_BODY), anchor="w",
        )
        self._price_total_label.grid(row=1, column=1, padx=theme.CARD_PAD_X, pady=2, sticky="w")

        self._price_patchable_key = ctk.CTkLabel(
            self._pricing_card, text="On CDN:",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        )
        self._price_patchable_label = ctk.CTkLabel(
            self._pricing_card, text="...",
            font=ctk.CTkFont(*theme.FONT_BODY), anchor="w",
        )

        ctk.CTkLabel(
            self._pricing_card, text="Total Original:",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=3, column=0, padx=theme.CARD_PAD_X, pady=2, sticky="w")
        self._price_original_label = ctk.CTkLabel(
            self._pricing_card, text="...",
            font=ctk.CTkFont(*theme.FONT_BODY), anchor="w",
        )
        self._price_original_label.grid(row=3, column=1, padx=theme.CARD_PAD_X, pady=2, sticky="w")

        ctk.CTkLabel(
            self._pricing_card, text="Current Total:",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=4, column=0, padx=theme.CARD_PAD_X, pady=2, sticky="w")
        self._price_current_label = ctk.CTkLabel(
            self._pricing_card, text="...",
            font=ctk.CTkFont(*theme.FONT_BODY), anchor="w",
        )
        self._price_current_label.grid(row=4, column=1, padx=theme.CARD_PAD_X, pady=2, sticky="w")

        ctk.CTkLabel(
            self._pricing_card, text="You Save:",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=5, column=0, padx=theme.CARD_PAD_X, pady=2, sticky="w")
        self._price_savings_label = ctk.CTkLabel(
            self._pricing_card, text="...",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["success"], anchor="w",
        )
        self._price_savings_label.grid(row=5, column=1, padx=theme.CARD_PAD_X, pady=2, sticky="w")

        ctk.CTkLabel(
            self._pricing_card, text="DLCs On Sale:",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=6, column=0, padx=theme.CARD_PAD_X, pady=(2, theme.CARD_PAD_Y), sticky="w")
        self._price_on_sale_label = ctk.CTkLabel(
            self._pricing_card, text="...",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["success"], anchor="w",
        )
        self._price_on_sale_label.grid(row=6, column=1, padx=theme.CARD_PAD_X, pady=(2, theme.CARD_PAD_Y), sticky="w")

        # ── Banner area (patch pending / new DLC notices) ──
        self._banner_frame = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._banner_frame.grid(row=4, column=0, padx=30, pady=0, sticky="ew")
        self._banner_frame.grid_columnconfigure(0, weight=1)

        # ── Status badge ──
        self._status_badge = StatusBadge(self._scroll, text="", style="muted")
        self._status_badge.grid(row=5, column=0, padx=30, pady=(5, 0), sticky="w")

        # ── Last checked timestamp ──
        self._last_checked_label = ctk.CTkLabel(
            self._scroll,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_muted"],
        )
        self._last_checked_label.grid(row=6, column=0, padx=32, pady=(2, 15), sticky="w")

        # ── Buttons (pinned to bottom, outside scroll) ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=1, column=0, padx=30, pady=10, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=3)
        btn_frame.grid_columnconfigure(1, weight=1)

        self._update_btn = ctk.CTkButton(
            btn_frame,
            text="Check for Updates",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_check_updates,
        )
        self._update_btn.grid(row=0, column=0, padx=(0, 10), sticky="ew")

        self._refresh_btn = ctk.CTkButton(
            btn_frame,
            text="Refresh",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card"],
            command=self.refresh,
        )
        self._refresh_btn.grid(row=0, column=1, sticky="ew")

        # ── Launch buttons row ──
        launch_frame = ctk.CTkFrame(self, fg_color="transparent")
        launch_frame.grid(row=2, column=0, padx=30, pady=(0, 10), sticky="ew")
        launch_frame.grid_columnconfigure(0, weight=1)
        launch_frame.grid_columnconfigure(1, weight=1)

        self._legit_launch_btn = ctk.CTkButton(
            launch_frame,
            text="Legit Launch",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["success"],
            hover_color="#26b863",
            command=self._on_legit_launch,
            state="disabled",
        )
        self._legit_launch_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self._cracked_launch_btn = ctk.CTkButton(
            launch_frame,
            text="Cracked Launch",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_cracked_launch,
            state="disabled",
        )
        self._cracked_launch_btn.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # Track detected exe paths
        self._legit_exe: Path | None = None
        self._cracked_exe: Path | None = None

    def on_show(self):
        """Play staggered entrance animation on first show only."""
        if not self._entrance_played:
            self._entrance_played = True
            self._animate_entrance()
        # Update pricing card if prices are available
        if self.app.price_cache.is_valid:
            self.update_pricing_card()

    def check_app_update(self):
        """Check for updater self-updates in background (silent)."""
        self.app.run_async(
            self._check_app_update_bg,
            on_done=self._on_app_update_checked,
        )

    def _set_status(self, text: str, style: str = "muted"):
        """Update the status badge."""
        self._status_badge.set_status(text, style)

    def _animate_entrance(self):
        """Staggered fade-in for title, card, and buttons."""
        animator = get_animator()
        # Fade title
        animator.animate_color(
            self._title, "text_color",
            theme.COLORS["bg_dark"], theme.COLORS["text"],
            theme.ANIM_SLOW, tag="entrance",
        )
        # Fade subtitle with slight delay
        self._subtitle.configure(text_color=theme.COLORS["bg_dark"])
        self.after(theme.ANIM_STAGGER, lambda: animator.animate_color(
            self._subtitle, "text_color",
            theme.COLORS["bg_dark"], theme.COLORS["text_muted"],
            theme.ANIM_SLOW, tag="entrance",
        ))

    def update_pricing_card(self):
        """Update the pricing summary card from the shared price cache."""
        cache = self.app.price_cache
        prices = cache.get_all()

        if not prices:
            # Hide the card if no prices available
            self._pricing_card.grid_forget()
            return

        # Show the card
        self._pricing_card.grid(row=3, column=0, padx=30, pady=(0, 10), sticky="ew")

        # Count DLCs with prices (excluding free ones)
        paid_prices = [p for p in prices.values() if not p.is_free]
        total_dlcs = len(paid_prices)
        total_original = sum(p.initial_cents for p in paid_prices)
        total_current = sum(p.final_cents for p in paid_prices)
        savings = total_original - total_current
        on_sale_count = sum(1 for p in paid_prices if p.on_sale)

        # Determine currency symbol from first price
        currency = "USD"
        if paid_prices:
            currency = paid_prices[0].currency

        def fmt(cents: int) -> str:
            if currency == "USD":
                return f"${cents / 100:,.2f}"
            return f"{cents / 100:,.2f} {currency}"

        self._price_total_label.configure(text=str(total_dlcs))
        self._price_original_label.configure(text=fmt(total_original))

        # Current total — green if different from original
        if savings > 0:
            self._price_current_label.configure(
                text=fmt(total_current),
                text_color=theme.COLORS["success"],
            )
        else:
            self._price_current_label.configure(
                text=fmt(total_current),
                text_color=theme.COLORS["text"],
            )

        # Savings
        if savings > 0:
            pct = savings / total_original * 100 if total_original > 0 else 0
            self._price_savings_label.configure(
                text=f"{fmt(savings)}  (-{pct:.0f}%)",
                text_color=theme.COLORS["success"],
            )
        else:
            self._price_savings_label.configure(
                text="No active sales",
                text_color=theme.COLORS["text_muted"],
            )

        self._price_on_sale_label.configure(
            text=str(on_sale_count) if on_sale_count > 0 else "None",
            text_color=theme.COLORS["success"] if on_sale_count > 0 else theme.COLORS["text_muted"],
        )

        # On CDN count — show how many DLCs are available for download
        manifest = self.app.updater.patch_client._manifest
        if manifest and manifest.dlc_downloads:
            on_cdn = len(manifest.dlc_downloads)
            total_cat = len(self.app.updater._dlc_manager.catalog.dlcs)
            self._price_patchable_key.grid(row=2, column=0, padx=theme.CARD_PAD_X, pady=2, sticky="w")
            self._price_patchable_label.configure(text=f"{on_cdn} / {total_cat}")
            self._price_patchable_label.grid(row=2, column=1, padx=theme.CARD_PAD_X, pady=2, sticky="w")
        else:
            self._price_patchable_key.grid_forget()
            self._price_patchable_label.grid_forget()

    def refresh(self):
        """Refresh game info in background."""
        self._set_status("Scanning...", "info")
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
                installed = sum(1 for s in states if s.installed)
                enabled = sum(1 for s in states if s.enabled is True)
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
        self._set_status("Ready", "muted")
        self._update_btn.configure(state="normal")

        # Reset button to default state
        self._update_btn.configure(
            text="Check for Updates",
            command=self._on_check_updates,
        )

        # Detect launch executables
        self._detect_launchers(game_dir)

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
        self._set_status("Checking for updates...", "info")
        self.app.run_async(
            self._check_updates_bg,
            on_done=self._on_updates_checked,
            on_error=self._on_check_error,
        )

    def _check_updates_bg(self):
        """Background: check for updates."""
        return self.app.updater.check_for_updates()

    def _on_updates_checked(self, info):
        """GUI thread: show update results with patch-pending awareness."""
        self._update_btn.configure(state="normal")
        self._last_update_info = info

        # Update last checked timestamp
        from datetime import datetime

        now = datetime.now().strftime("%b %d, %Y at %I:%M %p")
        self._last_checked_label.configure(text=f"Last checked: {now}")

        # Show latest patchable version
        self._latest_label.configure(text=info.latest_version)

        # Show game latest row if different from latest patchable
        game_latest = info.game_latest_version
        if game_latest and game_latest != info.latest_version:
            date_str = ""
            if info.game_latest_date:
                date_str = f"  ({info.game_latest_date})"
            self._game_latest_row_label.grid(
                row=3, column=0, padx=theme.CARD_PAD_X, pady=theme.CARD_ROW_PAD, sticky="w",
            )
            self._game_latest_label.configure(
                text=f"{game_latest}{date_str}",
                text_color=theme.COLORS["warning"],
            )
            self._game_latest_label.grid(
                row=3, column=1, padx=theme.CARD_PAD_X, pady=theme.CARD_ROW_PAD, sticky="w",
            )
        else:
            self._game_latest_row_label.grid_forget()
            self._game_latest_label.grid_forget()

        # Clear old banners
        self._clear_banners()

        if info.update_available:
            # DLC-only mode: skip base game update
            if self.app.settings.skip_game_update:
                self._set_status(
                    "Update available but DLC-only mode is enabled.",
                    "warning",
                )
                self._update_btn.configure(
                    text="Check for Updates",
                    command=self._on_check_updates,
                )
                self._add_banner(
                    f"Base game update to {info.latest_version} skipped "
                    f"(DLC-only mode). Disable in Settings to update.",
                    color=theme.COLORS["warning"],
                )
            else:
                # Patches available — can update now
                from ...patch.client import format_size

                size = format_size(info.total_download_size)
                self._set_status(
                    f"Update available: {info.step_count} step(s), {size}",
                    "warning",
                )
                self._update_btn.configure(
                    text="Update Now",
                    command=lambda: self._start_update(info),
                )

            # If there's also a pending newer version beyond the patchable one
            if info.patch_pending:
                self._add_banner(
                    f"New game version {game_latest} detected "
                    f"-- patch coming soon. You can update to "
                    f"{info.latest_version} now.",
                    color=theme.COLORS["warning"],
                )

        elif info.patch_pending:
            # At latest patchable, but a newer game version exists
            self._set_status("You have the latest available patch.", "success")
            self._add_banner(
                f"New game version {game_latest} has been released "
                f"-- patch coming soon!",
                color=theme.COLORS["warning"],
            )
            # Disable update button — nothing to update to
            self._update_btn.configure(
                text="Patch Pending",
                state="disabled",
            )

        else:
            # Fully up to date
            self._set_status("You are up to date!", "success")
            self._update_btn.configure(
                text="Check for Updates",
                command=self._on_check_updates,
            )

        # Show new DLC notifications and pass to DLC frame
        if info.new_dlcs:
            names = ", ".join(d.name for d in info.new_dlcs)
            self._add_banner(
                f"New DLC announced: {names} -- patch pending",
                color=theme.COLORS["text_muted"],
            )
            dlc_frame = self.app._frames.get("dlc")
            if dlc_frame and hasattr(dlc_frame, "set_pending_dlcs"):
                dlc_frame.set_pending_dlcs(info.new_dlcs)

    def _on_check_error(self, error):
        self._update_btn.configure(state="normal")
        self._set_status(f"Error: {error}", "error")

    def _start_update(self, info):
        """Start the actual update process."""
        self.app.switch_to_progress()
        progress_frame = self.app._frames.get("progress")
        if progress_frame:
            progress_frame.start_update(info.plan)

    # ── Self-update ─────────────────────────────────────────────

    def _check_app_update_bg(self):
        """Background: check GitHub for a new updater version."""
        from ...core.self_update import check_for_app_update
        manifest = self.app.updater.patch_client._manifest
        return check_for_app_update(manifest=manifest)

    def _on_app_update_checked(self, info):
        """GUI thread: show or hide the app update banner."""
        self._app_update_info = info
        if info and info.update_available:
            from ...patch.client import format_size
            size = format_size(info.download_size) if info.download_size else "?"
            self._app_update_label.configure(
                text=f"Updater v{info.latest_version} available ({size})",
            )
            self._app_update_frame.grid(
                row=0, column=0, padx=30, pady=(5, 0), sticky="ew",
            )
            # Shift title down — re-grid it at row 1 is not needed since
            # we use grid_rowconfigure weight; just show the banner above
        else:
            self._app_update_frame.grid_forget()

    def _on_self_update(self):
        """Handle 'Update Now' button for the updater itself."""
        if self._self_updating or not self._app_update_info:
            return
        self._self_updating = True

        # Switch banner to progress view
        self._app_update_inner.pack_forget()
        self._dl_progress_frame.pack(fill="x")

        info = self._app_update_info
        version = info.latest_version
        self._dl_title_label.configure(text=f"Downloading v{version}...")
        self._dl_progress_bar.set(0)
        self._dl_pct_label.configure(text="0%")
        self._dl_size_label.configure(text="Starting...")
        self._dl_speed_label.configure(text="")
        self._dl_start_time = time.monotonic()
        self._dl_last_bytes = 0
        self._dl_last_time = self._dl_start_time

        self.app.run_async(
            self._download_self_update_bg,
            on_done=self._on_self_update_downloaded,
            on_error=self._on_self_update_error,
        )

    def _download_self_update_bg(self):
        """Background: download the new updater exe with progress reporting."""
        from ...core.self_update import download_app_update
        return download_app_update(
            self._app_update_info,
            progress=self._on_dl_progress,
        )

    def _on_dl_progress(self, downloaded: int, total: int):
        """Background thread: enqueue a progress update for the GUI."""
        self.app._enqueue_gui(self._update_dl_progress, downloaded, total)

    def _update_dl_progress(self, downloaded: int, total: int):
        """GUI thread: update the download progress bar and labels."""
        from ...patch.client import format_size

        now = time.monotonic()

        # Progress bar and percentage
        if total > 0:
            pct = min(downloaded / total, 1.0)
            self._dl_progress_bar.set(pct)
            self._dl_pct_label.configure(text=f"{pct * 100:.0f}%")
        else:
            self._dl_pct_label.configure(text="")

        # Size display
        size_text = format_size(downloaded)
        if total > 0:
            size_text += f" / {format_size(total)}"
        self._dl_size_label.configure(text=size_text)

        # Speed (calculate over short window to smooth out jitter)
        elapsed_since_last = now - self._dl_last_time
        if elapsed_since_last >= 0.5:
            bytes_delta = downloaded - self._dl_last_bytes
            speed = bytes_delta / elapsed_since_last if elapsed_since_last > 0 else 0
            self._dl_last_bytes = downloaded
            self._dl_last_time = now

            if speed > 0:
                speed_text = f"{format_size(int(speed))}/s"
                # ETA
                if total > 0 and downloaded < total:
                    remaining = total - downloaded
                    eta_seconds = remaining / speed
                    if eta_seconds < 60:
                        eta_text = f"~{eta_seconds:.0f}s left"
                    else:
                        eta_text = f"~{eta_seconds / 60:.0f}m left"
                    speed_text += f"  {eta_text}"
                self._dl_speed_label.configure(text=speed_text)

    def _on_self_update_downloaded(self, new_exe_path):
        """GUI thread: show completion then apply the update."""
        # Show completed state briefly
        self._dl_progress_bar.set(1)
        self._dl_pct_label.configure(text="100%")
        self._dl_title_label.configure(text="Download complete!")
        self._dl_speed_label.configure(text="")

        import tkinter as tk

        confirm = tk.messagebox.askyesno(
            "Update Ready",
            f"Updater v{self._app_update_info.latest_version} downloaded.\n\n"
            "The application will close and relaunch with the new version.\n\n"
            "Continue?",
            parent=self,
        )
        if not confirm:
            self._self_updating = False
            self._dl_progress_frame.pack_forget()
            self._app_update_inner.pack(fill="x", padx=16, pady=10)
            return

        from ...core.self_update import apply_app_update

        # Save settings before apply_app_update() force-exits the process
        try:
            self.app.settings.save()
            self.app.updater.close()
        except Exception:
            pass

        apply_app_update(new_exe_path)  # calls os._exit(0)

    def _on_self_update_error(self, error):
        """GUI thread: show self-update error and restore banner."""
        self._self_updating = False
        self._dl_progress_frame.pack_forget()
        self._app_update_inner.pack(fill="x", padx=16, pady=10)
        self._app_update_btn.configure(state="normal", text="Update Now")
        self._app_update_label.configure(
            text=f"Update failed: {error}",
        )

    def _open_game_dir(self, event=None):
        """Open the game directory in Explorer."""
        game_dir = self.app.updater.find_game_dir()
        if game_dir and Path(game_dir).is_dir():
            import os
            os.startfile(str(game_dir))
        else:
            self.app.show_toast("Game directory not found.", "warning")

    # ── Game Launchers ─────────────────────────────────────────

    # Possible executable names in order of preference
    _GAME_EXES = ["TS4_x64.exe", "TS4_DX9_x64.exe"]

    def _detect_launchers(self, game_dir):
        """Detect legit and cracked game executables."""
        self._legit_exe = None
        self._cracked_exe = None

        if not game_dir:
            self._legit_launch_btn.configure(state="disabled")
            self._cracked_launch_btn.configure(state="disabled")
            return

        game_dir = Path(game_dir)

        # Legit: Game/Bin/TS4_x64.exe
        for exe_name in self._GAME_EXES:
            for bin_dir in ("Game/Bin", "Game/Bin_LE"):
                candidate = game_dir / bin_dir.replace("/", os.sep) / exe_name
                if candidate.is_file():
                    self._legit_exe = candidate
                    break
            if self._legit_exe:
                break

        # Cracked: Game-cracked/Bin/TS4_x64.exe
        for exe_name in self._GAME_EXES:
            for bin_dir in ("Game-cracked/Bin", "Game-cracked/Bin_LE"):
                candidate = game_dir / bin_dir.replace("/", os.sep) / exe_name
                if candidate.is_file():
                    self._cracked_exe = candidate
                    break
            if self._cracked_exe:
                break

        # Update button states
        if self._legit_exe:
            self._legit_launch_btn.configure(state="normal")
        else:
            self._legit_launch_btn.configure(state="disabled")

        if self._cracked_exe:
            self._cracked_launch_btn.configure(state="normal")
        else:
            self._cracked_launch_btn.configure(state="disabled")

    def _on_legit_launch(self):
        """Launch the legit game executable."""
        if not self._legit_exe or not self._legit_exe.is_file():
            self.app.show_toast("Legit game executable not found.", "warning")
            return
        self._launch_game(self._legit_exe, "Legit")

    def _on_cracked_launch(self):
        """Launch the cracked game executable."""
        if not self._cracked_exe or not self._cracked_exe.is_file():
            self.app.show_toast("Cracked game executable not found.", "warning")
            return
        self._launch_game(self._cracked_exe, "Cracked")

    def _launch_game(self, exe_path: Path, label: str):
        """Launch a game executable."""
        try:
            subprocess.Popen(
                [str(exe_path)],
                cwd=str(exe_path.parent),
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            self.app.show_toast(f"{label} game launched!", "success")
        except OSError as e:
            self.app.show_toast(f"Failed to launch: {e}", "error")

    # ── Banner helpers ──────────────────────────────────────────

    def _clear_banners(self):
        for widget in self._banner_frame.winfo_children():
            widget.destroy()

    def _add_banner(self, text: str, color: str = ""):
        """Add a notification banner to the banner area."""
        banner = ctk.CTkFrame(
            self._banner_frame,
            corner_radius=6,
            fg_color=theme.COLORS["bg_card"],
        )
        banner.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(
            banner,
            text=text,
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=color or theme.COLORS["text"],
            wraplength=500,
            anchor="w",
            justify="left",
        ).pack(padx=12, pady=8, fill="x")
