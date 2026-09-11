"""
Filename: locking.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Operating system lock that limits each data directory to one application process.
"""

import sys
from pathlib import Path
from typing import BinaryIO


class ProcessLock:
    """Hold an exclusive OS lock until close() or process exit, including a crash."""
    def __init__(self, directory: Path):
        """Acquire the data directory lock without waiting; raise RuntimeError if it is held."""
        directory.mkdir(parents=True, exist_ok=True)
        self.stream: BinaryIO = (directory / "process.lock").open("a+b")
        self.stream.write(b"0")
        self.stream.flush()
        self.stream.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            raise RuntimeError("Another Addarr process is using this data directory") from exc

    def close(self) -> None:
        """Release the lock and close its file handle once the application has stopped."""
        if sys.platform == "win32":
            import msvcrt

            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.stream.close()
