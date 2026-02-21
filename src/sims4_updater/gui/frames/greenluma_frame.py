"""
GreenLuma Manager tab — manage AppList, config.vdf keys, manifests, and launch Steam.
"""

from __future__ import annotations

import tkinter as tk
import tkinter.messagebox
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import InfoCard, StatusBadge

if TYPE_CHECKING:
    from ..app import App


class GreenLumaFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._busy = False
        self._steam_info = None
        self._gl_status = None
        self._readiness: list = []

        # ── Top section (fixed) ──────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="new", padx=0, pady=0)
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top,
            text="GreenLuma Manager",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, padx=30, pady=(20, 4), sticky="w")

        ctk.CTkLabel(
            top,
            text="Download legit DLC content directly from Steam via GreenLuma",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=1, column=0, padx=30, pady=(0, 12), sticky="w")

        # ── Status Card ──────────────────────────────────────────
        self._card = InfoCard(top, fg_color=theme.COLORS["bg_card"])
        self._card.grid(row=2, column=0, padx=30, pady=(0, 10), sticky="ew")
        self._card.grid_columnconfigure(1, weight=1)

        # Row 0: Steam Path
        ctk.CTkLabel(
            self._card, text="Steam Path",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, padx=(theme.CARD_PAD_X, 8),
               pady=(theme.CARD_PAD_Y, 4), sticky="w")

        self._steam_path_badge = StatusBadge(
            self._card, text="Detecting...", style="muted"
        )
        self._steam_path_badge.grid(
            row=0, column=1, padx=0, pady=(theme.CARD_PAD_Y, 4), sticky="w"
        )

        # Row 1: GreenLuma Status + Version
        ctk.CTkLabel(
            self._card, text="GreenLuma",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=1, column=0, padx=(theme.CARD_PAD_X, 8), pady=4, sticky="w")

        self._gl_badge = StatusBadge(
            self._card, text="Unknown", style="muted"
        )
        self._gl_badge.grid(row=1, column=1, padx=0, pady=4, sticky="w")

        # Row 2: Steam Running
        ctk.CTkLabel(
            self._card, text="Steam",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=2, column=0, padx=(theme.CARD_PAD_X, 8), pady=4, sticky="w")

        self._steam_status_badge = StatusBadge(
            self._card, text="Checking...", style="muted"
        )
        self._steam_status_badge.grid(row=2, column=1, padx=0, pady=4, sticky="w")

        # Row 3: Summary counts
        ctk.CTkLabel(
            self._card, text="Summary",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=3, column=0, padx=(theme.CARD_PAD_X, 8),
               pady=(4, theme.CARD_PAD_Y), sticky="w")

        self._summary_badge = StatusBadge(
            self._card, text="...", style="muted"
        )
        self._summary_badge.grid(
            row=3, column=1, padx=0, pady=(4, theme.CARD_PAD_Y), sticky="w"
        )

        # ── Action Buttons ───────────────────────────────────────
        btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=30, pady=(0, 10), sticky="ew")
        btn_frame.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        self._install_btn = ctk.CTkButton(
            btn_frame,
            text="Install (Normal)",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=lambda: self._on_install_gl(stealth=False),
        )
        self._install_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self._install_stealth_btn = ctk.CTkButton(
            btn_frame,
            text="Install (Stealth)",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=lambda: self._on_install_gl(stealth=True),
        )
        self._install_stealth_btn.grid(row=0, column=1, padx=5, sticky="ew")

        self._uninstall_btn = ctk.CTkButton(
            btn_frame,
            text="Uninstall GL",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_uninstall_gl,
        )
        self._uninstall_btn.grid(row=0, column=2, padx=5, sticky="ew")

        self._launch_btn = ctk.CTkButton(
            btn_frame,
            text="Launch Steam",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_launch_gl,
        )
        self._launch_btn.grid(row=0, column=3, padx=5, sticky="ew")

        self._apply_lua_btn = ctk.CTkButton(
            btn_frame,
            text="Apply LUA",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_apply_lua,
        )
        self._apply_lua_btn.grid(row=0, column=4, padx=5, sticky="ew")

        self._fix_btn = ctk.CTkButton(
            btn_frame,
            text="Fix AppList",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_fix_applist,
        )
        self._fix_btn.grid(row=0, column=5, padx=(5, 0), sticky="ew")

        # ── Scrollable body (DLC readiness + log) ────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 15))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        # ── DLC Readiness List ───────────────────────────────────
        readiness_container = ctk.CTkFrame(body, fg_color="transparent")
        readiness_container.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        readiness_container.grid_columnconfigure(0, weight=1)
        readiness_container.grid_rowconfigure(1, weight=1)

        readiness_header = ctk.CTkFrame(readiness_container, fg_color="transparent")
        readiness_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        readiness_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            readiness_header,
            text="DLC Readiness",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, sticky="w")

        # Filter segmented button
        self._filter_var = tk.StringVar(value="All")
        filter_frame = ctk.CTkFrame(readiness_header, fg_color="transparent")
        filter_frame.grid(row=0, column=1, sticky="e")

        for i, label in enumerate(("All", "Ready", "Incomplete")):
            btn = ctk.CTkButton(
                filter_frame,
                text=label,
                font=ctk.CTkFont(size=11),
                height=24,
                width=70,
                corner_radius=4,
                fg_color=theme.COLORS["accent"] if label == "All"
                else theme.COLORS["bg_card_alt"],
                hover_color=theme.COLORS["card_hover"],
                command=lambda lbl=label: self._set_filter(lbl),
            )
            btn.grid(row=0, column=i, padx=2)
        self._filter_buttons = filter_frame.winfo_children()

        self._readiness_box = ctk.CTkTextbox(
            readiness_container,
            font=ctk.CTkFont(*theme.FONT_MONO),
            fg_color=theme.COLORS["bg_deeper"],
            text_color=theme.COLORS["text_muted"],
            border_width=1,
            border_color=theme.COLORS["border"],
            corner_radius=theme.CORNER_RADIUS_SMALL,
            state="disabled",
            wrap="none",
        )
        self._readiness_box.grid(row=1, column=0, sticky="nsew")

        # ── Activity Log ─────────────────────────────────────────
        log_container = ctk.CTkFrame(body, fg_color="transparent")
        log_container.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        log_container.grid_columnconfigure(0, weight=1)
        log_container.grid_rowconfigure(1, weight=1)

        log_header = ctk.CTkFrame(log_container, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        log_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_header,
            text="Activity Log",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, sticky="w")

        self._clear_btn = ctk.CTkButton(
            log_header,
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
            log_container,
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
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"[{ts}] {message}\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _enqueue_log(self, msg: str):
        self.app._enqueue_gui(self._log, msg)

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # ── Lifecycle ────────────────────────────────────────────────

    def on_show(self):
        self._refresh_status()

    def _refresh_status(self):
        self._steam_path_badge.set_status("Scanning...", "muted")

        def _bg():
            from ...greenluma.installer import detect_greenluma
            from ...greenluma.steam import detect_steam_path, get_steam_info
            from ...greenluma.steam import is_steam_running as _is_running

            # Detect steam path (from settings or auto-detect)
            steam_path_str = self.app.settings.steam_path
            if steam_path_str and Path(steam_path_str).is_dir():
                steam_path = Path(steam_path_str)
            else:
                steam_path = detect_steam_path()

            if not steam_path:
                return None, None, False, [], steam_path

            info = get_steam_info(steam_path)
            gl_status = detect_greenluma(steam_path)
            running = _is_running()

            # Check DLC readiness
            readiness = []
            try:
                from ...dlc.catalog import DLCCatalog
                from ...greenluma.orchestrator import GreenLumaOrchestrator
                catalog = DLCCatalog()
                orch = GreenLumaOrchestrator(info)
                readiness = orch.check_readiness(catalog)
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug("DLC readiness check failed: %s", e)

            return info, gl_status, running, readiness, steam_path

        def _done(result):
            info, gl_status, running, readiness, steam_path = result

            # Save auto-detected steam path (on GUI thread — thread-safe)
            if steam_path and not self.app.settings.steam_path:
                self.app.settings.steam_path = str(steam_path)
                self.app.settings.save()

            if info is None:
                self._steam_path_badge.set_status("Not Found", "error")
                self._gl_badge.set_status("N/A", "muted")
                self._steam_status_badge.set_status("N/A", "muted")
                self._summary_badge.set_status(
                    "Set Steam path in Settings", "warning"
                )
                return

            self._steam_info = info
            self._gl_status = gl_status
            self._readiness = readiness

            short = str(info.steam_path)
            if len(short) > 40:
                short = "..." + short[-37:]
            self._steam_path_badge.set_status(short, "success")

            if gl_status and gl_status.installed:
                mode = gl_status.mode.title()
                ver = gl_status.version
                self._gl_badge.set_status(
                    f"v{ver} ({mode})", "success"
                )
            else:
                self._gl_badge.set_status("Not Installed", "warning")

            if running:
                self._steam_status_badge.set_status("Running", "warning")
            else:
                self._steam_status_badge.set_status("Not Running", "success")

            # Summary
            if readiness:
                ready_count = sum(1 for r in readiness if r.ready)
                total = len(readiness)
                if ready_count == total:
                    self._summary_badge.set_status(
                        f"All {total} DLCs ready", "success"
                    )
                else:
                    self._summary_badge.set_status(
                        f"{ready_count}/{total} DLCs ready", "warning"
                    )
            else:
                self._summary_badge.set_status("No DLC data", "muted")

            self._update_readiness_display()

        def _err(e):
            self._steam_path_badge.set_status("Error", "error")
            self._enqueue_log(f"Detection failed: {e}")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Readiness Display ────────────────────────────────────────

    def _set_filter(self, label: str):
        self._filter_var.set(label)
        for btn in self._filter_buttons:
            if btn.cget("text") == label:
                btn.configure(fg_color=theme.COLORS["accent"])
            else:
                btn.configure(fg_color=theme.COLORS["bg_card_alt"])
        self._update_readiness_display()

    def _update_readiness_display(self):
        filt = self._filter_var.get()
        items = self._readiness

        if filt == "Ready":
            items = [r for r in items if r.ready]
        elif filt == "Incomplete":
            items = [r for r in items if not r.ready]

        self._readiness_box.configure(state="normal")
        self._readiness_box.delete("1.0", "end")

        if not items:
            self._readiness_box.insert("end", "No DLCs to display.\n")
            self._readiness_box.configure(state="disabled")
            return

        # Header
        header = (
            f"{'DLC':<8} {'Name':<32} {'App':>3} {'Key':>3} {'Man':>3}  Status\n"
        )
        header += "-" * 70 + "\n"
        self._readiness_box.insert("end", header)

        for r in items:
            app_mark = "Y" if r.in_applist else "-"
            key_mark = "Y" if r.has_key else "-"
            man_mark = "Y" if r.has_manifest else "-"
            status = "Ready" if r.ready else "Incomplete"

            name = r.name[:30] if len(r.name) > 30 else r.name
            line = (
                f"{r.dlc_id:<8} {name:<32} "
                f"{app_mark:>3} {key_mark:>3} {man_mark:>3}  {status}\n"
            )
            self._readiness_box.insert("end", line)

        self._readiness_box.configure(state="disabled")

    # ── Busy State ───────────────────────────────────────────────

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._install_btn.configure(state=state)
        self._install_stealth_btn.configure(state=state)
        self._uninstall_btn.configure(state=state)
        self._launch_btn.configure(state=state)
        self._apply_lua_btn.configure(state=state)
        self._fix_btn.configure(state=state)

    # ── Install GreenLuma ────────────────────────────────────────

    def _on_install_gl(self, stealth: bool = False):
        if self._busy or not self._steam_info:
            if not self._steam_info:
                self.app.show_toast("Steam path not detected.", "warning")
            return

        archive = self.app.settings.greenluma_archive_path
        if not archive or not Path(archive).is_file():
            path = filedialog.askopenfilename(
                title="Select GreenLuma 7z Archive",
                filetypes=[("7z Archives", "*.7z"), ("All Files", "*.*")],
                parent=self.winfo_toplevel(),
            )
            if not path:
                return
            archive = path
            self.app.settings.greenluma_archive_path = archive
            self.app.settings.save()

        mode_label = "Stealth" if stealth else "Normal"
        self._set_busy(True)
        self._log(f"--- Installing GreenLuma ({mode_label}) ---")

        steam_path = self._steam_info.steam_path

        def _bg():
            from ...greenluma.installer import install_greenluma
            return install_greenluma(
                Path(archive), steam_path, stealth=stealth
            )

        def _done(status):
            self._set_busy(False)
            self._gl_status = status
            if status.installed:
                mode = status.mode.title()
                ver = status.version
                self.app.show_toast(
                    f"GreenLuma v{ver} installed ({mode})!", "success"
                )
                self._log(
                    f"GreenLuma installed: v{ver} ({mode})"
                )
                self._gl_badge.set_status(f"v{ver} ({mode})", "success")
            else:
                self.app.show_toast("Installation may have failed.", "warning")
                self._log("Installation completed but GreenLuma not detected.")

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Install failed: {e}")
            self.app.show_toast(f"Install failed: {e}", "error")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Uninstall GreenLuma ──────────────────────────────────────

    def _on_uninstall_gl(self):
        if self._busy or not self._steam_info:
            if not self._steam_info:
                self.app.show_toast("Steam path not detected.", "warning")
            return

        gl = self._gl_status
        if not gl or not gl.installed:
            self.app.show_toast("GreenLuma is not installed.", "info")
            return

        confirm = tkinter.messagebox.askyesno(
            "Confirm Uninstall",
            "Remove all GreenLuma files from Steam?\n\n"
            "This will delete GreenLuma DLLs, DLLInjector, and AppList entries.",
            parent=self.winfo_toplevel(),
        )
        if not confirm:
            return

        self._set_busy(True)
        self._log("--- Uninstalling GreenLuma ---")
        steam_path = self._steam_info.steam_path

        def _bg():
            from ...greenluma.installer import uninstall_greenluma
            return uninstall_greenluma(steam_path)

        def _done(result):
            self._set_busy(False)
            removed, failed = result
            if failed == 0:
                self.app.show_toast(f"GreenLuma uninstalled ({removed} files removed)", "success")
                self._log(f"Uninstalled: {removed} files removed")
            else:
                self.app.show_toast(
                    f"Uninstall partial: {removed} removed, {failed} failed", "warning"
                )
                self._log(f"Uninstall: {removed} removed, {failed} failed")
            self._refresh_status()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Uninstall failed: {e}")
            self.app.show_toast(f"Uninstall failed: {e}", "error")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Launch via GreenLuma ─────────────────────────────────────

    def _on_launch_gl(self):
        if self._busy:
            return

        gl = self._gl_status
        if not gl or not gl.installed or not gl.dll_injector_path:
            self.app.show_toast(
                "GreenLuma not installed or injector not found.", "warning"
            )
            return

        # Check if Steam is running before launching
        from ...greenluma.steam import is_steam_running

        if is_steam_running():
            restart = tkinter.messagebox.askyesno(
                "Steam is Running",
                "Steam must be closed to relaunch with GreenLuma.\n\n"
                "Would you like to close Steam and relaunch it\n"
                "with GreenLuma DLC unlocking enabled?",
                parent=self.winfo_toplevel(),
            )
            if not restart:
                return
            self._launch_gl_with_kill(gl.dll_injector_path)
        else:
            self._launch_gl_direct(gl.dll_injector_path)

    def _launch_gl_with_kill(self, injector_path: Path):
        """Kill Steam then launch via GreenLuma."""
        self._set_busy(True)
        self._log("Closing Steam...")

        def _kill_bg():
            from ...greenluma.installer import kill_steam
            return kill_steam()

        def _kill_done(success):
            if success:
                self._log("Steam closed. Launching via GreenLuma...")
                self._launch_gl_direct(injector_path)
            else:
                self._set_busy(False)
                self.app.show_toast("Failed to close Steam.", "error")
                self._log("Failed to close Steam process.")

        def _kill_err(e):
            self._set_busy(False)
            self._enqueue_log(f"Failed to close Steam: {e}")
            self.app.show_toast(f"Failed to close Steam: {e}", "error")

        self.app.run_async(_kill_bg, on_done=_kill_done, on_error=_kill_err)

    def _launch_gl_direct(self, injector_path: Path):
        """Launch GreenLuma directly (Steam assumed not running)."""
        if not self._busy:
            self._set_busy(True)
        self._log("Launching Steam via GreenLuma...")

        def _bg():
            from ...greenluma.installer import launch_steam_via_greenluma
            return launch_steam_via_greenluma(injector_path, force=True)

        def _done(success):
            self._set_busy(False)
            if success:
                self.app.show_toast("Steam launched via GreenLuma!", "success")
                self._log("Steam launched successfully via DLLInjector.")
                self._steam_status_badge.set_status("Running", "warning")
            else:
                self.app.show_toast("Failed to launch DLLInjector.", "error")
                self._log("Launch failed.")

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Launch failed: {e}")
            self.app.show_toast(f"Launch failed: {e}", "error")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Apply LUA ────────────────────────────────────────────────

    def _on_apply_lua(self):
        if self._busy or not self._steam_info:
            if not self._steam_info:
                self.app.show_toast("Steam path not detected.", "warning")
            return

        # Pre-populate LUA path from settings
        initial_lua = self.app.settings.greenluma_lua_path
        lua_kwargs = {}
        if initial_lua:
            lua_parent = Path(initial_lua).parent
            if lua_parent.is_dir():
                lua_kwargs["initialdir"] = str(lua_parent)
            lua_kwargs["initialfile"] = Path(initial_lua).name

        lua_path = filedialog.askopenfilename(
            title="Select LUA Manifest File",
            filetypes=[("LUA Files", "*.lua"), ("All Files", "*.*")],
            parent=self.winfo_toplevel(),
            **lua_kwargs,
        )
        if not lua_path:
            return

        # Save selected LUA path for next time
        self.app.settings.greenluma_lua_path = lua_path

        # Pre-populate manifest dir from settings, fallback to depotcache
        initial_manifest = self.app.settings.greenluma_manifest_dir
        if not initial_manifest and self._steam_info:
            initial_manifest = str(self._steam_info.depotcache_dir)

        manifest_kwargs = {}
        if initial_manifest and Path(initial_manifest).is_dir():
            manifest_kwargs["initialdir"] = initial_manifest

        manifest_dir = filedialog.askdirectory(
            title="Select Manifest Source Directory (Cancel to skip)",
            parent=self.winfo_toplevel(),
            **manifest_kwargs,
        )
        manifest_dir_path = Path(manifest_dir) if manifest_dir else None

        if manifest_dir:
            self.app.settings.greenluma_manifest_dir = manifest_dir

        self.app.settings.save()

        self._set_busy(True)
        self._log("--- Applying LUA Manifest ---")

        steam_info = self._steam_info
        auto_backup = self.app.settings.greenluma_auto_backup

        def _bg():
            from ...greenluma.orchestrator import GreenLumaOrchestrator
            orch = GreenLumaOrchestrator(steam_info)
            return orch.apply_lua(
                lua_path=Path(lua_path),
                manifest_source_dir=manifest_dir_path,
                auto_backup=auto_backup,
                progress=self._enqueue_log,
            )

        def _done(result):
            self._set_busy(False)
            if result.success:
                self.app.show_toast("LUA applied successfully!", "success")
                self._log(
                    f"Done: {result.keys_added} keys added, "
                    f"{result.keys_updated} updated, "
                    f"{result.manifests_copied} manifests copied, "
                    f"{result.applist_entries_added} AppList entries"
                )
            else:
                self.app.show_toast(
                    f"LUA applied with {len(result.errors)} error(s)", "warning"
                )
                for err in result.errors:
                    self._log(f"ERROR: {err}")

            # Refresh readiness
            self._refresh_status()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Apply failed: {e}")
            self.app.show_toast(f"Apply failed: {e}", "error")

        self.app.run_async(_bg, on_done=_done, on_error=_err)

    # ── Fix AppList ──────────────────────────────────────────────

    def _on_fix_applist(self):
        if self._busy or not self._steam_info:
            if not self._steam_info:
                self.app.show_toast("Steam path not detected.", "warning")
            return

        self._set_busy(True)
        self._log("--- Fixing AppList ---")
        steam_info = self._steam_info

        def _bg():
            from ...dlc.catalog import DLCCatalog
            from ...greenluma.orchestrator import GreenLumaOrchestrator
            catalog = DLCCatalog()
            orch = GreenLumaOrchestrator(steam_info)
            return orch.fix_applist(catalog)

        def _done(result):
            self._set_busy(False)
            dupes, missing = result
            msg = f"Fixed: {dupes} duplicates removed, {missing} missing IDs added"
            self._log(msg)
            self.app.show_toast(msg, "success")
            self._refresh_status()

        def _err(e):
            self._set_busy(False)
            self._enqueue_log(f"Fix failed: {e}")
            self.app.show_toast(f"Fix failed: {e}", "error")

        self.app.run_async(_bg, on_done=_done, on_error=_err)
