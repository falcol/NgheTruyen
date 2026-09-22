"""Load a local dict directory or the vietphrase.app manifest."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

from vp.engine import Engine, parse_dict_lines, parse_quality_overrides
from vp.textutil import load_trad_simp

MANIFEST_PAGE = "https://vietphrase.app/"
LOCAL_STACK = (
    ("ChinesePhienAmWords.txt", "phienam", 5),
    ("ChinesePhienAmWords_2.txt", "phienam", 5),
    ("LuatNhan.txt", "rules", 15),
    ("Names.txt", "names", 20),
    ("Names_2.txt", "names", 20),
    ("VietPhrase_1.txt", "vietphrase", 10),
    ("VietPhrase_2.txt", "vietphrase", 10),
    ("VietPhrase_3.txt", "vietphrase", 10),
    ("VietPhrase_4.txt", "vietphrase", 10),
    ("QualityOverrides.txt", "quality-overrides", 25),
    ("Custom.txt", "custom", 999),
)


def find_local_dict_dir(explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_dir():
            raise FileNotFoundError(f"Không thấy thư mục từ điển: {path}")
        return path
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        cand = parent / "crawler" / "vietphrase" / "dicts"
        if cand.is_dir():
            return cand
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "crawler" / "vietphrase" / "dicts"
        if cand.is_dir():
            return cand
    raise FileNotFoundError("Không thấy crawler/vietphrase/dicts. Truyền --dict-dir.")


def read_custom(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    text = path.read_text(encoding="utf-8-sig")
    for line in text.split("\n"):
        line = line.strip()
        if not line or line[0] == "#" or line.startswith("//"):
            continue
        eq = line.find("=")
        if eq < 1:
            continue
        zh = line[:eq].strip()
        vi = line[eq + 1 :].strip()
        if zh and vi:
            rows.append((zh, vi))
    return rows


_REVIEW_CATEGORIES = frozenset(
    {"character", "title_alias", "sect_org", "location", "item", "technique", "other"}
)


def _review_row_priority(fields: list[str]) -> int | None:
    """Novel-scan review lines are zh=vi, category, count, score."""
    if len(fields) < 4 or fields[1].strip() not in _REVIEW_CATEGORIES:
        return None
    try:
        float(fields[3].strip())
    except ValueError:
        return None
    return 30 if fields[1].strip() == "character" else 25


def read_overlay(path: Path) -> list[tuple[str, str, int]]:
    rows: list[tuple[str, str, int]] = []
    text = path.read_text(encoding="utf-8-sig")
    for line in text.split("\n"):
        line = line.strip()
        if not line or line[0] == "#" or line.startswith("//"):
            continue
        eq = line.find("=")
        if eq < 1:
            continue
        zh = line[:eq].strip()
        rest = line[eq + 1 :].strip()
        fields = rest.split("\t")
        review_pri = _review_row_priority(fields)
        if review_pri is not None:
            vi = fields[0].strip()
            pri = review_pri
        else:
            kind = "Book Names"
            tab = rest.rfind("\t")
            vi = rest
            if tab != -1:
                label = rest[tab + 1 :].strip().lower()
                vi = rest[:tab].strip()
                if label in ("vietphrase", "book vietphrase", "phrase"):
                    kind = "Book VietPhrase"
            pri = 30 if kind == "Book Names" else 25
        if zh and vi:
            rows.append((zh, vi, pri))
    return rows


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def records_from_files(
    files: list[tuple[Path, str, int]],
    *,
    phienam_as_base: bool = True,
) -> list[tuple[str, str, int, str]]:
    """Phien-am files can also be inserted at priority 0.

    That fills the Han-Viet map when there is no dict-default.json. The
    priority-5 copy still wins inside the phrase trie.
    """
    records: list[tuple[str, str, int, str]] = []
    for path, kind, priority in files:
        if not path.is_file():
            continue
        source = path.name
        text = _read(path)
        if kind == "quality-overrides":
            records.extend(parse_quality_overrides(text))
            continue
        if kind == "custom":
            records.extend(parse_dict_lines(text, 999, source))
            continue
        parsed = parse_dict_lines(text, priority, source)
        if kind == "phienam" and phienam_as_base:
            records.extend((key, value, 0, source) for key, value, _pri, _src in parsed)
        records.extend(parsed)
    return records


def load_local_engine(
    dict_dir: Path,
    *,
    simplified: bool,
    luat_nhan: int,
    custom: list[tuple[str, str]] | None = None,
) -> Engine:
    files = [(dict_dir / name, kind, pri) for name, kind, pri in LOCAL_STACK]
    present = [item for item in files if item[0].is_file()]
    if not present:
        raise FileNotFoundError(f"Thư mục không có từ điển VietPhrase: {dict_dir}")
    records = records_from_files(present)
    trad_path = dict_dir / "trad-simp.txt"
    trad = load_trad_simp(_read(trad_path)) if trad_path.is_file() else {}
    return Engine.build(
        records,
        trad,
        simplified=simplified,
        luat_nhan=luat_nhan,
        custom=custom,
    )


def _download(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "vp-cli"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _cache_file(cache_dir: Path, name: str, url: str, *, refresh: bool, sha256: str = "", size: int = 0) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / name
    if dest.is_file() and not refresh:
        data = dest.read_bytes()
    else:
        data = _download(url)
        dest.write_bytes(data)
    if size and len(data) != size:
        raise RuntimeError(f"{name}: sai kích thước ({len(data)}/{size})")
    if sha256:
        digest = hashlib.sha256(data).hexdigest()
        if digest != sha256:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"{name}: SHA-256 không khớp")
    return dest


def load_manifest_engine(
    *,
    cache_dir: Path,
    simplified: bool,
    luat_nhan: int,
    custom: list[tuple[str, str]] | None = None,
    refresh: bool = False,
    page: str = MANIFEST_PAGE,
) -> Engine:
    page = page if page.endswith("/") else page + "/"
    manifest_url = page + "dicts/manifest.json"
    manifest = json.loads(_download(manifest_url).decode("utf-8"))
    revision = str(manifest.get("revision") or "unknown")
    root = cache_dir / revision
    files: list[tuple[Path, str, int]] = []
    for item in manifest.get("files") or []:
        path_name = str(item["path"])
        kind = str(item.get("kind") or "")
        priority = int(item.get("priority") or 0)
        dest = _cache_file(
            root,
            path_name,
            page + "dicts/" + path_name,
            refresh=refresh,
            sha256=str(item.get("sha256") or ""),
            size=int(item.get("size") or 0),
        )
        files.append((dest, kind, priority))
    base_path = _cache_file(root, "dict-default.json", page + "dict-default.json", refresh=refresh)
    base = json.loads(base_path.read_text(encoding="utf-8"))
    phienam = base.get("phienam") or {}
    records: list[tuple[str, str, int, str]] = [
        (key, str(value), 0, "dict-default.json") for key, value in phienam.items() if key and value
    ]
    records.extend(records_from_files(files, phienam_as_base=False))
    trad_path = _cache_file(root, "trad-simp.txt", page + "dicts/trad-simp.txt", refresh=refresh)
    trad = load_trad_simp(trad_path.read_text(encoding="utf-8-sig"))
    return Engine.build(
        records,
        trad,
        simplified=simplified,
        luat_nhan=luat_nhan,
        custom=custom,
    )
