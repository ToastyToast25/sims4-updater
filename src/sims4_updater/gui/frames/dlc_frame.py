"""
DLC frame — card-style DLC rows with collapsible groups, ownership indicators,
search filtering, filter chips, Steam pricing, store links, hover effects,
pill status badges, and widget-reuse-based filtering.
"""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import get_animator
from ...dlc.catalog import DLCInfo, DLCStatus
from ...dlc.steam import SteamPrice, fetch_prices_batch

if TYPE_CHECKING:
    from ..app import App


# Status tag colors
_STATUS_COLORS = {
    "Owned": theme.COLORS["success"],
    "Patched": "#5b9bd5",
    "Patched (disabled)": theme.COLORS["text_muted"],
    "Incomplete": theme.COLORS["warning"],
    "Missing files": theme.COLORS["warning"],
    "Not installed": theme.COLORS["text_muted"],
}

# Filter chip definitions: (key, label)
_FILTER_DEFS = [
    ("owned", "Owned"),
    ("not_owned", "Not Owned"),
    ("installed", "Installed"),
    ("patched", "Patched"),
    ("on_sale", "On Sale"),
]

# Pack type ordering and labels
_TYPE_ORDER = ["expansion", "game_pack", "stuff_pack", "kit", "free_pack", "other"]
_TYPE_LABELS = {
    "expansion": "Expansion Packs",
    "game_pack": "Game Packs",
    "stuff_pack": "Stuff Packs",
    "kit": "Kits",
    "free_pack": "Free Packs",
    "other": "Other",
}


class DLCFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._animator = get_animator()

        # Widget-reuse state
        self._built = False
        self._all_states: list[DLCStatus] = []
        self._row_widgets: dict[str, dict] = {}  # dlc_id -> widget refs
        self._checkbox_vars: dict[str, ctk.BooleanVar] = {}
        self._section_widgets: dict[str, dict] = {}  # pack_type -> widget refs
        self._section_collapsed: dict[str, bool] = {}
        self._desc_expanded: dict[str, bool] = {}
        self._pending_dlcs = []
        self._skeleton_widgets: list[ctk.CTkFrame] = []

        # Filter state
        self._active_filters: set[str] = set()
        self._filter_buttons: dict[str, ctk.CTkButton] = {}
        self._prices_loaded = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

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

        # ── Search box ──
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.grid(row=1, column=0, padx=30, pady=(0, 5), sticky="ew")
        search_frame.grid_columnconfigure(0, weight=1)

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", self._on_search_changed)

        self._search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self._search_var,
            placeholder_text="Search DLCs...",
            font=ctk.CTkFont(size=12),
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
        )
        self._search_entry.grid(row=0, column=0, sticky="ew")

        self._clear_btn = ctk.CTkButton(
            search_frame,
            text="\u2715",
            width=30,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card"],
            command=self._clear_search,
        )
        self._clear_btn.grid(row=0, column=1, padx=(5, 0))

        # ── Filter Chips ──
        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.grid(row=2, column=0, padx=30, pady=(0, 5), sticky="ew")

        for i, (key, label) in enumerate(_FILTER_DEFS):
            btn = ctk.CTkButton(
                filter_frame,
                text=label,
                font=ctk.CTkFont(size=11),
                height=26,
                corner_radius=13,
                fg_color=theme.COLORS["bg_card_alt"],
                hover_color=theme.COLORS["card_hover"],
                text_color=theme.COLORS["text_muted"],
                border_width=1,
                border_color=theme.COLORS["border"],
                command=lambda k=key: self._toggle_filter(k),
            )
            btn.grid(row=0, column=i, padx=(0 if i == 0 else 4, 0))
            self._filter_buttons[key] = btn

        # ── Status ──
        self._status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._status_label.grid(row=4, column=0, padx=30, pady=(5, 10), sticky="w")

        # ── Scrollable DLC list ──
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, corner_radius=8,
            scrollbar_button_color=theme.COLORS["separator"],
            scrollbar_button_hover_color=theme.COLORS["accent"],
        )
        self._scroll_frame.grid(row=3, column=0, padx=30, pady=0, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        # ── Empty state (hidden by default) ──
        self._empty_frame = ctk.CTkFrame(self._scroll_frame, fg_color="transparent")
        ctk.CTkLabel(
            self._empty_frame,
            text="No DLCs match your filters",
            font=ctk.CTkFont(size=14),
            text_color=theme.COLORS["text_muted"],
        ).pack(pady=(60, 4))
        ctk.CTkLabel(
            self._empty_frame,
            text="Try adjusting your search or filters",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS.get("text_dim", "#6a6a8a"),
        ).pack()

        # ── No game dir message ──
        self._no_game_label = ctk.CTkLabel(
            self._scroll_frame,
            text="No game directory found. Set it in Settings.",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        )

    # ── Filter Chip Logic ──────────────────────────────────────

    def _toggle_filter(self, key: str):
        if key in self._active_filters:
            self._active_filters.discard(key)
            btn = self._filter_buttons[key]
            btn.configure(
                fg_color=theme.COLORS["bg_card_alt"],
                text_color=theme.COLORS["text_muted"],
                border_color=theme.COLORS["border"],
            )
        else:
            self._active_filters.add(key)
            btn = self._filter_buttons[key]
            if key == "on_sale":
                btn.configure(
                    fg_color=theme.COLORS["success"],
                    text_color="#1a1a2e",
                    border_color=theme.COLORS["success"],
                )
            else:
                btn.configure(
                    fg_color=theme.COLORS["accent"],
                    text_color=theme.COLORS["text"],
                    border_color=theme.COLORS["accent"],
                )
        self._apply_filter()

    def _is_on_sale(self, dlc: DLCInfo) -> bool:
        if not dlc.steam_app_id:
            return False
        price = self.app.price_cache.get(dlc.steam_app_id)
        return price is not None and price.on_sale

    def _get_price(self, dlc: DLCInfo) -> SteamPrice | None:
        if not dlc.steam_app_id:
            return None
        return self.app.price_cache.get(dlc.steam_app_id)

    # ── Data Loading ───────────────────────────────────────────

    def on_show(self):
        self._load_dlcs()

    def _load_dlcs(self):
        self._status_label.configure(text="Loading DLCs...")
        if not self._built:
            self._show_loading_skeleton()
        self.app.run_async(
            self._get_dlc_states,
            on_done=self._on_states_loaded,
            on_error=self._on_dlc_error,
        )

    def _get_dlc_states(self):
        game_dir = self.app.updater.find_game_dir()
        if not game_dir:
            return None
        return self.app.updater._dlc_manager.get_dlc_states(game_dir)

    def _on_states_loaded(self, states):
        self._destroy_skeleton()
        if states is None:
            self._all_states = []
            self._show_no_game()
            return
        self._all_states = states
        self._hide_no_game()

        # (Re)build widgets if data changed
        self._rebuild_rows()
        self._apply_filter()

        # Fetch Steam prices if cache is stale
        cache = self.app.price_cache
        if not cache.is_valid and not cache.is_fetching:
            self._fetch_steam_prices()

    # ── Loading Skeleton ──────────────────────────────────────

    def _show_loading_skeleton(self):
        for i in range(6):
            skel = ctk.CTkFrame(
                self._scroll_frame,
                fg_color=theme.COLORS["bg_card_alt"],
                corner_radius=6,
                height=36,
            )
            skel.grid(row=i, column=0, padx=5, pady=3, sticky="ew")
            skel.grid_propagate(False)
            ctk.CTkFrame(
                skel, fg_color=theme.COLORS["separator"],
                corner_radius=4, width=20, height=20,
            ).place(x=12, rely=0.5, anchor="w")
            ctk.CTkFrame(
                skel, fg_color=theme.COLORS["separator"],
                corner_radius=4, width=180, height=14,
            ).place(x=44, rely=0.5, anchor="w")
            ctk.CTkFrame(
                skel, fg_color=theme.COLORS["separator"],
                corner_radius=4, width=50, height=14,
            ).place(relx=0.85, rely=0.5, anchor="e")
            self._skeleton_widgets.append(skel)

    def _destroy_skeleton(self):
        for skel in self._skeleton_widgets:
            skel.destroy()
        self._skeleton_widgets.clear()

    # ── No Game / Empty State ─────────────────────────────────

    def _show_no_game(self):
        self._hide_all_sections()
        self._empty_frame.grid_remove()
        self._no_game_label.grid(row=0, column=0, padx=10, pady=20)
        self._status_label.configure(text="")

    def _hide_no_game(self):
        self._no_game_label.grid_remove()

    def _show_empty_state(self):
        self._empty_frame.grid(row=9999, column=0, sticky="nsew")

    def _hide_empty_state(self):
        self._empty_frame.grid_remove()

    def _hide_all_sections(self):
        for sw in self._section_widgets.values():
            sw["separator"].grid_remove()
            sw["header_frame"].grid_remove()
            sw["content_frame"].grid_remove()

    # ── Steam Price Fetching ───────────────────────────────────

    def _fetch_steam_prices(self):
        app_ids = [
            s.dlc.steam_app_id for s in self._all_states
            if s.dlc.steam_app_id is not None
        ]
        if not app_ids:
            return

        self.app.price_cache.is_fetching = True
        self._status_label.configure(
            text=self._status_label.cget("text") + "  |  Loading prices..."
        )
        self.app.run_async(
            self._fetch_prices_bg,
            app_ids,
            on_done=self._on_prices_fetched,
            on_error=self._on_prices_error,
        )

    def _fetch_prices_bg(self, app_ids):
        return fetch_prices_batch(app_ids, cc="US")

    def _on_prices_fetched(self, prices):
        self.app.price_cache.is_fetching = False
        self.app.price_cache.update(prices)
        self._prices_loaded = True

        # Update "On Sale" chip label with count
        sale_count = sum(1 for p in prices.values() if p.on_sale)
        btn = self._filter_buttons.get("on_sale")
        if btn:
            btn.configure(text=f"On Sale ({sale_count})" if sale_count > 0 else "On Sale")

        # Rebuild rows to include price data, then re-filter
        self._rebuild_rows()
        self._apply_filter()

        # Notify home frame
        home = self.app._frames.get("home")
        if home and hasattr(home, "update_pricing_card"):
            home.update_pricing_card()

    def _on_prices_error(self, error):
        self.app.price_cache.is_fetching = False
        import logging
        logging.warning("Steam price fetch failed: %s", error)

    # ── Search & Filter ────────────────────────────────────────

    def _on_search_changed(self, *_args):
        if self._all_states and self._built:
            self._apply_filter()

    def _clear_search(self):
        self._search_var.set("")

    def _apply_filter(self):
        """Show/hide pre-built rows based on current filters."""
        if not self._built:
            return

        filtered = list(self._all_states)

        # Text search
        query = self._search_var.get().strip().lower()
        if query:
            filtered = [
                s for s in filtered
                if query in s.dlc.get_name().lower() or query in s.dlc.id.lower()
            ]

        # Chip filters (OR logic)
        if self._active_filters:
            def matches(state: DLCStatus) -> bool:
                for f in self._active_filters:
                    if f == "owned" and state.owned:
                        return True
                    if f == "not_owned" and not state.owned and not (state.installed and state.registered):
                        return True
                    if f == "installed" and state.installed:
                        return True
                    if f == "patched" and state.registered and state.installed:
                        return True
                    if f == "on_sale" and self._is_on_sale(state.dlc):
                        return True
                return False
            filtered = [s for s in filtered if matches(s)]

        filtered_ids = {s.dlc.id for s in filtered}

        # Group filtered results by pack type
        scroll_row = 0
        any_visible = False

        for pack_type in _TYPE_ORDER:
            sw = self._section_widgets.get(pack_type)
            if sw is None:
                continue

            type_states = [s for s in filtered if s.dlc.pack_type == pack_type]

            if not type_states:
                sw["separator"].grid_remove()
                sw["header_frame"].grid_remove()
                sw["content_frame"].grid_remove()
                continue

            any_visible = True

            # Show separator (skip for first visible section)
            if scroll_row > 0:
                sw["separator"].grid(row=scroll_row, column=0, padx=5, pady=(8, 0), sticky="ew")
                scroll_row += 1
            else:
                sw["separator"].grid_remove()

            # Update header counts and show
            sec_installed = sum(1 for s in type_states if s.installed)
            sec_total = len(type_states)
            is_collapsed = self._section_collapsed.get(pack_type, False)
            arrow = "\u25b6" if is_collapsed else "\u25bc"
            sw["arrow_label"].configure(text=arrow)
            sw["count_label"].configure(text=f"{sec_installed}/{sec_total}")
            sw["header_frame"].grid(row=scroll_row, column=0, padx=2, pady=(10, 2), sticky="ew")
            scroll_row += 1

            # Content frame
            sw["content_frame"].grid(row=scroll_row, column=0, sticky="ew")
            scroll_row += 1

            if is_collapsed:
                sw["content_frame"].grid_remove()
                continue

            # Show/hide individual rows within this section
            cb_row = 0
            for state in type_states:
                dlc_id = state.dlc.id
                rw = self._row_widgets.get(dlc_id)
                if rw is None:
                    continue

                # Update alternating background
                bg = theme.COLORS["bg_card"] if cb_row % 2 == 0 else theme.COLORS["bg_card_alt"]
                rw["row_frame"].configure(fg_color=bg)
                rw["_bg_normal"] = bg

                rw["row_frame"].grid(row=cb_row, column=0, padx=5, pady=3, sticky="ew")
                cb_row += 1

                # Show/hide description
                if rw.get("desc_frame"):
                    if self._desc_expanded.get(dlc_id, False):
                        rw["desc_frame"].grid(row=cb_row, column=0, padx=(35, 10), pady=(0, 2), sticky="ew")
                    else:
                        rw["desc_frame"].grid_remove()
                    cb_row += 1

            # Hide rows NOT in filtered set for this section
            for state in self._all_states:
                if state.dlc.pack_type == pack_type and state.dlc.id not in filtered_ids:
                    rw = self._row_widgets.get(state.dlc.id)
                    if rw:
                        rw["row_frame"].grid_remove()
                        if rw.get("desc_frame"):
                            rw["desc_frame"].grid_remove()

        # Pending DLCs
        if self._pending_dlcs and any_visible:
            self._show_pending_section(scroll_row)

        # Empty state
        if any_visible:
            self._hide_empty_state()
        else:
            self._show_empty_state()

        # Status label
        total_owned = sum(1 for s in self._all_states if s.owned)
        total_patched = sum(1 for s in self._all_states if s.registered and s.installed)
        total_missing = sum(1 for s in self._all_states if not s.installed)
        total_enabled = sum(1 for s in self._all_states if s.enabled is True)
        self._status_label.configure(
            text=f"{total_owned} owned, {total_patched} patched, "
                 f"{total_missing} missing  |  {total_enabled} enabled",
            text_color=theme.COLORS["text_muted"],
        )

    # ── Row Building ───────────────────────────────────────────

    def _rebuild_rows(self):
        """Destroy old widgets and build all rows fresh from current states."""
        # Clear existing
        for rw in self._row_widgets.values():
            rw["row_frame"].destroy()
            if rw.get("desc_frame"):
                rw["desc_frame"].destroy()
        self._row_widgets.clear()
        self._checkbox_vars.clear()

        for sw in self._section_widgets.values():
            sw["separator"].destroy()
            sw["header_frame"].destroy()
            sw["content_frame"].destroy()
        self._section_widgets.clear()

        # Destroy pending section if any
        for w in self._scroll_frame.winfo_children():
            if w not in (self._empty_frame, self._no_game_label):
                w.destroy()

        self._built = False
        self._build_all_rows()

    def _build_all_rows(self):
        """Build all section headers and DLC rows once."""
        if not self._all_states:
            self._built = True
            return

        wrap = max(300, self._scroll_frame.winfo_width() - 80)

        for pack_type in _TYPE_ORDER:
            type_states = [s for s in self._all_states if s.dlc.pack_type == pack_type]
            if not type_states:
                continue

            # Section separator
            sep = ctk.CTkFrame(
                self._scroll_frame, height=1,
                fg_color=theme.COLORS["separator"],
            )

            # Section header frame
            header_frame = ctk.CTkFrame(
                self._scroll_frame,
                fg_color=theme.COLORS["separator"],
                corner_radius=6,
                height=38,
            )
            header_frame.grid_columnconfigure(1, weight=1)
            header_frame.grid_propagate(False)

            arrow_label = ctk.CTkLabel(
                header_frame,
                text="\u25bc",
                font=ctk.CTkFont(size=14),
                text_color=theme.COLORS["accent"],
                width=20,
            )
            arrow_label.grid(row=0, column=0, padx=(12, 4), pady=8)

            label_text = _TYPE_LABELS.get(pack_type, pack_type).upper()
            title_label = ctk.CTkLabel(
                header_frame,
                text=label_text,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=theme.COLORS["text"],
                anchor="w",
            )
            title_label.grid(row=0, column=1, sticky="w", pady=8)

            sec_installed = sum(1 for s in type_states if s.installed)
            count_label = ctk.CTkLabel(
                header_frame,
                text=f"{sec_installed}/{len(type_states)}",
                font=ctk.CTkFont(size=11),
                text_color=theme.COLORS["text_muted"],
                fg_color=theme.COLORS["bg_dark"],
                corner_radius=10,
                width=50, height=22,
            )
            count_label.grid(row=0, column=2, padx=(4, 12), pady=8)

            # Click bindings for collapse
            for widget in (header_frame, arrow_label, title_label, count_label):
                widget.bind("<Button-1>", lambda e, pt=pack_type: self._toggle_section(pt))
                widget.bind("<Enter>", lambda e, hf=header_frame: hf.configure(
                    fg_color=theme.COLORS["sidebar_hover"]))
                widget.bind("<Leave>", lambda e, hf=header_frame: hf.configure(
                    fg_color=theme.COLORS["separator"]))

            # Content frame
            content_frame = ctk.CTkFrame(self._scroll_frame, fg_color="transparent")
            content_frame.grid_columnconfigure(0, weight=1)

            self._section_widgets[pack_type] = {
                "separator": sep,
                "header_frame": header_frame,
                "arrow_label": arrow_label,
                "title_label": title_label,
                "count_label": count_label,
                "content_frame": content_frame,
            }

            # Build DLC rows inside content_frame
            cb_row = 0
            for idx, state in enumerate(type_states):
                self._build_dlc_row(content_frame, state, cb_row, idx, wrap)
                cb_row += 1
                if state.dlc.description:
                    cb_row += 1  # reserve row for desc_frame

        self._built = True

    def _build_dlc_row(self, parent, state: DLCStatus, grid_row: int, idx: int, wrap: int):
        """Build a single DLC row card."""
        dlc = state.dlc
        name = dlc.get_name()
        label = state.status_label
        color = _STATUS_COLORS.get(label, theme.COLORS["text_muted"])
        has_desc = bool(dlc.description)
        price = self._get_price(dlc)

        # Card-style row frame with alternating bg
        bg = theme.COLORS["bg_card"] if idx % 2 == 0 else theme.COLORS["bg_card_alt"]
        row_frame = ctk.CTkFrame(
            parent,
            fg_color=bg,
            corner_radius=6,
            border_width=1,
            border_color=theme.COLORS["border"],
        )
        row_frame.grid_columnconfigure(1, weight=1)

        col = 0

        # Expand/collapse button
        info_btn = None
        if has_desc:
            is_expanded = self._desc_expanded.get(dlc.id, False)
            arr = "\u25bc" if is_expanded else "\u25b8"
            info_btn = ctk.CTkButton(
                row_frame,
                text=arr,
                width=24, height=24,
                font=ctk.CTkFont(size=11),
                fg_color="transparent",
                hover_color=theme.COLORS["separator"],
                text_color=theme.COLORS["text_muted"],
                corner_radius=4,
                command=lambda did=dlc.id: self._toggle_desc(did),
            )
            info_btn.grid(row=0, column=col, padx=(10, 2), pady=6, sticky="w")
            col += 1

        # Checkbox
        if state.owned:
            var = ctk.BooleanVar(value=True)
            cb = ctk.CTkCheckBox(
                row_frame, text=name, variable=var,
                font=ctk.CTkFont(size=12),
                height=theme.BUTTON_HEIGHT_SMALL,
                corner_radius=4, state="disabled",
            )
        elif state.installed and state.registered:
            var = ctk.BooleanVar(value=state.enabled is True)
            cb = ctk.CTkCheckBox(
                row_frame, text=name, variable=var,
                font=ctk.CTkFont(size=12),
                height=theme.BUTTON_HEIGHT_SMALL,
                corner_radius=4,
            )
        else:
            var = ctk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(
                row_frame, text=name, variable=var,
                font=ctk.CTkFont(size=12),
                height=theme.BUTTON_HEIGHT_SMALL,
                corner_radius=4,
                text_color=theme.COLORS["text_muted"],
                state="disabled",
            )
        pad_left = 10 if not has_desc else 0
        cb.grid(row=0, column=col, padx=(pad_left, 0), pady=6, sticky="w")
        self._checkbox_vars[dlc.id] = var
        next_col = col + 1

        # Price display
        if price and not price.is_free:
            price_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            price_frame.grid(row=0, column=next_col, padx=(5, 0), pady=6, sticky="e")

            if price.on_sale:
                ctk.CTkLabel(
                    price_frame,
                    text=f"-{price.discount_percent}%",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="#1a1a2e",
                    fg_color=theme.COLORS["success"],
                    corner_radius=4,
                    width=42, height=22,
                ).pack(side="left", padx=(0, 6))

                ctk.CTkLabel(
                    price_frame,
                    text=price.initial_formatted or f"${price.initial_cents / 100:.2f}",
                    font=ctk.CTkFont(size=10, overstrike=True),
                    text_color=theme.COLORS["text_muted"],
                ).pack(side="left", padx=(0, 6))

                ctk.CTkLabel(
                    price_frame,
                    text=price.final_formatted or f"${price.final_cents / 100:.2f}",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=theme.COLORS["success"],
                ).pack(side="left")
            else:
                ctk.CTkLabel(
                    price_frame,
                    text=price.final_formatted or f"${price.final_cents / 100:.2f}",
                    font=ctk.CTkFont(size=11),
                    text_color=theme.COLORS["text_muted"],
                ).pack(side="left")
            next_col += 1

        # Steam store link
        if dlc.steam_app_id:
            steam_btn = ctk.CTkButton(
                row_frame,
                text="\u2197",
                width=28, height=24,
                font=ctk.CTkFont(size=12),
                fg_color="transparent",
                hover_color=theme.COLORS["separator"],
                text_color=theme.COLORS["accent"],
                corner_radius=4,
                command=lambda aid=dlc.steam_app_id: self._open_steam_page(aid),
            )
            steam_btn.grid(row=0, column=next_col, padx=(4, 0), pady=6, sticky="e")
            next_col += 1

        # Status pill badge
        pill = ctk.CTkFrame(
            row_frame,
            corner_radius=10,
            border_width=1,
            border_color=color,
            fg_color="transparent",
            height=22,
        )
        pill.grid(row=0, column=next_col, padx=(5, 10), pady=6, sticky="e")
        ctk.CTkLabel(
            pill,
            text=label,
            font=ctk.CTkFont(size=9),
            text_color=color,
        ).pack(padx=8, pady=2)

        # Hover effect — animate border color
        def on_enter(e, rf=row_frame):
            self._animator.cancel_all(rf, tag="row_hover")
            self._animator.animate_color(
                rf, "border_color",
                theme.COLORS["border"], theme.COLORS["accent"],
                theme.ANIM_FAST, tag="row_hover",
            )

        def on_leave(e, rf=row_frame, rw_ref=dlc.id):
            self._animator.cancel_all(rf, tag="row_hover")
            self._animator.animate_color(
                rf, "border_color",
                theme.COLORS["accent"], theme.COLORS["border"],
                theme.ANIM_NORMAL, tag="row_hover",
            )

        row_frame.bind("<Enter>", on_enter)
        row_frame.bind("<Leave>", on_leave)
        # Propagate hover to children
        for child in row_frame.winfo_children():
            child.bind("<Enter>", on_enter)
            child.bind("<Leave>", on_leave)

        # Description frame (hidden by default)
        desc_frame = None
        if has_desc:
            desc_frame = ctk.CTkFrame(
                parent,
                fg_color=theme.COLORS["bg_card_alt"],
                corner_radius=4,
            )
            desc_frame.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                desc_frame,
                text=dlc.description,
                font=ctk.CTkFont(*theme.FONT_SMALL),
                text_color=theme.COLORS["text_muted"],
                wraplength=wrap,
                justify="left",
                anchor="w",
            ).grid(row=0, column=0, padx=10, pady=6, sticky="w")

            if dlc.steam_app_id:
                steam_link = ctk.CTkLabel(
                    desc_frame,
                    text="View on Steam Store \u2197",
                    font=ctk.CTkFont(size=10, underline=True),
                    text_color=theme.COLORS["accent"],
                    cursor="hand2",
                )
                steam_link.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="w")
                steam_link.bind(
                    "<Button-1>",
                    lambda e, aid=dlc.steam_app_id: self._open_steam_page(aid),
                )

            if price and price.on_sale:
                ctk.CTkLabel(
                    desc_frame,
                    text=(
                        f"Steam Sale: {price.initial_formatted} \u2192 "
                        f"{price.final_formatted} ({price.discount_percent}% off)"
                    ),
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color=theme.COLORS["success"],
                ).grid(row=2, column=0, padx=10, pady=(0, 6), sticky="w")

        # Store references
        self._row_widgets[dlc.id] = {
            "row_frame": row_frame,
            "desc_frame": desc_frame,
            "info_btn": info_btn,
            "checkbox": cb,
            "_bg_normal": bg,
        }

    # ── Pending DLCs ──────────────────────────────────────────

    def _show_pending_section(self, start_row: int):
        """Show pending DLCs from manifest below the main list."""
        # These are lightweight — recreated each filter pass since they're few
        row = start_row
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

    # ── Toggle Helpers ─────────────────────────────────────────

    def _toggle_desc(self, dlc_id: str):
        self._desc_expanded[dlc_id] = not self._desc_expanded.get(dlc_id, False)
        rw = self._row_widgets.get(dlc_id)
        if rw is None:
            return

        btn = rw.get("info_btn")
        if btn:
            btn.configure(
                text="\u25bc" if self._desc_expanded[dlc_id] else "\u25b8"
            )

        # Re-run filter layout — it knows the correct grid positions
        self._apply_filter()

    def _toggle_section(self, pack_type: str):
        self._section_collapsed[pack_type] = not self._section_collapsed.get(pack_type, False)
        sw = self._section_widgets.get(pack_type)
        if sw is None:
            return

        is_collapsed = self._section_collapsed[pack_type]
        sw["arrow_label"].configure(text="\u25b6" if is_collapsed else "\u25bc")

        if is_collapsed:
            sw["content_frame"].grid_remove()
        else:
            sw["content_frame"].grid()

    def _open_steam_page(self, app_id: int):
        webbrowser.open(f"https://store.steampowered.com/app/{app_id}")

    # ── Actions ────────────────────────────────────────────────

    def _on_auto_toggle(self):
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
        self._pending_dlcs = pending_dlcs

    def _on_dlc_error(self, error):
        import traceback, logging
        logging.error("DLC error: %s\n%s", error, traceback.format_exc())
        self._auto_btn.configure(state="normal")
        self._apply_btn.configure(state="normal")
        self._status_label.configure(
            text=f"Error: {error}",
            text_color=theme.COLORS["error"],
        )
