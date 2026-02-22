"""Atomic file write helper — prevents vault corruption on crash."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(file_path: Path, data: bytes) -> None:
    """Write data atomically using write-to-temp + rename.

    The file at file_path is either the old contents or the new contents,
    never a partial write.
    """
    dir_path = file_path.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
    try:
        os.write(fd, data)
        os.fsync(fd)
        os.close(fd)
        os.rename(tmp_path, str(file_path))
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
