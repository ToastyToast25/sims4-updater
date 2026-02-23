class UpdaterError(Exception):
    pass


class ExitingError(UpdaterError):
    pass


class WritePermissionError(UpdaterError):
    pass


class NotEnoughSpaceError(UpdaterError):
    pass


class FileMissingError(UpdaterError):
    pass


class VersionDetectionError(UpdaterError):
    pass


class ManifestError(UpdaterError):
    pass


class DownloadError(UpdaterError):
    pass


class IntegrityError(UpdaterError):
    pass


class NoUpdatePathError(UpdaterError):
    pass


class NoCrackConfigError(UpdaterError):
    pass


class XdeltaError(UpdaterError):
    pass


class AVButtinInError(UpdaterError):
    pass


class BannedError(UpdaterError):
    """Raised when the CDN returns 403 indicating the user is banned."""

    def __init__(self, reason: str = "", ban_type: str = "", expires_at: str = ""):
        self.reason = reason
        self.ban_type = ban_type
        self.expires_at = expires_at
        parts = ["Your access to this CDN has been suspended."]
        if reason:
            parts.append(f"Reason: {reason}")
        if expires_at:
            parts.append(f"Expires: {expires_at}")
        super().__init__("\n".join(parts))


class AccessRequiredError(UpdaterError):
    """Raised when a private CDN requires access approval."""

    def __init__(self, cdn_name: str = "", request_url: str = ""):
        self.cdn_name = cdn_name or "This CDN"
        self.request_url = request_url
        super().__init__(
            f"Access to {self.cdn_name} requires approval. "
            "Request access from the CDN owner."
        )
