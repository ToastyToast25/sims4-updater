"""
DLC Unlocker tab — install/uninstall the EA DLC Unlocker with real-time logs.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import InfoCard, StatusBadge

if TYPE_CHECKING:
    from ..app import App


class UnlockerFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._status = None  # UnlockerStatus or None
        self._busy = False

        # ── Top section (fixed) ──────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="new", padx=0, pady=0)
        top.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(
            top,
            text="DLC Unlocker",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, padx=30, pady=(20, 4), sticky="w")

        ctk.CTkLabel(
            top,
            text="Install the EA DLC Unlocker to unlock DLC content",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=1, column=0, padx=30, pady=(0, 12), sticky="w")

        # ── Status card ──────────────────────────────────────────
        self._card = InfoCard(
            top,
            fg_color=theme.COLORS["bg_card"],
        )
        self._card.grid(row=2, column=0, padx=30, pady=(0, 10), sticky="ew")
        self._card.grid_columnconfigure(1, weight=1)

        # Row 0: Client detected
        ctk.CTkLabel(
            self._card, text="Client",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, padx=(theme.CARD_PAD_X, 8), pady=(theme.CARD_PAD_Y, 4), sticky="w")

        self._client_badge = StatusBadge(self._card, text="Detecting...", style="muted")
        self._client_badge.grid(row=0, column=1, padx=0, pady=(theme.CARD_PAD_Y, 4), sticky="w")

        # Row 1: Unlocker status
        ctk.CTkLabel(
            self._card, text="Status",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=1, column=0, padx=(theme.CARD_PAD_X, 8), pady=4, sticky="w")

        self._status_badge = StatusBadge(self._card, text="Unknown", style="muted")
        self._status_badge.grid(row=1, column=1, padx=0, pady=4, sticky="w")

        # Row 2: Admin status
        ctk.CTkLabel(
            self._card, text="Admin",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=2, column=0, padx=(theme.CARD_PAD_X, 8), pady=(4, theme.CARD_PAD_Y), sticky="w")

        from ...core.unlocker import is_admin
        self._is_admin = is_admin()
        admin_text = "Elevated" if self._is_admin else "Not Elevated"
        admin_style = "success" if self._is_admin else "warning"
        self._admin_badge = StatusBadge(self._card, text=admin_text, style=admin_style)
        self._admin_badge.grid(row=2, column=1, padx=0, pady=(4, theme.CARD_PAD_Y), sticky="w")

        # ── Action buttons ───────────────────────────────────────
        btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=30, pady=(0, 10), sticky="ew")
        btn_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self._install_btn = ctk.CTkButton(
            btn_frame,
            text="Install Unlocker",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_install,
        )
        self._install_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self._uninstall_btn = ctk.CTkButton(
            btn_frame,
            text="Uninstall",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_uninstall,
        )
        self._uninstall_btn.grid(row=0, column=1, padx=5, sticky="ew")

        self._configs_btn = ctk.CTkButton(
            btn_frame,
            text="Open Configs",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_open_configs,
        )
        self._configs_btn.grid(row=0, column=2, padx=(5, 0), sticky="ew")

        # ── Log viewer (fills remaining space) ───────────────────
        log_header = ctk.CTkFrame(self, fg_color="transparent")
        log_header.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 15))
        log_header.grid_columnconfigure(0, weight=1)
        log_header.grid_rowconfigure(1, weight=1)

        header_row = ctk.CTkFrame(log_header, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_row,
            text="Activity Log",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, sticky="w")

        self._clear_btn = ctk.CTkButton(
            header_row,
            text="Clear",
            font=ctk.CTkFont(size=11),
            height=24,
            width=60,
            corner_radius=4,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._clear_log,
        )
        self._clear_btn.grid(row=0, column=1, sticky="e")

        self._log_box = ctk.CTkTextbox(
            log_header,
            font=ctk.CTkFont(*theme.FONT_MONO),
            fg_color=theme.COLORS["bg_deeper"],
            text_color=theme.COLORS["text_muted"],
            border_width=1,
            border_color=theme.COLORS["border"],
            corner_radius=theme.CORNER_RADIUS_SMALL,
            state="disabled",
            wrap="word",
        )
        self._log_box.grid(row=1, column=0, sticky="nsew")

    # ── Logging ──────────────────────────────────────────────────

    def _log(self, message: str):
        """Append a line to the log viewer (thread-safe via enqueue)."""
        self._log_box.configure(state="normal")
        self._log_box.insert("end", message + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # ── Status Refresh ───────────────────────────────────────────

    def on_show(self):
        """Called when frame becomes visible."""
        self._refresh_status()

    def _refresh_status(self):
        """Detect client and update status badges."""
        from ...core.unlocker import get_status

        def _bg():
            return get_status(log=self._enqueue_log)

        def _done(status):
            self._status = status
            self._update_badges()

        def _err(e):
            self._status = None
            self._client_badge.set_status("Not Found", "error")
            self._status_badge.set_status("N/A", "muted")
            self._enqueue_log(f"Detection failed: {e}")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    def _enqueue_log(self, msg: str):
        """Thread-safe log — enqueue to GUI thread."""
        self.app._enqueue_gui(self._log, msg)

    def _update_badges(self):
        """Update UI badges from self._status."""
        s = self._status
        if s is None:
            return

        # Client badge
        self._client_badge.set_status(s.client_name, "info")

        # Install status
        if s.dll_installed and s.config_installed:
            label = "Installed"
            style = "success"
            if not s.task_exists:
                label = "Installed (task missing)"
                style = "warning"
        elif s.dll_installed:
            label = "Partial (config missing)"
            style = "warning"
        elif s.config_installed:
            label = "Partial (DLL missing)"
            style = "warning"
        else:
            label = "Not Installed"
            style = "error"

        self._status_badge.set_status(label, style)

    # ── Actions ──────────────────────────────────────────────────

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._install_btn.configure(state=state)
        self._uninstall_btn.configure(state=state)

    def _on_install(self):
        if self._busy:
            return
        if not self._is_admin:
            self.app.show_toast(
                "Run as Administrator to install the unlocker.", "warning"
            )
            self._log("Install requires administrator privileges. "
                       "Right-click the app and select 'Run as administrator'.")
            return
        self._set_busy(True)
        self._log("--- Installing DLC Unlocker ---")

        from ...core.unlocker import install

        def _bg():
            install(log=self._enqueue_log)

        def _done(_):
            self._set_busy(False)
            self.app.show_toast("DLC Unlocker installed!", "success")
            self._refresh_status()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Install failed: {e}")
            self.app.show_toast(f"Install failed: {e}", "error")
            self._refresh_status()

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    def _on_uninstall(self):
        if self._busy:
            return
        if not self._is_admin:
            self.app.show_toast(
                "Run as Administrator to uninstall the unlocker.", "warning"
            )
            self._log("Uninstall requires administrator privileges. "
                       "Right-click the app and select 'Run as administrator'.")
            return

        # Confirmation dialog
        confirmed = tk.messagebox.askyesno(
            "Confirm Uninstall",
            "Are you sure you want to uninstall the DLC Unlocker?\n\n"
            "This will remove the unlocker DLL, config files, and scheduled task.",
            parent=self.winfo_toplevel(),
        )
        if not confirmed:
            return

        self._set_busy(True)
        self._log("--- Uninstalling DLC Unlocker ---")

        from ...core.unlocker import uninstall

        def _bg():
            uninstall(log=self._enqueue_log)

        def _done(_):
            self._set_busy(False)
            self.app.show_toast("DLC Unlocker uninstalled.", "success")
            self._refresh_status()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Uninstall failed: {e}")
            self.app.show_toast(f"Uninstall failed: {e}", "error")
            self._refresh_status()

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    def _on_open_configs(self):
        from ...core.unlocker import open_configs_folder
        if not open_configs_folder():
            self.app.show_toast(
                "Configs folder not found. Install the Unlocker first.", "warning"
            )
