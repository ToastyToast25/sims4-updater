"""
CDN Manager — main application window with sidebar navigation.

Threading model:
  - Single-worker executor for general background tasks
  - Multi-worker upload executor for parallel DLC/patch uploads
  - deque-based callback queue polled every 100ms by tkinter .after()
  - All GUI updates happen on the main thread via the queue
"""

from __future__ import annotations

import concurrent.futures
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from threading import Event, Lock, Thread

import customtkinter as ctk

from . import theme
from .animations import Animator
from .components import ToastNotification
from .config import ManagerConfig


@dataclass
class UploadJob:
    """A queued upload job."""

    name: str
    func: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    on_done: Callable | None = None
    on_error: Callable | None = None


class UploadQueue:
    """Cross-frame sequential upload queue.

    Frames submit UploadJob instances. The queue processes them one at a time
    on a background thread. GUI callbacks are dispatched via the app's
    _enqueue_gui mechanism.
    """

    def __init__(self, app: CDNManagerApp):
        self._app = app
        self._queue: deque[UploadJob] = deque()
        self._active: UploadJob | None = None
        self._lock = Lock()

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return self._active is not None

    @property
    def active_name(self) -> str:
        with self._lock:
            return self._active.name if self._active else ""

    def submit(self, job: UploadJob):
        """Add a job to the queue and start processing if idle."""
        with self._lock:
            self._queue.append(job)
        self._update_status()
        self._process_next()

    def _process_next(self):
        with self._lock:
            if self._active or not self._queue:
                return
            self._active = self._queue.popleft()

        self._update_status()
        Thread(target=self._run_job, daemon=True).start()

    def _run_job(self):
        job = self._active
        try:
            result = job.func(*job.args, **job.kwargs)
            if job.on_done:
                self._app._enqueue_gui(job.on_done, result)
        except Exception as e:
            if job.on_error:
                self._app._enqueue_gui(job.on_error, e)

        with self._lock:
            self._active = None

        self._update_status()
        self._process_next()

    def _update_status(self):
        with self._lock:
            pending = len(self._queue)
            active = self._active

        if active:
            text = f"Running: {active.name}"
            if pending > 0:
                text += f"  |  {pending} queued"
        elif pending > 0:
            text = f"{pending} uploads queued"
        else:
            text = ""

        self._app._enqueue_gui(self._app.update_status, text or "Ready")


class CDNManagerApp(ctk.CTk):
    """CDN Manager GUI application."""

    def __init__(self):
        super().__init__()

        self.title("CDN Manager")
        self.minsize(theme.MIN_WIDTH, theme.MIN_HEIGHT)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Animation
        self._animator = Animator()
        self._current_frame_name: str | None = None
        self._transitioning = False
        self._notification_history: list[tuple[str, str, float]] = []
        self._last_history_seen = 0

        # Threading
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._upload_executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._callback_queue: deque = deque()
        self._lock = Lock()
        self._cancel_event = Event()

        # Active operations tracking (for close confirmation)
        self._active_operations = 0

        # Cross-frame upload queue
        self.upload_queue = UploadQueue(self)

        # Connection state (updated by dashboard)
        self._connection_state: dict = {"sftp": False, "kv": False}

        # Global log
        self._global_log: list[tuple[str, str, str, float]] = []

        # Config
        self.config_data = ManagerConfig.load()
        if self.config_data.window_geometry:
            try:
                self.geometry(self.config_data.window_geometry)
            except Exception:
                self.geometry(f"{theme.WINDOW_WIDTH}x{theme.WINDOW_HEIGHT}")
        else:
            self.geometry(f"{theme.WINDOW_WIDTH}x{theme.WINDOW_HEIGHT}")

        # Build UI
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content_area()
        self._build_status_bar()
        self._create_frames()
        self._bind_shortcuts()

        # Show dashboard
        self._show_frame("dashboard")

        # Start callback polling + clock
        self.after(100, self._poll_callbacks)
        self._update_clock()

        # Close handler
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- Sidebar ------------------------------------------------------------

    def _build_sidebar(self):
        self._sidebar = ctk.CTkFrame(
            self,
            width=theme.SIDEBAR_WIDTH,
            corner_radius=0,
        )
        self._sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self._sidebar.grid_propagate(False)

        # Two-column grid: col 0 = indicator bar, col 1 = button
        self._sidebar.grid_columnconfigure(0, weight=0, minsize=8)
        self._sidebar.grid_columnconfigure(1, weight=1)

        # Title
        ctk.CTkLabel(
            self._sidebar,
            text="CDN Manager",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 15))

        # Separator
        ctk.CTkFrame(
            self._sidebar,
            height=1,
            fg_color=theme.COLORS["separator"],
        ).grid(row=1, column=0, columnspan=2, padx=15, sticky="ew")

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._nav_indicators: dict[str, ctk.CTkFrame] = {}
        self._nav_keys: list[str] = []

        nav_items = [
            ("dashboard", "Dashboard"),
            ("dlc", "DLC Upload"),
            ("language", "Languages"),
            ("patch", "Patches"),
            ("manifest", "Manifest"),
            ("archive", "Archives"),
            ("kv", "KV Browser"),
            ("settings", "Settings"),
        ]

        for i, (key, label) in enumerate(nav_items):
            row = i + 2  # rows 0-1 are title + separator
            self._nav_keys.append(key)

            # Indicator bar (3px accent strip on left side)
            indicator = ctk.CTkFrame(
                self._sidebar,
                width=3,
                height=theme.SIDEBAR_BTN_HEIGHT,
                corner_radius=0,
                fg_color="transparent",
            )
            indicator.grid(row=row, column=0, padx=(5, 0), pady=3)
            indicator.grid_propagate(False)
            self._nav_indicators[key] = indicator

            # Nav button
            btn = ctk.CTkButton(
                self._sidebar,
                text=f"  {label}",
                font=ctk.CTkFont(size=13),
                height=theme.SIDEBAR_BTN_HEIGHT,
                corner_radius=theme.CORNER_RADIUS_SMALL,
                fg_color="transparent",
                text_color=theme.COLORS["text_muted"],
                hover_color=theme.COLORS["sidebar_hover"],
                anchor="w",
                command=lambda k=key: self._show_frame(k),
            )
            btn.grid(row=row, column=1, padx=(4, 10), pady=3, sticky="ew")
            self._nav_buttons[key] = btn

        # Push footer to bottom
        spacer_row = len(nav_items) + 2
        self._sidebar.grid_rowconfigure(spacer_row, weight=1)

        # Separator above footer
        ctk.CTkFrame(
            self._sidebar,
            height=1,
            fg_color=theme.COLORS["separator"],
        ).grid(row=spacer_row + 1, column=0, columnspan=2, padx=15, sticky="ew")

        # Footer
        from . import VERSION

        footer = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        footer.grid(
            row=spacer_row + 2,
            column=0,
            columnspan=2,
            padx=18,
            pady=(8, 14),
            sticky="ew",
        )

        # Bell icon for notification history
        bell_row = ctk.CTkFrame(footer, fg_color="transparent")
        bell_row.pack(anchor="w", fill="x", pady=(0, 6))

        self._bell_btn = ctk.CTkButton(
            bell_row,
            text="\u266a Notifications",
            font=ctk.CTkFont(size=11),
            height=26,
            width=120,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            text_color=theme.COLORS["text_muted"],
            anchor="w",
            command=self._show_notification_history,
        )
        self._bell_btn.pack(side="left")

        self._bell_dot = ctk.CTkLabel(
            bell_row,
            text="\u25cf",
            font=ctk.CTkFont(size=8),
            text_color=theme.COLORS["error"],
            width=12,
        )
        # Dot hidden initially — shown when unread notifications exist

        # Export logs button
        ctk.CTkButton(
            footer,
            text="Export All Logs",
            font=ctk.CTkFont(size=10),
            height=24,
            width=110,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            text_color=theme.COLORS["text_muted"],
            command=self._export_global_log,
        ).pack(anchor="w", pady=(0, 6))

        ctk.CTkLabel(
            footer,
            text=f"v{VERSION}",
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_muted"],
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            footer,
            text="Sims 4 CDN Tools",
            font=ctk.CTkFont(size=9),
            text_color=theme.COLORS["text_dim"],
        ).pack(anchor="w")

    # -- Content Area -------------------------------------------------------

    def _build_content_area(self):
        self._content = ctk.CTkFrame(
            self,
            fg_color=theme.COLORS["bg_dark"],
            corner_radius=0,
        )
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

    # -- Status Bar ---------------------------------------------------------

    def _build_status_bar(self):
        self._status_bar = ctk.CTkFrame(
            self,
            height=28,
            corner_radius=0,
            fg_color=theme.COLORS["bg_deeper"],
            border_width=1,
            border_color=theme.COLORS["border"],
        )
        self._status_bar.grid(row=1, column=1, sticky="sew")
        self._status_bar.grid_propagate(False)
        self._status_bar.grid_columnconfigure(1, weight=1)

        # Left: connection status dots
        conn_frame = ctk.CTkFrame(self._status_bar, fg_color="transparent")
        conn_frame.grid(row=0, column=0, padx=(10, 0), sticky="w")

        ctk.CTkLabel(
            conn_frame,
            text="SFTP",
            font=ctk.CTkFont(size=9),
            text_color=theme.COLORS["text_dim"],
        ).pack(side="left", padx=(0, 2))
        self._sftp_dot = ctk.CTkLabel(
            conn_frame,
            text="\u25cf",
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_dim"],
            width=12,
        )
        self._sftp_dot.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            conn_frame,
            text="KV",
            font=ctk.CTkFont(size=9),
            text_color=theme.COLORS["text_dim"],
        ).pack(side="left", padx=(0, 2))
        self._kv_dot = ctk.CTkLabel(
            conn_frame,
            text="\u25cf",
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_dim"],
            width=12,
        )
        self._kv_dot.pack(side="left")

        # Center: operation text
        self._status_label = ctk.CTkLabel(
            self._status_bar,
            text="Ready",
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_muted"],
        )
        self._status_label.grid(row=0, column=1, padx=10)

        # Right: clock
        self._clock_label = ctk.CTkLabel(
            self._status_bar,
            text="",
            font=ctk.CTkFont("Consolas", 10),
            text_color=theme.COLORS["text_dim"],
        )
        self._clock_label.grid(row=0, column=2, padx=(0, 10), sticky="e")

    def _update_clock(self):
        self._clock_label.configure(text=datetime.now().strftime("%H:%M:%S"))
        self.after(1000, self._update_clock)

    def _update_status_bar_connections(self):
        sftp = self._connection_state.get("sftp", False)
        kv = self._connection_state.get("kv", False)
        self._sftp_dot.configure(
            text_color=theme.COLORS["success"] if sftp else theme.COLORS["error"],
        )
        self._kv_dot.configure(
            text_color=theme.COLORS["success"] if kv else theme.COLORS["error"],
        )

    def update_status(self, text: str):
        """Update the status bar center text. Frames call this during operations."""
        self._status_label.configure(text=text)

    # -- Frames -------------------------------------------------------------

    def _create_frames(self):
        from .frames.archive_frame import ArchiveFrame
        from .frames.dashboard_frame import DashboardFrame
        from .frames.dlc_frame import DLCFrame
        from .frames.kv_frame import KVBrowserFrame
        from .frames.language_frame import LanguageFrame
        from .frames.manifest_frame import ManifestFrame
        from .frames.patch_frame import PatchFrame
        from .frames.settings_frame import SettingsFrame

        self._frames: dict[str, ctk.CTkFrame] = {}

        for key, cls in [
            ("dashboard", DashboardFrame),
            ("dlc", DLCFrame),
            ("language", LanguageFrame),
            ("patch", PatchFrame),
            ("manifest", ManifestFrame),
            ("archive", ArchiveFrame),
            ("kv", KVBrowserFrame),
            ("settings", SettingsFrame),
        ]:
            frame = cls(self._content, self)
            frame.grid(row=0, column=0, sticky="nsew")
            self._frames[key] = frame

        # Wire each frame's log panel to the global log collector
        source_names = {
            "dashboard": "Dashboard",
            "dlc": "DLC",
            "language": "Language",
            "patch": "Patch",
            "manifest": "Manifest",
            "archive": "Archive",
            "kv": "KV",
        }
        for key, name in source_names.items():
            frame = self._frames.get(key)
            if frame and hasattr(frame, "_log"):
                frame._log.set_global_logger(self, name)

    def _show_frame(self, name: str):
        if self._transitioning or name == self._current_frame_name:
            return

        frame = self._frames.get(name)
        if not frame:
            return

        # Call on_hide on the old frame
        if self._current_frame_name:
            old_frame = self._frames.get(self._current_frame_name)
            if old_frame and hasattr(old_frame, "on_hide"):
                old_frame.on_hide()

        # Update sidebar indicators
        for key, indicator in self._nav_indicators.items():
            if key == name:
                indicator.configure(fg_color=theme.COLORS["accent"])
                self._nav_buttons[key].configure(
                    fg_color=theme.COLORS["accent"],
                    text_color=theme.COLORS["text"],
                )
            else:
                indicator.configure(fg_color="transparent")
                self._nav_buttons[key].configure(
                    fg_color="transparent",
                    text_color=theme.COLORS["text_muted"],
                )

        # Raise frame
        frame.tkraise()
        self._current_frame_name = name

        # Call on_show if available
        if hasattr(frame, "on_show"):
            self.after(50, frame.on_show)

    # -- Keyboard Shortcuts -------------------------------------------------

    def _bind_shortcuts(self):
        # Ctrl+1 through Ctrl+8 for frame navigation
        for i, key in enumerate(self._nav_keys):
            self.bind(
                f"<Control-Key-{i + 1}>",
                lambda e, k=key: self._show_frame(k),
            )

        # Ctrl+R = refresh current frame
        self.bind("<Control-r>", self._shortcut_refresh)

        # Ctrl+S = save settings (if on settings frame)
        self.bind("<Control-s>", self._shortcut_save)

        # Escape = cancel current upload
        self.bind("<Escape>", self._shortcut_cancel)

        # F5 = refresh dashboard
        self.bind("<F5>", self._shortcut_f5)

    def _shortcut_refresh(self, _event=None):
        frame = self._frames.get(self._current_frame_name or "")
        if frame and hasattr(frame, "_refresh"):
            frame._refresh()
        elif frame and hasattr(frame, "on_show"):
            frame.on_show()

    def _shortcut_save(self, _event=None):
        if self._current_frame_name == "settings":
            frame = self._frames["settings"]
            if hasattr(frame, "_save"):
                frame._save()

    def _shortcut_cancel(self, _event=None):
        # Set cancel events on frames that have them
        for frame in self._frames.values():
            if hasattr(frame, "_cancel_event"):
                frame._cancel_event.set()

    def _shortcut_f5(self, _event=None):
        self._show_frame("dashboard")
        self.after(100, self._frames["dashboard"]._refresh)

    # -- Threading ----------------------------------------------------------

    def run_async(self, func, *args, on_done=None, on_error=None):
        """Run a function in the background thread pool."""

        def wrapper():
            try:
                result = func(*args)
                if on_done:
                    self._enqueue_gui(on_done, result)
            except Exception as e:
                if on_error:
                    self._enqueue_gui(on_error, e)

        self._executor.submit(wrapper)

    def _enqueue_gui(self, func, *args):
        """Thread-safe: schedule a function to run on the GUI thread."""
        self._callback_queue.append((func, args))

    def _poll_callbacks(self):
        """Drain the callback queue on the main thread (called every 100ms)."""
        while True:
            try:
                func, args = self._callback_queue.popleft()
            except IndexError:
                break
            try:
                func(*args)
            except Exception:
                import traceback

                traceback.print_exc()
        self.after(100, self._poll_callbacks)

    def get_upload_executor(self, workers: int) -> concurrent.futures.ThreadPoolExecutor:
        """Get or create the upload executor with the specified worker count."""
        if self._upload_executor:
            self._upload_executor.shutdown(wait=False)
        self._upload_executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        return self._upload_executor

    # -- Active Operations Tracking -----------------------------------------

    def begin_operation(self, description: str = ""):
        """Mark an operation as active (prevents close without confirmation)."""
        self._active_operations += 1
        if description:
            self.update_status(description)

    def end_operation(self):
        """Mark an operation as complete."""
        self._active_operations = max(0, self._active_operations - 1)
        if self._active_operations == 0:
            self.update_status("Ready")

    # -- Toast Notifications ------------------------------------------------

    def show_toast(self, message: str, style: str = "info"):
        """Show a toast notification."""
        self._notification_history.append((message, style, time.time()))
        # Cap history at 50
        if len(self._notification_history) > 50:
            self._notification_history = self._notification_history[-50:]
        # Show unread dot on bell
        if len(self._notification_history) > self._last_history_seen:
            self._bell_dot.pack(side="left", padx=(2, 0))
        toast = ToastNotification(self._content, message, style=style)
        toast.show()

    # -- Notification History -----------------------------------------------

    def _show_notification_history(self):
        self._last_history_seen = len(self._notification_history)
        self._bell_dot.pack_forget()

        popup = ctk.CTkToplevel(self)
        popup.title("Notification History")
        popup.geometry("450x400")
        popup.resizable(False, True)
        popup.transient(self)
        popup.grab_set()

        popup.grid_columnconfigure(0, weight=1)
        popup.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            popup,
            text="Recent Notifications",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, padx=15, pady=(15, 10), sticky="w")

        scroll = ctk.CTkScrollableFrame(
            popup,
            fg_color=theme.COLORS["bg_dark"],
            corner_radius=theme.CORNER_RADIUS_SMALL,
        )
        scroll.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")
        scroll.grid_columnconfigure(1, weight=1)

        if not self._notification_history:
            ctk.CTkLabel(
                scroll,
                text="No notifications yet",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=0, pady=30)
            return

        icons = {"success": "\u2713", "warning": "\u26a0", "error": "\u2717", "info": "\u2139"}
        colors = {
            "success": theme.COLORS["success"],
            "warning": theme.COLORS["warning"],
            "error": theme.COLORS["error"],
            "info": theme.COLORS["accent"],
        }

        now = time.time()
        for i, (msg, style, ts) in enumerate(reversed(self._notification_history)):
            row = i
            icon = icons.get(style, "\u2139")
            color = colors.get(style, theme.COLORS["text"])

            ctk.CTkLabel(
                scroll,
                text=icon,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=color,
                width=20,
            ).grid(row=row, column=0, padx=(8, 4), pady=3, sticky="nw")

            ctk.CTkLabel(
                scroll,
                text=msg,
                font=ctk.CTkFont(size=11),
                text_color=theme.COLORS["text"],
                wraplength=300,
                anchor="w",
                justify="left",
            ).grid(row=row, column=1, padx=(0, 4), pady=3, sticky="w")

            elapsed = now - ts
            if elapsed < 60:
                time_str = "just now"
            elif elapsed < 3600:
                time_str = f"{int(elapsed / 60)}m ago"
            elif elapsed < 86400:
                time_str = f"{int(elapsed / 3600)}h ago"
            else:
                time_str = datetime.fromtimestamp(ts).strftime("%m/%d %H:%M")

            ctk.CTkLabel(
                scroll,
                text=time_str,
                font=ctk.CTkFont(size=9),
                text_color=theme.COLORS["text_dim"],
                width=60,
            ).grid(row=row, column=2, padx=(0, 8), pady=3, sticky="ne")

    # -- Global Log ---------------------------------------------------------

    def global_log(self, msg: str, level: str = "info", source: str = ""):
        """Collect log entries from all frames for global export."""
        self._global_log.append((msg, level, source, time.time()))

    def _export_global_log(self):
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt")],
            initialfile=f"cdn_manager_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        )
        if not path:
            return

        lines = []
        for msg, level, source, ts in self._global_log:
            ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
            prefix = f"[{source}] " if source else ""
            lines.append(f"[{ts_str}] [{level.upper():7s}] {prefix}{msg}")

        from pathlib import Path

        Path(path).write_text("\n".join(lines), encoding="utf-8")
        self.show_toast(f"Exported {len(lines)} log entries", "success")

    # -- Lifecycle ----------------------------------------------------------

    def _on_close(self):
        """Save state and clean up on window close."""
        if self._active_operations > 0:
            self._show_close_confirmation()
            return

        self._do_close()

    def _show_close_confirmation(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Close")
        dialog.geometry("380x160")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # Center on parent
        dialog.after(
            10,
            lambda: dialog.geometry(
                f"+{self.winfo_x() + self.winfo_width() // 2 - 190}"
                f"+{self.winfo_y() + self.winfo_height() // 2 - 80}"
            ),
        )

        ctk.CTkLabel(
            dialog,
            text="\u26a0  Uploads In Progress",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=theme.COLORS["warning"],
        ).pack(padx=20, pady=(20, 8))

        ctk.CTkLabel(
            dialog,
            text=(
                f"{self._active_operations} operation(s) still running.\n"
                "Closing now may leave uploads incomplete."
            ),
            font=ctk.CTkFont(size=12),
            text_color=theme.COLORS["text_muted"],
        ).pack(padx=20, pady=(0, 15))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(padx=20, pady=(0, 15))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=dialog.destroy,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text="Force Close",
            width=120,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            command=lambda: (dialog.destroy(), self._force_close()),
        ).pack(side="left")

    def _force_close(self):
        # Signal all cancel events
        self._cancel_event.set()
        for frame in self._frames.values():
            if hasattr(frame, "_cancel_event"):
                frame._cancel_event.set()
        # Brief delay then close
        self.after(500, self._do_close)

    def _do_close(self):
        """Final close — save state and destroy."""
        self.config_data.window_geometry = self.geometry()
        self.config_data.save()

        self._cancel_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)
        if self._upload_executor:
            self._upload_executor.shutdown(wait=False, cancel_futures=True)

        self.destroy()
