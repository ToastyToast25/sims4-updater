"""Settings frame — credentials, paths, and preferences."""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import InfoCard, get_animator

if TYPE_CHECKING:
    from ..app import CDNManagerApp


class SettingsFrame(ctk.CTkFrame):
    def __init__(self, parent, app: CDNManagerApp):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Settings",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        ).grid(row=0, column=0, padx=theme.SECTION_PAD, pady=(20, 15), sticky="w")

        # Scrollable content
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=theme.COLORS["separator"],
            scrollbar_button_hover_color=theme.COLORS["accent"],
        )
        scroll.grid(row=1, column=0, padx=0, pady=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        config = self.app.config_data

        # -- Connection Settings card --
        conn_card = InfoCard(scroll, fg_color=theme.COLORS["bg_card"])
        conn_card.grid(row=0, column=0, padx=theme.SECTION_PAD, pady=(0, 15), sticky="ew")
        conn_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            conn_card, text="Seedbox Connection",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=(theme.CARD_PAD_Y, 10), sticky="w")

        self._entries = {}
        fields = [
            ("whatbox_host", "Host", config.whatbox_host, False),
            ("whatbox_port", "Port", str(config.whatbox_port), False),
            ("whatbox_user", "Username", config.whatbox_user, False),
            ("whatbox_pass", "Password", config.whatbox_pass, True),
        ]
        for i, (key, label, value, is_secret) in enumerate(fields):
            ctk.CTkLabel(
                conn_card, text=f"{label}:",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=i + 1, column=0, padx=(theme.CARD_PAD_X, 8), pady=4, sticky="w")

            entry = ctk.CTkEntry(
                conn_card, font=ctk.CTkFont(size=12), height=32,
                show="*" if is_secret else "",
            )
            entry.grid(row=i + 1, column=1, padx=(0, theme.CARD_PAD_X), pady=4, sticky="ew")
            if value:
                entry.insert(0, value)
            self._entries[key] = entry

        # -- Cloudflare Settings card --
        cf_card = InfoCard(scroll, fg_color=theme.COLORS["bg_card"])
        cf_card.grid(row=1, column=0, padx=theme.SECTION_PAD, pady=(0, 15), sticky="ew")
        cf_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            cf_card, text="Cloudflare Settings",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=(theme.CARD_PAD_Y, 10), sticky="w")

        cf_fields = [
            ("cloudflare_account_id", "Account ID", config.cloudflare_account_id, False),
            ("cloudflare_api_token", "API Token", config.cloudflare_api_token, True),
            ("cloudflare_kv_namespace_id", "KV Namespace ID", config.cloudflare_kv_namespace_id, False),
        ]
        for i, (key, label, value, is_secret) in enumerate(cf_fields):
            ctk.CTkLabel(
                cf_card, text=f"{label}:",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=i + 1, column=0, padx=(theme.CARD_PAD_X, 8), pady=4, sticky="w")

            entry = ctk.CTkEntry(
                cf_card, font=ctk.CTkFont(size=12), height=32,
                show="*" if is_secret else "",
            )
            entry.grid(row=i + 1, column=1, padx=(0, theme.CARD_PAD_X), pady=4, sticky="ew")
            if value:
                entry.insert(0, value)
            self._entries[key] = entry

        # -- Paths card --
        paths_card = InfoCard(scroll, fg_color=theme.COLORS["bg_card"])
        paths_card.grid(row=2, column=0, padx=theme.SECTION_PAD, pady=(0, 15), sticky="ew")
        paths_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            paths_card, text="Paths",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, padx=theme.CARD_PAD_X, pady=(theme.CARD_PAD_Y, 10), sticky="w")

        for i, (key, label, value, browse_title) in enumerate([
            ("game_dir", "Game Directory", config.game_dir, "Select Sims 4 Game Directory"),
            ("patcher_dir", "Patcher Directory", config.patcher_dir, "Select Patcher Directory"),
        ]):
            ctk.CTkLabel(
                paths_card, text=f"{label}:",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=i * 2 + 1, column=0, padx=theme.CARD_PAD_X, pady=(4, 2), sticky="w")

            path_frame = ctk.CTkFrame(paths_card, fg_color="transparent")
            path_frame.grid(
                row=i * 2 + 2, column=0, padx=theme.CARD_PAD_X,
                pady=(0, 8), sticky="ew",
            )
            path_frame.grid_columnconfigure(0, weight=1)

            entry = ctk.CTkEntry(path_frame, font=ctk.CTkFont(size=12), height=32)
            entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")
            if value:
                entry.insert(0, value)
            self._entries[key] = entry

            ctk.CTkButton(
                path_frame, text="Browse", height=32, width=70,
                corner_radius=theme.CORNER_RADIUS_SMALL,
                fg_color=theme.COLORS["bg_card_alt"],
                hover_color=theme.COLORS["card_hover"],
                command=lambda t=browse_title, e=entry: self._browse(t, e),
            ).grid(row=0, column=1)

        # -- Buttons --
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=theme.SECTION_PAD, pady=(0, 15), sticky="ew")

        self._save_btn = ctk.CTkButton(
            btn_frame, text="Save Settings",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._save,
        )
        self._save_btn.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame, text="Test Connection",
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._test_connection,
        ).pack(side="left")

    def on_show(self):
        pass

    def _browse(self, title: str, entry: ctk.CTkEntry):
        from tkinter import filedialog
        path = filedialog.askdirectory(title=title)
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)

    def _save(self):
        config = self.app.config_data
        config.whatbox_host = self._entries["whatbox_host"].get()
        try:
            config.whatbox_port = int(self._entries["whatbox_port"].get() or 22)
        except ValueError:
            self.app.show_toast("Port must be a number", "error")
            return
        config.whatbox_user = self._entries["whatbox_user"].get()
        config.whatbox_pass = self._entries["whatbox_pass"].get()
        config.cloudflare_account_id = self._entries["cloudflare_account_id"].get()
        config.cloudflare_api_token = self._entries["cloudflare_api_token"].get()
        config.cloudflare_kv_namespace_id = self._entries["cloudflare_kv_namespace_id"].get()
        config.game_dir = self._entries["game_dir"].get()
        config.patcher_dir = self._entries["patcher_dir"].get()
        config.save()
        config.save_credentials()

        # Flash save button green
        animator = get_animator()
        animator.cancel_all(self._save_btn, tag="save_flash")
        animator.animate_color(
            self._save_btn, "fg_color",
            theme.COLORS["success"], theme.COLORS["accent"],
            600, tag="save_flash",
        )
        self.app.show_toast("Settings saved", "success")

    def _test_connection(self):
        self.app.show_toast("Testing connection...", "info")
        self.app.run_async(
            self._bg_test,
            on_done=self._on_test_done,
            on_error=lambda e: self.app.show_toast(f"Test failed: {e}", "error"),
        )

    def _bg_test(self):
        results = {"sftp": False, "kv": False}
        config = self.app.config_data

        # Test SFTP
        try:
            import paramiko
            transport = paramiko.Transport((config.whatbox_host, config.whatbox_port))
            transport.connect(username=config.whatbox_user, password=config.whatbox_pass)
            transport.close()
            results["sftp"] = True
        except Exception:
            pass

        # Test KV
        try:
            import json
            import urllib.request
            url = (
                f"https://api.cloudflare.com/client/v4/accounts/"
                f"{config.cloudflare_account_id}/storage/kv/namespaces/"
                f"{config.cloudflare_kv_namespace_id}/keys?limit=1"
            )
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {config.cloudflare_api_token}"},
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            results["kv"] = data.get("success", False)
        except Exception:
            pass

        return results

    def _on_test_done(self, results):
        sftp = results["sftp"]
        kv = results["kv"]
        if sftp and kv:
            self.app.show_toast("Both connections successful!", "success")
        elif sftp:
            self.app.show_toast("SFTP OK, Cloudflare KV failed", "warning")
        elif kv:
            self.app.show_toast("Cloudflare KV OK, SFTP failed", "warning")
        else:
            self.app.show_toast("Both connections failed", "error")
