"""Project layout (thiet ke muc 5) va project lock (muc 29)."""
from __future__ import annotations

import fcntl
import os
import tomllib
import uuid
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
    def revisions_dir(self) -> Path:
        return self.state_dir / "revisions"

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

    @property
    def book_id(self) -> str:
        """ID on dinh cua truyen (data-model: tao 1 lan khi init; copy project
        giu ID — khong tinh la truyen doc lap)."""
        data = tomllib.loads((self.root / "zhvi.toml").read_text(encoding="utf-8"))
        book_id = data.get("book_id")
        if not book_id:
            raise ProjectError(f"{self.root}/zhvi.toml thieu book_id — chay zhvi init")
        return str(book_id)

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
    toml_text = toml_path.read_text(encoding="utf-8")
    if "book_id" not in tomllib.loads(toml_text):
        lines = toml_text.splitlines(keepends=True)
        # chen truoc section dau tien — book_id phai la key top-level
        for idx, line in enumerate(lines):
            if line.strip().startswith("["):
                lines.insert(idx, f'# stable book identity (data-model: tao 1 lan, khong doi)\nbook_id = "{uuid.uuid4().hex}"\n')
                break
        else:
            lines.append(f'book_id = "{uuid.uuid4().hex}"\n')
        toml_path.write_text("".join(lines), encoding="utf-8")
    if not project.manual_glossary.exists():
        # Carve-out AD-5: tao-if-missing header bootstrap lan init — khong phai
        # writer runtime (fsutil guard khong ap dung day); file ton tai la
        # cua nguoi dung, may khong bao ghi lai.
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
