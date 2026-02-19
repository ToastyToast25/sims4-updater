"""
Progress frame — download and patch progress bars with scrollable log.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme

if TYPE_CHECKING:
    from ..app import App
    from ...patch.planner import UpdatePlan


class ProgressFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._is_running = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # ── Title ──
        ctk.CTkLabel(
            self,
            text="Update Progress",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, padx=30, pady=(20, 10), sticky="w")

        # ── Status line ──
        self._status_label = ctk.CTkLabel(
            self,
            text="Ready",
            font=ctk.CTkFont(*theme.FONT_BODY),
        )
        self._status_label.grid(row=1, column=0, padx=30, pady=(0, 5), sticky="w")

        # ── Progress bar ──
        progress_card = ctk.CTkFrame(self, corner_radius=8)
        progress_card.grid(row=2, column=0, padx=30, pady=5, sticky="ew")
        progress_card.grid_columnconfigure(0, weight=1)

        self._progress_label = ctk.CTkLabel(
            progress_card,
            text="0%",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._progress_label.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")

        self._progress_bar = ctk.CTkProgressBar(
            progress_card,
            height=20,
            corner_radius=5,
            progress_color=theme.COLORS["accent"],
        )
        self._progress_bar.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="ew")
        self._progress_bar.set(0)

        # ── Log ──
        self._log = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(*theme.FONT_MONO),
            corner_radius=8,
            state="disabled",
            wrap="word",
        )
        self._log.grid(row=3, column=0, padx=30, pady=(10, 10), sticky="nsew")

        # ── Buttons ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, padx=30, pady=(0, 15), sticky="ew")

        self._cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            font=ctk.CTkFont(size=13),
            height=38,
            corner_radius=6,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            command=self._on_cancel,
        )
        self._cancel_btn.pack(side="left", padx=(0, 10))

        self._done_btn = ctk.CTkButton(
            btn_frame,
            text="Back to Home",
            font=ctk.CTkFont(size=13),
            height=38,
            corner_radius=6,
            fg_color=theme.COLORS["bg_card"],
            command=self._on_done,
            state="disabled",
        )
        self._done_btn.pack(side="left")

    def start_update(self, plan: UpdatePlan):
        """Begin the update process."""
        self._is_running = True
        self._clear_log()
        self._progress_bar.set(0)
        self._progress_label.configure(text="0%")
        self._cancel_btn.configure(state="normal")
        self._done_btn.configure(state="disabled")

        from ...patch.client import format_size

        total_size = format_size(plan.total_download_size)
        self._status_label.configure(
            text=f"Updating: {plan.current_version} -> {plan.target_version}"
        )
        self._log_message(
            f"Update plan: {plan.step_count} step(s), {total_size} download\n"
        )

        self.app.run_async(
            self._run_update,
            plan,
            on_done=self._on_update_done,
            on_error=self._on_update_error,
        )

    def _run_update(self, plan):
        """Background: download and apply patches."""
        updater = self.app.updater

        # Download
        updater.download_update(plan)

        # Load metadata and patch
        game_dir = updater.find_game_dir()
        if game_dir:
            game_names = updater.load_all_metadata()

            game_name = None
            for name in game_names:
                if "sims" in name.lower() or "ts4" in name.lower():
                    game_name = name
                    break
            if game_name is None:
                game_name = game_names[0]

            versions, dlc_count, languages, cached_path = updater.pick_game(game_name)

            lang = self.app.settings.language
            if lang and lang in languages:
                updater.select_language(lang)
            elif languages:
                updater.select_language(languages[0])

            all_dlcs, missing_dlcs = updater.check_files_quick(game_dir)
            selected = [d for d in all_dlcs if d not in missing_dlcs]
            updater.patch(selected)

            # Auto-toggle DLCs
            updater._dlc_manager.auto_toggle(game_dir)

    def _on_update_done(self, _):
        self._is_running = False
        self._progress_bar.set(1)
        self._progress_label.configure(text="100%")
        self._status_label.configure(
            text="Update complete!",
            text_color=theme.COLORS["success"],
        )
        self._log_message("\n--- UPDATE COMPLETE ---\n")
        self._cancel_btn.configure(state="disabled")
        self._done_btn.configure(state="normal")

    def _on_update_error(self, error):
        self._is_running = False
        self._status_label.configure(
            text=f"Error: {error}",
            text_color=theme.COLORS["error"],
        )
        self._log_message(f"\n--- ERROR: {error} ---\n")
        self._cancel_btn.configure(state="disabled")
        self._done_btn.configure(state="normal")

    def handle_callback(self, callback_type, *args, **kwargs):
        """Process patcher callbacks on GUI thread."""
        from ...updater import CallbackType

        if callback_type == CallbackType.HEADER:
            text = args[0] if args else ""
            self._status_label.configure(text=text)
            self._log_message(f"\n[{text}]\n")

        elif callback_type == CallbackType.INFO:
            text = str(args[0]) if args else ""
            self._log_message(f"  {text}\n")

        elif callback_type == CallbackType.PROGRESS:
            if len(args) >= 2:
                current, total = args[0], args[1]
                if total > 0:
                    pct = min(current / total, 1.0)
                    self._progress_bar.set(pct)
                    self._progress_label.configure(text=f"{pct * 100:.0f}%")

        elif callback_type == CallbackType.WARNING:
            text = args[0] if args else ""
            self._log_message(f"  WARNING: {text}\n")

        elif callback_type == CallbackType.FAILURE:
            text = args[0] if args else ""
            self._log_message(f"  FAILED: {text}\n")

        elif callback_type == CallbackType.FINISHED:
            self._log_message("\nDone.\n")
            force_scroll = kwargs.get("force_scroll", False)
            if force_scroll:
                self._log.see("end")

    def _log_message(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _on_cancel(self):
        if self._is_running:
            self.app.updater.exiting.set()
            self._status_label.configure(text="Cancelling...")
            self._cancel_btn.configure(state="disabled")

    def _on_done(self):
        self.app.switch_to_home()
        home = self.app._frames.get("home")
        if home and hasattr(home, "refresh"):
            home.refresh()
