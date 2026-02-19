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
from .frames.home_frame import HomeFrame
from .frames.dlc_frame import DLCFrame
from .frames.settings_frame import SettingsFrame
from .frames.progress_frame import ProgressFrame

from ..config import Settings
from ..updater import Sims4Updater, CallbackType


class App(ctk.CTk):
    """Main Sims 4 Updater GUI application."""

    def __init__(self):
        super().__init__()

        # Window setup
        self.title("Sims 4 Updater")
        self.geometry(f"{theme.WINDOW_WIDTH}x{theme.WINDOW_HEIGHT}")
        self.minsize(theme.MIN_WIDTH, theme.MIN_HEIGHT)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Threading
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._callback_queue: deque = deque()
        self._lock = Lock()
        self._current_future = None

        # Settings and updater
        self.settings = Settings.load()
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

        # Logo / title
        logo_label = ctk.CTkLabel(
            self._sidebar,
            text="TS4 Updater",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        logo_label.grid(row=0, column=0, padx=20, pady=(20, 30))

        # Nav buttons
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        nav_items = [
            ("home", "Home"),
            ("dlc", "DLCs"),
            ("settings", "Settings"),
        ]

        for i, (key, label) in enumerate(nav_items):
            btn = ctk.CTkButton(
                self._sidebar,
                text=label,
                font=ctk.CTkFont(size=13),
                height=theme.SIDEBAR_BTN_HEIGHT,
                corner_radius=6,
                fg_color="transparent",
                text_color=theme.COLORS["text_muted"],
                hover_color=theme.COLORS["bg_card"],
                anchor="w",
                command=lambda k=key: self._show_frame(k),
            )
            btn.grid(row=i + 1, column=0, padx=10, pady=2, sticky="ew")
            self._nav_buttons[key] = btn

        self._sidebar.grid_rowconfigure(len(nav_items) + 2, weight=1)

        # Version label at bottom
        from .. import VERSION

        ver_label = ctk.CTkLabel(
            self._sidebar,
            text=f"v{VERSION}",
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_muted"],
        )
        ver_label.grid(row=len(nav_items) + 3, column=0, padx=20, pady=(0, 10))

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
        self._frames["settings"] = SettingsFrame(self._content, self)
        self._frames["progress"] = ProgressFrame(self._content, self)

        for frame in self._frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

    def _show_frame(self, name: str):
        """Switch to a named frame."""
        frame = self._frames.get(name)
        if frame is None:
            return

        # Update nav button colors
        for key, btn in self._nav_buttons.items():
            if key == name:
                btn.configure(
                    fg_color=theme.COLORS["accent"],
                    text_color=theme.COLORS["text"],
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=theme.COLORS["text_muted"],
                )

        frame.tkraise()
        if hasattr(frame, "on_show"):
            frame.on_show()

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

    # ── Lifecycle ───────────────────────────────────────────────

    def _on_startup(self):
        """Run on first tick — detect game, load state."""
        home = self._frames.get("home")
        if home and hasattr(home, "refresh"):
            home.refresh()

    def _on_close(self):
        """Handle window close."""
        try:
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
