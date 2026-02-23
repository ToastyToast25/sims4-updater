"""Dashboard frame — CDN health overview and quick actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import InfoCard, LogPanel, StatusBadge

if TYPE_CHECKING:
    from ..app import CDNManagerApp


class DashboardFrame(ctk.CTkFrame):
    def __init__(self, parent, app: CDNManagerApp):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._refreshing = False
        self._auto_refresh_id = None
        self._auto_refresh_enabled = True

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_ui()

    def _build_ui(self):
        # Title
        ctk.CTkLabel(
            self,
            text="Dashboard",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        ).grid(row=0, column=0, padx=theme.SECTION_PAD, pady=(20, 15), sticky="w")

        # Cards grid (2x2)
        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.grid(row=1, column=0, padx=theme.SECTION_PAD, sticky="ew")
        cards.grid_columnconfigure(0, weight=1)
        cards.grid_columnconfigure(1, weight=1)

        # Connection card
        conn_card = InfoCard(cards, fg_color=theme.COLORS["bg_card"])
        conn_card.grid(row=0, column=0, padx=(0, 8), pady=(0, 8), sticky="ew")
        conn_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            conn_card,
            text="Connection",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            padx=theme.CARD_PAD_X,
            pady=(theme.CARD_PAD_Y, 8),
            sticky="w",
        )

        ctk.CTkLabel(
            conn_card,
            text="Seedbox (SFTP):",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=1, column=0, padx=(theme.CARD_PAD_X, 4), pady=2, sticky="w")
        self._sftp_badge = StatusBadge(conn_card, text="Unknown", style="muted")
        self._sftp_badge.grid(row=1, column=1, padx=(0, theme.CARD_PAD_X), pady=2, sticky="e")

        ctk.CTkLabel(
            conn_card,
            text="Cloudflare KV:",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=2, column=0, padx=(theme.CARD_PAD_X, 4), pady=2, sticky="w")
        self._kv_badge = StatusBadge(conn_card, text="Unknown", style="muted")
        self._kv_badge.grid(row=2, column=1, padx=(0, theme.CARD_PAD_X), pady=2, sticky="e")

        ctk.CTkLabel(
            conn_card,
            text="Disk Usage:",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=3, column=0, padx=(theme.CARD_PAD_X, 4), pady=(2, theme.CARD_PAD_Y), sticky="w")
        self._disk_label = ctk.CTkLabel(
            conn_card,
            text="—",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text"],
        )
        self._disk_label.grid(
            row=3,
            column=1,
            padx=(0, theme.CARD_PAD_X),
            pady=(2, theme.CARD_PAD_Y),
            sticky="e",
        )

        # CDN Stats card
        stats_card = InfoCard(cards, fg_color=theme.COLORS["bg_card"])
        stats_card.grid(row=0, column=1, padx=(8, 0), pady=(0, 8), sticky="ew")
        stats_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            stats_card,
            text="CDN Contents",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            padx=theme.CARD_PAD_X,
            pady=(theme.CARD_PAD_Y, 8),
            sticky="w",
        )

        self._stats_labels = {}
        for i, (key, label) in enumerate(
            [
                ("dlc", "DLC Packs"),
                ("lang", "Languages"),
                ("patch", "Patches"),
                ("archive", "Archives"),
            ]
        ):
            ctk.CTkLabel(
                stats_card,
                text=f"{label}:",
                font=ctk.CTkFont(*theme.FONT_SMALL),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=i + 1, column=0, padx=(theme.CARD_PAD_X, 4), pady=2, sticky="w")
            val = ctk.CTkLabel(
                stats_card,
                text="—",
                font=ctk.CTkFont(*theme.FONT_SMALL),
                text_color=theme.COLORS["text"],
            )
            val.grid(row=i + 1, column=1, padx=(0, theme.CARD_PAD_X), pady=2, sticky="e")
            self._stats_labels[key] = val

        # Version card
        ver_card = InfoCard(cards, fg_color=theme.COLORS["bg_card"])
        ver_card.grid(row=1, column=0, padx=(0, 8), pady=(8, 0), sticky="ew")
        ver_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            ver_card,
            text="Current Version",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            padx=theme.CARD_PAD_X,
            pady=(theme.CARD_PAD_Y, 8),
            sticky="w",
        )

        self._version_label = ctk.CTkLabel(
            ver_card,
            text="—",
            font=ctk.CTkFont(*theme.FONT_HEADING),
            text_color=theme.COLORS["accent"],
        )
        self._version_label.grid(
            row=1,
            column=0,
            columnspan=2,
            padx=theme.CARD_PAD_X,
            pady=(0, theme.CARD_PAD_Y),
            sticky="w",
        )

        # Quick actions card
        actions_card = InfoCard(cards, fg_color=theme.COLORS["bg_card"])
        actions_card.grid(row=1, column=1, padx=(8, 0), pady=(8, 0), sticky="ew")

        ctk.CTkLabel(
            actions_card,
            text="Quick Actions",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=0, column=0, padx=theme.CARD_PAD_X, pady=(theme.CARD_PAD_Y, 8), sticky="w")

        btn_frame = ctk.CTkFrame(actions_card, fg_color="transparent")
        btn_frame.grid(
            row=1,
            column=0,
            padx=theme.CARD_PAD_X,
            pady=(0, theme.CARD_PAD_Y),
            sticky="ew",
        )

        ctk.CTkButton(
            btn_frame,
            text="Refresh",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._refresh,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_frame,
            text="Upload Manifest",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._upload_manifest,
        ).pack(side="left", padx=(0, 6))

        self._auto_refresh_btn = ctk.CTkButton(
            btn_frame,
            text="Auto: ON",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["success"],
            hover_color="#3ae882",
            text_color="#1a1a2e",
            width=80,
            command=self._toggle_auto_refresh,
        )
        self._auto_refresh_btn.pack(side="left")

        # Log panel
        self._log = LogPanel(self)
        self._log.grid(row=2, column=0, padx=theme.SECTION_PAD, pady=(15, 15), sticky="nsew")

    def on_show(self):
        self._start_auto_refresh()

    def on_hide(self):
        self._stop_auto_refresh()

    def _start_auto_refresh(self):
        self._stop_auto_refresh()
        self._refresh()
        if self._auto_refresh_enabled:
            self._auto_refresh_id = self.after(30000, self._start_auto_refresh)

    def _stop_auto_refresh(self):
        if self._auto_refresh_id is not None:
            self.after_cancel(self._auto_refresh_id)
            self._auto_refresh_id = None

    def _toggle_auto_refresh(self):
        self._auto_refresh_enabled = not self._auto_refresh_enabled
        if self._auto_refresh_enabled:
            self._auto_refresh_btn.configure(
                text="Auto: ON",
                fg_color=theme.COLORS["success"],
                hover_color="#3ae882",
                text_color="#1a1a2e",
            )
            self._start_auto_refresh()
        else:
            self._auto_refresh_btn.configure(
                text="Auto: OFF",
                fg_color=theme.COLORS["bg_card_alt"],
                hover_color=theme.COLORS["card_hover"],
                text_color=theme.COLORS["text_muted"],
            )
            self._stop_auto_refresh()

    def _refresh(self):
        if self._refreshing:
            return
        self._refreshing = True
        self._log.log("Refreshing CDN status...")
        self.app.run_async(
            self._bg_refresh,
            on_done=self._on_refresh_done,
            on_error=self._on_refresh_error,
        )

    def _bg_refresh(self):
        """Background: fetch CDN stats."""
        import json
        import urllib.request

        results = {
            "sftp": False,
            "kv": False,
            "manifest": None,
            "kv_keys": [],
            "disk_usage": "",
        }

        # Test Cloudflare KV
        config = self.app.config_data
        try:
            account_id = config.cloudflare_account_id
            ns_id = config.cloudflare_kv_namespace_id
            token = config.cloudflare_api_token
            if account_id and ns_id and token:
                url = (
                    f"https://api.cloudflare.com/client/v4/accounts/"
                    f"{account_id}/storage/kv/namespaces/{ns_id}/keys?limit=1000"
                )
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
                resp = urllib.request.urlopen(req, timeout=15)
                data = json.loads(resp.read())
                results["kv"] = True
                results["kv_keys"] = [k["name"] for k in data.get("result", [])]

                # Handle pagination
                cursor = data.get("result_info", {}).get("cursor")
                while cursor:
                    paged_url = f"{url}&cursor={cursor}"
                    req = urllib.request.Request(
                        paged_url,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    resp = urllib.request.urlopen(req, timeout=15)
                    data = json.loads(resp.read())
                    results["kv_keys"].extend(k["name"] for k in data.get("result", []))
                    cursor = data.get("result_info", {}).get("cursor")
        except Exception:
            results["kv"] = False

        # Test SFTP + disk usage
        try:
            import paramiko

            transport = paramiko.Transport((config.whatbox_host, config.whatbox_port))
            transport.connect(username=config.whatbox_user, password=config.whatbox_pass)
            transport.close()
            results["sftp"] = True

            # Get disk usage via SSH
            try:
                from cdn_manager.backend.connection import (
                    _KNOWN_HOSTS_FILE,
                    _get_host_keys_policy,
                )

                client = paramiko.SSHClient()
                if _KNOWN_HOSTS_FILE.is_file():
                    client.load_host_keys(str(_KNOWN_HOSTS_FILE))
                client.set_missing_host_key_policy(_get_host_keys_policy())
                client.connect(
                    hostname=config.whatbox_host,
                    port=config.whatbox_port,
                    username=config.whatbox_user,
                    password=config.whatbox_pass,
                    timeout=10,
                )
                _, stdout, _ = client.exec_command("du -sh files/sims4/ 2>/dev/null")
                output = stdout.read().decode("utf-8").strip()
                if output:
                    results["disk_usage"] = output.split()[0]  # e.g. "12G"
                client.close()
            except Exception:
                pass
        except Exception:
            results["sftp"] = False

        # Fetch manifest
        try:
            req = urllib.request.Request(
                "https://cdn.hyperabyss.com/manifest.json",
                headers={"User-Agent": "CDNManager/1.0"},
            )
            resp = urllib.request.urlopen(req, timeout=15)
            results["manifest"] = json.loads(resp.read().decode("utf-8"))
        except Exception:
            pass

        return results

    def _on_refresh_done(self, results: dict):
        # Connection badges
        if results["sftp"]:
            self._sftp_badge.set_status("Connected", "success")
            self._log.log("Seedbox SFTP: connected", "success")
        else:
            self._sftp_badge.set_status("Offline", "error")
            self._log.log("Seedbox SFTP: connection failed", "error")

        if results["kv"]:
            self._kv_badge.set_status("Connected", "success")
            self._log.log("Cloudflare KV: connected", "success")
        else:
            self._kv_badge.set_status("Offline", "error")
            self._log.log("Cloudflare KV: connection failed", "error")

        # Disk usage
        disk = results.get("disk_usage", "")
        if disk:
            self._disk_label.configure(text=disk)
            self._log.log(f"Seedbox disk usage: {disk}")
        else:
            self._disk_label.configure(text="—")

        # CDN stats from KV keys
        keys = results.get("kv_keys", [])
        dlc_count = sum(1 for k in keys if k.startswith("dlc/"))
        lang_count = sum(1 for k in keys if k.startswith("language/"))
        patch_count = sum(1 for k in keys if k.startswith("patches/"))
        archive_count = sum(
            1 for k in keys if k.startswith("archives/") and k.endswith("manifest.json")
        )

        self._stats_labels["dlc"].configure(text=str(dlc_count))
        self._stats_labels["lang"].configure(text=str(lang_count))
        self._stats_labels["patch"].configure(text=str(patch_count))
        self._stats_labels["archive"].configure(text=str(archive_count))

        self._log.log(
            f"CDN contents: {dlc_count} DLCs, {lang_count} languages, "
            f"{patch_count} patches, {archive_count} archives",
        )

        # Version from manifest
        manifest = results.get("manifest")
        if manifest:
            latest = manifest.get("latest", "")
            game_latest = manifest.get("game_latest", "")
            version_text = latest or "(not set)"
            if game_latest and game_latest != latest:
                version_text += f"  (game: {game_latest})"
            self._version_label.configure(text=version_text)
            self._log.log(f"Manifest latest: {latest or '(empty)'}")
        else:
            self._version_label.configure(text="Failed to fetch")
            self._log.log("Failed to fetch manifest", "error")

        # Store connection state on app for status bar
        self.app._connection_state = {
            "sftp": results["sftp"],
            "kv": results["kv"],
        }
        if hasattr(self.app, "_update_status_bar_connections"):
            self.app._update_status_bar_connections()

        self._refreshing = False
        self._log.log("Refresh complete", "success")

    def _on_refresh_error(self, error):
        self._refreshing = False
        self._log.log(f"Refresh failed: {error}", "error")
        self.app.show_toast(f"Refresh failed: {error}", "error")

    def _upload_manifest(self):
        self._log.log("Uploading manifest...")
        self.app.run_async(
            self._bg_upload_manifest,
            on_done=lambda r: (
                self._log.log("Manifest uploaded successfully", "success"),
                self.app.show_toast("Manifest uploaded", "success"),
            ),
            on_error=lambda e: (
                self._log.log(f"Upload failed: {e}", "error"),
                self.app.show_toast(f"Upload failed: {e}", "error"),
            ),
        )

    def _bg_upload_manifest(self):
        from ..backend.connection import ConnectionManager
        from ..config import CONFIG_DIR

        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        manifest_path = CONFIG_DIR / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"manifest.json not found at {manifest_path}")

        conn.publish_manifest(manifest_path)
