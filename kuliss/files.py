"""Safe file writes, shared by every command. Stdlib only."""

import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path


def write_atomic(path: Path, write: Callable[[Path], None]) -> None:
    """Write `path` through `write(temp file)`, then swap it in, so a crash never leaves a
    half-written file. An existing file keeps its permissions; a failed write leaves no
    temp file behind."""
    tmp = path.with_name(path.name + ".partial")
    try:
        write(tmp)
        if path.exists():
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def backup(path: Path) -> Path:
    """Copy `path` to `<name>.<YYYYmmdd-HHMMSS>.bak` next to it. Returns the copy."""
    copy = path.with_name(f"{path.name}.{time.strftime('%Y%m%d-%H%M%S')}.bak")
    shutil.copy2(path, copy)
    return copy
