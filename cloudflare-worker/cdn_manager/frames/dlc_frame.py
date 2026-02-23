"""DLC Upload frame — scan, list, and upload DLCs with parallel workers."""

from __future__ import annotations

import concurrent.futures
import time
from pathlib import Path
from threading import Event, Thread
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import StatusBadge, LogPanel

if TYPE_CHECKING:
    from ..app import CDNManagerApp


class DLCFrame(ctk.CTkFrame):
    def __init__(self, parent, app: CDNManagerApp):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._busy = False
        self._cancel_event = Event()
        self._dlc_rows: dict[str, dict] = {}
        self._cdn_statuses: dict[str, str] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="DLC Upload",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        ).grid(row=0, column=0, padx=theme.SECTION_PAD, pady=(20, 15), sticky="w")

        # Header bar
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=1, column=0, padx=theme.SECTION_PAD, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        # Game dir entry + browse
        path_frame = ctk.CTkFrame(header, fg_color="transparent")
        path_frame.grid(row=0, column=0, sticky="ew")
        path_frame.grid_columnconfigure(0, weight=1)

        self._game_dir_entry = ctk.CTkEntry(
            path_frame, font=ctk.CTkFont(size=12), height=36,
            placeholder_text="Game directory...",
        )
        self._game_dir_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        if self.app.config_data.game_dir:
            self._game_dir_entry.insert(0, self.app.config_data.game_dir)

        ctk.CTkButton(
            path_frame, text="Browse", height=36, width=80,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            command=self._browse_game_dir,
        ).grid(row=0, column=1)

        # Buttons row
        btn_row = ctk.CTkFrame(header, fg_color="transparent")
        btn_row.grid(row=1, column=0, pady=(8, 0), sticky="ew")

        self._scan_btn = ctk.CTkButton(
            btn_row, text="Scan", height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._scan,
        )
        self._scan_btn.pack(side="left", padx=(0, 4))

        self._upload_btn = ctk.CTkButton(
            btn_row, text="Upload Selected", height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["success"],
            hover_color="#3ae882",
            text_color="#1a1a2e",
            command=self._upload_selected,
            state="disabled",
        )
        self._upload_btn.pack(side="left", padx=(0, 4))

        self._resume_btn = ctk.CTkButton(
            btn_row, text="Resume Upload", height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["warning"],
            hover_color="#ffc048",
            text_color="#1a1a2e",
            command=self._resume_upload,
        )

        self._cancel_btn = ctk.CTkButton(
            btn_row, text="Cancel", height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            command=self._cancel_upload,
        )

        # Selection helpers
        ctk.CTkButton(
            btn_row, text="All", height=28, width=50,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            font=ctk.CTkFont(size=11),
            command=self._select_all,
        ).pack(side="left", padx=(12, 2))

        ctk.CTkButton(
            btn_row, text="Missing", height=28, width=65,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            font=ctk.CTkFont(size=11),
            command=self._select_missing,
        ).pack(side="left", padx=(0, 2))

        ctk.CTkButton(
            btn_row, text="None", height=28, width=50,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            font=ctk.CTkFont(size=11),
            command=self._select_none,
        ).pack(side="left")

        # Force checkbox
        self._force_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            btn_row, text="Force", variable=self._force_var,
            font=ctk.CTkFont(size=11), height=28, width=60,
            checkbox_width=16, checkbox_height=16,
        ).pack(side="left", padx=(12, 0))

        # Workers
        ctk.CTkLabel(
            btn_row, text="Workers:",
            font=ctk.CTkFont(size=11), text_color=theme.COLORS["text_muted"],
        ).pack(side="left", padx=(12, 4))

        self._worker_var = ctk.StringVar(value="Auto")
        ctk.CTkOptionMenu(
            btn_row, values=["Auto"] + [str(i) for i in range(1, 11)],
            variable=self._worker_var, width=70, height=28,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            button_color=theme.COLORS["bg_card_alt"],
            button_hover_color=theme.COLORS["card_hover"],
        ).pack(side="left")

        # Progress (hidden initially)
        self._progress_frame = ctk.CTkFrame(self, fg_color="transparent", height=70)
        self._progress_bar = ctk.CTkProgressBar(
            self._progress_frame, height=16,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            progress_color=theme.COLORS["accent"],
        )
        self._progress_bar.pack(fill="x", padx=0, pady=(0, 2))
        self._progress_bar.set(0)
        self._progress_label = ctk.CTkLabel(
            self._progress_frame, text="",
            font=ctk.CTkFont(size=11), text_color=theme.COLORS["text_muted"],
        )
        self._progress_label.pack(anchor="w")

        # Sub-progress: current DLC byte-level
        self._sub_progress_label = ctk.CTkLabel(
            self._progress_frame, text="",
            font=ctk.CTkFont(size=10), text_color=theme.COLORS["text_dim"],
        )
        self._sub_progress_label.pack(anchor="w", pady=(2, 0))
        self._sub_progress_bar = ctk.CTkProgressBar(
            self._progress_frame, height=8,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            progress_color=theme.COLORS["success"],
        )
        self._sub_progress_bar.pack(fill="x", padx=0, pady=(2, 0))
        self._sub_progress_bar.set(0)

        # Upload byte tracking (updated from background thread)
        self._dlc_start_times: dict[str, float] = {}
        self._last_reported_dlc = ""

        # DLC list
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=theme.COLORS["bg_dark"],
            corner_radius=theme.CORNER_RADIUS,
            border_width=1, border_color=theme.COLORS["border"],
            scrollbar_button_color=theme.COLORS["separator"],
            scrollbar_button_hover_color=theme.COLORS["accent"],
        )
        self._scroll.grid(
            row=2, column=0, padx=theme.SECTION_PAD, pady=(10, 4), sticky="nsew",
        )
        for col, w in [(0, 30), (1, 60), (2, 0), (3, 80), (4, 80), (5, 90)]:
            self._scroll.grid_columnconfigure(col, weight=1 if w == 0 else 0, minsize=w)

        self._placeholder = ctk.CTkLabel(
            self._scroll, text="Click 'Scan' to detect installed DLCs",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        )
        self._placeholder.grid(row=0, column=0, columnspan=6, pady=40)

        # Log
        self._log = LogPanel(self)
        self._log.grid(row=3, column=0, padx=theme.SECTION_PAD, pady=(4, 15), sticky="nsew")

    def on_show(self):
        pass

    def _browse_game_dir(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Select Sims 4 Game Directory")
        if path:
            self._game_dir_entry.delete(0, "end")
            self._game_dir_entry.insert(0, path)

    # -- Scan ----------------------------------------------------------------

    def _scan(self):
        game_dir = self._game_dir_entry.get().strip()
        if not game_dir:
            self.app.show_toast("Enter a game directory first", "warning")
            return
        self._log.log("Scanning for installed DLCs...")
        self._scan_btn.configure(state="disabled")
        self.app.run_async(
            self._bg_scan, game_dir,
            on_done=self._on_scan_done,
            on_error=self._on_scan_error,
        )

    def _bg_scan(self, game_dir: str):
        from ..backend.dlc_ops import (
            scan_installed_dlcs, load_dlc_catalog, get_dlc_name,
            get_dlc_type, get_folder_size, fmt_size,
        )
        from ..backend.connection import ConnectionManager

        game_path = Path(game_dir)
        dlcs = scan_installed_dlcs(game_path)
        catalog = load_dlc_catalog()

        dlc_info = []
        for dlc_id in dlcs:
            dlc_dir = game_path / dlc_id
            folder_size = get_folder_size(dlc_dir) if dlc_dir.is_dir() else 0
            dlc_info.append({
                "id": dlc_id,
                "name": get_dlc_name(catalog, dlc_id),
                "type": get_dlc_type(catalog, dlc_id),
                "size": folder_size,
                "size_str": fmt_size(folder_size),
            })

        # Check CDN status via KV listing
        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        cdn_keys = conn.kv_list()
        cdn_dlcs = {
            k.replace("dlc/", "").replace(".zip", "")
            for k in cdn_keys if k.startswith("dlc/")
        }

        statuses = {}
        for info in dlc_info:
            statuses[info["id"]] = "uploaded" if info["id"] in cdn_dlcs else "missing"

        return dlc_info, statuses

    def _on_scan_done(self, result):
        dlc_info, statuses = result
        self._cdn_statuses = statuses
        self._scan_btn.configure(state="normal")

        # Clear
        for widget in self._scroll.winfo_children():
            widget.destroy()
        self._dlc_rows.clear()

        if not dlc_info:
            ctk.CTkLabel(
                self._scroll, text="No DLCs found in the game directory",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=0, columnspan=6, pady=40)
            self._log.log("No DLCs found", "warning")
            return

        # Headers
        for col, text in enumerate(["", "ID", "Name", "Type", "Size", "Status"]):
            ctk.CTkLabel(
                self._scroll, text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=col, padx=4, pady=(4, 6), sticky="w")

        type_colors = {
            "expansion": "#e94560", "game_pack": "#6c5ce7",
            "stuff_pack": "#00b894", "kit": "#fdcb6e", "free_pack": "#74b9ff",
        }

        for i, info in enumerate(dlc_info):
            row = i + 1
            dlc_id = info["id"]
            status = statuses.get(dlc_id, "unknown")

            var = ctk.BooleanVar(value=(status == "missing"))
            ctk.CTkCheckBox(
                self._scroll, text="", variable=var,
                width=20, height=20, checkbox_width=16, checkbox_height=16,
            ).grid(row=row, column=0, padx=4, pady=2)

            ctk.CTkLabel(
                self._scroll, text=dlc_id,
                font=ctk.CTkFont("Consolas", 11),
            ).grid(row=row, column=1, padx=4, pady=2, sticky="w")

            ctk.CTkLabel(
                self._scroll, text=info["name"],
                font=ctk.CTkFont(size=11),
            ).grid(row=row, column=2, padx=4, pady=2, sticky="w")

            ctk.CTkLabel(
                self._scroll, text=info["type"].replace("_", " ").title(),
                font=ctk.CTkFont(size=10),
                text_color=type_colors.get(info["type"], theme.COLORS["text_muted"]),
            ).grid(row=row, column=3, padx=4, pady=2, sticky="w")

            ctk.CTkLabel(
                self._scroll, text=info["size_str"],
                font=ctk.CTkFont(size=11), text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=4, padx=4, pady=2, sticky="e")

            badge = StatusBadge(self._scroll)
            if status == "uploaded":
                badge.set_status("Uploaded", "success")
            else:
                badge.set_status("Missing", "warning")
            badge.grid(row=row, column=5, padx=4, pady=2, sticky="e")

            self._dlc_rows[dlc_id] = {"var": var, "badge": badge, "info": info}

        uploaded = sum(1 for s in statuses.values() if s == "uploaded")
        missing = sum(1 for s in statuses.values() if s == "missing")
        self._log.log(
            f"Found {len(dlc_info)} DLCs: {uploaded} uploaded, {missing} missing",
            "success",
        )
        self._upload_btn.configure(state="normal")

        # Check for resumable upload session
        from ..backend.dlc_ops import get_pending_resume
        remaining = get_pending_resume()
        if remaining:
            # Filter to DLCs that are actually in our scan list
            present = [d for d in remaining if d in self._dlc_rows]
            if present:
                self._resume_btn.pack(side="left", padx=(4, 0))
                self._resume_dlcs = present
                self._log.log(
                    f"Resumable session found: {len(present)} DLCs remaining",
                    "warning",
                )
            else:
                self._resume_btn.pack_forget()
                self._resume_dlcs = []
        else:
            self._resume_btn.pack_forget()
            self._resume_dlcs = []

    def _on_scan_error(self, error):
        self._scan_btn.configure(state="normal")
        self._log.log(f"Scan failed: {error}", "error")

    # -- Selection -----------------------------------------------------------

    def _select_all(self):
        for row in self._dlc_rows.values():
            row["var"].set(True)

    def _select_missing(self):
        for dlc_id, row in self._dlc_rows.items():
            row["var"].set(self._cdn_statuses.get(dlc_id) == "missing")

    def _select_none(self):
        for row in self._dlc_rows.values():
            row["var"].set(False)

    # -- Upload --------------------------------------------------------------

    def _resume_upload(self):
        """Resume an interrupted upload session."""
        if not hasattr(self, "_resume_dlcs") or not self._resume_dlcs:
            self.app.show_toast("No resumable session found", "warning")
            return
        # Select the remaining DLCs and start upload
        for dlc_id, row in self._dlc_rows.items():
            row["var"].set(dlc_id in self._resume_dlcs)
        self._log.log(f"Resuming upload of {len(self._resume_dlcs)} DLCs...")
        self._upload_selected(resume=True)

    def _upload_selected(self, resume: bool = False):
        selected = [d for d, r in self._dlc_rows.items() if r["var"].get()]
        if not selected:
            self.app.show_toast("No DLCs selected", "warning")
            return
        game_dir = self._game_dir_entry.get().strip()
        if not game_dir:
            self.app.show_toast("Enter a game directory first", "warning")
            return

        self._busy = True
        self._cancel_event.clear()
        self._scan_btn.configure(state="disabled")
        self._upload_btn.configure(state="disabled")
        self._resume_btn.pack_forget()
        self._cancel_btn.pack(side="left", padx=(4, 0))
        self.app.begin_operation(f"Uploading {len(selected)} DLCs")

        # Show progress
        self._progress_frame.grid(
            row=2, column=0, padx=theme.SECTION_PAD, pady=(10, 0), sticky="ew",
        )
        self._scroll.grid(
            row=2, column=0, padx=theme.SECTION_PAD, pady=(80, 4), sticky="nsew",
        )
        self._progress_bar.set(0)
        self._sub_progress_bar.set(0)
        self._sub_progress_label.configure(text="")
        self._dlc_start_times.clear()
        self._last_reported_dlc = ""
        self._progress_label.configure(text=f"0/{len(selected)} DLCs")
        self._log.log(f"Starting upload of {len(selected)} DLCs...")

        worker_val = self._worker_var.get()
        num_workers = 4 if worker_val == "Auto" else int(worker_val)
        force = self._force_var.get()

        Thread(
            target=self._bg_upload,
            args=(game_dir, selected, num_workers, force),
            daemon=True,
        ).start()

    def _bg_upload(self, game_dir: str, dlc_ids: list[str], num_workers: int, force: bool):
        from ..backend.dlc_ops import (
            process_single_dlc, fmt_size,
            start_upload_session, record_dlc_complete, finish_upload_session,
        )
        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        game_path = Path(game_dir)
        output_dir = Path(__file__).resolve().parent.parent.parent / "packed_temp"

        # Start persistent upload session
        start_upload_session(dlc_ids)

        total = len(dlc_ids)
        completed = 0
        uploaded = 0
        uploaded_bytes = 0
        failed = []
        uploaded_entries: dict[str, dict] = {}  # dlc_id -> manifest entry
        start_time = time.time()

        # Per-DLC byte-level progress tracking (throttled to 200ms)
        last_sub_update = [0.0]

        def make_progress_cb(dlc_id):
            def progress_cb(sent, total_bytes):
                now = time.time()
                if now - last_sub_update[0] < 0.2:
                    return
                last_sub_update[0] = now
                self.app._enqueue_gui(
                    self._update_sub_progress, dlc_id, sent, total_bytes,
                )
            return progress_cb

        def log(msg, level="info"):
            self.app._enqueue_gui(self._log.log, msg, level)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as pool:
            future_to_dlc = {}
            for dlc_id in dlc_ids:
                if self._cancel_event.is_set():
                    break
                future = pool.submit(
                    process_single_dlc,
                    game_path, dlc_id, conn, output_dir,
                    force=force,
                    cancel_event=self._cancel_event,
                    log_cb=log,
                    progress_cb=make_progress_cb(dlc_id),
                )
                future_to_dlc[future] = dlc_id

            for future in concurrent.futures.as_completed(future_to_dlc):
                dlc_id = future_to_dlc[future]
                try:
                    entry = future.result()
                    if entry:
                        completed += 1
                        if entry.get("size", 0) > 0:
                            uploaded += 1
                            uploaded_bytes += entry["size"]
                            uploaded_entries[dlc_id] = entry
                        record_dlc_complete(dlc_id, entry)
                        self.app._enqueue_gui(self._update_badge, dlc_id, "uploaded")
                    else:
                        completed += 1
                        if not self._cancel_event.is_set():
                            failed.append(dlc_id)
                except Exception as e:
                    completed += 1
                    failed.append(dlc_id)
                    log(f"[{dlc_id}] Failed: {e}", "error")

                progress = completed / total
                elapsed = time.time() - start_time
                self.app._enqueue_gui(
                    self._update_progress, progress, completed, total, elapsed,
                )

        # Mark session complete if all finished without cancellation
        if not self._cancel_event.is_set():
            finish_upload_session()

        # Auto-update manifest with new DLC entries
        if uploaded_entries and not self._cancel_event.is_set():
            from ..backend.manifest_ops import merge_dlc_entries_and_publish
            merge_dlc_entries_and_publish(conn, uploaded_entries, log_cb=log)

        total_time = time.time() - start_time

        def finish():
            self._busy = False
            self._scan_btn.configure(state="normal")
            self._upload_btn.configure(state="normal")
            self._cancel_btn.pack_forget()
            self._progress_frame.grid_forget()
            self._scroll.grid(
                row=2, column=0,
                padx=theme.SECTION_PAD, pady=(10, 4), sticky="nsew",
            )
            self.app.end_operation()
            msg = f"Upload complete: {uploaded} uploaded"
            if failed:
                msg += f", {len(failed)} failed"
            msg += f" in {total_time:.0f}s"
            if uploaded_bytes > 0:
                msg += f" ({fmt_size(uploaded_bytes)})"
            self._log.log(msg, "success" if not failed else "warning")
            self.app.show_toast(msg, "success" if not failed else "warning")

        self.app._enqueue_gui(finish)

    def _update_badge(self, dlc_id: str, status: str):
        row = self._dlc_rows.get(dlc_id)
        if row:
            if status == "uploaded":
                row["badge"].set_status("Uploaded", "success")
            row["var"].set(False)

    def _update_progress(self, progress: float, completed: int, total: int, elapsed: float):
        self._progress_bar.set(progress)
        if elapsed > 0 and completed > 0:
            remaining = elapsed / completed * (total - completed)
            self._progress_label.configure(
                text=(
                    f"{completed}/{total} DLCs  |  "
                    f"{elapsed:.0f}s elapsed  |  ~{remaining:.0f}s remaining"
                ),
            )
        else:
            self._progress_label.configure(text=f"{completed}/{total} DLCs")

    def _update_sub_progress(self, dlc_id: str, sent: int, total_bytes: int):
        from ..backend.dlc_ops import fmt_size
        if total_bytes > 0:
            pct = sent / total_bytes
            self._sub_progress_bar.set(pct)
            speed = ""
            if dlc_id not in self._dlc_start_times:
                self._dlc_start_times[dlc_id] = time.time()
            self._last_reported_dlc = dlc_id
            elapsed = time.time() - self._dlc_start_times[dlc_id]
            if elapsed > 0.5 and sent > 0:
                mbps = sent / elapsed / 1_048_576
                speed = f"  |  {mbps:.1f} MB/s"
            self._sub_progress_label.configure(
                text=f"Uploading {dlc_id}.zip — {fmt_size(sent)} / {fmt_size(total_bytes)}{speed}",
            )
        else:
            self._sub_progress_bar.set(0)
            self._sub_progress_label.configure(text=f"Uploading {dlc_id}...")

    def _cancel_upload(self):
        self._cancel_event.set()
        self._log.log("Cancellation requested — finishing active uploads...", "warning")
        self._cancel_btn.configure(state="disabled")
