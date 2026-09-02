"""Project layout (thiet ke muc 5) va project lock (muc 29)."""
from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .config import PROJECT_TOML_TEMPLATE, Config, resolve_config

STATE_DIRNAME = ".zhvi"


class ProjectError(RuntimeError):
    pass


@dataclass
class Project:
    root: Path  # book-project/ (contains zhvi.toml and .zhvi/)

    # ---- derived paths (muc 5) ----
    @property
    def state_dir(self) -> Path:
        return self.root / STATE_DIRNAME

    @property
    def db_path(self) -> Path:
        return self.state_dir / "state.sqlite3"

    @property
    def sources_dir(self) -> Path:
        return self.state_dir / "sources"

    @property
    def dictionaries_dir(self) -> Path:
        return self.state_dir / "dictionaries"

    @property
    def runs_dir(self) -> Path:
        return self.state_dir / "runs"

    @property
    def logs_dir(self) -> Path:
        return self.state_dir / "logs"

    @property
    def cache_dir(self) -> Path:
        return self.state_dir / "cache"

    @property
    def locks_dir(self) -> Path:
        return self.state_dir / "locks"

    @property
    def dist_dir(self) -> Path:
        return self.root / "dist"

    @property
    def manual_glossary(self) -> Path:
        return self.root / "glossary.manual.tsv"

    def config(self, dict_dir: str | None = None) -> Config:
        return resolve_config(self.root, dict_dir=dict_dir)


def workspace_for(source_file: Path) -> Path:
    """Auto workspace cạnh input: truyen.txt -> truyen.zhvi/ (muc 3.1)."""
    return source_file.with_name(source_file.stem + STATE_DIRNAME)


def create_project(root: Path) -> Project:
    """Tao layout project moi; idempotent voi project da ton tai."""
    project = Project(root)
    if project.state_dir.exists() and not project.db_path.parent.exists():
        raise ProjectError(f"{project.state_dir} ton tai nhung khong phai zhvi project")
    for d in (
        project.state_dir,
        project.sources_dir,
        project.dictionaries_dir,
        project.runs_dir,
        project.logs_dir,
        project.cache_dir,
        project.locks_dir,
        project.dist_dir,
    ):
        d.mkdir(parents=True, exist_ok=True)
    toml_path = root / "zhvi.toml"
    if not toml_path.exists():
        toml_path.write_text(PROJECT_TOML_TEMPLATE, encoding="utf-8")
    if not project.manual_glossary.exists():
        project.manual_glossary.write_text(
            "# source<TAB>target — term nguoi dung khoa cho truyen (book manual)\n",
            encoding="utf-8",
        )
    return project


def open_project(root: Path) -> Project:
    project = Project(root)
    if not project.state_dir.is_dir():
        raise ProjectError(f"Khong phai zhvi project (thieu {STATE_DIRNAME}/): {root}")
    return project


@contextmanager
def project_lock(project: Project, name: str = "translate"):
    """Ngan hai process cung ghi (muc 29). Exit code 5 khi conflict."""
    project.locks_dir.mkdir(parents=True, exist_ok=True)
    path = project.locks_dir / f"{name}.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ProjectError(
                f"Một process khác đang giữ lock project: {path}"
            ) from None
        os.write(fd, f"{os.getpid()}\n".encode())
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
