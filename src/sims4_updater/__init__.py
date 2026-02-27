VERSION = "2.6.1"

# Ensure the sibling patcher package is importable (dev & PyInstaller)
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_patcher_root = _Path(__file__).resolve().parents[3] / "patcher"
if (
    _patcher_root.is_dir()
    and (_patcher_root / "patcher" / "__init__.py").is_file()
    and str(_patcher_root) not in _sys.path
):
    _sys.path.insert(0, str(_patcher_root))

del _sys, _Path, _patcher_root

import patcher as _patcher  # noqa: E402

_patcher.check_version("1.2.0")
del _patcher
