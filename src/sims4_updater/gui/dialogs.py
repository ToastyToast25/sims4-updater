"""
Custom dialog and tooltip widgets for the Sims 4 Updater GUI.

Provides CTkDialog (modal message/input dialogs) and CTkToolTip (hover tooltips)
built on top of customtkinter, replacing tkinter.messagebox usage.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from . import theme


class CTkDialog:
    """Static dialog helpers using CTkToplevel modals.

    All methods block until the user responds (via a nested event loop).
    """

    @staticmethod
    def _center_dialog(dialog: ctk.CTkToplevel, width: int, height: int):
        """Center a dialog over its parent window."""
        dialog.update_idletasks()
        parent = dialog.master
        if parent and parent.winfo_exists():
            px = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
            py = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        else:
            px = (dialog.winfo_screenwidth() - width) // 2
            py = (dialog.winfo_screenheight() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(0, px)}+{max(0, py)}")

    @staticmethod
    def _make_dialog(
        parent: ctk.CTk | ctk.CTkToplevel,
        title: str,
        width: int = 420,
        height: int = 200,
    ) -> ctk.CTkToplevel:
        """Create a transient, modal CTkToplevel dialog."""
        dialog = ctk.CTkToplevel(parent)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(parent)
        dialog.grab_set()
        dialog.attributes("-topmost", True)
        dialog.configure(fg_color=theme.COLORS["bg_surface"])
        CTkDialog._center_dialog(dialog, width, height)
        return dialog

    @staticmethod
    def ask_yes_no(
        parent: ctk.CTk | ctk.CTkToplevel,
        *,
        title: str = "Question",
        message: str = "",
    ) -> bool:
        """Show a yes/no question dialog. Returns True for Yes, False for No."""
        result = tk.BooleanVar(value=False)
        dialog = CTkDialog._make_dialog(parent, title, width=420, height=180)

        ctk.CTkLabel(
            dialog,
            text=message,
            font=ctk.CTkFont(size=13),
            text_color=theme.COLORS["text"],
            wraplength=380,
        ).pack(padx=20, pady=(24, 16))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(0, 16))

        def _yes():
            result.set(True)
            dialog.destroy()

        def _no():
            result.set(False)
            dialog.destroy()

        ctk.CTkButton(
            btn_frame,
            text="Yes",
            width=100,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=_yes,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="No",
            width=100,
            fg_color=theme.COLORS["bg_card"],
            hover_color=theme.COLORS["card_hover"],
            command=_no,
        ).pack(side="left")

        dialog.protocol("WM_DELETE_WINDOW", _no)
        dialog.wait_window()
        return result.get()

    @staticmethod
    def show_error(
        parent: ctk.CTk | ctk.CTkToplevel,
        *,
        title: str = "Error",
        message: str = "",
    ) -> None:
        """Show an error message dialog with an OK button."""
        dialog = CTkDialog._make_dialog(parent, title, width=440, height=200)

        # Error icon
        ctk.CTkLabel(
            dialog,
            text="\u26d4",
            font=ctk.CTkFont(size=24),
            text_color=theme.COLORS["error"],
        ).pack(pady=(16, 4))

        ctk.CTkLabel(
            dialog,
            text=message,
            font=ctk.CTkFont(size=12),
            text_color=theme.COLORS["text"],
            wraplength=400,
        ).pack(padx=20, pady=(0, 16))

        ctk.CTkButton(
            dialog,
            text="OK",
            width=100,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=dialog.destroy,
        ).pack(pady=(0, 16))

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.wait_window()

    @staticmethod
    def show_info(
        parent: ctk.CTk | ctk.CTkToplevel,
        *,
        title: str = "Info",
        message: str = "",
    ) -> None:
        """Show an informational message dialog with an OK button."""
        dialog = CTkDialog._make_dialog(parent, title, width=440, height=200)

        # Info icon
        ctk.CTkLabel(
            dialog,
            text="\u2139",
            font=ctk.CTkFont(size=24),
            text_color=theme.COLORS["accent"],
        ).pack(pady=(16, 4))

        ctk.CTkLabel(
            dialog,
            text=message,
            font=ctk.CTkFont(size=12),
            text_color=theme.COLORS["text"],
            wraplength=400,
        ).pack(padx=20, pady=(0, 16))

        ctk.CTkButton(
            dialog,
            text="OK",
            width=100,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=dialog.destroy,
        ).pack(pady=(0, 16))

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.wait_window()

    @staticmethod
    def ask_input(
        parent: ctk.CTk | ctk.CTkToplevel,
        *,
        title: str = "Input",
        message: str = "",
        detail: str = "",
        placeholder: str = "",
    ) -> str | None:
        """Show an input dialog. Returns the entered string, or None if cancelled."""
        result: list[str | None] = [None]
        dialog = CTkDialog._make_dialog(parent, title, width=440, height=260)

        ctk.CTkLabel(
            dialog,
            text=message,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=theme.COLORS["warning"],
            wraplength=400,
        ).pack(padx=20, pady=(20, 4))

        if detail:
            ctk.CTkLabel(
                dialog,
                text=detail,
                font=ctk.CTkFont(size=12),
                text_color=theme.COLORS["text_muted"],
            ).pack(padx=20, pady=(4, 8))

        entry = ctk.CTkEntry(
            dialog,
            placeholder_text=placeholder,
            width=380,
            height=32,
        )
        entry.pack(padx=20)
        entry.focus_set()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(16, 16))

        def _submit():
            result[0] = entry.get().strip()
            dialog.destroy()

        def _cancel():
            result[0] = None
            dialog.destroy()

        ctk.CTkButton(
            btn_frame,
            text="Submit",
            width=120,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=_submit,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            fg_color=theme.COLORS["bg_card"],
            hover_color=theme.COLORS["card_hover"],
            command=_cancel,
        ).pack(side="left")

        entry.bind("<Return>", lambda e: _submit())
        dialog.protocol("WM_DELETE_WINDOW", _cancel)
        dialog.wait_window()
        return result[0]


class CTkToolTip:
    """Hover tooltip for any tkinter/customtkinter widget.

    Shows a small label near the cursor after a short delay.

    Usage:
        CTkToolTip(button, message="Click to save")
    """

    _DELAY_MS = 400
    _OFFSET_X = 12
    _OFFSET_Y = 8

    def __init__(
        self,
        widget: ctk.CTkBaseClass | tk.Widget,
        *,
        message: str = "",
    ):
        self._widget = widget
        self._message = message
        self._tooltip_window: tk.Toplevel | None = None
        self._after_id: str | None = None

        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")

    def _on_enter(self, event):
        self._schedule(event)

    def _on_leave(self, event):
        self._cancel()
        self._hide()

    def _schedule(self, event):
        self._cancel()
        self._after_id = self._widget.after(self._DELAY_MS, lambda: self._show(event))

    def _cancel(self):
        if self._after_id is not None:
            self._widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self, event):
        if self._tooltip_window is not None:
            return
        x = self._widget.winfo_rootx() + event.x + self._OFFSET_X
        y = self._widget.winfo_rooty() + event.y + self._OFFSET_Y

        tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        tw.configure(bg=theme.COLORS["bg_card"])

        label = tk.Label(
            tw,
            text=self._message,
            fg=theme.COLORS["text"],
            bg=theme.COLORS["bg_card"],
            font=("Segoe UI", 9),
            padx=6,
            pady=3,
        )
        label.pack()

        tw.wm_geometry(f"+{x}+{y}")
        self._tooltip_window = tw

    def _hide(self):
        if self._tooltip_window is not None:
            self._tooltip_window.destroy()
            self._tooltip_window = None
