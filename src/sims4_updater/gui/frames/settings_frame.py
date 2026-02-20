"""
Settings frame — game path, language, manifest URL, preferences.
"""

from __future__ import annotations

import tkinter.filedialog
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import InfoCard, get_animator

if TYPE_CHECKING:
    from ..app import App


class SettingsFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)

        # ── Title ──
        ctk.CTkLabel(
            self,
            text="Settings",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, padx=30, pady=(20, 15), sticky="w")

        # ── Settings card (with hover glow) ──
        card = InfoCard(self)
        card.grid(row=1, column=0, padx=30, pady=0, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        row = 0

        # Game directory
        ctk.CTkLabel(
            card,
            text="Game Directory",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=row, column=0, padx=theme.CARD_PAD_X, pady=(theme.CARD_PAD_Y, 2), sticky="w")
        row += 1

        path_frame = ctk.CTkFrame(card, fg_color="transparent")
        path_frame.grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=(0, 10), sticky="ew")
        path_frame.grid_columnconfigure(0, weight=1)

        self._game_dir_entry = ctk.CTkEntry(
            path_frame,
            font=ctk.CTkFont(size=12),
            height=36,
        )
        self._game_dir_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        ctk.CTkButton(
            path_frame,
            text="Browse",
            font=ctk.CTkFont(size=12),
            height=36,
            width=80,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            command=self._browse_game_dir,
        ).grid(row=0, column=1)

        row += 1

        # ── Separator ──
        ctk.CTkFrame(
            card, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=6, sticky="ew")
        row += 1

        # Manifest URL
        ctk.CTkLabel(
            card,
            text="Manifest URL",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=row, column=0, padx=theme.CARD_PAD_X, pady=(6, 2), sticky="w")
        row += 1

        self._manifest_entry = ctk.CTkEntry(
            card,
            font=ctk.CTkFont(size=12),
            height=36,
            placeholder_text="https://example.com/manifest.json",
        )
        self._manifest_entry.grid(
            row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=(0, 10), sticky="ew"
        )
        row += 1

        # ── Separator ──
        ctk.CTkFrame(
            card, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=6, sticky="ew")
        row += 1

        # Language
        ctk.CTkLabel(
            card,
            text="Language",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=row, column=0, padx=theme.CARD_PAD_X, pady=(6, 2), sticky="w")
        row += 1

        from ...language.changer import LANGUAGES

        lang_values = [f"{code} — {name}" for code, name in LANGUAGES.items()]
        self._lang_var = ctk.StringVar()

        self._lang_dropdown = ctk.CTkComboBox(
            card,
            values=lang_values,
            variable=self._lang_var,
            font=ctk.CTkFont(size=12),
            height=36,
            state="readonly",
        )
        self._lang_dropdown.grid(
            row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=(0, 10), sticky="ew"
        )
        row += 1

        # ── Separator ──
        ctk.CTkFrame(
            card, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=6, sticky="ew")
        row += 1

        # Theme
        ctk.CTkLabel(
            card,
            text="Theme",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=row, column=0, padx=theme.CARD_PAD_X, pady=(6, 2), sticky="w")
        row += 1

        self._theme_var = ctk.StringVar(value="Dark")
        theme_frame = ctk.CTkFrame(card, fg_color="transparent")
        theme_frame.grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=(0, 10), sticky="w")

        ctk.CTkRadioButton(
            theme_frame,
            text="Dark",
            variable=self._theme_var,
            value="Dark",
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(0, 20))

        ctk.CTkRadioButton(
            theme_frame,
            text="Light",
            variable=self._theme_var,
            value="Light",
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(0, 20))

        ctk.CTkRadioButton(
            theme_frame,
            text="System",
            variable=self._theme_var,
            value="System",
            font=ctk.CTkFont(size=12),
        ).pack(side="left")

        row += 1

        # ── Separator ──
        ctk.CTkFrame(
            card, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=6, sticky="ew")
        row += 1

        # Check on start
        self._check_start_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            card,
            text="Check for updates on startup",
            variable=self._check_start_var,
            font=ctk.CTkFont(size=12),
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=(6, theme.CARD_PAD_Y), sticky="w")

        row += 1

        # ── Save button ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=theme.SECTION_PAD, pady=20, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)

        self._save_btn = ctk.CTkButton(
            btn_frame,
            text="Save Settings",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._save_settings,
        )
        self._save_btn.grid(row=0, column=0, sticky="ew")

        self._status_label = ctk.CTkLabel(
            btn_frame,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
        )
        self._status_label.grid(row=1, column=0, pady=(8, 0), sticky="w")

    def on_show(self):
        """Load current settings into fields."""
        settings = self.app.settings

        self._game_dir_entry.delete(0, "end")
        if settings.game_path:
            self._game_dir_entry.insert(0, settings.game_path)

        self._manifest_entry.delete(0, "end")
        if settings.manifest_url:
            self._manifest_entry.insert(0, settings.manifest_url)

        # Set language dropdown
        from ...language.changer import LANGUAGES

        current_lang = settings.language or "English"
        for code, name in LANGUAGES.items():
            display = f"{code} — {name}"
            if code == current_lang or name == current_lang:
                self._lang_var.set(display)
                break

        # Theme
        theme_map = {"dark": "Dark", "light": "Light", "system": "System"}
        self._theme_var.set(theme_map.get(settings.theme, "Dark"))

        self._check_start_var.set(settings.check_updates_on_start)
        self._status_label.configure(text="")

    def _browse_game_dir(self):
        path = tkinter.filedialog.askdirectory(
            title="Select Sims 4 Installation Directory",
            parent=self,
        )
        if path:
            self._game_dir_entry.delete(0, "end")
            self._game_dir_entry.insert(0, path)

    def _save_settings(self):
        settings = self.app.settings

        settings.game_path = self._game_dir_entry.get().strip()
        settings.manifest_url = self._manifest_entry.get().strip()

        # Parse language from dropdown
        lang_display = self._lang_var.get()
        if " — " in lang_display:
            lang_code = lang_display.split(" — ")[0]
            settings.language = lang_code

        # Theme
        theme_val = self._theme_var.get().lower()
        settings.theme = theme_val
        ctk.set_appearance_mode(theme_val)

        settings.check_updates_on_start = self._check_start_var.get()

        try:
            settings.save()
            self._status_label.configure(text="")
            self.app.show_toast("Settings saved!", "success")

            # Flash save button green → back to accent
            animator = get_animator()
            animator.cancel_all(self._save_btn, tag="save_flash")
            animator.animate_color(
                self._save_btn, "fg_color",
                theme.COLORS["success"], theme.COLORS["accent"],
                600, tag="save_flash",
            )
        except Exception as e:
            self._status_label.configure(
                text=f"Error: {e}",
                text_color=theme.COLORS["error"],
            )
