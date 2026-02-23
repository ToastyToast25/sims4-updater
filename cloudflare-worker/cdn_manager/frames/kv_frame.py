"""KV Browser frame — browse, search, add, and delete Cloudflare KV entries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import LogPanel

if TYPE_CHECKING:
    from ..app import CDNManagerApp


class KVBrowserFrame(ctk.CTkFrame):
    def __init__(self, parent, app: CDNManagerApp):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._all_keys: list[str] = []
        self._filtered_keys: list[str] = []
        self._key_check_vars: dict[str, ctk.BooleanVar] = {}
        self._loaded = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self,
            text="KV Browser",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        ).grid(row=0, column=0, padx=theme.SECTION_PAD, pady=(20, 15), sticky="w")

        # Header bar
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=1, column=0, padx=theme.SECTION_PAD, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        # Search row
        search_frame = ctk.CTkFrame(header, fg_color="transparent")
        search_frame.grid(row=0, column=0, sticky="ew")
        search_frame.grid_columnconfigure(0, weight=1)

        self._search_entry = ctk.CTkEntry(
            search_frame,
            font=ctk.CTkFont(size=12),
            height=36,
            placeholder_text="Filter keys...",
        )
        self._search_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self._search_entry.bind("<KeyRelease>", lambda _: self._filter_keys())

        ctk.CTkButton(
            search_frame,
            text="Refresh",
            height=36,
            width=80,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._refresh,
        ).grid(row=0, column=1)

        # Button row
        btn_row = ctk.CTkFrame(header, fg_color="transparent")
        btn_row.grid(row=1, column=0, pady=(8, 0), sticky="ew")

        ctk.CTkButton(
            btn_row,
            text="Add Key",
            height=28,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            font=ctk.CTkFont(size=11),
            command=self._add_key,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            btn_row,
            text="Delete Selected",
            height=28,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            font=ctk.CTkFont(size=11),
            command=self._delete_selected,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            btn_row,
            text="Copy Key",
            height=28,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            font=ctk.CTkFont(size=11),
            command=self._copy_selected_key,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            btn_row,
            text="View Value",
            height=28,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            font=ctk.CTkFont(size=11),
            command=self._view_selected_value,
        ).pack(side="left", padx=(0, 12))

        self._count_label = ctk.CTkLabel(
            btn_row,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=theme.COLORS["text_muted"],
        )
        self._count_label.pack(side="left")

        # Key list
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=theme.COLORS["bg_dark"],
            corner_radius=theme.CORNER_RADIUS,
            border_width=1,
            border_color=theme.COLORS["border"],
            scrollbar_button_color=theme.COLORS["separator"],
            scrollbar_button_hover_color=theme.COLORS["accent"],
        )
        self._scroll.grid(
            row=2,
            column=0,
            padx=theme.SECTION_PAD,
            pady=(10, 4),
            sticky="nsew",
        )
        self._scroll.grid_columnconfigure(1, weight=1)

        self._placeholder = ctk.CTkLabel(
            self._scroll,
            text="Click 'Refresh' to load KV keys",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        )
        self._placeholder.grid(row=0, column=0, columnspan=3, pady=40)

        # Log
        self._log = LogPanel(self)
        self._log.grid(
            row=3,
            column=0,
            padx=theme.SECTION_PAD,
            pady=(4, 15),
            sticky="nsew",
        )

    def on_show(self):
        if not self._loaded:
            self._refresh()

    # -- Refresh -------------------------------------------------------------

    def _refresh(self):
        self._log.log("Loading KV keys...")
        self.app.run_async(
            self._bg_refresh,
            on_done=self._on_refresh_done,
            on_error=self._on_refresh_error,
        )

    def _bg_refresh(self):
        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        return conn.kv_list()

    def _on_refresh_done(self, keys: list[str]):
        self._loaded = True
        self._all_keys = sorted(keys)
        self._filter_keys()
        self._log.log(f"Loaded {len(keys)} KV keys", "success")

    def _on_refresh_error(self, error):
        self._log.log(f"Failed to load keys: {error}", "error")

    # -- Filter / Display ----------------------------------------------------

    def _filter_keys(self):
        query = self._search_entry.get().strip().lower()
        if query:
            self._filtered_keys = [k for k in self._all_keys if query in k.lower()]
        else:
            self._filtered_keys = list(self._all_keys)

        self._count_label.configure(
            text=f"{len(self._filtered_keys)} / {len(self._all_keys)} keys",
        )
        self._populate_list()

    def _populate_list(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._key_check_vars.clear()

        if not self._filtered_keys:
            ctk.CTkLabel(
                self._scroll,
                text="No keys found",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=0, columnspan=3, pady=40)
            return

        # Header
        for col, text in enumerate(["", "Key", "Type"]):
            ctk.CTkLabel(
                self._scroll,
                text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=col, padx=6, pady=(4, 6), sticky="w")

        # Color-code by prefix
        prefix_colors = {
            "dlc/": "#e94560",
            "language/": "#6c5ce7",
            "patches/": "#00b894",
            "archives/": "#fdcb6e",
            "manifest.json": "#74b9ff",
        }

        for i, key in enumerate(self._filtered_keys):
            row = i + 1

            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(
                self._scroll,
                text="",
                variable=var,
                width=20,
                height=20,
                checkbox_width=14,
                checkbox_height=14,
            ).grid(row=row, column=0, padx=4, pady=1)
            self._key_check_vars[key] = var

            # Determine type/color
            color = theme.COLORS["text"]
            type_str = "other"
            for prefix, c in prefix_colors.items():
                if key.startswith(prefix):
                    color = c
                    type_str = prefix.rstrip("/")
                    break

            ctk.CTkLabel(
                self._scroll,
                text=key,
                font=ctk.CTkFont("Consolas", 11),
                text_color=color,
            ).grid(row=row, column=1, padx=6, pady=1, sticky="w")

            ctk.CTkLabel(
                self._scroll,
                text=type_str,
                font=ctk.CTkFont(size=9),
                text_color=theme.COLORS["text_dim"],
            ).grid(row=row, column=2, padx=6, pady=1, sticky="w")

    # -- Actions -------------------------------------------------------------

    def _get_selected(self) -> list[str]:
        return [k for k, v in self._key_check_vars.items() if v.get()]

    def _add_key(self):
        dialog = _AddKVDialog(self)
        self.wait_window(dialog)
        if not dialog.key or not dialog.value:
            return

        self._log.log(f"Adding key: {dialog.key}")
        self.app.run_async(
            self._bg_add_key,
            dialog.key,
            dialog.value,
            on_done=lambda _: (
                self._log.log(f"Added: {dialog.key}", "success"),
                self._refresh(),
            ),
            on_error=lambda e: self._log.log(f"Failed to add key: {e}", "error"),
        )

    def _bg_add_key(self, key: str, value: str):
        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        conn.kv_put(key, value)

    def _delete_selected(self):
        selected = self._get_selected()
        if not selected:
            self.app.show_toast("No keys selected", "warning")
            return

        # Confirmation dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Delete")
        dialog.geometry("350x140")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=f"Delete {len(selected)} KV key(s)?",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=theme.COLORS["warning"],
        ).pack(padx=20, pady=(20, 8))

        preview = ", ".join(selected[:3])
        if len(selected) > 3:
            preview += f" ... (+{len(selected) - 3} more)"
        ctk.CTkLabel(
            dialog,
            text=preview,
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_muted"],
            wraplength=310,
        ).pack(padx=20, pady=(0, 12))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(padx=20, pady=(0, 15))

        confirmed = [False]

        def do_delete():
            confirmed[0] = True
            dialog.destroy()

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=80,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=dialog.destroy,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Delete",
            width=80,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            command=do_delete,
        ).pack(side="left")

        self.wait_window(dialog)
        if not confirmed[0]:
            return

        self._log.log(f"Deleting {len(selected)} keys...")
        self.app.run_async(
            self._bg_delete_keys,
            selected,
            on_done=lambda count: (
                self._log.log(f"Deleted {count} keys", "success"),
                self._refresh(),
            ),
            on_error=lambda e: self._log.log(f"Delete failed: {e}", "error"),
        )

    def _bg_delete_keys(self, keys: list[str]) -> int:
        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        count = 0
        for key in keys:
            if conn.kv_delete(key):
                count += 1
        return count

    def _copy_selected_key(self):
        selected = self._get_selected()
        if not selected:
            self.app.show_toast("No keys selected", "warning")
            return
        self.clipboard_clear()
        self.clipboard_append("\n".join(selected))
        self.app.show_toast(f"Copied {len(selected)} key(s)", "success")

    def _view_selected_value(self):
        selected = self._get_selected()
        if not selected:
            self.app.show_toast("No keys selected", "warning")
            return

        key = selected[0]
        self._log.log(f"Fetching value for: {key}")
        self.app.run_async(
            self._bg_get_value,
            key,
            on_done=lambda v: self._show_value_popup(key, v),
            on_error=lambda e: self._log.log(f"Failed to read value: {e}", "error"),
        )

    def _bg_get_value(self, key: str) -> str:
        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        value = conn.kv_get(key)
        return value if value is not None else "(key not found)"

    def _show_value_popup(self, key: str, value: str):
        popup = ctk.CTkToplevel(self)
        popup.title(f"KV Value — {key}")
        popup.geometry("500x300")
        popup.resizable(True, True)
        popup.transient(self)
        popup.grab_set()

        popup.grid_columnconfigure(0, weight=1)
        popup.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            popup,
            text=key,
            font=ctk.CTkFont("Consolas", 12, weight="bold"),
            text_color=theme.COLORS["accent"],
        ).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        text_box = ctk.CTkTextbox(
            popup,
            font=ctk.CTkFont("Consolas", 11),
            fg_color=theme.COLORS["bg_deeper"],
            corner_radius=theme.CORNER_RADIUS_SMALL,
        )
        text_box.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="nsew")
        text_box.insert("1.0", value)

        ctk.CTkButton(
            popup,
            text="Copy Value",
            width=100,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=lambda: (
                self.clipboard_clear(),
                self.clipboard_append(value),
                self.app.show_toast("Value copied", "success"),
            ),
        ).grid(row=2, column=0, padx=15, pady=(0, 15), sticky="e")


class _AddKVDialog(ctk.CTkToplevel):
    """Dialog to add a new KV entry."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add KV Entry")
        self.geometry("420x160")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=theme.COLORS["bg_card"])

        self.key: str = ""
        self.value: str = ""

        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text="Key:",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=0, padx=(15, 6), pady=(15, 4), sticky="w")

        self._key_entry = ctk.CTkEntry(
            self,
            height=30,
            font=ctk.CTkFont(size=11),
            placeholder_text="e.g. dlc/EP01.zip",
        )
        self._key_entry.grid(row=0, column=1, padx=(0, 15), pady=(15, 4), sticky="ew")

        ctk.CTkLabel(
            self,
            text="Value:",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=1, column=0, padx=(15, 6), pady=4, sticky="w")

        self._val_entry = ctk.CTkEntry(
            self,
            height=30,
            font=ctk.CTkFont(size=11),
            placeholder_text="e.g. files/sims4/dlc/EP01.zip",
        )
        self._val_entry.grid(row=1, column=1, padx=(0, 15), pady=4, sticky="ew")
        self._val_entry.bind("<Return>", lambda _: self._ok())

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, columnspan=2, padx=15, pady=(8, 12), sticky="ew")

        ctk.CTkButton(
            btn_frame,
            text="Add",
            width=80,
            height=30,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._ok,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=70,
            height=30,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self.destroy,
        ).pack(side="right")

    def _ok(self):
        self.key = self._key_entry.get().strip()
        self.value = self._val_entry.get().strip()
        if self.key and self.value:
            self.destroy()
