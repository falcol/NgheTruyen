"""Merge keys present in VietPhrase-master but missing from local dicts.

Pairs (master -> dict target(s)):
  LuatNhan.txt      -> dicts/LuatNhan.txt        (append missing)
  luatnhan.txt      -> dicts/LuatNhan.txt        (append missing)
  Names.txt         -> dicts/Names.txt + Names_2.txt (append missing to Names_2.txt)
  names.txt         -> same
  Names2.txt        -> same
  VietPhrase.txt    -> dicts/VietPhrase_1.txt + VietPhrase_2.txt + VietPhrase_3.txt + VietPhrase_4.txt
  vietphrase.txt    -> same VietPhrase dicts union (append to VietPhrase_4.txt)

Master files may be UTF-16 LE (BOM) or UTF-8 with BOM; dict files are UTF-8.
A key is the text before the first '=' in a line.
"""
from __future__ import annotations

from pathlib import Path

MASTER_DIR = Path("/home/falcol/Downloads/VietPhrase-master")
DICT_DIR = Path(__file__).resolve().parent / "dicts"

DICT_LUATNHAN = DICT_DIR / "LuatNhan.txt"
DICT_NAMES = DICT_DIR / "Names.txt"
DICT_NAMES_2 = DICT_DIR / "Names_2.txt"
DICT_PHIENAM_2 = DICT_DIR / "ChinesePhienAmWords_2.txt"
DICT_VIETPHRASE_1 = DICT_DIR / "VietPhrase_1.txt"
DICT_VIETPHRASE_2 = DICT_DIR / "VietPhrase_2.txt"
DICT_VIETPHRASE_3 = DICT_DIR / "VietPhrase_3.txt"
DICT_VIETPHRASE_4 = DICT_DIR / "VietPhrase_4.txt"

# (master name, [existing dict files to compare against], target dict file)
# [Note] Compare list is per-family only (VP vs VP, Names vs Names).
# Cross-family keys (Names ∩ VietPhrase) are not skipped — re-run recreates
# dups that check_dup_keys.py --apply just stripped. Confirm before widening?
PAIRS: list[tuple[str, list[str], str]] = [
    ("LuatNhan.txt", ["LuatNhan.txt"], "LuatNhan.txt"),
    ("luatnhan.txt", ["LuatNhan.txt"], "LuatNhan.txt"),
    ("Names.txt", ["Names.txt", "Names_2.txt"], "Names_2.txt"),
    ("names.txt", ["Names.txt", "Names_2.txt"], "Names_2.txt"),
    ("Names2.txt", ["Names.txt", "Names_2.txt"], "Names_2.txt"),
    (
        "ChinesePhienAmWords.txt",
        ["ChinesePhienAmWords.txt", "ChinesePhienAmWords_2.txt"],
        "ChinesePhienAmWords_2.txt",
    ),
    (
        "VietPhrase.txt",
        ["VietPhrase_1.txt", "VietPhrase_2.txt", "VietPhrase_3.txt", "VietPhrase_4.txt"],
        "VietPhrase_4.txt",
    ),
    (
        "vietphrase.txt",
        ["VietPhrase_1.txt", "VietPhrase_2.txt", "VietPhrase_3.txt", "VietPhrase_4.txt"],
        "VietPhrase_4.txt",
    ),
]


def read_master_lines(name: str) -> list[str]:
    path = MASTER_DIR / name
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16").splitlines()
    return data.decode("utf-8-sig").splitlines()


def read_dict_keys(names: list[str]) -> set[str]:
    keys: set[str] = set()
    for name in names:
        path = DICT_DIR / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            eq = line.find("=")
            if eq > 0:
                keys.add(line[:eq].strip())
    return keys


def key_of(line: str) -> str | None:
    eq = line.find("=")
    if eq > 0:
        return line[:eq].strip()
    return None


def main() -> None:
    appended = {}
    for master_name, compare_list, target_name in PAIRS:
        dict_keys = read_dict_keys(compare_list)
        missing: list[str] = []
        for line in read_master_lines(master_name):
            line = line.strip()
            if not line:
                continue
            key = key_of(line)
            if key is not None and key not in dict_keys:
                missing.append(line)
        if missing:
            target = DICT_DIR / target_name
            with target.open("a", encoding="utf-8") as f:
                f.write("\n".join(missing) + "\n")
        appended[master_name] = (len(missing), target_name)

    for master_name, (count, target) in appended.items():
        print(f"{master_name}: appended {count} missing lines -> {target}")


if __name__ == "__main__":
    main()