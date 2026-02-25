"""
Progress frame — clean, structured view of download and patch progress.

Shows:
  - Current stage header with step indicator
  - Overall progress bar with percentage and size
  - Scrollable file activity log with color-coded entries
  - Cancel / Back buttons
"""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..animations import ease_in_out_cubic
from ..components import RichTextbox, get_animator

if TYPE_CHECKING:
    from ...patch.planner import UpdatePlan
    from ..app import App


class ProgressFrame(ctk.CTkFrame):
    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._is_running = False
        self._file_count = 0
        self._error_count = 0
        self._pulse_active = False
        self._pulse_after_id = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)  # log area expands

        # ── Title bar ──
        title_row = ctk.CTkFrame(self, fg_color="transparent")
        title_row.grid(row=0, column=0, padx=30, pady=(20, 0), sticky="ew")
        title_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            title_row,
            text="Update Progress",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        ).grid(row=0, column=0, sticky="w")

        self._step_label = ctk.CTkLabel(
            title_row,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._step_label.grid(row=0, column=1, padx=(15, 0), sticky="w")

        # ── Stage header ──
        self._stage_label = ctk.CTkLabel(
            self,
            text="Preparing...",
            font=ctk.CTkFont(*theme.FONT_HEADING),
            text_color=theme.COLORS["accent"],
        )
        self._stage_label.grid(row=1, column=0, padx=30, pady=(12, 0), sticky="w")

        # ── Progress card ──
        progress_card = ctk.CTkFrame(self, corner_radius=8)
        progress_card.grid(row=2, column=0, padx=30, pady=(10, 0), sticky="ew")
        progress_card.grid_columnconfigure(0, weight=1)

        # Top row: percentage left, size info right
        prog_top = ctk.CTkFrame(progress_card, fg_color="transparent")
        prog_top.grid(row=0, column=0, padx=15, pady=(10, 0), sticky="ew")
        prog_top.grid_columnconfigure(1, weight=1)

        self._pct_label = ctk.CTkLabel(
            prog_top,
            text="0%",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._pct_label.grid(row=0, column=0, sticky="w")

        self._size_label = ctk.CTkLabel(
            prog_top,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._size_label.grid(row=0, column=1, sticky="e")

        # Bar
        self._progress_bar = ctk.CTkProgressBar(
            progress_card,
            height=20,
            corner_radius=theme.CORNER_RADIUS,
            progress_color=theme.COLORS["accent"],
        )
        self._progress_bar.grid(row=1, column=0, padx=15, pady=(5, 10), sticky="ew")
        self._progress_bar.set(0)

        # ── Current file label ──
        self._file_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
            anchor="w",
        )
        self._file_label.grid(row=3, column=0, padx=30, pady=(6, 0), sticky="ew")

        # ── Activity log ──
        self._log = RichTextbox(self, wrap="none")
        self._log.grid(row=4, column=0, padx=30, pady=(8, 10), sticky="nsew")

        # ── Bottom button bar ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=5, column=0, padx=30, pady=(0, 15), sticky="ew")
        btn_frame.grid_columnconfigure(1, weight=1)

        self._cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            font=ctk.CTkFont(size=13),
            width=100,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color=theme.COLORS["hover_cancel"],
            command=self._on_cancel,
        )
        self._cancel_btn.grid(row=0, column=0, sticky="w")

        self._stats_label = ctk.CTkLabel(
            btn_frame,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._stats_label.grid(row=0, column=1)

        self._done_btn = ctk.CTkButton(
            btn_frame,
            text="Back to Home",
            font=ctk.CTkFont(size=13),
            width=120,
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card"],
            command=self._on_done,
            state="disabled",
        )
        self._done_btn.grid(row=0, column=2, sticky="e")

    # ── Public API ───────────────────────────────────────────────

    def start_update(self, plan: UpdatePlan):
        """Begin the update process."""
        self._is_running = True
        self._file_count = 0
        self._error_count = 0
        self._clear_log()
        self._progress_bar.set(0)
        self._pct_label.configure(text="0%")
        self._size_label.configure(text="")
        self._file_label.configure(text="")
        self._stats_label.configure(text="")
        self._cancel_btn.configure(state="normal")
        self._done_btn.configure(state="disabled")
        self._stage_label.configure(
            text="Starting update...",
            text_color=theme.COLORS["accent"],
        )

        from ...patch.client import format_size

        total_size = format_size(plan.total_download_size)
        steps = plan.step_count
        self._step_label.configure(text=f"{steps} step{'s' if steps != 1 else ''} | {total_size}")
        self._stage_label.configure(
            text=f"Updating: {plan.current_version}  ->  {plan.target_version}"
        )

        self._log_header(
            f"Update: {plan.current_version} -> {plan.target_version}\n"
            f"Steps: {steps} | Download: {total_size}\n"
        )

        # Start progress bar pulse animation
        self._start_pulse()

        # Telemetry: update started
        self._update_plan = plan
        self._update_start_time = time.monotonic()
        self.app.telemetry.track_event(
            "update_started",
            {
                "from_version": plan.current_version,
                "to_version": plan.target_version,
                "steps": plan.step_count,
            },
        )

        self.app.run_async(
            self._run_update,
            plan,
            on_done=self._on_update_done,
            on_error=self._on_update_error,
        )

    def handle_callback(self, callback_type, *args, **kwargs):
        """Process patcher callbacks on GUI thread."""
        from ...updater import CallbackType

        if callback_type == CallbackType.HEADER:
            text = str(args[0]) if args else ""
            self._stage_label.configure(text=text)
            self._file_label.configure(text="")
            self._log_text(f"\n--- {text} ---\n", "header")

        elif callback_type == CallbackType.INFO:
            text = str(args[0]) if args else ""
            short = self._short_path(text)
            self._file_label.configure(text=short)
            self._file_count += 1

            # Categorize the log entry
            if text.startswith("extracting "):
                self._log_text(f"  EXTRACT  {text[11:]}\n", "muted")
            elif text.startswith("hashing "):
                self._log_text(f"  HASH     {text[8:]}\n", "muted")
            elif text.startswith("updating "):
                self._log_text(f"  PATCH    {text[9:]}\n")
            elif text.startswith("copying "):
                self._log_text(f"  COPY     {text[8:]}\n")
            elif text.startswith("moving "):
                self._log_text(f"  MOVE     {text[7:]}\n")
            elif text.startswith("Applying patch"):
                self._log_text(f"  APPLY    {text}\n")
            else:
                self._log_text(f"  {text}\n")

            self._update_stats()

        elif callback_type == CallbackType.PROGRESS:
            if len(args) >= 2:
                current, total = args[0], args[1]
                if total > 0:
                    pct = min(current / total, 1.0)
                    self._progress_bar.set(pct)
                    self._pct_label.configure(text=f"{pct * 100:.0f}%")

                    from ...patch.client import format_size

                    self._size_label.configure(
                        text=f"{format_size(current)} / {format_size(total)}"
                    )

        elif callback_type == CallbackType.WARNING:
            text = str(args[0]) if args else ""
            self._log_text(f"  WARN     {text}\n", "warning")

        elif callback_type == CallbackType.FAILURE:
            text = str(args[0]) if args else ""
            self._error_count += 1
            self._log_text(f"  FAIL     {text}\n", "error")
            self._update_stats()

        elif callback_type == CallbackType.FINISHED:
            self._log_text("\nDone.\n", "success")

    # ── Background work ──────────────────────────────────────────

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

            # Backup game files before patching (if enabled)
            if self.app.settings.backup_enabled:
                try:
                    from pathlib import Path as _Path

                    from ...config import get_app_dir
                    from ...core.backup import BackupManager

                    bm = BackupManager(
                        get_app_dir(),
                        self.app.settings.backup_max_count,
                    )
                    files = updater.get_patchable_files(game_dir)
                    size = bm.estimate_backup_size(_Path(game_dir), files)
                    size_mb = size / 1024 / 1024
                    self._enqueue_gui(
                        self._log_text,
                        f"Creating backup ({size_mb:.1f} MB)...\n",
                        "info",
                    )
                    version_label = plan.target_version or "unknown"
                    bm.create_backup(_Path(game_dir), files, version_label)
                    bm.prune_old_backups()
                    self._enqueue_gui(
                        self._log_text,
                        "Backup created.\n",
                        "success",
                    )
                    self.app.telemetry.track_event(
                        "backup_created",
                        {
                            "size_bytes": size,
                            "version": version_label,
                        },
                    )
                except Exception as e:
                    self._enqueue_gui(
                        self._log_text,
                        f"Backup failed: {e} — continuing without backup.\n",
                        "warning",
                    )

            updater.patch(selected)

            # Learn new version hashes
            target_version = plan.target_version
            if target_version:
                updater.learn_version(game_dir, target_version)

            # Auto-toggle DLCs
            updater._dlc_manager.auto_toggle(game_dir)

    def _on_update_done(self, _):
        self._is_running = False
        self._stop_pulse()
        self._progress_bar.set(1)
        self._progress_bar.configure(progress_color=theme.COLORS["success"])
        self._pct_label.configure(text="100%")
        self._file_label.configure(text="")
        self._stage_label.configure(
            text="Update complete!",
            text_color=theme.COLORS["success"],
        )
        self._log_text("\n=== UPDATE COMPLETE ===\n", "success")
        self._cancel_btn.configure(state="disabled")
        self._done_btn.configure(state="normal")
        self._update_stats()

        # Flash stage label and show toast
        animator = get_animator()
        animator.animate_color(
            self._stage_label,
            "text_color",
            "#ffffff",
            theme.COLORS["success"],
            400,
            tag="done_flash",
        )
        self.app.show_toast("Update complete!", "success")

        # Telemetry: update completed
        plan = getattr(self, "_update_plan", None)
        start = getattr(self, "_update_start_time", None)
        duration = round(time.monotonic() - start, 1) if start else None
        self.app.telemetry.track_event(
            "update_completed",
            {
                "to_version": plan.target_version if plan else None,
                "duration_seconds": duration,
            },
        )

    def _on_update_error(self, error):
        self._is_running = False
        self._stop_pulse()
        self._progress_bar.configure(progress_color=theme.COLORS["error"])
        self._file_label.configure(text="")
        self._stage_label.configure(
            text="Update failed",
            text_color=theme.COLORS["error"],
        )
        self._log_text(f"\n=== ERROR ===\n{error}\n", "error")
        self._cancel_btn.configure(state="disabled")
        self._done_btn.configure(state="normal")
        self.app.show_toast(f"Update failed: {error}", "error")

        # Telemetry: update failed
        self.app.telemetry.track_event(
            "update_failed",
            {
                "error": str(error)[:200],
            },
        )

    # ── Log helpers ──────────────────────────────────────────────

    def _log_text(self, text: str, tag: str = ""):
        """Append text to the log, optionally with a color tag."""
        self._log.add_text(text, style=tag)

    def _log_header(self, text: str):
        self._log_text(text, "header")

    def _clear_log(self):
        self._log.clear()

    def _update_stats(self):
        parts = [f"{self._file_count} files processed"]
        if self._error_count:
            parts.append(f"{self._error_count} errors")
        self._stats_label.configure(text="  |  ".join(parts))

    @staticmethod
    def _short_path(text: str) -> str:
        """Shorten a file path/action for the current-file label."""
        for prefix in ("extracting ", "hashing ", "updating ", "copying ", "moving "):
            if text.startswith(prefix):
                return text[len(prefix) :]
        return text

    # ── Button handlers ──────────────────────────────────────────

    def _on_cancel(self):
        if self._is_running:
            self.app.updater.exiting.set()
            self._stage_label.configure(
                text="Cancelling...",
                text_color=theme.COLORS["warning"],
            )
            self._cancel_btn.configure(state="disabled")
            self._log_text("\nCancelling...\n", "warning")
            start = getattr(self, "_update_start_time", None)
            elapsed = round(time.monotonic() - start, 1) if start else None
            self.app.telemetry.track_event(
                "update_cancelled",
                {
                    "elapsed_seconds": elapsed,
                },
            )

    def _on_done(self):
        # Reset progress bar color for next update
        self._progress_bar.configure(progress_color=theme.COLORS["accent"])
        self.app.switch_to_home()
        home = self.app._frames.get("home")
        if home and hasattr(home, "refresh"):
            home.refresh()

    # ── Pulse animation ───────────────────────────────────────────

    def _start_pulse(self):
        """Start a breathing pulse on the progress bar color."""
        self._pulse_active = True
        self._progress_bar.configure(progress_color=theme.COLORS["accent"])
        self._pulse_step(0)

    def _pulse_step(self, phase: int):
        """One pulse cycle: accent -> accent_hover -> accent."""
        if not self._pulse_active:
            return

        animator = get_animator()
        if phase == 0:
            # Brighten
            animator.animate_color(
                self._progress_bar,
                "progress_color",
                theme.COLORS["accent"],
                theme.COLORS["accent_hover"],
                800,
                easing=ease_in_out_cubic,
                tag="pulse",
            )
            self._pulse_after_id = self.after(850, lambda: self._pulse_step(1))
        else:
            # Dim back
            animator.animate_color(
                self._progress_bar,
                "progress_color",
                theme.COLORS["accent_hover"],
                theme.COLORS["accent"],
                800,
                easing=ease_in_out_cubic,
                tag="pulse",
            )
            self._pulse_after_id = self.after(850, lambda: self._pulse_step(0))

    def _stop_pulse(self):
        """Stop the pulse animation."""
        self._pulse_active = False
        animator = get_animator()
        animator.cancel_all(self._progress_bar, tag="pulse")
        if self._pulse_after_id is not None:
            with contextlib.suppress(Exception):
                self.after_cancel(self._pulse_after_id)
            self._pulse_after_id = None
