"""Cross-file dict-key dups: scan, optionally strip.

Stream line-by-line (no read_text of whole files). RAM is one owner map
(unique keys -> keeper filename), not values / locations.

Keeper = highest engine trust; same trust -> last-loaded file (last-write
wins, matching engine._upsert pri >=). Names 1-char is not a keeper
(engine skips them) unless no other file has the key.

Usage:
  python crawler/vietphrase/check_dup_keys.py
  python crawler/vietphrase/check_dup_keys.py --apply
"""
from __future__ import annotations

import argparse
import os
import tempfile
from collections import defaultdict
from pathlib import Path

DICT_DIR = Path(__file__).resolve().parent / "dicts"

# High trust first. Within the same trust, later-loaded file first
# (engine last-write wins when pri is equal).
KEEP_ORDER = (
    "Custom.txt",  # 100
    "ContextPatterns.txt",  # 25, after QualityOverrides
    "QualityOverrides.txt",  # 25
    "Names_2.txt",  # 20, after Names
    "Names.txt",  # 20
    "LuatNhan.txt",  # 15
    "VietPhrase_4.txt",  # 10, last of VP_*
    "VietPhrase_3.txt",
    "VietPhrase_2.txt",
    "VietPhrase_1.txt",
    "ChinesePhienAmWords_2.txt",  # 5, after base
    "ChinesePhienAmWords.txt",  # 5
)

BOM = b"\xef\xbb\xbf"


def _is_keeper_file(name: str, key: str) -> bool:
    # engine: pri==20 (Names*) skips 1-char keys
    if name.startswith("Names") and len(key) == 1:
        return False
    return True


def _first_meaning(raw: str) -> str:
    # Match zhvi loader.parse_dict_line: empty first meaning is not loaded.
    cut = raw.find("//")
    if cut != -1:
        raw = raw[:cut]
    for sep in ("/", "|"):
        i = raw.find(sep)
        if i != -1:
            raw = raw[:i]
            break
    return raw.rstrip("*").strip()


def parse_raw_key(line: str) -> str | None:
    s = line.strip()
    if not s or s[0] in "#;" or s.startswith("//"):
        return None
    eq = s.find("=")
    if eq <= 0:
        return None
    key = s[:eq].strip()
    if not key or "{0}" in key:
        return None
    return key


def parse_key(line: str) -> str | None:
    """Loadable key only (non-empty first meaning). Dead `的=/…` is not a keeper."""
    key = parse_raw_key(line)
    if key is None:
        return None
    s = line.strip()
    eq = s.find("=")
    if not _first_meaning(s[eq + 1 :]):
        return None
    return key


def iter_lines(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for line in f:
            yield line


def has_bom(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(3) == BOM


def build_owner(dict_dir: Path) -> tuple[dict[str, str], dict[str, int]]:
    """owner[key] = keeper filename. intra[file] = extra copies inside file."""
    owner: dict[str, str] = {}
    weak: dict[str, str] = {}
    intra: dict[str, int] = defaultdict(int)

    for name in KEEP_ORDER:
        path = dict_dir / name
        if not path.is_file():
            continue
        seen_here: set[str] = set()
        for line in iter_lines(path):
            key = parse_key(line)
            if key is None:
                continue
            if key in seen_here:
                intra[name] += 1
                continue
            seen_here.add(key)
            if key in owner:
                continue
            if _is_keeper_file(name, key):
                owner[key] = name
                weak.pop(key, None)
            elif key not in weak:
                weak[key] = name
        del seen_here

    for key, name in weak.items():
        owner.setdefault(key, name)
    return owner, dict(intra)


def count_stats(
    dict_dir: Path, owner: dict[str, str], intra: dict[str, int]
) -> dict:
    drops: dict[str, int] = defaultdict(int)
    kept: dict[str, int] = defaultdict(int)
    by_keeper: dict[tuple[str, str], int] = defaultdict(int)
    for name in KEEP_ORDER:
        path = dict_dir / name
        if not path.is_file():
            continue
        seen_here: set[str] = set()
        for line in iter_lines(path):
            key = parse_key(line)
            if key is None:
                continue
            if key in seen_here:
                continue
            seen_here.add(key)
            keeper = owner[key]
            if keeper == name:
                kept[name] += 1
            else:
                drops[name] += 1
                by_keeper[(keeper, name)] += 1
        del seen_here
    return {
        "drops": dict(drops),
        "intra": intra,
        "kept": dict(kept),
        "by_keeper": dict(by_keeper),
        "unique": len(owner),
    }


def rewrite(path: Path, name: str, owner: dict[str, str]) -> tuple[int, int, int]:
    """Keep lines whose key is owned by this file (first hit). Return kept, dropped, intra."""
    kept = dropped = intra = 0
    emitted: set[str] = set()
    bom = has_bom(path)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as out:
            if bom:
                out.write("\ufeff")
            for line in iter_lines(path):
                key = parse_raw_key(line)
                if key is None:
                    out.write(line if line.endswith("\n") else line + "\n")
                    continue
                if owner.get(key) != name:
                    dropped += 1
                    continue
                if key in emitted:
                    intra += 1
                    continue
                emitted.add(key)
                out.write(line if line.endswith("\n") else line + "\n")
                kept += 1
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return kept, dropped, intra


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dict-dir", type=Path, default=DICT_DIR)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite files: drop keys owned by a higher-trust file",
    )
    args = parser.parse_args()

    print(f"scan {args.dict_dir}")
    owner, intra = build_owner(args.dict_dir)
    st = count_stats(args.dict_dir, owner, intra)
    print(f"unique keys: {st['unique']:,}")
    print("per file (kept / would-drop / intra):")
    for name in KEEP_ORDER:
        k = st["kept"].get(name, 0)
        d = st["drops"].get(name, 0)
        i = st["intra"].get(name, 0)
        if k or d or i:
            print(f"  {name:28} keep={k:7,}  drop={d:7,}  intra={i:5,}")
    print("drop by keeper -> from:")
    rows = sorted(st["by_keeper"].items(), key=lambda x: -x[1])
    for (keeper, src), n in rows[:25]:
        print(f"  {n:7,}  keep {keeper}  drop {src}")
    total_drop = sum(st["drops"].values())
    total_intra = sum(st["intra"].values())
    print(f"total drop: {total_drop:,}  intra: {total_intra:,}")

    if not args.apply:
        print("dry-run (pass --apply to rewrite)")
        return

    print("apply:")
    for name in KEEP_ORDER:
        path = args.dict_dir / name
        if not path.is_file():
            continue
        if st["drops"].get(name, 0) == 0 and st["intra"].get(name, 0) == 0:
            continue
        kept, dropped, intra = rewrite(path, name, owner)
        print(f"  {name:28} wrote keep={kept:7,}  drop={dropped:7,}  intra={intra:5,}")
    print("done")


if __name__ == "__main__":
    main()
