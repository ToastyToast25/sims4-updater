"""Manifest Editor frame — view, edit, audit, and upload the CDN manifest."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme
from ..components import LogPanel, StatusBadge

if TYPE_CHECKING:
    from ..app import CDNManagerApp


class ManifestFrame(ctk.CTkFrame):
    def __init__(self, parent, app: CDNManagerApp):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._manifest = None
        self._original_manifest = None
        self._audit_results = None
        self._lang_audit_results = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self,
            text="Manifest Editor",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        ).grid(row=0, column=0, padx=theme.SECTION_PAD, pady=(20, 15), sticky="w")

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=1, column=0, padx=theme.SECTION_PAD, sticky="ew")

        self._load_btn = ctk.CTkButton(
            header,
            text="Load from CDN",
            height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._load_manifest,
        )
        self._load_btn.pack(side="left", padx=(0, 6))

        self._audit_btn = ctk.CTkButton(
            header,
            text="Audit",
            height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._audit,
            state="disabled",
        )
        self._audit_btn.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            header,
            text="Fix Sizes",
            height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._fix_sizes,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            header,
            text="Diff",
            height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._show_diff,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            header,
            text="Save Local",
            height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self._save_local,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            header,
            text="Upload to CDN",
            height=32,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["success"],
            hover_color="#3ae882",
            text_color="#1a1a2e",
            command=self._upload,
        ).pack(side="left")

        # Tabview
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
            pady=(10, 4),
            sticky="nsew",
        )

        # Overview tab
        overview = self._tabview.add("Overview")
        overview.grid_columnconfigure(1, weight=1)

        self._overview_fields = {}
        for i, (key, label) in enumerate(
            [
                ("latest", "Latest Version"),
                ("game_latest", "Game Latest"),
                ("game_latest_date", "Game Latest Date"),
            ]
        ):
            ctk.CTkLabel(
                overview,
                text=f"{label}:",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=i, column=0, padx=(12, 8), pady=4, sticky="w")

            entry = ctk.CTkEntry(overview, font=ctk.CTkFont(size=12), height=32)
            entry.grid(row=i, column=1, padx=(0, 12), pady=4, sticky="ew")
            self._overview_fields[key] = entry

        self._meta_labels = {}
        meta_keys = [
            ("entitlements_url", "Entitlements URL"),
            ("self_update_url", "Self Update URL"),
            ("contribute_url", "Contribute URL"),
            ("report_url", "Report URL"),
            ("fingerprints_url", "Fingerprints URL"),
        ]
        offset = 3
        for i, (key, label) in enumerate(meta_keys):
            ctk.CTkLabel(
                overview,
                text=f"{label}:",
                font=ctk.CTkFont(*theme.FONT_SMALL),
                text_color=theme.COLORS["text_dim"],
            ).grid(row=offset + i, column=0, padx=(12, 8), pady=2, sticky="w")

            lbl = ctk.CTkLabel(
                overview,
                text="\u2014",
                font=ctk.CTkFont(size=10),
                text_color=theme.COLORS["text_muted"],
            )
            lbl.grid(row=offset + i, column=1, padx=(0, 12), pady=2, sticky="w")
            self._meta_labels[key] = lbl

        self._summary_label = ctk.CTkLabel(
            overview,
            text="Load the manifest to see contents",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        )
        self._summary_label.grid(
            row=offset + len(meta_keys),
            column=0,
            columnspan=2,
            padx=12,
            pady=(12, 4),
            sticky="w",
        )

        # DLC tab
        dlc_tab = self._tabview.add("DLC Downloads")
        dlc_tab.grid_columnconfigure(0, weight=1)
        dlc_tab.grid_rowconfigure(0, weight=1)

        self._dlc_scroll = ctk.CTkScrollableFrame(dlc_tab, fg_color=theme.COLORS["bg_dark"])
        self._dlc_scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 0))

        ctk.CTkLabel(
            self._dlc_scroll,
            text="Load manifest first",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=0, column=0, pady=30)

        dlc_btn_frame = ctk.CTkFrame(dlc_tab, fg_color="transparent")
        dlc_btn_frame.grid(row=1, column=0, padx=4, pady=(4, 4), sticky="ew")
        ctk.CTkButton(
            dlc_btn_frame,
            text="Add DLC",
            height=26,
            width=80,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            font=ctk.CTkFont(size=11),
            command=self._add_dlc_entry,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            dlc_btn_frame,
            text="Remove Selected",
            height=26,
            width=110,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            font=ctk.CTkFont(size=11),
            command=self._remove_dlc_entries,
        ).pack(side="left")

        self._dlc_check_vars: dict[str, ctk.BooleanVar] = {}

        # Language tab
        lang_tab = self._tabview.add("Languages")
        lang_tab.grid_columnconfigure(0, weight=1)
        lang_tab.grid_rowconfigure(0, weight=1)

        self._lang_scroll = ctk.CTkScrollableFrame(lang_tab, fg_color=theme.COLORS["bg_dark"])
        self._lang_scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 0))

        ctk.CTkLabel(
            self._lang_scroll,
            text="Load manifest first",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=0, column=0, pady=30)

        lang_btn_frame = ctk.CTkFrame(lang_tab, fg_color="transparent")
        lang_btn_frame.grid(row=1, column=0, padx=4, pady=(4, 4), sticky="ew")
        ctk.CTkButton(
            lang_btn_frame,
            text="Add Language",
            height=26,
            width=100,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            font=ctk.CTkFont(size=11),
            command=self._add_lang_entry,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            lang_btn_frame,
            text="Remove Selected",
            height=26,
            width=110,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            font=ctk.CTkFont(size=11),
            command=self._remove_lang_entries,
        ).pack(side="left")

        self._lang_check_vars: dict[str, ctk.BooleanVar] = {}

        # Patches tab
        patches_tab = self._tabview.add("Patches")
        patches_tab.grid_columnconfigure(0, weight=1)
        patches_tab.grid_rowconfigure(0, weight=1)

        self._patches_scroll = ctk.CTkScrollableFrame(
            patches_tab,
            fg_color=theme.COLORS["bg_dark"],
        )
        self._patches_scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 0))

        ctk.CTkLabel(
            self._patches_scroll,
            text="No patches",
            font=ctk.CTkFont(*theme.FONT_BODY),
            text_color=theme.COLORS["text_muted"],
        ).grid(row=0, column=0, pady=30)

        patches_btn_frame = ctk.CTkFrame(patches_tab, fg_color="transparent")
        patches_btn_frame.grid(row=1, column=0, padx=4, pady=(4, 4), sticky="ew")
        ctk.CTkButton(
            patches_btn_frame,
            text="Add Patch",
            height=26,
            width=80,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            font=ctk.CTkFont(size=11),
            command=self._add_patch_entry,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            patches_btn_frame,
            text="Remove Selected",
            height=26,
            width=110,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["error"],
            hover_color="#ff6b6b",
            font=ctk.CTkFont(size=11),
            command=self._remove_patch_entries,
        ).pack(side="left")

        self._patch_check_vars: dict[int, ctk.BooleanVar] = {}

        # Raw JSON tab
        raw_tab = self._tabview.add("Raw JSON")
        raw_tab.grid_columnconfigure(0, weight=1)
        raw_tab.grid_rowconfigure(0, weight=1)

        self._json_editor = ctk.CTkTextbox(
            raw_tab,
            font=ctk.CTkFont("Consolas", 11),
            fg_color=theme.COLORS["bg_deeper"],
            corner_radius=theme.CORNER_RADIUS_SMALL,
            wrap="none",
        )
        self._json_editor.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        # Log
        self._log = LogPanel(self)
        self._log.grid(row=3, column=0, padx=theme.SECTION_PAD, pady=(4, 15), sticky="nsew")

    def on_show(self):
        pass

    # -- Load ----------------------------------------------------------------

    def _load_manifest(self):
        self._log.log("Loading manifest from CDN...")
        self._load_btn.configure(state="disabled")
        self.app.run_async(
            self._bg_load,
            on_done=self._on_load_done,
            on_error=lambda e: (
                self._log.log(f"Failed: {e}", "error"),
                self._load_btn.configure(state="normal"),
            ),
        )

    def _bg_load(self):
        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        return conn.fetch_manifest()

    def _on_load_done(self, manifest: dict):
        self._manifest = manifest
        self._original_manifest = copy.deepcopy(manifest)
        self._load_btn.configure(state="normal")
        self._audit_btn.configure(state="normal")

        # Overview
        for key, entry in self._overview_fields.items():
            entry.delete(0, "end")
            val = manifest.get(key, "")
            if val:
                entry.insert(0, str(val))

        for key, lbl in self._meta_labels.items():
            val = manifest.get(key, "")
            lbl.configure(text=str(val) if val else "\u2014")

        dlc_count = len(manifest.get("dlc_downloads", {}))
        lang_count = len(manifest.get("language_downloads", {}))
        patch_count = len(manifest.get("patches", []))
        self._summary_label.configure(
            text=f"{dlc_count} DLCs, {lang_count} languages, {patch_count} patches",
        )

        self._populate_dlc_tab(manifest)
        self._populate_lang_tab(manifest)
        self._populate_patches_tab(manifest)

        self._json_editor.delete("1.0", "end")
        self._json_editor.insert("1.0", json.dumps(manifest, indent=2, ensure_ascii=False))

        self._log.log(
            f"Loaded: {dlc_count} DLCs, {lang_count} languages, {patch_count} patches",
            "success",
        )

    def _populate_dlc_tab(self, manifest: dict):
        from ..backend.dlc_ops import fmt_size

        for w in self._dlc_scroll.winfo_children():
            w.destroy()
        self._dlc_check_vars.clear()

        dlc_downloads = manifest.get("dlc_downloads", {})
        if not dlc_downloads:
            ctk.CTkLabel(
                self._dlc_scroll,
                text="No DLC entries",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=0, columnspan=5, pady=30)
            return

        for col, text in enumerate(["", "ID", "Size", "MD5", "Status"]):
            ctk.CTkLabel(
                self._dlc_scroll,
                text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=col, padx=6, pady=(4, 6), sticky="w")

        for i, (dlc_id, entry) in enumerate(sorted(dlc_downloads.items())):
            row = i + 1

            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(
                self._dlc_scroll,
                text="",
                variable=var,
                width=20,
                height=20,
                checkbox_width=14,
                checkbox_height=14,
            ).grid(row=row, column=0, padx=4, pady=1)
            self._dlc_check_vars[dlc_id] = var

            ctk.CTkLabel(
                self._dlc_scroll,
                text=dlc_id,
                font=ctk.CTkFont("Consolas", 11),
            ).grid(row=row, column=1, padx=6, pady=1, sticky="w")

            size = entry.get("size", 0)
            ctk.CTkLabel(
                self._dlc_scroll,
                text=fmt_size(size) if size else "0",
                font=ctk.CTkFont(size=10),
                text_color=theme.COLORS["text_muted"] if size else theme.COLORS["error"],
            ).grid(row=row, column=2, padx=6, pady=1, sticky="w")

            md5 = entry.get("md5", "")
            ctk.CTkLabel(
                self._dlc_scroll,
                text=(md5[:12] + "...") if md5 else "none",
                font=ctk.CTkFont("Consolas", 9),
                text_color=theme.COLORS["text_muted"] if md5 else theme.COLORS["error"],
            ).grid(row=row, column=3, padx=6, pady=1, sticky="w")

            badge = StatusBadge(self._dlc_scroll)
            if size > 0 and md5:
                badge.set_status("OK", "success")
            elif size > 0:
                badge.set_status("No MD5", "warning")
            else:
                badge.set_status("No Size", "error")
            badge.grid(row=row, column=4, padx=6, pady=1, sticky="w")

    def _populate_lang_tab(self, manifest: dict):
        from ..backend.dlc_ops import fmt_size

        for w in self._lang_scroll.winfo_children():
            w.destroy()
        self._lang_check_vars.clear()

        lang_downloads = manifest.get("language_downloads", {})
        if not lang_downloads:
            ctk.CTkLabel(
                self._lang_scroll,
                text="No language entries",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=0, columnspan=4, pady=30)
            return

        for col, text in enumerate(["", "Locale", "Size", "MD5"]):
            ctk.CTkLabel(
                self._lang_scroll,
                text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=col, padx=6, pady=(4, 6), sticky="w")

        for i, (locale, entry) in enumerate(sorted(lang_downloads.items())):
            row = i + 1

            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(
                self._lang_scroll,
                text="",
                variable=var,
                width=20,
                height=20,
                checkbox_width=14,
                checkbox_height=14,
            ).grid(row=row, column=0, padx=4, pady=1)
            self._lang_check_vars[locale] = var

            ctk.CTkLabel(
                self._lang_scroll,
                text=locale,
                font=ctk.CTkFont("Consolas", 11),
            ).grid(row=row, column=1, padx=6, pady=1, sticky="w")

            size = entry.get("size", 0)
            ctk.CTkLabel(
                self._lang_scroll,
                text=fmt_size(size) if size else "0",
                font=ctk.CTkFont(size=10),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=2, padx=6, pady=1, sticky="w")

            md5 = entry.get("md5", "")
            ctk.CTkLabel(
                self._lang_scroll,
                text=(md5[:12] + "...") if md5 else "none",
                font=ctk.CTkFont("Consolas", 9),
                text_color=theme.COLORS["text_muted"] if md5 else theme.COLORS["error"],
            ).grid(row=row, column=3, padx=6, pady=1, sticky="w")

    def _populate_patches_tab(self, manifest: dict):
        from ..backend.dlc_ops import fmt_size

        for w in self._patches_scroll.winfo_children():
            w.destroy()
        self._patch_check_vars.clear()

        patches = manifest.get("patches", [])
        if not patches:
            ctk.CTkLabel(
                self._patches_scroll,
                text="No patches in manifest",
                font=ctk.CTkFont(*theme.FONT_BODY),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=0, columnspan=5, pady=30)
            return

        for col, text in enumerate(["", "From", "To", "Size", "URL"]):
            ctk.CTkLabel(
                self._patches_scroll,
                text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=0, column=col, padx=6, pady=(4, 6), sticky="w")

        for i, patch in enumerate(patches):
            row = i + 1

            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(
                self._patches_scroll,
                text="",
                variable=var,
                width=20,
                height=20,
                checkbox_width=14,
                checkbox_height=14,
            ).grid(row=row, column=0, padx=4, pady=1)
            self._patch_check_vars[i] = var

            for col, key in enumerate(["from", "to"], start=1):
                ctk.CTkLabel(
                    self._patches_scroll,
                    text=patch.get(key, ""),
                    font=ctk.CTkFont("Consolas", 10),
                ).grid(row=row, column=col, padx=6, pady=1, sticky="w")

            size = patch.get("size", 0)
            ctk.CTkLabel(
                self._patches_scroll,
                text=fmt_size(size) if size else "?",
                font=ctk.CTkFont(size=10),
                text_color=theme.COLORS["text_muted"],
            ).grid(row=row, column=3, padx=6, pady=1, sticky="w")

            ctk.CTkLabel(
                self._patches_scroll,
                text=patch.get("url", ""),
                font=ctk.CTkFont(size=9),
                text_color=theme.COLORS["text_dim"],
            ).grid(row=row, column=4, padx=6, pady=1, sticky="w")

    # -- Audit ---------------------------------------------------------------

    def _audit(self):
        if not self._manifest:
            return
        self._log.log("Auditing manifest...")
        self._audit_btn.configure(state="disabled")
        self.app.run_async(
            self._bg_audit,
            on_done=self._on_audit_done,
            on_error=lambda e: (
                self._log.log(f"Audit failed: {e}", "error"),
                self._audit_btn.configure(state="normal"),
            ),
        )

    def _bg_audit(self):
        from ..backend.connection import ConnectionManager
        from ..backend.manifest_ops import (
            audit_dlc_entries,
            audit_language_entries,
            audit_meta_urls,
            detect_orphans,
        )

        # Use SFTP to verify files on the seedbox (bypasses CDN JWT auth)
        conn = ConnectionManager(self.app.config_data.to_cdn_config())

        # SFTP stat is fast (~20ms each), so use fewer workers to avoid
        # creating excessive SSH connections (pool max_idle=2).
        dlc = audit_dlc_entries(self._manifest.get("dlc_downloads", {}), conn, workers=3)
        lang = audit_language_entries(self._manifest.get("language_downloads", {}), conn, workers=3)

        # Check meta URLs (fingerprints, entitlements, etc.)
        meta = audit_meta_urls(self._manifest, conn)

        # Orphan detection: cross-reference KV keys vs manifest
        orphans = ([], [])
        try:
            kv_keys = conn.kv_list()
            orphans = detect_orphans(self._manifest, kv_keys)
        except Exception:
            pass

        conn.close()
        return dlc, lang, orphans, meta

    def _on_audit_done(self, result):
        dlc_results, lang_results, orphans = result[0], result[1], result[2]
        self._audit_results = dlc_results
        self._lang_audit_results = lang_results
        self._audit_btn.configure(state="normal")

        ok = sum(1 for r in dlc_results if r[1] == "ok")
        issues = len(dlc_results) - ok
        l_ok = sum(1 for r in lang_results if r[1] == "ok")
        l_issues = len(lang_results) - l_ok

        self._log.log(f"DLC: {ok} OK, {issues} issues  |  Lang: {l_ok} OK, {l_issues} issues")

        for did, issue, old_s, real_s, _status in dlc_results:
            if issue == "unreachable":
                self._log.log(f"  DLC {did}: unreachable", "error")
            elif issue in ("size_zero", "size_mismatch"):
                self._log.log(f"  DLC {did}: {issue} ({old_s} -> {real_s})", "warning")

        for locale, issue, old_s, real_s, _status in lang_results:
            if issue == "unreachable":
                self._log.log(f"  Lang {locale}: unreachable", "error")
            elif issue in ("size_zero", "size_mismatch"):
                self._log.log(f"  Lang {locale}: {issue} ({old_s} -> {real_s})", "warning")

        # Meta URL report
        meta_results = result[3] if len(result) > 3 else []
        if meta_results:
            m_ok = sum(1 for r in meta_results if r[1] == "ok")
            m_issues = len(meta_results) - m_ok
            self._log.log(f"Meta URLs: {m_ok} OK, {m_issues} issues")
            for name, issue, *_ in meta_results:
                if issue != "ok":
                    self._log.log(f"  {name}: {issue}", "error")

        # Orphan report
        in_kv_not_manifest, in_manifest_not_kv = orphans
        if in_kv_not_manifest:
            self._log.log(
                f"Orphan KV keys ({len(in_kv_not_manifest)} not in manifest):",
                "warning",
            )
            for key in in_kv_not_manifest[:20]:
                self._log.log(f"  KV orphan: {key}", "warning")
            if len(in_kv_not_manifest) > 20:
                self._log.log(
                    f"  ... and {len(in_kv_not_manifest) - 20} more",
                    "warning",
                )
        if in_manifest_not_kv:
            self._log.log(
                f"Missing KV keys ({len(in_manifest_not_kv)} in manifest but not KV):",
                "error",
            )
            for key in in_manifest_not_kv[:20]:
                self._log.log(f"  Missing KV: {key}", "error")
            if len(in_manifest_not_kv) > 20:
                self._log.log(
                    f"  ... and {len(in_manifest_not_kv) - 20} more",
                    "error",
                )

        m_issues = sum(1 for r in meta_results if r[1] != "ok") if meta_results else 0
        total = issues + l_issues + m_issues + len(in_manifest_not_kv)
        orphan_count = len(in_kv_not_manifest)
        if total == 0 and orphan_count == 0:
            self._log.log("All entries OK, no orphans!", "success")
            self.app.show_toast("Audit passed", "success")
        else:
            parts = []
            if issues + l_issues > 0:
                parts.append(f"{issues + l_issues} URL issues")
            if len(in_manifest_not_kv) > 0:
                parts.append(f"{len(in_manifest_not_kv)} missing KV")
            if orphan_count > 0:
                parts.append(f"{orphan_count} orphan KV keys")
            self.app.show_toast(f"Audit: {', '.join(parts)}", "warning")

    # -- Fix Sizes -----------------------------------------------------------

    def _fix_sizes(self):
        if not self._manifest or not self._audit_results:
            self.app.show_toast("Load manifest and run audit first", "warning")
            return

        from ..backend.dlc_ops import fmt_size
        from ..backend.manifest_ops import fix_sizes

        dlc_fixes = fix_sizes(self._manifest.get("dlc_downloads", {}), self._audit_results)
        lang_fixes = fix_sizes(
            self._manifest.get("language_downloads", {}),
            self._lang_audit_results or [],
        )

        total = len(dlc_fixes) + len(lang_fixes)
        if total == 0:
            self._log.log("No sizes to fix")
            return

        for eid, _issue, old, new in dlc_fixes + lang_fixes:
            self._log.log(f"Fixed {eid}: {fmt_size(old)} -> {fmt_size(new)}", "success")

        self._json_editor.delete("1.0", "end")
        self._json_editor.insert("1.0", json.dumps(self._manifest, indent=2, ensure_ascii=False))
        self._populate_dlc_tab(self._manifest)
        self._populate_lang_tab(self._manifest)
        self.app.show_toast(f"Fixed {total} sizes", "success")

    # -- Diff ----------------------------------------------------------------

    def _show_diff(self):
        if not self._manifest or not self._original_manifest:
            return
        self._apply_overview_edits()
        from ..backend.manifest_ops import diff_manifests

        for change in diff_manifests(self._original_manifest, self._manifest):
            self._log.log(f"  {change}")

    def _apply_overview_edits(self):
        for key, entry in self._overview_fields.items():
            val = entry.get().strip()
            if val:
                self._manifest[key] = val

    # -- Save / Upload -------------------------------------------------------

    def _save_local(self):
        if not self._manifest:
            return
        self._apply_overview_edits()

        raw = self._json_editor.get("1.0", "end").strip()
        if raw:
            try:
                self._manifest = json.loads(raw)
            except json.JSONDecodeError as e:
                self._log.log(f"Invalid JSON: {e}", "error")
                return

        from pathlib import Path

        from ..backend.manifest_ops import save_manifest_local

        output = Path(__file__).resolve().parent.parent.parent / "manifest.json"
        save_manifest_local(self._manifest, output)
        self._log.log(f"Saved to {output}", "success")
        self.app.show_toast("Manifest saved locally", "success")

    def _upload(self):
        if not self._manifest:
            return
        self._apply_overview_edits()

        raw = self._json_editor.get("1.0", "end").strip()
        if raw:
            try:
                self._manifest = json.loads(raw)
            except json.JSONDecodeError as e:
                self._log.log(f"Invalid JSON: {e}", "error")
                return

        self._log.log("Uploading manifest to CDN...")
        # Snapshot manifest on GUI thread to avoid thread-unsafe dict access
        import copy

        manifest_snapshot = copy.deepcopy(self._manifest)
        self.app.run_async(
            lambda: self._bg_upload(manifest_snapshot),
            on_done=lambda _: (
                self._log.log("Manifest uploaded!", "success"),
                self.app.show_toast("Manifest uploaded", "success"),
            ),
            on_error=lambda e: self._log.log(f"Upload failed: {e}", "error"),
        )

    def _bg_upload(self, manifest_data: dict):
        import tempfile
        from pathlib import Path

        from ..backend.connection import ConnectionManager

        conn = ConnectionManager(self.app.config_data.to_cdn_config())
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            json.dump(manifest_data, tmp, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp.name)
        try:
            conn.publish_manifest(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    # -- Add/Remove Entries --------------------------------------------------

    def _sync_json_editor(self):
        """Sync the raw JSON editor with the current manifest dict."""
        self._json_editor.delete("1.0", "end")
        self._json_editor.insert(
            "1.0",
            json.dumps(self._manifest, indent=2, ensure_ascii=False),
        )

    def _add_dlc_entry(self):
        if not self._manifest:
            self.app.show_toast("Load manifest first", "warning")
            return
        dialog = _AddEntryDialog(
            self,
            "Add DLC Entry",
            [
                ("DLC ID", "e.g. EP01"),
                ("URL", "https://cdn.hyperabyss.com/dlc/EP01.zip"),
                ("Size (bytes)", "0"),
                ("MD5", ""),
            ],
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        dlc_id = dialog.result[0]
        if not dlc_id:
            return
        downloads = self._manifest.setdefault("dlc_downloads", {})
        try:
            size = int(dialog.result[2] or 0)
        except ValueError:
            self.app.show_toast("Invalid size — must be a number", "warning")
            return
        downloads[dlc_id] = {
            "url": dialog.result[1],
            "size": size,
            "md5": dialog.result[3],
            "filename": f"{dlc_id}.zip",
        }
        self._populate_dlc_tab(self._manifest)
        self._sync_json_editor()
        self._log.log(f"Added DLC entry: {dlc_id}", "success")

    def _remove_dlc_entries(self):
        if not self._manifest:
            return
        selected = [k for k, v in self._dlc_check_vars.items() if v.get()]
        if not selected:
            self.app.show_toast("No DLC entries selected", "warning")
            return
        downloads = self._manifest.get("dlc_downloads", {})
        for dlc_id in selected:
            downloads.pop(dlc_id, None)
        self._populate_dlc_tab(self._manifest)
        self._sync_json_editor()
        self._log.log(f"Removed {len(selected)} DLC entries", "success")

    def _add_lang_entry(self):
        if not self._manifest:
            self.app.show_toast("Load manifest first", "warning")
            return
        dialog = _AddEntryDialog(
            self,
            "Add Language Entry",
            [
                ("Locale", "e.g. de_DE"),
                ("URL", "https://cdn.hyperabyss.com/language/de_DE.zip"),
                ("Size (bytes)", "0"),
                ("MD5", ""),
            ],
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        locale = dialog.result[0]
        if not locale:
            return
        downloads = self._manifest.setdefault("language_downloads", {})
        try:
            size = int(dialog.result[2] or 0)
        except ValueError:
            self.app.show_toast("Invalid size — must be a number", "warning")
            return
        downloads[locale] = {
            "url": dialog.result[1],
            "size": size,
            "md5": dialog.result[3],
            "filename": f"{locale}.zip",
        }
        self._populate_lang_tab(self._manifest)
        self._sync_json_editor()
        self._log.log(f"Added language entry: {locale}", "success")

    def _remove_lang_entries(self):
        if not self._manifest:
            return
        selected = [k for k, v in self._lang_check_vars.items() if v.get()]
        if not selected:
            self.app.show_toast("No language entries selected", "warning")
            return
        downloads = self._manifest.get("language_downloads", {})
        for locale in selected:
            downloads.pop(locale, None)
        self._populate_lang_tab(self._manifest)
        self._sync_json_editor()
        self._log.log(f"Removed {len(selected)} language entries", "success")

    def _add_patch_entry(self):
        if not self._manifest:
            self.app.show_toast("Load manifest first", "warning")
            return
        dialog = _AddEntryDialog(
            self,
            "Add Patch Entry",
            [
                ("From Version", "e.g. 1.120.140.1020"),
                ("To Version", "e.g. 1.121.372.1020"),
                ("URL", "https://cdn.hyperabyss.com/patches/..."),
                ("Size (bytes)", "0"),
            ],
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        from_ver, to_ver = dialog.result[0], dialog.result[1]
        if not from_ver or not to_ver:
            return
        try:
            size = int(dialog.result[3] or 0)
        except ValueError:
            self.app.show_toast("Invalid size — must be a number", "warning")
            return
        patches = self._manifest.setdefault("patches", [])
        patches.append(
            {
                "from": from_ver,
                "to": to_ver,
                "url": dialog.result[2],
                "size": size,
            }
        )
        self._populate_patches_tab(self._manifest)
        self._sync_json_editor()
        self._log.log(f"Added patch entry: {from_ver} -> {to_ver}", "success")

    def _remove_patch_entries(self):
        if not self._manifest:
            return
        selected = sorted(
            [i for i, v in self._patch_check_vars.items() if v.get()],
            reverse=True,
        )
        if not selected:
            self.app.show_toast("No patch entries selected", "warning")
            return
        patches = self._manifest.get("patches", [])
        for idx in selected:
            if 0 <= idx < len(patches):
                patches.pop(idx)
        self._populate_patches_tab(self._manifest)
        self._sync_json_editor()
        self._log.log(f"Removed {len(selected)} patch entries", "success")


class _AddEntryDialog(ctk.CTkToplevel):
    """Generic dialog for adding a manifest entry with labeled fields."""

    def __init__(self, parent, title: str, fields: list[tuple[str, str]]):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"450x{80 + len(fields) * 44}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=theme.COLORS["bg_card"])

        self.result: list[str] | None = None
        self._entries: list[ctk.CTkEntry] = []

        self.grid_columnconfigure(1, weight=1)

        for i, (label, placeholder) in enumerate(fields):
            ctk.CTkLabel(
                self,
                text=f"{label}:",
                font=ctk.CTkFont(size=11, weight="bold"),
            ).grid(row=i, column=0, padx=(15, 6), pady=4, sticky="w")

            entry = ctk.CTkEntry(
                self,
                height=30,
                font=ctk.CTkFont(size=11),
                placeholder_text=placeholder,
            )
            entry.grid(row=i, column=1, padx=(0, 15), pady=4, sticky="ew")
            entry.bind("<Return>", lambda _: self._ok())
            self._entries.append(entry)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(
            row=len(fields),
            column=0,
            columnspan=2,
            padx=15,
            pady=(8, 12),
            sticky="ew",
        )
        ctk.CTkButton(
            btn_frame,
            text="Add",
            width=80,
            height=30,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["accent"],
            hover_color=theme.COLORS["accent_hover"],
            command=self._ok,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=70,
            height=30,
            corner_radius=theme.CORNER_RADIUS_SMALL,
            fg_color=theme.COLORS["bg_card_alt"],
            hover_color=theme.COLORS["card_hover"],
            command=self.destroy,
        ).pack(side="right")

    def _ok(self):
        self.result = [e.get().strip() for e in self._entries]
        self.destroy()
