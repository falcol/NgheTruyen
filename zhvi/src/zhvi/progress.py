"""Progress rendering (thiet ke muc 31).

TTY: mot dong status tren stderr, khong animation rua man hinh; non-TTY: in
dinh ky theo nguong. Ton trong NO_COLOR. stdout danh rieng cho JSON.
"""
from __future__ import annotations

import os
import sys
import time


class Progress:
    def __init__(self, total: int, label: str = "block") -> None:
        self.total = total
        self.label = label
        self.start = time.monotonic()
        self.tty = sys.stderr.isatty() and not os.environ.get("NO_PROGRESS")
        self._last_emit = 0.0

    def update(self, done: int, committed: int, warnings: int) -> None:
        now = time.monotonic()
        if not self.tty:
            if now - self._last_emit < 10.0 or done == self.total:
                self._last_emit = now
                self._emit(done, committed, warnings, newline=True)
            return
        self._emit(done, committed, warnings, newline=False)

    def _emit(self, done: int, committed: int, warnings: int, *, newline: bool) -> None:
        elapsed = time.monotonic() - self.start
        rate = done / elapsed if elapsed > 0 else 0.0
        eta = (self.total - done) / rate if rate > 0 else 0.0
        line = (
            f"{self.label} {done}/{self.total} | committed {committed} | "
            f"{rate:.0f} blk/s | ETA {eta:.0f}s | warn {warnings}"
        )
        if self.tty:
            sys.stderr.write("\r" + line.ljust(79))
        else:
            sys.stderr.write(line + "\n")
        sys.stderr.flush()

    def finish(self) -> None:
        if self.tty:
            sys.stderr.write("\n")
            sys.stderr.flush()
