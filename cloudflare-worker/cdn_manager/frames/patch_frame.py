"""Patch Creator frame — version registry and patch creation."""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from threading import Event, Thread
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import LogPanel, StatusBadge

if TYPE_CHECKING:
    from ..app import CDNManagerApp


class PatchFrame(ctk.CTkFrame):
    def __init__(self, parent, app: CDNManagerApp):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._busy = False
        self._cancel_event = Event()
        self._registry: list[dict] = []
        self._registry_rows: dict[str, dict] = {}
        self._last_patch_path: Path | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self,
            text="Patch Creator",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        ).grid(row=0, column=0, padx=theme.SECTION_PAD, pady=(20, 15), sticky="w")

        # Tabs
        self._tabview = ctk.CTkTabview(
            self,
            fg_color=theme.COLORS["bg_card"],
            segmented_button_fg_color=theme.COLORS["bg_card_alt"],
            segmented_button_selected_color=theme.COLORS["accent"],
            segmented_button_selected_hover_color=theme.COLORS["accent_hover"],
            segmented_button_unselected_color=theme.COLORS["bg_card_alt"],
            segmented_button_unselected_hover_color=theme.COLORS["card_hover"],
        )
        self._tabview.grid(
            row=2,
            column=0,
            padx=theme.SECTION_PAD,
            pady=(0, 4),
            sticky="nsew",
        )

        self._build_registry_tab()
        self._build_create_tab()

        # Log
        self._log = LogPanel(self)
        self._log.grid(row=3, column=0, padx=theme.SECTION_PAD, pady=(4, 15), sticky="nsew")

    # -- Version Registry Tab --------------------------------------------------

    def _build_registry_tab(self):
        tab = self._tabview.add("Version Registry")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Buttons
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=0, column=0, pady=(8, 4), sticky="ew")

        self._register_btn = ctk.CTkButton(
            btn_frame,
            text="Register Version",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._register_version,
        )
        self._register_btn.pack(side="left", padx=(0, 6))

        self._remove_btn = ctk.CTkButton(
            btn_frame,
            text="Remove Selected",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            command=self._remove_version,
        )
        self._remove_btn.pack(side="left", padx=(0, 6))

        self._reverify_btn = ctk.CTkButton(
            btn_frame,
            text="Re-verify",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._reverify_version,
        )
        self._reverify_btn.pack(side="left")

        # Registry list
        self._reg_scroll = ctk.CTkScrollableFrame(
            tab,
            fg_color=theme.COLORS["bg_dark"],
            corner_radius=theme.CORNER_RADIUS,
            border_width=1,
            border_color=theme.COLORS["border"],
        )
        self._reg_scroll.grid(row=1, column=0, pady=(6, 6), sticky="nsew")
        for col, w in [(0, 30), (1, 130), (2, 0), (3, 60), (4, 110), (5, 80)]:
            self._reg_scroll.grid_columnconfigure(col, weight=1 if w == 0 else 0, minsize=w)

        self._reg_placeholder = ctk.CTkLabel(
            self._reg_scroll,
            text="No versions registered. Click 'Register Version' to add one.",
            font=ctk.CTkFont(*theme.FONT_SMALL),
            text_color=theme.COLORS["text_muted"],
        )
        self._reg_placeholder.grid(row=0, column=0, columnspan=6, pady=30)

    # -- Create Patch Tab ------------------------------------------------------

    def _build_create_tab(self):
        tab = self._tabview.add("Create Patch")
        tab.grid_columnconfigure(1, weight=1)

        # From version
        ctk.CTkLabel(
            tab,
            text="From Version:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, padx=(10, 6), pady=(12, 4), sticky="w")

        self._from_var = ctk.StringVar()
        self._from_menu = ctk.CTkOptionMenu(
            tab,
            variable=self._from_var,
            values=["(none)"],
            height=32,
            width=250,
            fg_color=theme.COLORS["bg_card_alt"],
            button_color=theme.COLORS["accent"],
            button_hover_color=theme.COLORS["accent_hover"],
        )
        self._from_menu.grid(row=0, column=1, padx=(0, 10), pady=(12, 4), sticky="w")

        # To version
        ctk.CTkLabel(
            tab,
            text="To Version:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=1, column=0, padx=(10, 6), pady=4, sticky="w")

        self._to_var = ctk.StringVar()
        self._to_menu = ctk.CTkOptionMenu(
            tab,
            variable=self._to_var,
            values=["(none)"],
            height=32,
            width=250,
            fg_color=theme.COLORS["bg_card_alt"],
            button_color=theme.COLORS["accent"],
            button_hover_color=theme.COLORS["accent_hover"],
        )
        self._to_menu.grid(row=1, column=1, padx=(0, 10), pady=4, sticky="w")

        # Output info
        self._patch_info_label = ctk.CTkLabel(
            tab,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=theme.COLORS["text_muted"],
        )
        self._patch_info_label.grid(
            row=2,
            column=0,
            columnspan=2,
            padx=10,
            pady=(4, 0),
            sticky="w",
        )

        # Progress
        self._patch_progress_frame = ctk.CTkFrame(tab, fg_color="transparent")

        self._patch_progress_bar = ctk.CTkProgressBar(
            self._patch_progress_frame,
            height=16,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            progress_color=theme.COLORS["accent"],
        )
        self._patch_progress_bar.pack(fill="x", pady=(0, 2))
        self._patch_progress_bar.set(0)

        self._patch_progress_label = ctk.CTkLabel(
            self._patch_progress_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=theme.COLORS["text_muted"],
        )
        self._patch_progress_label.pack(anchor="w")

        # Buttons
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=4, column=0, columnspan=2, padx=10, pady=(8, 10), sticky="ew")

        self._create_btn = ctk.CTkButton(
            btn_frame,
            text="Create Patch",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._create_patch,
        )
        self._create_btn.pack(side="left", padx=(0, 6))

        self._upload_patch_btn = ctk.CTkButton(
            btn_frame,
            text="Upload to CDN",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["success"],
            hover_color="#3ae882",
            text_color="#1a1a2e",
            command=self._upload_patch,
            state="disabled",
        )
        self._upload_patch_btn.pack(side="left", padx=(0, 6))

        self._cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            height=theme.BUTTON_HEIGHT_SMALL,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            command=self._cancel_patch,
        )

    # -- Lifecycle -------------------------------------------------------------

    def on_show(self):
        self._load_registry()

    # -- Registry Operations ---------------------------------------------------

    def _load_registry(self):
        from ..backend.patch_ops import load_version_registry
        from ..config import CONFIG_FILE

        self._registry = load_version_registry(CONFIG_FILE)
        self._refresh_registry_ui()
        self._refresh_version_menus()

    def _save_registry(self):
        from ..backend.patch_ops import save_version_registry
        from ..config import CONFIG_FILE

        save_version_registry(CONFIG_FILE, self._registry)
        # Sync in-memory config so ManagerConfig.save() doesn't clobber with stale data
        self.app.config_data.version_registry = list(self._registry)

    def _refresh_registry_ui(self):
        for widget in self._reg_scroll.winfo_children():
            widget.destroy()
        self._registry_rows.clear()

        if not self._registry:
            self._reg_placeholder = ctk.CTkLabel(
                self._reg_scroll,
                text="No versions registered. Click 'Register Version' to add one.",
                font=ctk.CTkFont(*theme.FONT_SMALL),
                text_color=theme.COLORS["text_muted"],
            )
            self._reg_placeholder.grid(row=0, column=0, columnspan=6, pady=30)
            return

        # Header
        for col, text in enumerate(["", "Version", "Directory", "Files", "Date", "Status"]):
            ctk.CTkLabel(
                self._reg_scroll,
                text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=col, padx=4, pady=(4, 6), sticky="w")

        for i, entry in enumerate(self._registry):
            row = i + 1
            version = entry["version"]

            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(
                self._reg_scroll,
                text="",
                variable=var,
                width=20,
                height=20,
                checkbox_width=16,
                checkbox_height=16,
            ).grid(row=row, column=0, padx=4, pady=2)

            ctk.CTkLabel(
                self._reg_scroll,
                text=version,
                font=ctk.CTkFont("Consolas", 11),
            ).grid(row=row, column=1, padx=4, pady=2, sticky="w")

            dir_text = entry.get("directory", "")
            if len(dir_text) > 50:
                dir_text = "..." + dir_text[-47:]
            ctk.CTkLabel(
                self._reg_scroll,
                text=dir_text,
                font=ctk.CTkFont(size=10),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=2, padx=4, pady=2, sticky="w")

            ctk.CTkLabel(
                self._reg_scroll,
                text=str(entry.get("file_count", "?")),
                font=ctk.CTkFont(size=11),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=3, padx=4, pady=2, sticky="e")

            ctk.CTkLabel(
                self._reg_scroll,
                text=entry.get("date_added", ""),
                font=ctk.CTkFont(size=10),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=4, padx=4, pady=2, sticky="w")

            badge = StatusBadge(self._reg_scroll)
            if entry.get("verified"):
                conf = entry.get("fingerprint_confidence", 0)
                if conf >= 0.5:
                    badge.set_status(f"Verified ({int(conf * 100)}%)", "success")
                else:
                    badge.set_status("Verified", "success")
            elif entry.get("fingerprint_match"):
                badge.set_status("Mismatch", "error")
            elif Path(entry.get("directory", "")).is_dir():
                badge.set_status("Unverified", "warning")
            else:
                badge.set_status("Missing Dir", "error")
            badge.grid(row=row, column=5, padx=4, pady=2, sticky="e")

            self._registry_rows[version] = {"var": var, "badge": badge, "entry": entry}

    def _refresh_version_menus(self):
        versions = [e["version"] for e in self._registry]
        if not versions:
            versions = ["(none)"]
        self._from_menu.configure(values=versions)
        self._to_menu.configure(values=versions)
        if len(self._registry) >= 1:
            self._from_var.set(versions[0])
        if len(self._registry) >= 2:
            self._to_var.set(versions[-1])

    def _register_version(self):
        dialog = _RegisterVersionDialog(self)
        self.wait_window(dialog)
        if not dialog.directory or not dialog.version:
            return

        self._log.log(f"Registering {dialog.version}...")
        self.app.run_async(
            self._bg_register,
            dialog.directory,
            dialog.version,
            on_done=self._on_register_done,
            on_error=self._on_register_error,
        )

    def _bg_register(self, directory: str, version: str):
        from ..backend.patch_ops import register_version

        return register_version(directory, version, self._registry)

    def _on_register_done(self, entry):
        self._save_registry()
        self._refresh_registry_ui()
        self._refresh_version_menus()
        self._log.log(
            f"Registered {entry['version']}: {entry['file_count']} files",
            "success",
        )
        self.app.show_toast(f"Registered {entry['version']}", "success")

    def _on_register_error(self, error):
        self._log.log(f"Registration failed: {error}", "error")

    def _remove_version(self):
        selected = [v for v, r in self._registry_rows.items() if r["var"].get()]
        if not selected:
            self.app.show_toast("No versions selected", "warning")
            return

        self._registry[:] = [e for e in self._registry if e["version"] not in selected]
        self._save_registry()
        self._refresh_registry_ui()
        self._refresh_version_menus()
        self._log.log(f"Removed {len(selected)} version(s)", "success")

    def _reverify_version(self):
        selected = [v for v, r in self._registry_rows.items() if r["var"].get()]
        if not selected:
            self.app.show_toast("No versions selected", "warning")
            return

        self._reverify_btn.configure(state="disabled")
        self._log.log(f"Re-verifying {len(selected)} version(s)...")
        self.app.run_async(
            self._bg_reverify,
            selected,
            on_done=self._on_reverify_done,
            on_error=lambda e: (
                self._log.log(f"Re-verify failed: {e}", "error"),
                self._reverify_btn.configure(state="normal"),
            ),
        )

    def _bg_reverify(self, selected: list[str]):
        from ..backend.patch_ops import detect_version_fingerprint

        results = []
        for entry in self._registry:
            if entry["version"] not in selected:
                continue
            dir_path = Path(entry.get("directory", ""))
            if dir_path.is_dir():
                file_count = sum(1 for f in dir_path.rglob("*") if f.is_file())
                entry["file_count"] = file_count
                detected, confidence = detect_version_fingerprint(str(dir_path))
                entry["fingerprint_match"] = detected
                entry["fingerprint_confidence"] = confidence
                if detected and detected == entry["version"] and confidence >= 0.5:
                    entry["verified"] = True
                    results.append(("success", entry["version"], file_count, detected, confidence))
                elif detected:
                    entry["verified"] = False
                    results.append(("mismatch", entry["version"], file_count, detected, confidence))
                else:
                    entry["verified"] = True
                    results.append(("no_data", entry["version"], file_count, None, 0.0))
            else:
                entry["verified"] = False
                results.append(("missing", entry["version"], 0, None, 0.0))
        return results

    def _on_reverify_done(self, results):
        self._reverify_btn.configure(state="normal")
        for status, version, file_count, detected, confidence in results:
            if status == "success":
                pct = int(confidence * 100)
                self._log.log(
                    f"Verified {version}: {file_count} files, fingerprint match ({pct}%)",
                    "success",
                )
            elif status == "mismatch":
                self._log.log(
                    f"Fingerprint mismatch for {version}: detected {detected} instead",
                    "warning",
                )
            elif status == "no_data":
                self._log.log(
                    f"Verified {version}: {file_count} files (no fingerprint data available)",
                    "success",
                )
            else:
                entry = next((e for e in self._registry if e["version"] == version), None)
                self._log.log(
                    f"Directory not found for {version}: "
                    f"{entry.get('directory', '?') if entry else '?'}",
                    "error",
                )
        self._save_registry()
        self._refresh_registry_ui()

    # -- Patch Creation --------------------------------------------------------

    def _create_patch(self):
        if self._busy:
            self.app.show_toast("Operation in progress", "warning")
            return

        from_version = self._from_var.get()
        to_version = self._to_var.get()

        if from_version == "(none)" or to_version == "(none)":
            self.app.show_toast("Register at least 2 versions first", "warning")
            return
        if from_version == to_version:
            self.app.show_toast("From and To versions must be different", "warning")
            return

        from_entry = next((e for e in self._registry if e["version"] == from_version), None)
        to_entry = next((e for e in self._registry if e["version"] == to_version), None)

        if not from_entry or not to_entry:
            self.app.show_toast("Version not found in registry", "error")
            return

        from_dir = from_entry["directory"]
        to_dir = to_entry["directory"]

        if not Path(from_dir).is_dir():
            self.app.show_toast(f"From directory not found: {from_dir}", "error")
            return
        if not Path(to_dir).is_dir():
            self.app.show_toast(f"To directory not found: {to_dir}", "error")
            return

        from ..backend.patch_ops import get_patcher_dir

        patcher_dir = get_patcher_dir(self.app.config_data.patcher_dir)
        if not patcher_dir:
            self.app.show_toast("Patcher directory not found", "error")
            self._log.log(
                "Patcher directory not found. Set it in Settings or place it at ../patcher/",
                "error",
            )
            return

        self._busy = True
        self._cancel_event.clear()
        self._create_btn.configure(state="disabled")
        self._upload_patch_btn.configure(state="disabled")
        self._cancel_btn.pack(side="left", padx=(0, 6))
        self._last_patch_path = None

        # Show progress
        self._patch_progress_frame.grid(
            row=3,
            column=0,
            columnspan=2,
            padx=10,
            pady=(4, 0),
            sticky="ew",
        )
        self._patch_progress_bar.set(0)
        self._patch_progress_label.configure(text="Starting...")
        self._patch_info_label.configure(text=f"Creating: {from_version} -> {to_version}")
        self._log.log(f"Creating patch: {from_version} -> {to_version}")

        output_dir = Path(__file__).resolve().parent.parent.parent / "patch_output"

        Thread(
            target=self._bg_create_patch,
            args=(from_dir, to_dir, from_version, to_version, patcher_dir, output_dir),
            daemon=True,
        ).start()

    def _bg_create_patch(
        self,
        from_dir,
        to_dir,
        from_version,
        to_version,
        patcher_dir,
        output_dir,
    ):
        from ..backend.dlc_ops import fmt_size
        from ..backend.patch_ops import create_patch

        start_time = time.time()

        def log(msg, level="info"):
            self.app._enqueue_gui(self._log.log, msg, level)

        def progress(current, total):
            if total > 0:
                pct = current / total
                self.app._enqueue_gui(self._patch_progress_bar.set, pct)
                elapsed = time.time() - start_time
                self.app._enqueue_gui(
                    self._patch_progress_label.configure,
                    text=f"{current}/{total} files  |  {elapsed:.0f}s",
                )

        result = create_patch(
            from_dir,
            to_dir,
            from_version,
            to_version,
            patcher_dir,
            output_dir,
            cancel_event=self._cancel_event,
            log_cb=log,
            progress_cb=progress,
        )

        total_time = time.time() - start_time

        def finish():
            self._busy = False
            self._create_btn.configure(state="normal")
            self._cancel_btn.pack_forget()
            self._patch_progress_frame.grid_forget()

            if result and result.is_file():
                size = result.stat().st_size
                self._last_patch_path = result
                self._upload_patch_btn.configure(state="normal")
                self._patch_info_label.configure(
                    text=f"Patch ready: {fmt_size(size)} — {from_version} -> {to_version}",
                )
                self._log.log(
                    f"Patch created: {result.name} ({fmt_size(size)}) in {total_time:.0f}s",
                    "success",
                )
                self.app.show_toast("Patch created successfully", "success")
            else:
                self._patch_info_label.configure(text="Patch creation failed or cancelled")
                if self._cancel_event.is_set():
                    self._log.log("Patch creation cancelled", "warning")
                else:
                    self.app.show_toast("Patch creation failed", "error")

        self.app._enqueue_gui(finish)

    def _cancel_patch(self):
        self._cancel_event.set()
        self._log.log("Cancellation requested...", "warning")
        self._cancel_btn.configure(state="disabled")

    # -- Patch Upload ----------------------------------------------------------

    def _upload_patch(self):
        if self._busy:
            self.app.show_toast("Operation in progress", "warning")
            return
        if not self._last_patch_path or not self._last_patch_path.is_file():
            self.app.show_toast("No patch file to upload", "warning")
            return

        # Parse versions from filename (from_to_to.zip)
        stem = self._last_patch_path.stem
        parts = stem.split("_to_")
        if len(parts) != 2:
            self.app.show_toast("Cannot parse versions from patch filename", "error")
            return

        from_version, to_version = parts

        self._busy = True
        self._upload_patch_btn.configure(state="disabled")
        self._create_btn.configure(state="disabled")
        self._log.log(f"Uploading patch: {from_version} -> {to_version}")

        Thread(
            target=self._bg_upload_patch,
            args=(self._last_patch_path, from_version, to_version),
            daemon=True,
        ).start()

    def _bg_upload_patch(self, patch_path: Path, from_version: str, to_version: str):
        from ..backend.connection import ConnectionManager
        from ..backend.patch_ops import upload_patch

        conn = ConnectionManager(self.app.config_data.to_cdn_config())

        def log(msg, level="info"):
            self.app._enqueue_gui(self._log.log, msg, level)

        entry = upload_patch(
            conn,
            patch_path,
            from_version,
            to_version,
            log_cb=log,
        )

        if entry:
            # Update manifest patches array
            log("Updating manifest with patch entry...")
            try:
                manifest = conn.fetch_manifest()
                patches = manifest.get("patches", [])

                # Remove existing entry for same from->to
                patches = [
                    p
                    for p in patches
                    if not (
                        p.get("from_version") == from_version and p.get("to_version") == to_version
                    )
                ]
                patches.append(entry)
                manifest["patches"] = patches

                import json
                import tempfile

                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".json",
                    delete=False,
                    encoding="utf-8",
                ) as tmp:
                    json.dump(manifest, tmp, indent=2)
                    tmp_path = Path(tmp.name)
                try:
                    conn.publish_manifest(tmp_path)
                finally:
                    tmp_path.unlink(missing_ok=True)

                log("Manifest updated with patch entry", "success")
            except Exception as e:
                log(f"Manifest update failed: {e}", "error")

        def finish():
            self._busy = False
            self._create_btn.configure(state="normal")
            self._upload_patch_btn.configure(state="normal")
            if entry:
                self.app.show_toast("Patch uploaded to CDN", "success")
            else:
                self.app.show_toast("Patch upload failed", "error")

        self.app._enqueue_gui(finish)


# -- Dialogs ------------------------------------------------------------------


class _RegisterVersionDialog(ctk.CTkToplevel):
    """Dialog to register a game directory as a version with fingerprint auto-detect."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Register Version")
        self.geometry("500x250")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.directory: str = ""
        self.version: str = ""

        self.configure(fg_color=theme.COLORS["bg_card"])

        # Directory
        ctk.CTkLabel(
            self,
            text="Game Directory:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, padx=(20, 6), pady=(20, 4), sticky="w")

        dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        dir_frame.grid(row=0, column=1, padx=(0, 20), pady=(20, 4), sticky="ew")
        dir_frame.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._dir_entry = ctk.CTkEntry(
            dir_frame,
            height=32,
            font=ctk.CTkFont(size=11),
            placeholder_text="C:\\...\\The Sims 4",
        )
        self._dir_entry.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        ctk.CTkButton(
            dir_frame,
            text="Browse",
            width=70,
            height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            command=self._browse,
        ).grid(row=0, column=1)

        # Version
        ctk.CTkLabel(
            self,
            text="Version String:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=1, column=0, padx=(20, 6), pady=4, sticky="w")

        ver_frame = ctk.CTkFrame(self, fg_color="transparent")
        ver_frame.grid(row=1, column=1, padx=(0, 20), pady=4, sticky="ew")
        ver_frame.grid_columnconfigure(0, weight=1)

        self._ver_entry = ctk.CTkEntry(
            ver_frame,
            height=32,
            font=ctk.CTkFont("Consolas", 12),
            placeholder_text="e.g. 1.121.372.1020",
        )
        self._ver_entry.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        self._ver_entry.bind("<Return>", lambda _: self._ok())

        self._detect_btn = ctk.CTkButton(
            ver_frame,
            text="Detect",
            width=70,
            height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._detect_version,
        )
        self._detect_btn.grid(row=0, column=1)

        # Detection status label
        self._detect_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_muted"],
        )
        self._detect_label.grid(row=2, column=0, columnspan=2, padx=20, pady=(2, 0), sticky="w")

        # Help text
        ctk.CTkLabel(
            self,
            text="Point to a clean game directory for this version. "
            "Click 'Detect' to auto-detect version from file hashes.",
            font=ctk.CTkFont(size=10),
            text_color=theme.COLORS["text_muted"],
            wraplength=440,
        ).grid(row=3, column=0, columnspan=2, padx=20, pady=(4, 8), sticky="w")

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, columnspan=2, padx=20, pady=(4, 15), sticky="ew")

        ctk.CTkButton(
            btn_frame,
            text="Register",
            width=90,
            height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._ok,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=80,
            height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self.destroy,
        ).pack(side="right")

    def _browse(self):
        from tkinter import filedialog

        path = filedialog.askdirectory(title="Select Game Directory")
        if path:
            self._dir_entry.delete(0, "end")
            self._dir_entry.insert(0, path)
            self._detect_version()

    def _detect_version(self):
        directory = self._dir_entry.get().strip()
        if not directory:
            self._detect_label.configure(
                text="Enter a directory first",
                text_color=theme.COLORS["warning"],
            )
            return

        self._detect_label.configure(
            text="Detecting...",
            text_color=theme.COLORS["text_muted"],
        )
        self._detect_btn.configure(state="disabled")
        self.update_idletasks()

        import threading

        def _bg_detect():
            from ..backend.patch_ops import (
                detect_version_fingerprint,
                parse_version_from_default_ini,
            )

            try:
                detected, confidence = detect_version_fingerprint(directory)
            except Exception:
                detected, confidence = None, 0.0

            ini_version = None
            if not detected or confidence < 0.5:
                with contextlib.suppress(Exception):
                    ini_version = parse_version_from_default_ini(directory)

            # Update GUI on main thread
            def _apply():
                self._detect_btn.configure(state="normal")
                if detected and confidence >= 0.5:
                    self._ver_entry.delete(0, "end")
                    self._ver_entry.insert(0, detected)
                    pct = int(confidence * 100)
                    self._detect_label.configure(
                        text=f"Detected: {detected} ({pct}% confidence)",
                        text_color=theme.COLORS["success"],
                    )
                elif ini_version:
                    self._ver_entry.delete(0, "end")
                    self._ver_entry.insert(0, ini_version)
                    self._detect_label.configure(
                        text=f"Read from Default.ini: {ini_version} (unverified)",
                        text_color=theme.COLORS["warning"],
                    )
                else:
                    self._detect_label.configure(
                        text="No match found — enter version manually",
                        text_color=theme.COLORS["warning"],
                    )

            self.after(0, _apply)

        threading.Thread(target=_bg_detect, daemon=True).start()

    def _ok(self):
        directory = self._dir_entry.get().strip()
        version = self._ver_entry.get().strip()
        if directory and version:
            self.directory = directory
            self.version = version
            self.destroy()
