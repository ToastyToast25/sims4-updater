"""
Reusable animated GUI components for the Sims 4 Updater.

Components:
  - InfoCard: CTkFrame with hover border glow
  - StatusBadge: colored pill showing status text
  - ToastNotification: slide-in notification from top-right
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from . import theme
from .animations import Animator, lerp_color, ease_out_cubic

if TYPE_CHECKING:
    pass


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
        self._base_fg = self.cget("fg_color")
        self._hover_border = theme.COLORS["accent_glow"]
        self._hover_fg = theme.COLORS["card_hover"]

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event):
        _animator.cancel_all(self, tag="card_hover")
        _animator.animate_color(
            self, "border_color",
            self._base_border, self._hover_border,
            theme.ANIM_FAST, tag="card_hover",
        )

    def _on_leave(self, _event):
        _animator.cancel_all(self, tag="card_hover")
        _animator.animate_color(
            self, "border_color",
            self._hover_border, self._base_border,
            theme.ANIM_FAST, tag="card_hover",
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
                self, "fg_color", old_bg, s["bg"],
                theme.ANIM_FAST, tag="badge",
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
    },
    "warning": {
        "bg": theme.COLORS["toast_warning"],
        "border": theme.COLORS["warning"],
        "text": theme.COLORS["warning"],
        "icon": "\u26a0",
    },
    "error": {
        "bg": theme.COLORS["toast_error"],
        "border": theme.COLORS["error"],
        "text": theme.COLORS["error"],
        "icon": "\u2717",
    },
    "info": {
        "bg": theme.COLORS["toast_info"],
        "border": theme.COLORS["accent"],
        "text": theme.COLORS["text"],
        "icon": "\u2139",
    },
}


class ToastNotification(ctk.CTkFrame):
    """Slide-in notification from top-right corner."""

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
        msg.pack(side="left", padx=(6, 14), pady=10)

        # Click anywhere on the toast to dismiss
        self.bind("<Button-1>", lambda e: self._dismiss())
        icon.bind("<Button-1>", lambda e: self._dismiss())
        msg.bind("<Button-1>", lambda e: self._dismiss())
        self.configure(cursor="hand2")

    def show(self):
        """Animate toast sliding in from the right edge."""
        # Position off-screen to the right
        self.place(relx=1.0, rely=0.0, x=300, y=10, anchor="ne")
        self.lift()

        # Slide in
        _animator.animate(
            self, theme.TOAST_SLIDE_MS,
            on_tick=lambda t: self.place(
                relx=1.0, rely=0.0,
                x=int(300 * (1 - t)) - 10,
                y=10, anchor="ne",
            ),
            on_done=self._start_dismiss_timer,
            easing=ease_out_cubic,
        )

    def _start_dismiss_timer(self):
        self._dismiss_id = self.after(theme.TOAST_DURATION, self._dismiss)

    def _dismiss(self):
        """Slide out and destroy."""
        _animator.cancel_all(self)
        _animator.animate(
            self, theme.TOAST_SLIDE_MS,
            on_tick=lambda t: self.place(
                relx=1.0, rely=0.0,
                x=-10 + int(310 * t),
                y=10, anchor="ne",
            ),
            on_done=self._destroy,
            easing=ease_out_cubic,
        )

    def _destroy(self):
        try:
            self.place_forget()
            self.destroy()
        except Exception:
            pass
