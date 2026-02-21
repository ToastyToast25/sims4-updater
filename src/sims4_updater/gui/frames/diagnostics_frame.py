"""
Diagnostics frame — system health checks and game file validation.

Two sections:
  1. Quick Diagnostics: VC Redist, .NET, permissions, AV checks (instant)
  2. File Validator: scan all game files for missing/corrupt DLC folders
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme

if TYPE_CHECKING:
    from ..app import App


class DiagnosticsFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._diag_running = False
        self._validator_running = False
        self._validator = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # ── Header ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=30, pady=(20, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Diagnostics & Validation",
            font=ctk.CTkFont(*theme.FONT_HEADING),
        ).grid(row=0, column=0, sticky="w")

        self._status_label = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._status_label.grid(row=0, column=1, sticky="e")

        # ── Buttons ──
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=1, column=0, padx=30, pady=(0, 10), sticky="ew")

        self._diag_btn = ctk.CTkButton(
            btn_row,
            text="Run Diagnostics",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._on_run_diagnostics,
        )
        self._diag_btn.pack(side="left", padx=(0, 10))

        self._validate_btn = ctk.CTkButton(
            btn_row,
            text="Validate Game Files",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["success"],
            hover_color="#3ae882",
            text_color="#1a1a2e",
            command=self._on_validate_files,
        )
        self._validate_btn.pack(side="left", padx=(0, 10))

        self._export_btn = ctk.CTkButton(
            btn_row,
            text="Export Report",
            font=ctk.CTkFont(size=13),
            height=theme.BUTTON_HEIGHT,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card"],
            command=self._on_export,
            state="disabled",
        )
        self._export_btn.pack(side="left")

        # ── Progress bar ──
        self._progress_bar = ctk.CTkProgressBar(
            self,
            height=4,
            corner_radius=2,
            progress_color=theme.COLORS["accent"],
        )
        self._progress_bar.grid(row=2, column=0, padx=30, pady=(0, 5), sticky="ew")
        self._progress_bar.set(0)
        self._progress_bar.grid_remove()

        # ── Results area ──
        self._results = ctk.CTkScrollableFrame(
            self,
            corner_radius=8,
            scrollbar_button_color=theme.COLORS["separator"],
            scrollbar_button_hover_color=theme.COLORS["accent"],
        )
        self._results.grid(row=3, column=0, padx=30, pady=(0, 15), sticky="nsew")
        self._results.grid_columnconfigure(0, weight=1)

        # ── Placeholder ──
        self._placeholder = ctk.CTkLabel(
            self._results,
            text=(
                "Click 'Run Diagnostics' to check your system,\n"
                "or 'Validate Game Files' to verify your installation."
            ),
            font=ctk.CTkFont(size=13),
            text_color=theme.COLORS["text_muted"],
            justify="center",
        )
        self._placeholder.grid(row=0, column=0, padx=20, pady=60)

        # Store last report for export
        self._last_diag_report = None
        self._last_validation_report = None

    def on_show(self):
        pass

    # ── Diagnostics ──────────────────────────────────────────

    def _on_run_diagnostics(self):
        if self._diag_running:
            return
        self._diag_running = True
        self._diag_btn.configure(state="disabled", text="Running...")
        self._status_label.configure(text="Running diagnostics...")
        self._progress_bar.grid()
        self._progress_bar.set(0)
        self.app.run_async(
            self._run_diagnostics_bg,
            on_done=self._on_diagnostics_done,
            on_error=self._on_error,
        )

    def _run_diagnostics_bg(self):
        from ...core.diagnostics import run_diagnostics

        game_dir = self.app.settings.game_path
        if not game_dir:
            try:
                detected = self.app.updater.find_game_dir()
                if detected:
                    game_dir = str(detected)
            except Exception:
                pass

        return run_diagnostics(game_dir if game_dir else None)

    def _on_diagnostics_done(self, report):
        self._diag_running = False
        self._diag_btn.configure(state="normal", text="Run Diagnostics")
        self._progress_bar.set(1)
        self._last_diag_report = report

        # Clear results
        self._clear_results()

        # Summary header
        summary_text = (
            f"{report.pass_count} passed, "
            f"{report.warn_count} warnings, "
            f"{report.fail_count} failures"
        )
        if report.is_healthy:
            summary_color = theme.COLORS["success"]
            self._status_label.configure(text="All checks passed!")
        elif report.fail_count > 0:
            summary_color = theme.COLORS["error"]
            self._status_label.configure(text=f"{report.fail_count} issue(s) found")
        else:
            summary_color = theme.COLORS["warning"]
            self._status_label.configure(text=f"{report.warn_count} warning(s)")

        # Section header
        self._add_section_header("System Diagnostics", summary_text, summary_color)

        # Results
        from ...core.diagnostics import CheckStatus

        row = 1
        for result in report.results:
            row = self._add_check_result(row, result, CheckStatus)

        self._export_btn.configure(state="normal")
        self._progress_bar.grid_remove()

    # ── File Validation ──────────────────────────────────────

    def _on_validate_files(self):
        if self._validator_running:
            return
        self._validator_running = True
        self._validate_btn.configure(state="disabled", text="Validating...")
        self._status_label.configure(text="Scanning game files...")
        self._progress_bar.grid()
        self._progress_bar.set(0)

        thread = threading.Thread(target=self._validate_bg, daemon=True)
        thread.start()

    def _validate_bg(self):
        from ...core.validator import GameValidator

        game_dir = self.app.settings.game_path
        if not game_dir:
            try:
                detected = self.app.updater.find_game_dir()
                if detected:
                    game_dir = str(detected)
            except Exception:
                pass

        if not game_dir:
            self.app._enqueue_gui(self._on_validate_error, "No game directory found.")
            return

        self._validator = GameValidator()

        def progress(msg, current, total):
            pct = current / total if total > 0 else 0
            self.app._enqueue_gui(self._update_validate_progress, msg, pct)

        try:
            report = self._validator.validate(
                game_dir, progress=progress, check_hashes=False,
            )
            self.app._enqueue_gui(self._on_validate_done, report)
        except Exception as e:
            self.app._enqueue_gui(self._on_validate_error, str(e))

    def _update_validate_progress(self, msg, pct):
        self._status_label.configure(text=msg)
        self._progress_bar.set(max(0.01, pct))

    def _on_validate_done(self, report):
        self._validator_running = False
        self._validate_btn.configure(state="normal", text="Validate Game Files")
        self._progress_bar.set(1)
        self._last_validation_report = report

        # Clear results
        self._clear_results()

        from ...core.validator import FileState, GameValidator

        validator = GameValidator()

        # Summary
        if report.is_healthy:
            summary_color = theme.COLORS["success"]
            summary_text = "Installation looks healthy!"
            self._status_label.configure(text="Validation passed!")
        else:
            problems = report.get_problems()
            summary_color = theme.COLORS["warning"]
            summary_text = f"{len(problems)} issue(s) found"
            self._status_label.configure(text=summary_text)

        # Overall stats
        self._add_section_header(
            "Game File Validation",
            f"Scanned {report.total_files_scanned} files | "
            f"Total: {validator.format_size(report.total_size)}",
            summary_color,
        )

        row = 1

        # Folder breakdown
        if report.folders:
            folder_card = ctk.CTkFrame(
                self._results,
                fg_color=theme.COLORS["bg_card"],
                corner_radius=6,
            )
            folder_card.grid(
                row=row, column=0, padx=5, pady=(5, 10), sticky="ew",
            )
            folder_card.grid_columnconfigure(1, weight=1)
            row += 1

            ctk.CTkLabel(
                folder_card,
                text="Folder Breakdown",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=theme.COLORS["text"],
            ).grid(row=0, column=0, columnspan=4, padx=12, pady=(8, 4), sticky="w")

            # Column headers
            for ci, header_text in enumerate(["Folder", "Files", "Size", "Status"]):
                ctk.CTkLabel(
                    folder_card,
                    text=header_text,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color=theme.COLORS["text_muted"],
                ).grid(row=1, column=ci, padx=12, pady=2, sticky="w")

            for fi, folder in enumerate(report.folders):
                fr = fi + 2
                ctk.CTkLabel(
                    folder_card,
                    text=folder.name,
                    font=ctk.CTkFont(size=11),
                ).grid(row=fr, column=0, padx=12, pady=2, sticky="w")

                ctk.CTkLabel(
                    folder_card,
                    text=str(folder.total_files),
                    font=ctk.CTkFont(size=11),
                    text_color=theme.COLORS["text_muted"],
                ).grid(row=fr, column=1, padx=12, pady=2, sticky="w")

                ctk.CTkLabel(
                    folder_card,
                    text=validator.format_size(folder.total_size),
                    font=ctk.CTkFont(size=11),
                    text_color=theme.COLORS["text_muted"],
                ).grid(row=fr, column=2, padx=12, pady=2, sticky="w")

                if folder.missing_count > 0:
                    status_text = f"{folder.missing_count} missing"
                    status_color = theme.COLORS["error"]
                elif folder.corrupt_count > 0:
                    status_text = f"{folder.corrupt_count} corrupt"
                    status_color = theme.COLORS["warning"]
                else:
                    status_text = "OK"
                    status_color = theme.COLORS["success"]

                ctk.CTkLabel(
                    folder_card,
                    text=status_text,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color=status_color,
                ).grid(row=fr, column=3, padx=12, pady=2, sticky="w")

            # Bottom padding
            ctk.CTkFrame(
                folder_card, height=6, fg_color="transparent",
            ).grid(row=len(report.folders) + 2, column=0, columnspan=4)

        # Problems list
        problems = report.get_problems()
        if problems:
            self._add_section_header(
                "Problems Found",
                f"{len(problems)} file(s)",
                theme.COLORS["error"],
            )
            row += 1
            for problem in problems:
                prob_card = ctk.CTkFrame(
                    self._results,
                    fg_color=theme.COLORS["toast_error"]
                    if problem.state == FileState.MISSING
                    else theme.COLORS["toast_warning"],
                    corner_radius=6,
                )
                prob_card.grid(row=row, column=0, padx=5, pady=2, sticky="ew")
                prob_card.grid_columnconfigure(1, weight=1)

                icon = "\u2716" if problem.state == FileState.MISSING else "\u26a0"
                color = (
                    theme.COLORS["error"]
                    if problem.state == FileState.MISSING
                    else theme.COLORS["warning"]
                )

                ctk.CTkLabel(
                    prob_card,
                    text=icon,
                    font=ctk.CTkFont(size=12),
                    text_color=color,
                    width=24,
                ).grid(row=0, column=0, padx=(10, 4), pady=6)

                ctk.CTkLabel(
                    prob_card,
                    text=problem.path,
                    font=ctk.CTkFont("Consolas", 11),
                    text_color=theme.COLORS["text"],
                    anchor="w",
                ).grid(row=0, column=1, padx=4, pady=6, sticky="w")

                ctk.CTkLabel(
                    prob_card,
                    text=f"  {problem.state.value.upper()}  ",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color=color,
                    fg_color=theme.COLORS["bg_dark"],
                    corner_radius=8,
                    height=22,
                ).grid(row=0, column=2, padx=(4, 10), pady=6)
                row += 1
        elif report.total_files_scanned > 0:
            ok_card = ctk.CTkFrame(
                self._results,
                fg_color=theme.COLORS["toast_success"],
                corner_radius=6,
            )
            ok_card.grid(row=row, column=0, padx=5, pady=5, sticky="ew")
            ctk.CTkLabel(
                ok_card,
                text="\u2714  All checked files are present and accounted for.",
                font=ctk.CTkFont(size=13),
                text_color=theme.COLORS["success"],
            ).pack(padx=15, pady=12)

        self._export_btn.configure(state="normal")
        self._progress_bar.grid_remove()

    def _on_validate_error(self, error):
        self._validator_running = False
        self._validate_btn.configure(state="normal", text="Validate Game Files")
        self._progress_bar.grid_remove()
        self._status_label.configure(
            text=f"Error: {error}", text_color=theme.COLORS["error"],
        )
        self.app.show_toast(f"Validation failed: {error}", "error")

    # ── Export ────────────────────────────────────────────────

    def _on_export(self):
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(
            title="Save Diagnostics Report",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("YAML Files", "*.yaml")],
            parent=self.winfo_toplevel(),
        )
        if not path:
            return

        lines = []
        if self._last_diag_report:
            report = self._last_diag_report
            lines.append("=== System Diagnostics ===")
            lines.append(f"Game Dir: {report.game_dir}")
            lines.append(
                f"Results: {report.pass_count} pass, "
                f"{report.warn_count} warn, {report.fail_count} fail"
            )
            lines.append("")
            for r in report.results:
                lines.append(f"[{r.status.value.upper()}] {r.name}: {r.message}")
                if r.fix:
                    lines.append(f"  Fix: {r.fix}")
            lines.append("")

        if self._last_validation_report:
            from ...core.validator import GameValidator

            validator = GameValidator()
            lines.append("=== Game File Validation ===")
            lines.append(validator.export_yaml(self._last_validation_report))

        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
            self.app.show_toast(f"Report saved to {Path(path).name}", "success")
        except OSError as e:
            self.app.show_toast(f"Failed to save: {e}", "error")

    # ── Helpers ───────────────────────────────────────────────

    def _on_error(self, error):
        self._diag_running = False
        self._validator_running = False
        self._diag_btn.configure(state="normal", text="Run Diagnostics")
        self._validate_btn.configure(state="normal", text="Validate Game Files")
        self._progress_bar.grid_remove()
        self._status_label.configure(
            text=f"Error: {error}", text_color=theme.COLORS["error"],
        )

    def _clear_results(self):
        self._placeholder.grid_remove()
        for widget in self._results.winfo_children():
            if widget != self._placeholder:
                widget.destroy()

    def _add_section_header(self, title: str, subtitle: str, color: str):
        """Add a section header card to the results."""
        card = ctk.CTkFrame(
            self._results,
            fg_color=theme.COLORS["separator"],
            corner_radius=6,
            height=40,
        )
        card.grid(
            row=len(self._results.winfo_children()),
            column=0, padx=5, pady=(5, 5), sticky="ew",
        )
        card.grid_columnconfigure(1, weight=1)
        card.grid_propagate(False)

        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=theme.COLORS["text"],
        ).grid(row=0, column=0, padx=12, pady=8, sticky="w")

        ctk.CTkLabel(
            card,
            text=subtitle,
            font=ctk.CTkFont(size=11),
            text_color=color,
        ).grid(row=0, column=1, padx=12, pady=8, sticky="e")

    def _add_check_result(self, row: int, result, CheckStatus) -> int:
        """Add a single diagnostic check result to the results area."""
        # Choose colors/icons
        if result.status == CheckStatus.PASS:
            icon = "\u2714"
            color = theme.COLORS["success"]
            bg = theme.COLORS["toast_success"]
        elif result.status == CheckStatus.WARN:
            icon = "\u26a0"
            color = theme.COLORS["warning"]
            bg = theme.COLORS["toast_warning"]
        elif result.status == CheckStatus.FAIL:
            icon = "\u2716"
            color = theme.COLORS["error"]
            bg = theme.COLORS["toast_error"]
        else:  # SKIP
            icon = "\u2014"
            color = theme.COLORS["text_muted"]
            bg = theme.COLORS["bg_card_alt"]

        card = ctk.CTkFrame(
            self._results,
            fg_color=bg,
            corner_radius=6,
        )
        card.grid(row=row, column=0, padx=5, pady=2, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        # Icon
        ctk.CTkLabel(
            card,
            text=icon,
            font=ctk.CTkFont(size=14),
            text_color=color,
            width=28,
        ).grid(row=0, column=0, padx=(10, 4), pady=8)

        # Name and message
        text_frame = ctk.CTkFrame(card, fg_color="transparent")
        text_frame.grid(row=0, column=1, padx=4, pady=6, sticky="ew")
        text_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            text_frame,
            text=result.name,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=theme.COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            text_frame,
            text=result.message,
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_muted"],
            anchor="w",
            wraplength=500,
            justify="left",
        ).grid(row=1, column=0, sticky="w")

        # Status pill
        ctk.CTkLabel(
            card,
            text=f"  {result.status.value.upper()}  ",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=color,
            fg_color=theme.COLORS["bg_dark"],
            corner_radius=8,
            height=22,
        ).grid(row=0, column=2, padx=(4, 10), pady=8)

        row += 1

        # Fix suggestion (if any)
        if result.fix:
            fix_card = ctk.CTkFrame(
                self._results,
                fg_color=theme.COLORS["bg_card_alt"],
                corner_radius=4,
            )
            fix_card.grid(row=row, column=0, padx=(35, 10), pady=(0, 4), sticky="ew")

            ctk.CTkLabel(
                fix_card,
                text=f"\u2192 Fix: {result.fix}",
                font=ctk.CTkFont(size=10),
                text_color=theme.COLORS["accent"],
                anchor="w",
                wraplength=550,
                justify="left",
            ).pack(padx=10, pady=6, anchor="w")
            row += 1

        return row
