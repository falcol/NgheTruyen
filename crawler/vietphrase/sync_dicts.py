"""Download official VietPhrase dicts and keep local harvest/Custom.

Official files come from https://vietphrase.app/dicts/manifest.json.
Local-only keys in those files are moved to harvest sidecars (or appended
back onto LuatNhan / QualityOverrides, which have no sidecar).

Does not touch Custom.txt or ContextPatterns.txt.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import requests

DICT_DIR = Path(__file__).resolve().parent / "dicts"
DICT_BASE = "https://vietphrase.app/dicts"
MANIFEST_URL = f"{DICT_BASE}/manifest.json"

# Official file -> where to store local-only keys. None = append onto the
# official file itself after replace (no harvest sidecar in LOAD_ORDER).
HARVEST_OF = {
    "ChinesePhienAmWords.txt": "ChinesePhienAmWords_2.txt",
    "Names.txt": "Names_2.txt",
    "VietPhrase_1.txt": "VietPhrase_4.txt",
    "VietPhrase_2.txt": "VietPhrase_4.txt",
    "LuatNhan.txt": None,
    "QualityOverrides.txt": None,
}

KEEP_UNTOUCHED = frozenset(
    {
        "Custom.txt",
        "ContextPatterns.txt",
        "Names_2.txt",
        "VietPhrase_3.txt",
        "VietPhrase_4.txt",
        "ChinesePhienAmWords_2.txt",
    }
)

# dict-engine.js HANVIET_PATCH — fill empty / leftover-CJK phienam.
HANVIET_PATCH = {
    "的": "đích",
    "了": "liễu",
    "旳": "đích",
    "宁": "ninh",
    "寧": "ninh",
    "㝉": "ninh",
    "靦": "điến",
    "䩄": "điến",
    "撝": "huy",
    "㧑": "huy",
    "灮": "quang",
}
CJK_IN_VI_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
PHIENAM_MIN_BYTES = 50_000


def _key_of(line: str) -> str | None:
    s = line.strip()
    if not s or s[0] in "#;" or s.startswith("//"):
        return None
    eq = s.find("=")
    if eq < 1:
        return None
    return s[:eq].strip() or None


def _read_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.is_file():
        return keys
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        k = _key_of(line)
        if k:
            keys.add(k)
    return keys


def _extra_lines(local: Path, official_keys: set[str]) -> list[str]:
    if not local.is_file():
        return []
    out: list[str] = []
    seen: set[str] = set()
    for line in local.read_text(encoding="utf-8-sig").splitlines():
        k = _key_of(line)
        if k is None or k in official_keys or k in seen:
            continue
        seen.add(k)
        out.append(line.rstrip("\n"))
    return out


def _append_lines(path: Path, lines: list[str], note: str) -> int:
    if not lines:
        return 0
    existing = _read_keys(path)
    fresh = [ln for ln in lines if (k := _key_of(ln)) and k not in existing]
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = ""
    if path.is_file() and path.stat().st_size and not path.read_bytes().endswith(b"\n"):
        prefix = "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(prefix)
        if note:
            f.write(f"# {note}\n")
        f.write("\n".join(fresh) + "\n")
    return len(fresh)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_manifest() -> dict:
    resp = requests.get(MANIFEST_URL, timeout=60)
    resp.raise_for_status()
    return resp.json()


def download_file(path_name: str, expected_sha: str, expected_size: int) -> bytes:
    url = f"{DICT_BASE}/{path_name}"
    print(f"[sync] GET {url}", flush=True)
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    data = resp.content
    if expected_size and len(data) != expected_size:
        raise RuntimeError(f"{path_name}: size {len(data)} != manifest {expected_size}")
    got = _sha256(data)
    if expected_sha and got != expected_sha:
        raise RuntimeError(f"{path_name}: sha256 {got} != manifest {expected_sha}")
    return data


def apply_hanviet_patch(phienam: Path) -> int:
    lines = phienam.read_text(encoding="utf-8-sig").splitlines()
    by_key: dict[str, int] = {}
    for i, line in enumerate(lines):
        k = _key_of(line)
        if k:
            by_key[k] = i
    changed = 0
    for zh, vi in HANVIET_PATCH.items():
        if zh in by_key:
            old = lines[by_key[zh]]
            eq = old.find("=")
            cur = old[eq + 1 :].strip() if eq != -1 else ""
            if cur and not CJK_IN_VI_RE.search(cur):
                continue
            lines[by_key[zh]] = f"{zh}={vi}"
            changed += 1
        else:
            lines.append(f"{zh}={vi}")
            changed += 1
    if changed:
        phienam.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def sync(dict_dir: Path = DICT_DIR) -> dict[str, int]:
    dict_dir.mkdir(parents=True, exist_ok=True)
    manifest = fetch_manifest()
    revision = str(manifest.get("revision") or "")
    print(f"[sync] revision {revision}", flush=True)
    stats: dict[str, int] = {"files": 0, "harvested": 0, "patched": 0}

    for spec in manifest.get("files") or []:
        name = spec["path"]
        if name in KEEP_UNTOUCHED:
            print(f"[sync] skip kept {name}", flush=True)
            continue
        data = download_file(name, spec.get("sha256") or "", int(spec.get("size") or 0))
        dest = dict_dir / name
        official_keys = set()
        text = data.decode("utf-8-sig")
        for line in text.splitlines():
            k = _key_of(line)
            if k:
                official_keys.add(k)
        extras = _extra_lines(dest, official_keys)
        harvest_name = HARVEST_OF.get(name)
        dest.write_bytes(data)
        stats["files"] += 1
        if extras:
            if harvest_name:
                n = _append_lines(
                    dict_dir / harvest_name,
                    extras,
                    f"local extras after official {revision} from {name}",
                )
            else:
                n = _append_lines(
                    dest,
                    extras,
                    f"local extras after official {revision}",
                )
            stats["harvested"] += n
            print(f"[sync] {name}: replaced, harvested {n} extra keys", flush=True)
        else:
            print(f"[sync] {name}: replaced", flush=True)

        if name == "ChinesePhienAmWords.txt":
            stats["patched"] = apply_hanviet_patch(dest)
            print(f"[sync] HANVIET_PATCH {stats['patched']} keys", flush=True)

    trad = dict_dir / "trad-simp.txt"
    if not trad.is_file():
        try:
            raw = download_file("trad-simp.txt", "", 0)
            trad.write_bytes(raw)
            print("[sync] trad-simp.txt downloaded", flush=True)
        except Exception as exc:
            print(f"[sync] trad-simp.txt skip: {exc}", flush=True)

    return stats


def phienam_needs_refresh(dict_dir: Path = DICT_DIR) -> bool:
    path = dict_dir / "ChinesePhienAmWords.txt"
    return (not path.is_file()) or path.stat().st_size < PHIENAM_MIN_BYTES


if __name__ == "__main__":
    try:
        stats = sync()
    except Exception as exc:
        print(f"[sync] FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    print(
        f"[sync] done files={stats['files']} harvested={stats['harvested']} patched={stats['patched']}",
        flush=True,
    )
