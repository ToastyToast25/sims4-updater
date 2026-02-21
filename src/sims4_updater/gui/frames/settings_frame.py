"""
Settings frame — game path, language, patch manifest URL, GreenLuma settings, preferences.
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
        self.grid_rowconfigure(1, weight=1)

        # ── Title ──
        ctk.CTkLabel(
            self,
            text="Settings",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, padx=30, pady=(20, 15), sticky="w")

        # ── Scrollable body ──
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=theme.COLORS["separator"],
            scrollbar_button_hover_color=theme.COLORS["accent"],
        )
        scroll.grid(row=1, column=0, padx=0, pady=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        # ═══════════════════════════════════════════════════════════
        # CARD 1: Game & Updates
        # ═══════════════════════════════════════════════════════════
        card1 = InfoCard(scroll)
        card1.grid(row=0, column=0, padx=30, pady=(0, 15), sticky="ew")
        card1.grid_columnconfigure(1, weight=1)

        row = 0

        # ── Game Directory ──
        ctk.CTkLabel(
            card1, text="Game Directory",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=row, column=0, columnspan=2,
               padx=theme.CARD_PAD_X, pady=(theme.CARD_PAD_Y, 2), sticky="w")
        row += 1

        path_frame = ctk.CTkFrame(card1, fg_color="transparent")
        path_frame.grid(
            row=row, column=0, columnspan=2,
            padx=theme.CARD_PAD_X, pady=(0, 10), sticky="ew",
        )
        path_frame.grid_columnconfigure(0, weight=1)

        self._game_dir_entry = ctk.CTkEntry(
            path_frame, font=ctk.CTkFont(size=12), height=36,
            placeholder_text=r"C:\Program Files (x86)\Steam\steamapps\common\The Sims 4",
        )
        self._game_dir_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        ctk.CTkButton(
            path_frame, text="Browse", font=ctk.CTkFont(size=12),
            height=36, width=80, corner_radius=theme.CORNER_RADIUS_SMALL,
            command=self._browse_game_dir,
        ).grid(row=0, column=1, padx=(0, 5))

        ctk.CTkButton(
            path_frame, text="Auto Detect", font=ctk.CTkFont(size=12),
            height=36, width=100, corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._auto_detect_game_dir,
        ).grid(row=0, column=2)

        row += 1

        # ── Separator ──
        ctk.CTkFrame(
            card1, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=6, sticky="ew")
        row += 1

        # ── Patch Manifest URL ──
        ctk.CTkLabel(
            card1, text="Patch Manifest URL",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=row, column=0, columnspan=2,
               padx=theme.CARD_PAD_X, pady=(6, 0), sticky="w")
        row += 1

        ctk.CTkLabel(
            card1, text="URL for game patches and DLC content updates",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=row, column=0, columnspan=2,
               padx=theme.CARD_PAD_X, pady=(0, 4), sticky="w")
        row += 1

        self._manifest_entry = ctk.CTkEntry(
            card1, font=ctk.CTkFont(size=12), height=36,
            placeholder_text="https://example.com/manifest.json",
        )
        self._manifest_entry.grid(
            row=row, column=0, columnspan=2,
            padx=theme.CARD_PAD_X, pady=(0, 10), sticky="ew",
        )
        row += 1

        # ── Separator ──
        ctk.CTkFrame(
            card1, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=6, sticky="ew")
        row += 1

        # ── Language ──
        ctk.CTkLabel(
            card1, text="Language",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=row, column=0, padx=theme.CARD_PAD_X, pady=(6, 2), sticky="w")
        row += 1

        from ...language.changer import LANGUAGES

        lang_values = [f"{code} — {name}" for code, name in LANGUAGES.items()]
        self._lang_var = ctk.StringVar()

        self._lang_dropdown = ctk.CTkComboBox(
            card1, values=lang_values, variable=self._lang_var,
            font=ctk.CTkFont(size=12), height=36, state="readonly",
        )
        self._lang_dropdown.grid(
            row=row, column=0, columnspan=2,
            padx=theme.CARD_PAD_X, pady=(0, 10), sticky="ew",
        )
        row += 1

        # ── Separator ──
        ctk.CTkFrame(
            card1, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=6, sticky="ew")
        row += 1

        # ── Theme ──
        ctk.CTkLabel(
            card1, text="Theme",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=row, column=0, padx=theme.CARD_PAD_X, pady=(6, 2), sticky="w")
        row += 1

        self._theme_var = ctk.StringVar(value="Dark")
        theme_frame = ctk.CTkFrame(card1, fg_color="transparent")
        theme_frame.grid(
            row=row, column=0, columnspan=2,
            padx=theme.CARD_PAD_X, pady=(0, 10), sticky="w",
        )
        for val in ("Dark", "Light", "System"):
            ctk.CTkRadioButton(
                theme_frame, text=val, variable=self._theme_var, value=val,
                font=ctk.CTkFont(size=12),
            ).pack(side="left", padx=(0, 20))
        row += 1

        # ── Separator ──
        ctk.CTkFrame(
            card1, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=6, sticky="ew")
        row += 1

        # ── Check on start ──
        self._check_start_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            card1, text="Check for updates on startup",
            variable=self._check_start_var, font=ctk.CTkFont(size=12),
        ).grid(
            row=row, column=0, columnspan=2,
            padx=theme.CARD_PAD_X, pady=(6, 4), sticky="w",
        )
        row += 1

        # ── DLC-Only Mode ──
        self._skip_update_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            card1, text="DLC-only mode (skip base game updates)",
            variable=self._skip_update_var, font=ctk.CTkFont(size=12),
        ).grid(
            row=row, column=0, columnspan=2,
            padx=theme.CARD_PAD_X, pady=(0, 2), sticky="w",
        )
        row += 1

        ctk.CTkLabel(
            card1,
            text="When enabled, only DLC downloads run — the base game is not patched.",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(
            row=row, column=0, columnspan=2,
            padx=(theme.CARD_PAD_X + 24, theme.CARD_PAD_X),
            pady=(0, theme.CARD_PAD_Y), sticky="w",
        )
        row += 1

        # ═══════════════════════════════════════════════════════════
        # CARD 2: GreenLuma
        # ═══════════════════════════════════════════════════════════
        ctk.CTkLabel(
            scroll, text="GreenLuma",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=1, column=0, padx=30, pady=(5, 2), sticky="w")

        ctk.CTkLabel(
            scroll, text="Settings for Steam DLC downloads via GreenLuma",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=2, column=0, padx=30, pady=(0, 8), sticky="w")

        card2 = InfoCard(scroll)
        card2.grid(row=3, column=0, padx=30, pady=(0, 15), sticky="ew")
        card2.grid_columnconfigure(1, weight=1)

        row = 0

        # ── Steam Path ──
        ctk.CTkLabel(
            card2, text="Steam Path",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=row, column=0, columnspan=2,
               padx=theme.CARD_PAD_X, pady=(theme.CARD_PAD_Y, 2), sticky="w")
        row += 1

        sp_frame = ctk.CTkFrame(card2, fg_color="transparent")
        sp_frame.grid(
            row=row, column=0, columnspan=2,
            padx=theme.CARD_PAD_X, pady=(0, 10), sticky="ew",
        )
        sp_frame.grid_columnconfigure(0, weight=1)

        self._steam_path_entry = ctk.CTkEntry(
            sp_frame, font=ctk.CTkFont(size=12), height=36,
            placeholder_text=r"C:\Program Files (x86)\Steam",
        )
        self._steam_path_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        ctk.CTkButton(
            sp_frame, text="Browse", font=ctk.CTkFont(size=12),
            height=36, width=80, corner_radius=theme.CORNER_RADIUS_SMALL,
            command=self._browse_steam_path,
        ).grid(row=0, column=1)
        row += 1

        # ── Separator ──
        ctk.CTkFrame(
            card2, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=6, sticky="ew")
        row += 1

        # ── GreenLuma Archive ──
        ctk.CTkLabel(
            card2, text="GreenLuma Archive",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=row, column=0, columnspan=2,
               padx=theme.CARD_PAD_X, pady=(6, 2), sticky="w")
        row += 1

        ar_frame = ctk.CTkFrame(card2, fg_color="transparent")
        ar_frame.grid(
            row=row, column=0, columnspan=2,
            padx=theme.CARD_PAD_X, pady=(0, 10), sticky="ew",
        )
        ar_frame.grid_columnconfigure(0, weight=1)

        self._gl_archive_entry = ctk.CTkEntry(
            ar_frame, font=ctk.CTkFont(size=12), height=36,
            placeholder_text=r"C:\path\to\GreenLuma_2025_1.7.0.7z",
        )
        self._gl_archive_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        ctk.CTkButton(
            ar_frame, text="Browse", font=ctk.CTkFont(size=12),
            height=36, width=80, corner_radius=theme.CORNER_RADIUS_SMALL,
            command=self._browse_gl_archive,
        ).grid(row=0, column=1)
        row += 1

        # ── Separator ──
        ctk.CTkFrame(
            card2, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=6, sticky="ew")
        row += 1

        # ── LUA Manifest File ──
        ctk.CTkLabel(
            card2, text="LUA Manifest File",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=row, column=0, columnspan=2,
               padx=theme.CARD_PAD_X, pady=(6, 2), sticky="w")
        row += 1

        lua_frame = ctk.CTkFrame(card2, fg_color="transparent")
        lua_frame.grid(
            row=row, column=0, columnspan=2,
            padx=theme.CARD_PAD_X, pady=(0, 10), sticky="ew",
        )
        lua_frame.grid_columnconfigure(0, weight=1)

        self._gl_lua_entry = ctk.CTkEntry(
            lua_frame, font=ctk.CTkFont(size=12), height=36,
            placeholder_text=r"C:\path\to\manifest.lua",
        )
        self._gl_lua_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        ctk.CTkButton(
            lua_frame, text="Browse", font=ctk.CTkFont(size=12),
            height=36, width=80, corner_radius=theme.CORNER_RADIUS_SMALL,
            command=self._browse_gl_lua,
        ).grid(row=0, column=1)
        row += 1

        # ── Separator ──
        ctk.CTkFrame(
            card2, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=6, sticky="ew")
        row += 1

        # ── Manifest Files Directory ──
        ctk.CTkLabel(
            card2, text="Manifest Files Directory",
            font=ctk.CTkFont(*theme.FONT_BODY_BOLD),
        ).grid(row=row, column=0, columnspan=2,
               padx=theme.CARD_PAD_X, pady=(6, 0), sticky="w")
        row += 1

        ctk.CTkLabel(
            card2, text="Directory containing .manifest files (defaults to Steam depotcache)",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=row, column=0, columnspan=2,
               padx=theme.CARD_PAD_X, pady=(0, 4), sticky="w")
        row += 1

        md_frame = ctk.CTkFrame(card2, fg_color="transparent")
        md_frame.grid(
            row=row, column=0, columnspan=2,
            padx=theme.CARD_PAD_X, pady=(0, 10), sticky="ew",
        )
        md_frame.grid_columnconfigure(0, weight=1)

        self._gl_manifest_dir_entry = ctk.CTkEntry(
            md_frame, font=ctk.CTkFont(size=12), height=36,
            placeholder_text=r"C:\Program Files (x86)\Steam\depotcache",
        )
        self._gl_manifest_dir_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        ctk.CTkButton(
            md_frame, text="Browse", font=ctk.CTkFont(size=12),
            height=36, width=80, corner_radius=theme.CORNER_RADIUS_SMALL,
            command=self._browse_gl_manifest_dir,
        ).grid(row=0, column=1)
        row += 1

        # ── Separator ──
        ctk.CTkFrame(
            card2, height=1, fg_color=theme.COLORS["separator"],
        ).grid(row=row, column=0, columnspan=2, padx=theme.CARD_PAD_X, pady=6, sticky="ew")
        row += 1

        # ── Auto-backup ──
        self._gl_auto_backup_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            card2, text="Auto-backup config.vdf and AppList before changes",
            variable=self._gl_auto_backup_var, font=ctk.CTkFont(size=12),
        ).grid(
            row=row, column=0, columnspan=2,
            padx=theme.CARD_PAD_X, pady=(6, theme.CARD_PAD_Y), sticky="w",
        )
        row += 1

        # ═══════════════════════════════════════════════════════════
        # Save Button (below scroll)
        # ═══════════════════════════════════════════════════════════
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=30, pady=(10, 20), sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)

        self._save_btn = ctk.CTkButton(
            btn_frame, text="Save Settings",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._save_settings,
        )
        self._save_btn.grid(row=0, column=0, sticky="ew")

        self._status_label = ctk.CTkLabel(
            btn_frame, text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
        )
        self._status_label.grid(row=1, column=0, pady=(8, 0), sticky="w")

    # ── Lifecycle ─────────────────────────────────────────────

    def on_show(self):
        """Load current settings into fields."""
        settings = self.app.settings

        self._game_dir_entry.delete(0, "end")
        if settings.game_path:
            self._game_dir_entry.insert(0, settings.game_path)

        self._manifest_entry.delete(0, "end")
        if settings.manifest_url:
            self._manifest_entry.insert(0, settings.manifest_url)

        # Language
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
        self._skip_update_var.set(settings.skip_game_update)

        # GreenLuma fields
        self._steam_path_entry.delete(0, "end")
        if settings.steam_path:
            self._steam_path_entry.insert(0, settings.steam_path)

        self._gl_archive_entry.delete(0, "end")
        if settings.greenluma_archive_path:
            self._gl_archive_entry.insert(0, settings.greenluma_archive_path)

        self._gl_lua_entry.delete(0, "end")
        if settings.greenluma_lua_path:
            self._gl_lua_entry.insert(0, settings.greenluma_lua_path)

        self._gl_manifest_dir_entry.delete(0, "end")
        if settings.greenluma_manifest_dir:
            self._gl_manifest_dir_entry.insert(0, settings.greenluma_manifest_dir)

        self._gl_auto_backup_var.set(settings.greenluma_auto_backup)

        self._status_label.configure(text="")

    # ── Browse Helpers ────────────────────────────────────────

    def _browse_game_dir(self):
        path = tkinter.filedialog.askdirectory(
            title="Select Sims 4 Installation Directory",
            parent=self,
        )
        if path:
            self._game_dir_entry.delete(0, "end")
            self._game_dir_entry.insert(0, path)

    def _auto_detect_game_dir(self):
        try:
            game_dir = self.app.updater.find_game_dir()
            if game_dir:
                self._game_dir_entry.delete(0, "end")
                self._game_dir_entry.insert(0, str(game_dir))
                self.app.show_toast("Game directory detected!", "success")
            else:
                self.app.show_toast("Could not auto-detect game directory.", "warning")
        except Exception:
            self.app.show_toast("Auto-detection failed.", "error")

    def _browse_steam_path(self):
        path = tkinter.filedialog.askdirectory(
            title="Select Steam Installation Directory",
            parent=self,
        )
        if path:
            self._steam_path_entry.delete(0, "end")
            self._steam_path_entry.insert(0, path)

    def _browse_gl_archive(self):
        path = tkinter.filedialog.askopenfilename(
            title="Select GreenLuma 7z Archive",
            filetypes=[("7z Archives", "*.7z"), ("All Files", "*.*")],
            parent=self,
        )
        if path:
            self._gl_archive_entry.delete(0, "end")
            self._gl_archive_entry.insert(0, path)

    def _browse_gl_lua(self):
        path = tkinter.filedialog.askopenfilename(
            title="Select LUA Manifest File",
            filetypes=[("LUA Files", "*.lua"), ("All Files", "*.*")],
            parent=self,
        )
        if path:
            self._gl_lua_entry.delete(0, "end")
            self._gl_lua_entry.insert(0, path)

    def _browse_gl_manifest_dir(self):
        path = tkinter.filedialog.askdirectory(
            title="Select Manifest Files Directory",
            parent=self,
        )
        if path:
            self._gl_manifest_dir_entry.delete(0, "end")
            self._gl_manifest_dir_entry.insert(0, path)

    # ── Save ──────────────────────────────────────────────────

    def _save_settings(self):
        settings = self.app.settings

        # Card 1 fields
        settings.game_path = self._game_dir_entry.get().strip()
        settings.manifest_url = self._manifest_entry.get().strip()

        lang_display = self._lang_var.get()
        if " — " in lang_display:
            settings.language = lang_display.split(" — ")[0]

        theme_val = self._theme_var.get().lower()
        settings.theme = theme_val
        ctk.set_appearance_mode(theme_val)

        settings.check_updates_on_start = self._check_start_var.get()
        settings.skip_game_update = self._skip_update_var.get()

        # Card 2 fields (GreenLuma)
        settings.steam_path = self._steam_path_entry.get().strip()
        settings.greenluma_archive_path = self._gl_archive_entry.get().strip()
        settings.greenluma_lua_path = self._gl_lua_entry.get().strip()
        settings.greenluma_manifest_dir = self._gl_manifest_dir_entry.get().strip()
        settings.greenluma_auto_backup = self._gl_auto_backup_var.get()

        try:
            settings.save()
            self._status_label.configure(text="")
            self.app.show_toast("Settings saved!", "success")

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
