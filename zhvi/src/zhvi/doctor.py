"""zhvi doctor (thiet ke muc 35) — ban M1 toi thieu.

Kiem tra: thu muc tu dien + du file nen, doc duoc, SQLite write duoc, disk con
trong, smoke test convert mot cau.
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

from .config import BASE_DICT_FILES, Config


def run_doctor(console, cfg: Config) -> bool:
    ok = True

    def check(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        mark = "[ok]  " if passed else "[FAIL]"
        console.print(f"{mark} {name}" + (f" — {detail}" if detail else ""))
        ok = ok and passed

    dict_dir = Path(cfg.dict_dir)
    missing: list[str] = []
    if not dict_dir.is_absolute():
        for base in (Path.cwd(), Path(__file__).resolve().parents[3]):
            if (base / cfg.dict_dir).is_dir():
                dict_dir = base / cfg.dict_dir
                break
    check("dict dir", dict_dir.is_dir(), str(dict_dir))
    if dict_dir.is_dir():
        missing = [n for n in BASE_DICT_FILES if not (dict_dir / n).is_file()]
        check("dict files", not missing, f"thieu: {missing}" if missing else f"{len(BASE_DICT_FILES)} file")

    # SQLite + disk
    try:
        with tempfile.TemporaryDirectory() as td:
            db = sqlite3.connect(Path(td) / "t.sqlite3")
            db.execute("CREATE TABLE t(x)")
            db.commit()
            db.close()
        free_gb = shutil.disk_usage(Path.cwd()).free / 1e9
        check("sqlite writable", True)
        check("disk > 1GB", free_gb > 1.0, f"{free_gb:.1f} GB free")
    except Exception as e:  # noqa: BLE001
        check("sqlite writable", False, str(e))

    # glossary toan cuc (informational — thieu khong phai loi)
    gg_raw = cfg.global_glossary.strip()
    gg = Path(gg_raw).expanduser() if gg_raw else None
    if gg is not None and gg.is_file():
        n = sum(1 for ln in gg.read_text(encoding="utf-8-sig").splitlines() if ln.strip() and not ln.startswith("#"))
        check("global glossary", True, f"{gg} ({n} term)")
    else:
        check("global glossary", True, f"khong co ({gg_raw or '—'}) — chi dung book manual")

    # smoke test convert
    if dict_dir.is_dir() and not missing:
        try:
            from .vietphrase.lattice import vp_plan
            from .vietphrase.loader import load_dictionary

            dic = load_dictionary(dict_dir, global_glossary=gg if gg and gg.is_file() else None)
            draft = vp_plan(dic, "凌天")
            check("smoke convert", "Lăng Thiên" in draft.text, f"'凌天' -> '{draft.text}'")
        except Exception as e:  # noqa: BLE001
            check("smoke convert", False, str(e))
    return ok
