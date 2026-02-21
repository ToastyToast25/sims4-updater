"""
Main application window with sidebar navigation.

Threading model:
  - Worker thread runs updater operations via ThreadPoolExecutor
  - deque-based callback queue polled every 100ms by tkinter .after()
  - All GUI updates happen on the main thread via the queue
"""

from __future__ import annotations

import concurrent.futures
import tkinter as tk
import traceback
from collections import deque
from threading import Lock

import customtkinter as ctk

from . import theme
from .animations import Animator, ease_out_cubic
from .components import ToastNotification
from .frames.home_frame import HomeFrame
from .frames.dlc_frame import DLCFrame
from .frames.downloader_frame import DownloaderFrame
from .frames.greenluma_frame import GreenLumaFrame
from .frames.language_frame import LanguageFrame
from .frames.packer_frame import PackerFrame
from .frames.unlocker_frame import UnlockerFrame
from .frames.mods_frame import ModsFrame
from .frames.settings_frame import SettingsFrame
from .frames.progress_frame import ProgressFrame

from ..config import Settings
from ..dlc.steam import SteamPriceCache
from ..updater import Sims4Updater, CallbackType


class App(ctk.CTk):
    """Main Sims 4 Updater GUI application."""

    def __init__(self):
        super().__init__()

        # Window setup
        self.title("Sims 4 Updater")
        self.geometry(f"{theme.WINDOW_WIDTH}x{theme.WINDOW_HEIGHT}")
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
        self._active_toast: ToastNotification | None = None

        # Threading
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._callback_queue: deque = deque()
        self._lock = Lock()
        self._current_future = None

        # Settings, shared state, and updater
        self.settings = Settings.load()
        self.price_cache = SteamPriceCache()
        self.updater = Sims4Updater(
            ask_question=self._ask_question,
            callback=self._enqueue_callback,
            settings=self.settings,
        )

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
            self._sidebar, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=1, column=0, columnspan=2, padx=15, sticky="ew")

        # Nav buttons — two-column grid: col 0 = indicator, col 1 = button
        self._sidebar.grid_columnconfigure(0, weight=0, minsize=8)
        self._sidebar.grid_columnconfigure(1, weight=1)

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._nav_indicators: dict[str, ctk.CTkFrame] = {}
        nav_items = [
            ("home", "Home"),
            ("dlc", "DLCs"),
            ("downloader", "DLC Downloader"),
            ("packer", "DLC Packer"),
            ("unlocker", "Unlocker"),
            ("greenluma", "GreenLuma"),
            ("language", "Language"),
            ("mods", "Mods"),
            ("settings", "Settings"),
        ]

        for i, (key, label) in enumerate(nav_items):
            row_idx = i + 2

            # Left accent bar (3px, hidden by default)
            indicator = ctk.CTkFrame(
                self._sidebar, width=3, height=theme.SIDEBAR_BTN_HEIGHT,
                corner_radius=0, fg_color="transparent",
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

            # Animated hover
            btn.bind("<Enter>", lambda e, k=key: self._on_nav_enter(k))
            btn.bind("<Leave>", lambda e, k=key: self._on_nav_leave(k))

        spacer_row = len(nav_items) + 2
        self._sidebar.grid_rowconfigure(spacer_row, weight=1)

        # Separator above footer
        ctk.CTkFrame(
            self._sidebar, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=spacer_row + 1, column=0, columnspan=2, padx=15, sticky="ew")

        # Footer: version, admin status, copyright, creator, GitHub link
        from .. import VERSION
        from ..core.unlocker import is_admin

        footer = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        footer.grid(
            row=spacer_row + 2, column=0, columnspan=2, padx=18, pady=(8, 14), sticky="ew",
        )

        version_row = ctk.CTkFrame(footer, fg_color="transparent")
        version_row.pack(anchor="w", pady=(0, 1))

        ctk.CTkLabel(
            version_row,
            text=f"v{VERSION}",
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_muted"],
        ).pack(side="left")

        admin_color = theme.COLORS["success"] if is_admin() else theme.COLORS["warning"]
        admin_text = "Admin" if is_admin() else "No Admin"
        admin_pill = ctk.CTkFrame(
            version_row, corner_radius=6, border_width=1,
            border_color=admin_color, fg_color="transparent", height=16,
        )
        admin_pill.pack(side="left", padx=(8, 0))
        ctk.CTkLabel(
            admin_pill, text=admin_text,
            font=ctk.CTkFont(size=7, weight="bold"),
            text_color=admin_color,
        ).pack(padx=4, pady=0)

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
        self._frames["settings"] = SettingsFrame(self._content, self)
        self._frames["progress"] = ProgressFrame(self._content, self)

        for frame in self._frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

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
            try:
                frame.place_forget()
            except Exception:
                pass
            frame.grid(row=0, column=0, sticky="nsew")
            frame.tkraise()
            self._transitioning = False
            if hasattr(frame, "on_show"):
                frame.on_show()

        self._animator.animate(
            frame, theme.ANIM_NORMAL,
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
        msg = str(error)
        if not msg:
            msg = type(error).__name__
        tk.messagebox.showerror("Error", msg, parent=self)

    def show_message(self, title: str, message: str):
        tk.messagebox.showinfo(title, message, parent=self)

    def show_toast(self, message: str, style: str = "success"):
        """Show a slide-in toast notification over the content area."""
        # Dismiss previous toast immediately to prevent stacking
        if self._active_toast is not None:
            try:
                self._active_toast._destroy()
            except Exception:
                pass
        toast = ToastNotification(self._content, message, style)
        self._active_toast = toast
        toast.show()

    # ── Lifecycle ───────────────────────────────────────────────

    def _on_startup(self):
        """Run on first tick — detect game, load state, check for app updates."""
        home = self._frames.get("home")
        if home and hasattr(home, "refresh"):
            home.refresh()

        # Check for updater self-updates silently after a short delay
        self.after(1000, self._check_app_update)

    def _check_app_update(self):
        """Silently check GitHub for a new updater version."""
        home = self._frames.get("home")
        if home and hasattr(home, "check_app_update"):
            home.check_app_update()

    def _on_close(self):
        """Handle window close."""
        try:
            self._animator.cancel_all()
            self.updater.exiting.set()
            self.settings.save()
            self.updater.close()
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self.destroy()

    def switch_to_progress(self):
        """Switch to progress frame (called when update starts)."""
        self._show_frame("progress")

    def switch_to_home(self):
        """Switch back to home after operation completes."""
        self._show_frame("home")


def launch():
    """Entry point for the GUI."""
    app = App()
    app.mainloop()
