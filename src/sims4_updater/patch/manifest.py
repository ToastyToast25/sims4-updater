"""
Manifest parsing and validation.

The manifest is a JSON file hosted at a known URL that describes
available patches and their download locations. This decouples the
updater from any specific hosting — patches can live anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.exceptions import ManifestError


@dataclass
class FileEntry:
    """A single downloadable file (patch archive or crack)."""

    url: str
    size: int
    md5: str
    filename: str = ""  # derived from URL if not specified

    def __post_init__(self):
        if not self.filename:
            self.filename = self.url.rsplit("/", 1)[-1].split("?")[0]


@dataclass
class PatchEntry:
    """A single version-to-version patch with downloadable files."""

    version_from: str
    version_to: str
    files: list[FileEntry] = field(default_factory=list)
    crack: FileEntry | None = None

    @property
    def total_size(self) -> int:
        total = sum(f.size for f in self.files)
        if self.crack:
            total += self.crack.size
        return total


@dataclass
class PendingDLC:
    """A DLC announced in the manifest but not yet patchable."""

    id: str
    name: str
    status: str = "pending"


@dataclass
class ManifestDLC:
    """A DLC entry from the manifest for catalog updates."""

    id: str
    code: str = ""
    code2: str = ""
    pack_type: str = "other"
    names: dict[str, str] = field(default_factory=dict)
    description: str = ""
    steam_app_id: int | None = None


@dataclass
class DLCDownloadEntry:
    """A downloadable DLC content archive."""

    dlc_id: str  # e.g. "EP01"
    url: str  # direct download URL
    size: int = 0  # archive size in bytes
    md5: str = ""  # verification hash
    filename: str = ""  # derived from URL if not specified

    def __post_init__(self):
        if not self.filename:
            self.filename = self.url.rsplit("/", 1)[-1].split("?")[0]

    def to_file_entry(self) -> FileEntry:
        """Convert to FileEntry for use with Downloader."""
        return FileEntry(
            url=self.url,
            size=self.size,
            md5=self.md5,
            filename=self.filename,
        )


@dataclass
class LanguageDownloadEntry:
    """A downloadable language pack (Strings file) archive."""

    locale_code: str  # e.g. "da_DK"
    url: str  # direct download URL
    size: int = 0  # archive size in bytes
    md5: str = ""  # verification hash
    filename: str = ""  # derived from URL if not specified

    def __post_init__(self):
        if not self.filename:
            self.filename = self.url.rsplit("/", 1)[-1].split("?")[0]

    def to_file_entry(self) -> FileEntry:
        """Convert to FileEntry for use with Downloader."""
        return FileEntry(
            url=self.url,
            size=self.size,
            md5=self.md5,
            filename=self.filename,
        )


@dataclass
class ArchivedVersion:
    """An archived version available for DLC/language download."""

    version: str
    date: str = ""
    manifest_url: str = ""
    dlc_count: int = 0
    language_count: int = 0


@dataclass
class GreenLumaEntry:
    """A GreenLuma depot entry with decryption key and manifest reference."""

    depot_id: str
    dlc_id: str = ""
    key: str = ""  # 64-char hex decryption key
    manifest_id: str = ""
    manifest_url: str = ""  # CDN URL for the binary .manifest file


@dataclass
class Manifest:
    """Parsed manifest describing all available patches."""

    latest: str
    patches: list[PatchEntry] = field(default_factory=list)
    fingerprints: dict[str, dict[str, str]] = field(default_factory=dict)
    fingerprints_url: str = ""
    report_url: str = ""
    manifest_url: str = ""
    game_latest: str = ""
    game_latest_date: str = ""
    new_dlcs: list[PendingDLC] = field(default_factory=list)
    dlc_catalog: list[ManifestDLC] = field(default_factory=list)
    dlc_downloads: dict[str, DLCDownloadEntry] = field(default_factory=dict)
    language_downloads: dict[str, LanguageDownloadEntry] = field(default_factory=dict)
    archived_versions: dict[str, ArchivedVersion] = field(default_factory=dict)
    entitlements_url: str = ""
    self_update_url: str = ""
    contribute_url: str = ""
    greenluma: dict[str, GreenLumaEntry] = field(default_factory=dict)

    @property
    def patch_pending(self) -> bool:
        """True if the actual game version is ahead of the latest patchable."""
        return bool(self.game_latest and self.game_latest != self.latest)

    def get_patch(self, version_from: str, version_to: str) -> PatchEntry | None:
        for p in self.patches:
            if p.version_from == version_from and p.version_to == version_to:
                return p
        return None

    @property
    def all_versions(self) -> set[str]:
        versions = {self.latest}
        for p in self.patches:
            versions.add(p.version_from)
            versions.add(p.version_to)
        return versions


def parse_manifest(data: dict, source_url: str = "") -> Manifest:
    """Parse a manifest dict into a Manifest object.

    Raises ManifestError on invalid data.
    """
    if not isinstance(data, dict):
        raise ManifestError("Manifest must be a JSON object.")

    latest = data.get("latest", "")
    if not isinstance(latest, str):
        raise ManifestError("Manifest 'latest' must be a string.")

    patches_raw = data.get("patches", [])
    if not isinstance(patches_raw, list):
        raise ManifestError("Manifest 'patches' must be a list.")

    patches = []
    for i, entry in enumerate(patches_raw):
        try:
            patches.append(_parse_patch_entry(entry))
        except (KeyError, TypeError, ValueError) as e:
            raise ManifestError(f"Invalid patch entry at index {i}: {e}") from e

    # Parse optional fingerprints: {version: {sentinel: md5}}
    fingerprints = {}
    raw_fp = data.get("fingerprints", {})
    if isinstance(raw_fp, dict):
        for version, hashes in raw_fp.items():
            if isinstance(hashes, dict):
                fingerprints[version] = {str(k): str(v) for k, v in hashes.items()}

    # Parse optional new_dlcs list
    new_dlcs = []
    for dlc_raw in data.get("new_dlcs", []):
        if isinstance(dlc_raw, dict) and "id" in dlc_raw:
            new_dlcs.append(
                PendingDLC(
                    id=dlc_raw["id"],
                    name=dlc_raw.get("name", dlc_raw["id"]),
                    status=dlc_raw.get("status", "pending"),
                )
            )

    # Parse optional dlc_catalog list (remote catalog updates)
    dlc_catalog = []
    for dlc_raw in data.get("dlc_catalog", []):
        if isinstance(dlc_raw, dict) and "id" in dlc_raw:
            dlc_catalog.append(
                ManifestDLC(
                    id=dlc_raw["id"],
                    code=dlc_raw.get("code", ""),
                    code2=dlc_raw.get("code2", ""),
                    pack_type=dlc_raw.get("type", "other"),
                    names=dlc_raw.get("names", {}),
                    description=dlc_raw.get("description", ""),
                    steam_app_id=dlc_raw.get("steam_app_id"),
                )
            )

    # Parse optional dlc_downloads: {dlc_id: {url, size, md5}}
    dlc_downloads = {}
    raw_dl = data.get("dlc_downloads", {})
    if isinstance(raw_dl, dict):
        for dlc_id, dl_data in raw_dl.items():
            if isinstance(dl_data, dict) and "url" in dl_data:
                dlc_downloads[dlc_id] = DLCDownloadEntry(
                    dlc_id=dlc_id,
                    url=dl_data["url"],
                    size=int(dl_data.get("size", 0)),
                    md5=dl_data.get("md5", ""),
                    filename=dl_data.get("filename", ""),
                )

    # Parse optional language_downloads: {locale_code: {url, size, md5}}
    language_downloads = {}
    raw_lang = data.get("language_downloads", {})
    if isinstance(raw_lang, dict):
        for locale_code, lang_data in raw_lang.items():
            if isinstance(lang_data, dict) and "url" in lang_data:
                language_downloads[locale_code] = LanguageDownloadEntry(
                    locale_code=locale_code,
                    url=lang_data["url"],
                    size=int(lang_data.get("size", 0)),
                    md5=lang_data.get("md5", ""),
                    filename=lang_data.get("filename", ""),
                )

    # Parse optional versions index: {version_str: {date, manifest_url, ...}}
    archived_versions: dict[str, ArchivedVersion] = {}
    raw_versions = data.get("versions", {})
    if isinstance(raw_versions, dict):
        for ver_str, ver_data in raw_versions.items():
            if isinstance(ver_data, dict) and "manifest_url" in ver_data:
                archived_versions[ver_str] = ArchivedVersion(
                    version=ver_str,
                    date=ver_data.get("date", ""),
                    manifest_url=ver_data["manifest_url"],
                    dlc_count=int(ver_data.get("dlc_count", 0)),
                    language_count=int(ver_data.get("language_count", 0)),
                )

    # Parse optional greenluma: {depot_id: {dlc_id, key, manifest_id, manifest_url}}
    greenluma: dict[str, GreenLumaEntry] = {}
    raw_gl = data.get("greenluma", {})
    if isinstance(raw_gl, dict):
        for depot_id, gl_data in raw_gl.items():
            if isinstance(gl_data, dict) and "key" in gl_data:
                greenluma[depot_id] = GreenLumaEntry(
                    depot_id=depot_id,
                    dlc_id=gl_data.get("dlc_id", ""),
                    key=gl_data.get("key", ""),
                    manifest_id=gl_data.get("manifest_id", ""),
                    manifest_url=gl_data.get("manifest_url", ""),
                )

    return Manifest(
        latest=latest,
        patches=patches,
        fingerprints=fingerprints,
        fingerprints_url=data.get("fingerprints_url", ""),
        report_url=data.get("report_url", ""),
        manifest_url=source_url,
        game_latest=data.get("game_latest", ""),
        game_latest_date=data.get("game_latest_date", ""),
        new_dlcs=new_dlcs,
        dlc_catalog=dlc_catalog,
        dlc_downloads=dlc_downloads,
        language_downloads=language_downloads,
        archived_versions=archived_versions,
        entitlements_url=data.get("entitlements_url", ""),
        self_update_url=data.get("self_update_url", ""),
        contribute_url=data.get("contribute_url", ""),
        greenluma=greenluma,
    )


def _parse_patch_entry(entry: dict) -> PatchEntry:
    """Parse a single patch entry from manifest data."""
    version_from = entry["from"]
    version_to = entry["to"]

    files = []
    for f in entry.get("files", []):
        files.append(
            FileEntry(
                url=f["url"],
                size=int(f.get("size", 0)),
                md5=f.get("md5", ""),
                filename=f.get("filename", ""),
            )
        )

    crack = None
    crack_data = entry.get("crack")
    if crack_data and isinstance(crack_data, dict):
        crack = FileEntry(
            url=crack_data["url"],
            size=int(crack_data.get("size", 0)),
            md5=crack_data.get("md5", ""),
            filename=crack_data.get("filename", ""),
        )

    return PatchEntry(
        version_from=version_from,
        version_to=version_to,
        files=files,
        crack=crack,
    )
