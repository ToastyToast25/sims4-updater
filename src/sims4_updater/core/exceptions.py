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
