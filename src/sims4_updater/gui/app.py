"""
Main application window with sidebar navigation.

Threading model:
  - Worker thread runs updater operations via ThreadPoolExecutor
  - deque-based callback queue polled every 100ms by tkinter .after()
  - All GUI updates happen on the main thread via the queue
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import tkinter as tk
import traceback
from collections import deque
from threading import Lock

import customtkinter as ctk

from ..config import Settings
from ..dlc.steam import SteamPriceCache
from ..updater import Sims4Updater
from . import theme
from .animations import Animator, ease_out_cubic
from .components import ToastNotification
from .frames.diagnostics_frame import DiagnosticsFrame
from .frames.dlc_frame import DLCFrame
from .frames.downloader_frame import DownloaderFrame
from .frames.greenluma_frame import GreenLumaFrame
from .frames.home_frame import HomeFrame
from .frames.language_frame import LanguageFrame
from .frames.mods_frame import ModsFrame
from .frames.packer_frame import PackerFrame
from .frames.progress_frame import ProgressFrame
from .frames.settings_frame import SettingsFrame
from .frames.unlocker_frame import UnlockerFrame


class App(ctk.CTk):
    """Main Sims 4 Updater GUI application."""

    def __init__(self):
        super().__init__()

        # Window setup
        self.title("Sims 4 Updater")
        self.minsize(theme.MIN_WIDTH, theme.MIN_HEIGHT)

        # Prevent CustomTkinter from overriding our icon (it checks this flag)
        self._iconbitmap_method_called = True

        # Window icon (use PNG via wm_iconphoto for crisp rendering)
        from ..constants import get_icon_path

        icon_path = get_icon_path()
        if icon_path.is_file():
            raw = tk.PhotoImage(file=str(icon_path))
            # Subsample 1024x1024 → 32x32 for crisp title bar / taskbar icon
            self._icon_image = raw.subsample(raw.width() // 32)
            self.wm_iconphoto(True, self._icon_image)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Animation
        self._animator = Animator()
        self._current_frame_name: str | None = None
        self._transitioning = False
        self._notification_history: list[tuple[str, str, float]] = []  # (msg, style, time)

        # Threading
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._callback_queue: deque = deque()
        self._lock = Lock()
        self._current_future = None

        # Settings, shared state, and updater
        self.settings = Settings.load()
        if self.settings.window_geometry:
            try:
                self.geometry(self.settings.window_geometry)
            except Exception:
                self.geometry(f"{theme.WINDOW_WIDTH}x{theme.WINDOW_HEIGHT}")
        else:
            self.geometry(f"{theme.WINDOW_WIDTH}x{theme.WINDOW_HEIGHT}")

        # Configure machine identity for CDN/API requests (always active)
        from ..core import identity
        from ..core.machine_id import get_machine_id

        identity.configure(get_machine_id(), self.settings.uid)

        self.price_cache = SteamPriceCache()
        self.updater = Sims4Updater(
            ask_question=self._ask_question,
            callback=self._enqueue_callback,
            settings=self.settings,
        )

        # CDN auth — initialized after manifest fetch via init_cdn_auth()
        self._cdn_auth = None

        # Telemetry (fire-and-forget, deferred import)
        from ..core.telemetry import TelemetryClient

        self.telemetry = TelemetryClient(self.settings)

        # Build UI
        self._build_sidebar()
        self._build_content_area()
        self._create_frames()

        # Show home frame
        self._show_frame("home")

        # Start callback polling
        self.after(100, self._poll_callbacks)

        # Protocol handlers
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Initialize on next tick
        self.after(200, self._on_startup)

    # ── Sidebar ─────────────────────────────────────────────────

    def _build_sidebar(self):
        self._sidebar = ctk.CTkFrame(
            self,
            width=theme.SIDEBAR_WIDTH,
            corner_radius=0,
        )
        self._sidebar.grid(row=0, column=0, sticky="nsw")
        self._sidebar.grid_propagate(False)
        self._sidebar.grid_columnconfigure(0, weight=1)

        # Logo / title
        ctk.CTkLabel(
            self._sidebar,
            text="TS4 Updater",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 15))

        # Separator below logo
        ctk.CTkFrame(
            self._sidebar,
            height=1,
            fg_color=theme.COLORS["separator"],
        ).grid(row=1, column=0, columnspan=2, padx=15, sticky="ew")

        # Nav buttons — two-column grid: col 0 = indicator, col 1 = button
        self._sidebar.grid_columnconfigure(0, weight=0, minsize=8)
        self._sidebar.grid_columnconfigure(1, weight=1)

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._nav_indicators: dict[str, ctk.CTkFrame] = {}
        self._nav_labels: dict[str, str] = {}  # base labels for badge updates

        main_items = [
            ("home", "Home"),
            ("dlc", "DLCs"),
            ("downloader", "DLC Downloader"),
            ("unlocker", "Unlocker"),
            ("language", "Language"),
            ("settings", "Settings"),
        ]
        tools_items = [
            ("packer", "Packer"),
            ("greenluma", "GreenLuma"),
            ("mods", "Mods"),
            ("diagnostics", "Diagnostics"),
        ]
        self._tools_keys = {key for key, _ in tools_items}

        current_row = 2  # rows 0-1 are logo + separator

        # ── Main nav items ──
        for key, label in main_items:
            self._build_nav_item(key, label, current_row)
            current_row += 1

        # ── Tools section header (collapsible) ──
        self._tools_collapsed = getattr(self.settings, "tools_collapsed", True)
        tools_header = ctk.CTkFrame(
            self._sidebar,
            fg_color="transparent",
            cursor="hand2",
        )
        tools_header.grid(
            row=current_row,
            column=0,
            columnspan=2,
            padx=(10, 10),
            pady=(8, 2),
            sticky="ew",
        )
        tools_header.grid_columnconfigure(1, weight=1)

        arrow = "\u25b6" if self._tools_collapsed else "\u25bc"
        self._tools_chevron = ctk.CTkLabel(
            tools_header,
            text=arrow,
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_dim"],
            width=14,
        )
        self._tools_chevron.grid(row=0, column=0, padx=(4, 2))

        tools_label = ctk.CTkLabel(
            tools_header,
            text="Tools",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=theme.COLORS["text_dim"],
            anchor="w",
        )
        tools_label.grid(row=0, column=1, sticky="w")

        for widget in (tools_header, self._tools_chevron, tools_label):
            widget.bind("<Button-1>", lambda e: self._toggle_tools_section())

        current_row += 1

        # ── Tools nav items ──
        self._tools_nav_widgets: list[tuple[ctk.CTkFrame, ctk.CTkButton]] = []
        for key, label in tools_items:
            indicator, btn = self._build_nav_item(key, label, current_row)
            self._tools_nav_widgets.append((indicator, btn))
            if self._tools_collapsed:
                indicator.grid_remove()
                btn.grid_remove()
            current_row += 1

        # Progress nav item — hidden by default, shown during updates
        self._progress_indicator = ctk.CTkFrame(
            self._sidebar,
            width=3,
            height=theme.SIDEBAR_BTN_HEIGHT,
            corner_radius=0,
            fg_color="transparent",
        )
        self._progress_indicator.grid(row=current_row, column=0, padx=(5, 0), pady=3)
        self._progress_indicator.grid_propagate(False)
        self._nav_indicators["progress"] = self._progress_indicator

        self._progress_nav_btn = ctk.CTkButton(
            self._sidebar,
            text="  Updating...",
            font=ctk.CTkFont(size=13),
            height=theme.SIDEBAR_BTN_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color="transparent",
            text_color=theme.COLORS["text_muted"],
            hover_color=theme.COLORS["sidebar_hover"],
            anchor="w",
            command=lambda: self._show_frame("progress"),
        )
        self._progress_nav_btn.grid(
            row=current_row,
            column=1,
            padx=(4, 10),
            pady=3,
            sticky="ew",
        )
        self._nav_buttons["progress"] = self._progress_nav_btn
        self._nav_labels["progress"] = "Updating..."
        # Hide until an update starts
        self._progress_indicator.grid_remove()
        self._progress_nav_btn.grid_remove()
        current_row += 1

        self._sidebar.grid_rowconfigure(current_row, weight=1)

        # Separator above footer
        ctk.CTkFrame(
            self._sidebar,
            height=1,
            fg_color=theme.COLORS["separator"],
        ).grid(row=current_row + 1, column=0, columnspan=2, padx=15, sticky="ew")

        # Bell icon — notification history
        bell_row = current_row + 2
        self._bell_btn = ctk.CTkButton(
            self._sidebar,
            text="\U0001f514",
            font=ctk.CTkFont(size=14),
            width=30,
            height=26,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color="transparent",
            hover_color=theme.COLORS["sidebar_hover"],
            text_color=theme.COLORS["text_muted"],
            command=self._toggle_notification_popup,
        )
        self._bell_btn.grid(
            row=bell_row,
            column=0,
            columnspan=2,
            padx=18,
            pady=(6, 0),
            sticky="w",
        )
        self._notification_popup = None

        # Footer: version, admin status, copyright, creator, GitHub link
        from .. import VERSION
        from ..core.unlocker import is_admin

        footer = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        footer.grid(
            row=bell_row + 1,
            column=0,
            columnspan=2,
            padx=18,
            pady=(4, 14),
            sticky="ew",
        )

        elevated = is_admin()
        admin_color = theme.COLORS["success"] if elevated else theme.COLORS["warning"]
        admin_text = "\u2714 Admin" if elevated else "\u26a0 No Admin"

        ctk.CTkLabel(
            footer,
            text=f"v{VERSION}",
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_muted"],
        ).pack(anchor="w", pady=(0, 1))

        ctk.CTkLabel(
            footer,
            text=admin_text,
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=admin_color,
        ).pack(anchor="w", pady=(0, 2))

        ctk.CTkLabel(
            footer,
            text="\u00a9 2026 ToastyToast25",
            font=ctk.CTkFont(size=9),
            text_color=theme.COLORS["text_muted"],
        ).pack(anchor="w", pady=(0, 1))

        gh_link = ctk.CTkLabel(
            footer,
            text="GitHub",
            font=ctk.CTkFont(size=9, underline=True),
            text_color=theme.COLORS["accent"],
            cursor="hand2",
        )
        gh_link.pack(anchor="w")
        gh_link.bind(
            "<Button-1>",
            lambda e: __import__("webbrowser").open(
                "https://github.com/ToastyToast25/sims4-updater"
            ),
        )

    def update_nav_badge(self, key: str, badge: str = ""):
        """Update a sidebar nav button with a badge count, e.g. 'DLCs (3 missing)'."""
        btn = self._nav_buttons.get(key)
        base = self._nav_labels.get(key, "")
        if not btn or not base:
            return
        if badge:
            btn.configure(text=f"  {base}  {badge}")
        else:
            btn.configure(text=f"  {base}")

    # ── Content Area ────────────────────────────────────────────

    def _build_content_area(self):
        self._content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self._content.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

    def _create_frames(self):
        self._frames: dict[str, ctk.CTkFrame] = {}

        self._frames["home"] = HomeFrame(self._content, self)
        self._frames["dlc"] = DLCFrame(self._content, self)
        self._frames["downloader"] = DownloaderFrame(self._content, self)
        self._frames["packer"] = PackerFrame(self._content, self)
        self._frames["unlocker"] = UnlockerFrame(self._content, self)
        self._frames["greenluma"] = GreenLumaFrame(self._content, self)
        self._frames["language"] = LanguageFrame(self._content, self)
        self._frames["mods"] = ModsFrame(self._content, self)
        self._frames["diagnostics"] = DiagnosticsFrame(self._content, self)
        self._frames["settings"] = SettingsFrame(self._content, self)
        self._frames["progress"] = ProgressFrame(self._content, self)

        for frame in self._frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

    def _build_nav_item(
        self,
        key: str,
        label: str,
        row_idx: int,
    ) -> tuple[ctk.CTkFrame, ctk.CTkButton]:
        """Create a sidebar nav indicator + button at the given row."""
        indicator = ctk.CTkFrame(
            self._sidebar,
            width=3,
            height=theme.SIDEBAR_BTN_HEIGHT,
            corner_radius=0,
            fg_color="transparent",
        )
        indicator.grid(row=row_idx, column=0, padx=(5, 0), pady=3)
        indicator.grid_propagate(False)
        self._nav_indicators[key] = indicator

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
        btn.grid(row=row_idx, column=1, padx=(4, 10), pady=3, sticky="ew")
        self._nav_buttons[key] = btn
        self._nav_labels[key] = label

        btn.bind("<Enter>", lambda e, k=key: self._on_nav_enter(k))
        btn.bind("<Leave>", lambda e, k=key: self._on_nav_leave(k))

        return indicator, btn

    def _toggle_tools_section(self):
        """Expand or collapse the Tools section in the sidebar."""
        self._tools_collapsed = not self._tools_collapsed
        arrow = "\u25b6" if self._tools_collapsed else "\u25bc"
        self._tools_chevron.configure(text=arrow)
        for indicator, btn in self._tools_nav_widgets:
            if self._tools_collapsed:
                indicator.grid_remove()
                btn.grid_remove()
            else:
                indicator.grid()
                btn.grid()
        # Persist setting
        self.settings.tools_collapsed = self._tools_collapsed
        self.settings.save()

    def _on_nav_enter(self, key: str):
        """Sidebar button hover-in — skip for active tab."""
        if key == self._current_frame_name:
            return

    def _on_nav_leave(self, key: str):
        """Sidebar button hover-out — skip for active tab."""
        if key == self._current_frame_name:
            return

    def _show_frame(self, name: str):
        """Switch to a named frame with slide animation."""
        frame = self._frames.get(name)
        if frame is None or self._transitioning:
            return

        # Skip if already showing this frame
        if name == self._current_frame_name:
            return

        # Auto-expand tools section if navigating to a tools tab
        if name in self._tools_keys and self._tools_collapsed:
            self._toggle_tools_section()

        # Update nav button colors and indicator bars
        for key, btn in self._nav_buttons.items():
            if key == name:
                btn.configure(
                    fg_color=theme.COLORS["accent"],
                    text_color=theme.COLORS["text"],
                )
                self._nav_indicators[key].configure(
                    fg_color=theme.COLORS["accent"],
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=theme.COLORS["text_muted"],
                )
                self._nav_indicators[key].configure(
                    fg_color="transparent",
                )

        old_name = self._current_frame_name
        self._current_frame_name = name

        # Track navigation
        if old_name is not None:
            self.telemetry.track_event(
                "frame_navigation",
                {
                    "from_frame": old_name,
                    "to_frame": name,
                },
            )

        # First frame show — no animation needed
        if old_name is None:
            frame.tkraise()
            if hasattr(frame, "on_show"):
                frame.on_show()
            return

        # Slide transition: new frame slides in from right
        self._transitioning = True
        content_w = self._content.winfo_width()
        if content_w <= 1:
            # Content not yet rendered, just raise
            frame.tkraise()
            if hasattr(frame, "on_show"):
                frame.on_show()
            self._transitioning = False
            return

        # Place new frame off-screen to the right, on top
        frame.place(x=content_w, y=0, relwidth=1.0, relheight=1.0)
        frame.lift()

        def on_tick(t):
            x = int(content_w * (1 - t))
            frame.place(x=x, y=0, relwidth=1.0, relheight=1.0)

        def finalize():
            # Switch back to grid layout — place() removed grid management,
            # so we must re-grid the frame before raising it.
            if not self._transitioning:
                return  # Already finalized
            if self._current_frame_name != name:
                return  # Stale: a newer transition has started
            with contextlib.suppress(Exception):
                frame.place_forget()
            frame.grid(row=0, column=0, sticky="nsew")
            frame.tkraise()
            self._transitioning = False
            if hasattr(frame, "on_show"):
                frame.on_show()

        self._animator.animate(
            frame,
            theme.ANIM_NORMAL,
            on_tick=on_tick,
            on_done=finalize,
            easing=ease_out_cubic,
        )

        # Safety: if animation errors out, force-finalize after timeout
        self.after(theme.ANIM_NORMAL + 500, finalize)

    # ── Threading ───────────────────────────────────────────────

    def run_async(self, func, *args, on_done=None, on_error=None):
        """Run a function in the background thread."""

        def wrapper():
            try:
                result = func(*args)
                if on_done:
                    self._enqueue_gui(on_done, result)
            except Exception as e:
                if on_error:
                    self._enqueue_gui(on_error, e)
                else:
                    self._enqueue_gui(self._show_error, e)

        self._current_future = self._executor.submit(wrapper)

    def _enqueue_gui(self, func, *args):
        """Schedule a function to run on the GUI thread."""
        self._callback_queue.append(("gui", func, args))

    def _enqueue_callback(self, *args, **kwargs):
        """Patcher callback — enqueue for GUI thread processing."""
        self._callback_queue.append(("patcher", args, kwargs))

    def _poll_callbacks(self):
        """Process queued callbacks on the GUI thread."""
        while True:
            try:
                item = self._callback_queue.popleft()
            except IndexError:
                break

            if item[0] == "gui":
                _, func, args = item
                try:
                    func(*args)
                except Exception:
                    traceback.print_exc()
            elif item[0] == "patcher":
                _, args, kwargs = item
                self._handle_patcher_callback(*args, **kwargs)

        self.after(100, self._poll_callbacks)

    def _handle_patcher_callback(self, callback_type, *args, **kwargs):
        """Route patcher callbacks to the progress frame."""
        progress_frame = self._frames.get("progress")
        if progress_frame and hasattr(progress_frame, "handle_callback"):
            progress_frame.handle_callback(callback_type, *args, **kwargs)

    # ── Questions and Errors ────────────────────────────────────

    def _ask_question(self, question: str) -> bool:
        return tk.messagebox.askyesno("Question", question, parent=self)

    def _show_error(self, error: Exception):
        """Display an error to the user."""
        from ..core.exceptions import AccessRequiredError, BannedError

        if isinstance(error, BannedError):
            # Prominent dialog — user must see this clearly
            tk.messagebox.showerror(
                "CDN Access Suspended",
                str(error),
                parent=self,
            )
            return

        if isinstance(error, AccessRequiredError):
            self._show_access_request_dialog(error)
            return

        msg = str(error)
        if not msg:
            msg = type(error).__name__
        tk.messagebox.showerror("Error", msg, parent=self)

    def show_message(self, title: str, message: str):
        tk.messagebox.showinfo(title, message, parent=self)

    def show_toast(self, message: str, style: str = "success"):
        """Show a slide-in toast notification over the content area."""
        import time as _time

        # Record in history (cap at 50)
        self._notification_history.append((message, style, _time.time()))
        if len(self._notification_history) > 50:
            self._notification_history = self._notification_history[-50:]

        toast = ToastNotification(self._content, message, style)
        toast.show()

    # ── Notification History Popup ───────────────────────────────

    def _toggle_notification_popup(self):
        """Toggle the notification history popup anchored to the bell icon."""
        if self._notification_popup is not None:
            self._close_notification_popup()
            return
        self._show_notification_popup()

    def _show_notification_popup(self):
        """Show a popup listing recent notification history."""
        import time as _time

        from .components import _TOAST_STYLES

        popup = ctk.CTkToplevel(self)
        popup.overrideredirect(True)
        popup.configure(fg_color=theme.COLORS["bg_surface"])
        popup.attributes("-topmost", True)

        # Position above the bell button
        try:
            bx = self._bell_btn.winfo_rootx()
            by = self._bell_btn.winfo_rooty()
        except Exception:
            bx, by = 100, 400
        popup_w, popup_h = 300, min(320, 60 + len(self._notification_history) * 38)
        popup_h = max(popup_h, 80)
        popup.geometry(f"{popup_w}x{popup_h}+{bx}+{by - popup_h - 4}")

        self._notification_popup = popup

        # Title row
        header = ctk.CTkFrame(popup, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(
            header,
            text="Notifications",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=theme.COLORS["text"],
        ).pack(side="left")

        if self._notification_history:
            clear_btn = ctk.CTkLabel(
                header,
                text="Clear all",
                font=ctk.CTkFont(size=10, underline=True),
                text_color=theme.COLORS["accent"],
                cursor="hand2",
            )
            clear_btn.pack(side="right")
            clear_btn.bind("<Button-1>", lambda e: self._clear_notifications())

        # Scrollable list
        scroll = ctk.CTkScrollableFrame(
            popup,
            fg_color="transparent",
            scrollbar_button_color=theme.COLORS["separator"],
            height=popup_h - 50,
        )
        scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        if not self._notification_history:
            ctk.CTkLabel(
                scroll,
                text="No notifications yet",
                font=ctk.CTkFont(*theme.FONT_SMALL),
                text_color=theme.COLORS["text_muted"],
            ).pack(pady=10)
        else:
            now = _time.time()
            # Show most recent first
            for msg, style, ts in reversed(self._notification_history):
                s = _TOAST_STYLES.get(style, _TOAST_STYLES["info"])
                row = ctk.CTkFrame(scroll, fg_color=s["bg"], corner_radius=6, height=32)
                row.pack(fill="x", pady=2)
                row.pack_propagate(False)

                ctk.CTkLabel(
                    row,
                    text=s["icon"],
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color=s["text"],
                    width=16,
                ).pack(side="left", padx=(8, 2))

                ctk.CTkLabel(
                    row,
                    text=msg,
                    font=ctk.CTkFont(size=10),
                    text_color=s["text"],
                    anchor="w",
                ).pack(side="left", fill="x", expand=True, padx=(0, 4))

                elapsed = int(now - ts)
                if elapsed < 60:
                    time_str = "just now"
                elif elapsed < 3600:
                    time_str = f"{elapsed // 60}m ago"
                else:
                    time_str = f"{elapsed // 3600}h ago"

                ctk.CTkLabel(
                    row,
                    text=time_str,
                    font=ctk.CTkFont(size=9),
                    text_color=theme.COLORS["text_dim"],
                    width=50,
                ).pack(side="right", padx=(0, 8))

        # Close on focus loss
        popup.bind("<FocusOut>", lambda e: self._close_notification_popup())

    def _close_notification_popup(self):
        """Close the notification history popup."""
        if self._notification_popup is not None:
            with contextlib.suppress(Exception):
                self._notification_popup.destroy()
            self._notification_popup = None

    def _clear_notifications(self):
        """Clear notification history and close popup."""
        self._notification_history.clear()
        self._close_notification_popup()

    # ── CDN Auth ──────────────────────────────────────────────

    def init_cdn_auth(self, manifest):
        """Initialize CDN authentication from manifest config.

        Call after fetching the manifest.  Creates a CDNAuth instance for
        the CDN described in manifest.cdn, updates the telemetry base URL,
        and returns the auth adapter for download sessions.

        Returns CDNTokenAuth adapter or None.
        """
        if not manifest.cdn.api_url:
            return None

        from .. import VERSION
        from ..core.cdn_auth import CDNAuth
        from ..core.machine_id import get_machine_id

        self._cdn_auth = CDNAuth(
            api_url=manifest.cdn.api_url,
            machine_id=get_machine_id(),
            uid=self.settings.uid,
            app_version=VERSION,
        )

        # Update telemetry to use CDN-specific telemetry URL
        if manifest.cdn.telemetry_url:
            self.telemetry._base_url = manifest.cdn.telemetry_url

        return self._cdn_auth.get_auth_adapter()

    def _show_access_request_dialog(self, error):
        """Show a dialog for requesting access to a private CDN."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Access Request Required")
        dialog.geometry("420x240")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.attributes("-topmost", True)

        pad = {"padx": 20}

        ctk.CTkLabel(
            dialog,
            text=f"Access to {error.cdn_name} requires approval.",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=theme.COLORS["warning"],
            wraplength=380,
        ).pack(pady=(20, 4), **pad)

        ctk.CTkLabel(
            dialog,
            text="You may provide a reason for your request (optional):",
            font=ctk.CTkFont(size=12),
            text_color=theme.COLORS["text_muted"],
        ).pack(pady=(4, 8), **pad)

        reason_entry = ctk.CTkEntry(
            dialog,
            placeholder_text="Reason for access...",
            width=360,
            height=32,
        )
        reason_entry.pack(**pad)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(16, 10), **pad)

        def _submit():
            reason = reason_entry.get().strip()
            dialog.destroy()

            if not self._cdn_auth:
                self.show_toast("CDN auth not initialized.", "error")
                return

            def _bg():
                return self._cdn_auth.request_access(reason=reason)

            def _done(resp):
                self.show_toast("Access request submitted.", "success")

            def _err(e):
                self.show_toast(f"Request failed: {e}", "error")

            self.run_async(_bg, on_done=_done, on_error=_err)

        ctk.CTkButton(
            btn_frame,
            text="Request Access",
            width=160,
            fg_color=theme.COLORS["accent"],
            command=_submit,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            fg_color=theme.COLORS["bg_elevated"],
            command=dialog.destroy,
        ).pack(side="left")

    # ── Lifecycle ───────────────────────────────────────────────

    def _on_startup(self):
        """Run on first tick — detect game, load state, check for app updates."""
        home = self._frames.get("home")
        if home and hasattr(home, "refresh"):
            home.refresh()

        # Check for updater self-updates silently after a short delay
        self.after(1000, self._check_app_update)

        # Auto-check for game updates if enabled in settings
        if self.settings.check_updates_on_start:
            self.after(2000, self._auto_check_game_updates)

        # Auto-contribute GreenLuma keys silently in background
        self.after(5000, self._auto_contribute_keys)

        # Send telemetry heartbeat
        self.after(7000, self._send_heartbeat)

    def _auto_check_game_updates(self):
        """Automatically check for game updates on startup if configured."""
        if not self.settings.manifest_url:
            return
        home = self._frames.get("home")
        if home and hasattr(home, "_on_check_updates"):
            home._on_check_updates()

    def _check_app_update(self):
        """Silently check GitHub for a new updater version."""
        home = self._frames.get("home")
        if home and hasattr(home, "check_app_update"):
            home.check_app_update()

    def _auto_contribute_keys(self):
        """Silently scan and contribute GreenLuma depot keys on startup."""
        if not self.settings.contribute_url:
            return

        def _bg():
            from pathlib import Path as _Path

            from ..greenluma.contribute import (
                scan_gl_contributions,
                submit_gl_contribution,
            )
            from ..greenluma.orchestrator import GreenLumaOrchestrator
            from ..greenluma.steam import detect_steam_path, get_steam_info

            # Detect Steam
            steam_path_str = self.settings.steam_path
            steam_path = _Path(steam_path_str) if steam_path_str else detect_steam_path()
            if not steam_path or not steam_path.is_dir():
                return None

            steam_info = get_steam_info(steam_path)
            if not steam_info.config_vdf_path.is_file():
                return None

            # Check readiness for all DLCs (works without GL)
            catalog = self.updater._dlc_manager.catalog
            orch = GreenLumaOrchestrator(steam_info)
            readiness = orch.check_readiness(catalog)

            # Scan for keys + manifests we can contribute
            scan = scan_gl_contributions(steam_info, readiness)
            if scan.count == 0:
                return None

            # Submit silently
            resp = submit_gl_contribution(
                scan.contributions,
                url=self.settings.contribute_url,
            )
            return {
                "count": scan.count,
                "status": resp.get("status", "unknown"),
            }

        def _done(result):
            if not result:
                return
            count = result["count"]
            status = result["status"]
            if status == "accepted":
                self.show_toast(
                    f"Contributed {count} depot key(s) — thank you!",
                    "success",
                )

        self.run_async(_bg, on_done=_done, on_error=lambda e: None)

    def _send_heartbeat(self):
        """Send telemetry heartbeat in a daemon thread (fire-and-forget)."""
        import threading

        def _bg():
            try:
                game_version = None
                crack_format = None
                dlc_count = None
                game_detected = False

                game_dir = self.updater.find_game_dir()
                if game_dir:
                    game_detected = True
                    try:
                        from ..core.version_detect import VersionDetector

                        detector = VersionDetector()
                        result = detector.detect(game_dir)
                        game_version = result.version
                    except Exception:
                        pass
                    try:
                        from ..dlc.formats import detect_format

                        adapter = detect_format(game_dir)
                        if adapter:
                            crack_format = adapter.get_format_name()
                    except Exception:
                        pass
                    try:
                        dlc_states = self.updater._dlc_manager.get_dlc_states(game_dir)
                        dlc_count = sum(1 for s in dlc_states.values() if s)
                    except Exception:
                        pass

                locale = self.settings.language or None
                self.telemetry.heartbeat(
                    game_version=game_version,
                    crack_format=crack_format,
                    dlc_count=dlc_count,
                    game_detected=game_detected,
                    locale=locale,
                )
                self.telemetry.track_event(
                    "app_launch",
                    {
                        "session_id": self.telemetry.session_id,
                    },
                )
                # Cache game info for periodic heartbeats and start 5-min pings
                self.telemetry.set_game_info(
                    game_version=game_version,
                    crack_format=crack_format,
                    dlc_count=dlc_count,
                    game_detected=game_detected,
                    locale=locale,
                )
                self.telemetry.start_periodic_heartbeat(300)
            except Exception:
                pass  # Never fail

        threading.Thread(target=_bg, daemon=True).start()

    def _on_close(self):
        """Handle window close."""
        with contextlib.suppress(Exception):
            self.telemetry.session_end()
        try:
            self._animator.cancel_all()
            self.updater.exiting.set()
            # Save window geometry before closing
            self.settings.window_geometry = self.geometry()
            self.settings.save()
            self.updater.close()
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self.destroy()

    def switch_to_progress(self):
        """Switch to progress frame (called when update starts)."""
        self._progress_indicator.grid()
        self._progress_nav_btn.grid()
        self._show_frame("progress")

    def switch_to_home(self):
        """Switch back to home after operation completes."""
        self._progress_indicator.grid_remove()
        self._progress_nav_btn.grid_remove()
        self._show_frame("home")


def launch():
    """Entry point for the GUI."""
    app = App()
    app.mainloop()
