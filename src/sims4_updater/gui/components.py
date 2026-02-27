"""
Reusable animated GUI components for the Sims 4 Updater.

Components:
  - InfoCard: CTkFrame with hover border glow
  - StatusBadge: colored pill showing status text
  - ToastNotification: slide-in notification from top-right
  - ConfirmDialog: themed Yes/No confirmation dialog
  - ThreeButtonDialog: themed Yes/No/Cancel dialog
  - Tooltip: hover tooltip for widgets
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import customtkinter as ctk

from . import theme
from .animations import Animator, ease_out_cubic

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Shared animator instance for all components
_animator = Animator()


def get_animator() -> Animator:
    return _animator


# ── InfoCard ────────────────────────────────────────────────────


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


# ── StatusBadge ─────────────────────────────────────────────────

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
        """Update badge text and optionally change style."""
        if style and style != self._style:
            s = _BADGE_STYLES.get(style, _BADGE_STYLES["muted"])
            self._style = style

            # Animate color transition
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


# ── ToastNotification ───────────────────────────────────────────

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
_TOAST_HEIGHT_ESTIMATE = 44  # fallback if winfo_reqheight unavailable


class ToastNotification(ctk.CTkFrame):
    """Slide-in notification from top-right corner with stacking support."""

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
        self._style_key = style
        self._message = message

        # Compute auto-dismiss duration: base + 50ms per char over 40
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

        # Error toasts get an explicit close button
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
            # Click anywhere on non-error toasts to dismiss
            self.bind("<Button-1>", lambda e: self._dismiss())
            icon.bind("<Button-1>", lambda e: self._dismiss())
            msg.bind("<Button-1>", lambda e: self._dismiss())
            self.configure(cursor="hand2")

    def show(self):
        """Animate toast sliding in from the right edge with stacking."""
        # Enforce max visible — dismiss oldest if over limit
        while len(ToastNotification._active_toasts) >= _MAX_VISIBLE_TOASTS:
            oldest = ToastNotification._active_toasts[0]
            oldest._destroy()

        ToastNotification._active_toasts.append(self)
        y = self._compute_y_offset()

        # Position off-screen to the right
        self.place(relx=1.0, rely=0.0, x=300, y=y, anchor="ne")
        self.lift()

        # Slide in
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
        """Compute vertical position based on toasts above this one."""
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
        """Slide out and destroy."""
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
            logger.debug("Toast cleanup error", exc_info=True)
        # Reposition remaining toasts
        _reflow_toasts()


def _reflow_toasts():
    """Reposition all visible toasts after one is removed."""
    for toast in ToastNotification._active_toasts:
        try:
            if not toast.winfo_exists():
                continue
        except Exception:
            continue
        target_y = toast._compute_y_offset()
        try:
            current_y = toast.winfo_y()
        except Exception:
            current_y = target_y
        if current_y == target_y:
            continue
        with contextlib.suppress(Exception):
            _animator.animate(
                toast,
                150,
                on_tick=lambda t, _toast=toast, _from=current_y, _to=target_y: _toast.place(
                    relx=1.0,
                    rely=0.0,
                    x=-10,
                    y=int(_from + (_to - _from) * t),
                    anchor="ne",
                ),
                easing=ease_out_cubic,
            )


# ── ConfirmDialog ──────────────────────────────────────────────


class ConfirmDialog(ctk.CTkToplevel):
    """Themed Yes/No confirmation dialog replacing tk.messagebox.askyesno."""

    def __init__(self, parent, title: str = "Confirm", message: str = ""):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=theme.COLORS["bg_dark"])
        self.grab_set()
        self.focus_force()

        self._result: bool = False

        # Center relative to parent
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_no)

        pad = ctk.CTkFrame(self, fg_color="transparent")
        pad.pack(padx=24, pady=(20, 16), fill="both", expand=True)

        ctk.CTkLabel(
            pad,
            text=message,
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text"],
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(0, 16))

        btn_frame = ctk.CTkFrame(pad, fg_color="transparent")
        btn_frame.pack(fill="x")

        ctk.CTkButton(
            btn_frame,
            text="No",
            width=90,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_no,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_frame,
            text="Yes",
            width=90,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_yes,
        ).pack(side="right")

        # Wait for user action
        self.wait_window()

    def _on_yes(self):
        self._result = True
        self.grab_release()
        self.destroy()

    def _on_no(self):
        self._result = False
        self.grab_release()
        self.destroy()

    def get_result(self) -> bool:
        return self._result


def ask_yes_no(parent, title: str, message: str) -> bool:
    """Show a themed Yes/No dialog. Returns True for Yes, False for No."""
    dialog = ConfirmDialog(parent, title=title, message=message)
    return dialog.get_result()


# ── ThreeButtonDialog ──────────────────────────────────────────


class ThreeButtonDialog(ctk.CTkToplevel):
    """Themed Yes/No/Cancel dialog replacing tk.messagebox.askyesnocancel.

    get_result() returns True (Yes), False (No), or None (Cancel/closed).
    """

    def __init__(self, parent, title: str = "Confirm", message: str = ""):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=theme.COLORS["bg_dark"])
        self.grab_set()
        self.focus_force()

        self._result: bool | None = None

        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        pad = ctk.CTkFrame(self, fg_color="transparent")
        pad.pack(padx=24, pady=(20, 16), fill="both", expand=True)

        ctk.CTkLabel(
            pad,
            text=message,
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text"],
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(0, 16))

        btn_frame = ctk.CTkFrame(pad, fg_color="transparent")
        btn_frame.pack(fill="x")

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=90,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card"],
            hover_color=theme.COLORS["hover_cancel"],
            command=self._on_cancel,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_frame,
            text="No",
            width=90,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card"],
            hover_color=theme.COLORS["card_hover"],
            command=self._on_no,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_frame,
            text="Yes",
            width=90,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_yes,
        ).pack(side="right")

        self.wait_window()

    def _on_yes(self):
        self._result = True
        self.grab_release()
        self.destroy()

    def _on_no(self):
        self._result = False
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self._result = None
        self.grab_release()
        self.destroy()

    def get_result(self) -> bool | None:
        return self._result


def ask_yes_no_cancel(parent, title: str, message: str) -> bool | None:
    """Show a themed Yes/No/Cancel dialog.

    Returns True (Yes), False (No), or None (Cancel/closed).
    """
    dialog = ThreeButtonDialog(parent, title=title, message=message)
    return dialog.get_result()


# ── Tooltip ────────────────────────────────────────────────────


class Tooltip:
    """Hover tooltip for any widget. Shows a small themed popup after a short delay."""

    def __init__(self, widget, message: str, delay: int = 400):
        self._widget = widget
        self._message = message
        self._delay = delay
        self._toplevel: ctk.CTkToplevel | None = None
        self._after_id: str | None = None

        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")

    def _on_enter(self, _event):
        self._after_id = self._widget.after(self._delay, self._show)

    def _on_leave(self, _event):
        if self._after_id is not None:
            self._widget.after_cancel(self._after_id)
            self._after_id = None
        self._hide()

    def _show(self):
        if self._toplevel is not None:
            return
        x = self._widget.winfo_rootx() + self._widget.winfo_width() // 2
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4

        self._toplevel = tw = ctk.CTkToplevel(self._widget)
        tw.withdraw()
        tw.overrideredirect(True)
        tw.configure(fg_color=theme.COLORS["bg_card"])

        label = ctk.CTkLabel(
            tw,
            text=self._message,
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text"],
            corner_radius=4,
            fg_color=theme.COLORS["bg_card"],
        )
        label.pack(padx=8, pady=4)

        tw.update_idletasks()
        tw_width = tw.winfo_reqwidth()
        tw.geometry(f"+{x - tw_width // 2}+{y}")
        tw.deiconify()
        tw.lift()

    def _hide(self):
        if self._toplevel is not None:
            with contextlib.suppress(Exception):
                self._toplevel.destroy()
            self._toplevel = None


# ── RichTextbox ───────────────────────────────────────────────


# Pre-defined style → foreground color mapping
_RICH_STYLES = {
    "header": {"foreground": theme.COLORS["accent"], "font": ("Consolas", 11, "bold")},
    "success": {"foreground": theme.COLORS["success"]},
    "warning": {"foreground": theme.COLORS["warning"]},
    "error": {"foreground": theme.COLORS["error"]},
    "info": {"foreground": theme.COLORS["accent"]},
    "muted": {"foreground": theme.COLORS["text_muted"]},
}


class RichTextbox(ctk.CTkTextbox):
    """CTkTextbox with pre-configured semantic text styles (colored output).

    Usage:
        log = RichTextbox(parent)
        log.add_line("Connected", style="success")
        log.add_line("Warning: low disk space", style="warning")
        log.add_line("=== Header ===", style="header")
        log.clear()
    """

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("font", ctk.CTkFont(*theme.FONT_MONO))
        kwargs.setdefault("fg_color", theme.COLORS["bg_deeper"])
        kwargs.setdefault("text_color", theme.COLORS["text_muted"])
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.COLORS["border"])
        kwargs.setdefault("corner_radius", theme.CORNER_RADIUS_SMALL)
        kwargs.setdefault("state", "disabled")
        kwargs.setdefault("wrap", "word")
        kwargs.setdefault("activate_scrollbars", True)
        super().__init__(parent, **kwargs)

        # Configure text tags on the underlying tk.Text widget
        for tag_name, tag_opts in _RICH_STYLES.items():
            self._textbox.tag_configure(tag_name, **tag_opts)

    def add_text(self, text: str, style: str = ""):
        """Append text, optionally with a semantic style (color tag)."""
        self.configure(state="normal")
        if style and style in _RICH_STYLES:
            self._textbox.insert("end", text, style)
        else:
            self.insert("end", text)
        self.see("end")
        self.configure(state="disabled")

    def add_line(self, text: str, style: str = ""):
        """Append a line (text + newline) with optional style."""
        self.add_text(text + "\n", style=style)

    def clear(self):
        """Clear all content."""
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")


# ── Builder Helpers ───────────────────────────────────────────


def make_section_header(
    parent,
    title: str,
    subtitle: str = "",
) -> tuple[ctk.CTkLabel, ctk.CTkLabel | None]:
    """Create a standard frame header with title and optional subtitle.

    Returns (title_label, subtitle_label_or_None).
    """
    title_lbl = ctk.CTkLabel(
        parent,
        text=title,
        font=ctk.CTkFont(*theme.FONT_TITLE),
        text_color=theme.COLORS["text"],
        anchor="w",
    )
    sub_lbl = None
    if subtitle:
        sub_lbl = ctk.CTkLabel(
            parent,
            text=subtitle,
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
            anchor="w",
        )
    return title_lbl, sub_lbl


def make_separator(parent) -> ctk.CTkFrame:
    """Create a horizontal 1px separator line."""
    return ctk.CTkFrame(
        parent,
        height=1,
        fg_color=theme.COLORS["separator"],
    )


def make_action_button(
    parent,
    text: str,
    style: str = "primary",
    **kwargs,
) -> ctk.CTkButton:
    """Create a themed button using BUTTON_STYLES presets.

    Extra kwargs are forwarded to CTkButton and override style defaults.
    """
    style_props = theme.BUTTON_STYLES.get(style, theme.BUTTON_STYLES["primary"])
    merged = {**style_props, **kwargs}
    merged.setdefault("font", ctk.CTkFont(size=13, weight="bold"))
    merged.setdefault("height", theme.BUTTON_HEIGHT)
    merged.setdefault("corner_radius", theme.CORNER_RADIUS_SMALL)
    return ctk.CTkButton(parent, text=text, **merged)


def make_status_row(
    parent,
    label: str,
    badge_text: str = "...",
    badge_style: str = "muted",
    row: int = 0,
) -> tuple[ctk.CTkLabel, StatusBadge]:
    """Create a label + StatusBadge row for status info cards.

    Grids them at the given row. Returns (label_widget, badge_widget).
    """
    lbl = ctk.CTkLabel(
        parent,
        text=label,
        font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        text_color=theme.COLORS["text"],
    )
    lbl.grid(
        row=row,
        column=0,
        padx=(theme.CARD_PAD_X, 8),
        pady=(theme.CARD_PAD_Y if row == 0 else theme.CARD_ROW_PAD, 4),
        sticky="w",
    )
    badge = StatusBadge(parent, text=badge_text, style=badge_style)
    badge.grid(
        row=row,
        column=1,
        padx=0,
        pady=(theme.CARD_PAD_Y if row == 0 else theme.CARD_ROW_PAD, 4),
        sticky="w",
    )
    return lbl, badge


def make_log_section(
    parent,
    height: int = 180,
) -> tuple[ctk.CTkFrame, RichTextbox, ctk.CTkButton]:
    """Create a standard Activity Log section with header, Clear button, and log widget.

    Returns (header_frame, log_textbox, clear_button).
    """
    header = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(
        header,
        text="Activity Log",
        font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        text_color=theme.COLORS["text"],
    ).pack(side="left")

    clear_btn = ctk.CTkButton(
        header,
        text="Clear",
        width=60,
        height=theme.BUTTON_HEIGHT_SMALL,
        corner_radius=theme.CORNER_RADIUS_SMALL,
        font=ctk.CTkFont(*theme.FONT_SMALL),
        **theme.BUTTON_STYLES["ghost"],
    )
    clear_btn.pack(side="right")

    log = RichTextbox(parent, height=height)
    return header, log, clear_btn


def make_browse_entry(
    parent,
    placeholder: str = "",
    browse_command=None,
) -> tuple[ctk.CTkEntry, ctk.CTkButton]:
    """Create an entry + Browse button pair in a horizontal frame.

    Returns (entry_widget, browse_button). The pair is packed into `parent`.
    """
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.pack(fill="x")
    frame.grid_columnconfigure(0, weight=1)

    entry = ctk.CTkEntry(
        frame,
        font=ctk.CTkFont(*theme.FONT_BODY),
        height=36,
        placeholder_text=placeholder,
        corner_radius=theme.CORNER_RADIUS_SMALL,
    )
    entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

    browse_btn = ctk.CTkButton(
        frame,
        text="Browse",
        width=80,
        height=36,
        corner_radius=theme.CORNER_RADIUS_SMALL,
        font=ctk.CTkFont(*theme.FONT_BODY),
        **theme.BUTTON_STYLES["ghost"],
        command=browse_command,
    )
    browse_btn.grid(row=0, column=1)

    return entry, browse_btn
