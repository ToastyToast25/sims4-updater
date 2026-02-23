"""
Reusable GUI components for the CDN Manager.

Components:
  - InfoCard: CTkFrame with hover border glow
  - StatusBadge: colored pill showing status text
  - ToastNotification: slide-in notification from top-right
  - LogPanel: color-coded scrollable log with filtering and export
"""

from __future__ import annotations

import contextlib
from datetime import datetime
from pathlib import Path

import customtkinter as ctk

from . import theme
from .animations import Animator, ease_out_cubic

_animator = Animator()


def get_animator() -> Animator:
    return _animator


# -- InfoCard ---------------------------------------------------------------


class InfoCard(ctk.CTkFrame):
    """CTkFrame with animated border glow on hover."""

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("corner_radius", theme.CORNER_RADIUS)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.COLORS["border"])
        super().__init__(parent, **kwargs)

        self._base_border = kwargs.get("border_color", theme.COLORS["border"])
        self._hover_border = theme.COLORS["accent_glow"]

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event):
        _animator.cancel_all(self, tag="card_hover")
        _animator.animate_color(
            self,
            "border_color",
            self._base_border,
            self._hover_border,
            theme.ANIM_FAST,
            tag="card_hover",
        )

    def _on_leave(self, _event):
        _animator.cancel_all(self, tag="card_hover")
        _animator.animate_color(
            self,
            "border_color",
            self._hover_border,
            self._base_border,
            theme.ANIM_FAST,
            tag="card_hover",
        )


# -- StatusBadge ------------------------------------------------------------

_BADGE_STYLES = {
    "success": {
        "bg": theme.COLORS["toast_success"],
        "text": theme.COLORS["success"],
        "dot": theme.COLORS["success"],
    },
    "warning": {
        "bg": theme.COLORS["toast_warning"],
        "text": theme.COLORS["warning"],
        "dot": theme.COLORS["warning"],
    },
    "error": {
        "bg": theme.COLORS["toast_error"],
        "text": theme.COLORS["error"],
        "dot": theme.COLORS["error"],
    },
    "info": {
        "bg": theme.COLORS["toast_info"],
        "text": theme.COLORS["accent"],
        "dot": theme.COLORS["accent"],
    },
    "muted": {
        "bg": theme.COLORS["bg_card_alt"],
        "text": theme.COLORS["text_muted"],
        "dot": theme.COLORS["text_muted"],
    },
}


class StatusBadge(ctk.CTkFrame):
    """Small colored pill badge showing status text with a dot indicator."""

    def __init__(self, parent, text: str = "", style: str = "muted", **kwargs):
        s = _BADGE_STYLES.get(style, _BADGE_STYLES["muted"])
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("fg_color", s["bg"])
        kwargs.setdefault("height", 26)
        super().__init__(parent, **kwargs)

        self._dot = ctk.CTkLabel(
            self,
            text="\u25cf",
            font=ctk.CTkFont(size=8),
            text_color=s["dot"],
            width=12,
        )
        self._dot.pack(side="left", padx=(10, 0), pady=4)

        self._label = ctk.CTkLabel(
            self,
            text=text,
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=s["text"],
        )
        self._label.pack(side="left", padx=(2, 10), pady=4)
        self._style = style

    def set_status(self, text: str, style: str = ""):
        if style and style != self._style:
            s = _BADGE_STYLES.get(style, _BADGE_STYLES["muted"])
            self._style = style
            old_bg = self.cget("fg_color")
            if isinstance(old_bg, (list, tuple)):
                old_bg = old_bg[0]
            _animator.cancel_all(self, tag="badge")
            _animator.animate_color(
                self,
                "fg_color",
                old_bg,
                s["bg"],
                theme.ANIM_FAST,
                tag="badge",
            )
            self._dot.configure(text_color=s["dot"])
            self._label.configure(text_color=s["text"])
        self._label.configure(text=text)


# -- ToastNotification ------------------------------------------------------

_TOAST_STYLES = {
    "success": {
        "bg": theme.COLORS["toast_success"],
        "border": theme.COLORS["success"],
        "text": theme.COLORS["success"],
        "icon": "\u2713",
        "base_duration": 2500,
    },
    "warning": {
        "bg": theme.COLORS["toast_warning"],
        "border": theme.COLORS["warning"],
        "text": theme.COLORS["warning"],
        "icon": "\u26a0",
        "base_duration": 4000,
    },
    "error": {
        "bg": theme.COLORS["toast_error"],
        "border": theme.COLORS["error"],
        "text": theme.COLORS["error"],
        "icon": "\u2717",
        "base_duration": 6000,
    },
    "info": {
        "bg": theme.COLORS["toast_info"],
        "border": theme.COLORS["accent"],
        "text": theme.COLORS["text"],
        "icon": "\u2139",
        "base_duration": 3000,
    },
}

_MAX_VISIBLE_TOASTS = 3
_TOAST_GAP = 8
_TOAST_HEIGHT_ESTIMATE = 44


class ToastNotification(ctk.CTkFrame):
    _active_toasts: list[ToastNotification] = []

    def __init__(self, parent, message: str, style: str = "success"):
        s = _TOAST_STYLES.get(style, _TOAST_STYLES["info"])
        super().__init__(
            parent,
            corner_radius=8,
            fg_color=s["bg"],
            border_width=1,
            border_color=s["border"],
        )
        self._parent = parent
        self._dismiss_id = None
        self._message = message
        extra = max(0, len(message) - 40) * 50
        self._duration = min(s["base_duration"] + extra, 8000)

        icon = ctk.CTkLabel(
            self,
            text=s["icon"],
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=s["text"],
            width=20,
        )
        icon.pack(side="left", padx=(12, 0), pady=10)

        msg = ctk.CTkLabel(
            self,
            text=message,
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=s["text"],
        )
        msg.pack(side="left", padx=(6, 8), pady=10)

        if style == "error":
            close_btn = ctk.CTkLabel(
                self,
                text="\u2715",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=s["text"],
                width=20,
                cursor="hand2",
            )
            close_btn.pack(side="right", padx=(0, 8), pady=10)
            close_btn.bind("<Button-1>", lambda e: self._dismiss())
        else:
            self.bind("<Button-1>", lambda e: self._dismiss())
            icon.bind("<Button-1>", lambda e: self._dismiss())
            msg.bind("<Button-1>", lambda e: self._dismiss())
            self.configure(cursor="hand2")

    def show(self):
        while len(ToastNotification._active_toasts) >= _MAX_VISIBLE_TOASTS:
            ToastNotification._active_toasts[0]._destroy()
        ToastNotification._active_toasts.append(self)
        y = self._compute_y_offset()
        self.place(relx=1.0, rely=0.0, x=300, y=y, anchor="ne")
        self.lift()
        _animator.animate(
            self,
            theme.TOAST_SLIDE_MS,
            on_tick=lambda t, _y=y: self.place(
                relx=1.0,
                rely=0.0,
                x=int(300 * (1 - t)) - 10,
                y=_y,
                anchor="ne",
            ),
            on_done=self._start_dismiss_timer,
            easing=ease_out_cubic,
        )

    def _compute_y_offset(self) -> int:
        y = 10
        for toast in ToastNotification._active_toasts:
            if toast is self:
                break
            try:
                h = toast.winfo_reqheight()
                if h < 10:
                    h = _TOAST_HEIGHT_ESTIMATE
            except Exception:
                h = _TOAST_HEIGHT_ESTIMATE
            y += h + _TOAST_GAP
        return y

    def _start_dismiss_timer(self):
        self._dismiss_id = self.after(self._duration, self._dismiss)

    def _dismiss(self):
        if self._dismiss_id is not None:
            with contextlib.suppress(Exception):
                self.after_cancel(self._dismiss_id)
            self._dismiss_id = None
        _animator.cancel_all(self)
        _animator.animate(
            self,
            theme.TOAST_SLIDE_MS,
            on_tick=lambda t: self.place(
                relx=1.0,
                rely=0.0,
                x=-10 + int(310 * t),
                y=self._compute_y_offset(),
                anchor="ne",
            ),
            on_done=self._destroy,
            easing=ease_out_cubic,
        )

    def _destroy(self):
        try:
            if self in ToastNotification._active_toasts:
                ToastNotification._active_toasts.remove(self)
            self.place_forget()
            self.destroy()
        except Exception:
            pass
        _reflow_toasts()


def _reflow_toasts():
    for toast in ToastNotification._active_toasts:
        y = toast._compute_y_offset()
        with contextlib.suppress(Exception):
            _animator.animate(
                toast,
                150,
                on_tick=lambda t, _toast=toast, _y=y: _toast.place(
                    relx=1.0,
                    rely=0.0,
                    x=-10,
                    y=_y,
                    anchor="ne",
                ),
                easing=ease_out_cubic,
            )


# -- LogPanel ---------------------------------------------------------------

_LOG_COLORS = {
    "debug": theme.COLORS["text_dim"],
    "info": theme.COLORS["text"],
    "success": theme.COLORS["success"],
    "warning": theme.COLORS["warning"],
    "error": theme.COLORS["error"],
}

_LOG_LEVELS = ["debug", "info", "success", "warning", "error"]


class LogPanel(ctk.CTkFrame):
    """Color-coded scrollable log panel with filtering, copy, and export."""

    def __init__(self, parent, max_lines: int = 5000, **kwargs):
        kwargs.setdefault("fg_color", theme.COLORS["bg_deeper"])
        kwargs.setdefault("corner_radius", theme.CORNER_RADIUS_SMALL)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.COLORS["border"])
        super().__init__(parent, **kwargs)

        self._max_lines = max_lines
        self._line_count = 0
        self._min_level = "debug"
        self._auto_scroll = True
        self._collapsed = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Toolbar
        toolbar = ctk.CTkFrame(self, fg_color="transparent", height=28)
        toolbar.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 0))
        toolbar.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            toolbar,
            text="Log",
            font=ctk.CTkFont(*theme.FONT_SMALL, "bold"),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=0, column=0, padx=(4, 8))

        self._level_menu = ctk.CTkOptionMenu(
            toolbar,
            values=["All", "Info+", "Warnings+", "Errors"],
            width=90,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10),
            fg_color=theme.COLORS["bg_card_alt"],
            button_color=theme.COLORS["bg_card_alt"],
            button_hover_color=theme.COLORS["card_hover"],
            command=self._on_filter_change,
        )
        self._level_menu.set("All")
        self._level_menu.grid(row=0, column=1, padx=2)

        btn_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        btn_frame.grid(row=0, column=3)

        self._copy_btn = ctk.CTkButton(
            btn_frame,
            text="Copy",
            width=50,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10),
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self.copy_to_clipboard,
        )
        self._copy_btn.pack(side="left", padx=2)

        self._export_btn = ctk.CTkButton(
            btn_frame,
            text="Export",
            width=55,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10),
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._export_dialog,
        )
        self._export_btn.pack(side="left", padx=2)

        self._clear_btn = ctk.CTkButton(
            btn_frame,
            text="Clear",
            width=50,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10),
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self.clear,
        )
        self._clear_btn.pack(side="left", padx=2)

        # Log textbox
        self._textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont("Consolas", 11),
            fg_color=theme.COLORS["bg_deeper"],
            corner_radius=0,
            border_width=0,
            state="disabled",
            wrap="none",
            activate_scrollbars=True,
        )
        self._textbox.grid(row=1, column=0, sticky="nsew", padx=4, pady=(4, 4))

        # Configure color tags
        for level, color in _LOG_COLORS.items():
            self._textbox._textbox.tag_configure(level, foreground=color)
        self._textbox._textbox.tag_configure(
            "timestamp",
            foreground=theme.COLORS["text_dim"],
        )

    def log(self, message: str, level: str = "info"):
        if level not in _LOG_LEVELS:
            level = "info"
        if _LOG_LEVELS.index(level) < _LOG_LEVELS.index(self._min_level):
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        self._textbox.configure(state="normal")
        self._textbox._textbox.insert("end", f"[{timestamp}] ", "timestamp")
        self._textbox._textbox.insert("end", f"{message}\n", level)

        self._line_count += 1
        if self._max_lines and self._line_count > self._max_lines:
            self._textbox._textbox.delete("1.0", "2.0")
            self._line_count -= 1

        if self._auto_scroll:
            self._textbox.see("end")
        self._textbox.configure(state="disabled")

    def clear(self):
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")
        self._line_count = 0

    def copy_to_clipboard(self):
        text = self._textbox._textbox.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)

    def export_to_file(self, path: str):
        text = self._textbox._textbox.get("1.0", "end-1c")
        Path(path).write_text(text, encoding="utf-8")

    def _export_dialog(self):
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt")],
            initialfile=f"cdn_manager_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        )
        if path:
            self.export_to_file(path)

    def _on_filter_change(self, value: str):
        mapping = {"All": "debug", "Info+": "info", "Warnings+": "warning", "Errors": "error"}
        self._min_level = mapping.get(value, "debug")

    def set_filter(self, min_level: str):
        self._min_level = min_level

    def set_global_logger(self, app, source: str = ""):
        """Wire this log panel to the app's global log collector."""
        self._global_app = app
        self._global_source = source

        original_log = self.log

        def _log_with_global(message: str, level: str = "info"):
            original_log(message, level)
            if hasattr(self, "_global_app") and self._global_app:
                self._global_app.global_log(message, level, self._global_source)

        self.log = _log_with_global
