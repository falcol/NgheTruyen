"""Write Novel Scan review and reject files beside a Chinese source."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from vp.dicts import find_local_dict_dir
from vp.textutil import decode_source

PAGE = "https://vietphrase.app/"
RUNNER = Path(__file__).with_name("novel_scan_runner.mjs")
HEADER = "# zh=vi\tloại\tsố_lần\tđiểm\tluật"
# kind is the verifier source class. Only VietPhrase_1/2 count as vietphrase.
DICT_FILES = (
    ("ChinesePhienAmWords.txt", "other", 5),
    ("ChinesePhienAmWords_2.txt", "other", 5),
    ("LuatNhan.txt", "other", 15),
    ("Names.txt", "name", 20),
    ("Names_2.txt", "name", 20),
    ("VietPhrase_1.txt", "vietphrase", 10),
    ("VietPhrase_2.txt", "vietphrase", 10),
    ("VietPhrase_3.txt", "other", 10),
    ("VietPhrase_4.txt", "other", 10),
    ("QualityOverrides.txt", "override", 25),
    ("Custom.txt", "custom", 999),
)
ASSETS = (
    ("term-typing.js", 5764, "d02592091c46acf97bf25925b3cbeccad9f9049620363dfa7375f0256f740509"),
    ("novel-scan-policy.js", 13652, "1bc8e32b681b53327e6cac6477734559e78e59348f8a1d2d62137d7490ce9091"),
    ("novel-glossary-pipeline.js", 12728, "11226e242a36036c5bdb4ab1f75191b8a2ee4e273aa6fbf5933803d0004d418f"),
    ("term-verifier.js", 35090, "138796abf6456163474fef693ebc73c4b85a98abff79743591188051c0151cc0"),
    ("term-verifier-cascade.js", 37110, "0a795184318ff7c3dd07c03bf2d583a539493fafa251bc794456d7cf63b46bdc"),
    ("novel-term-detector.js", 236243, "896d1a81ba367193920d96b3f48abdcca95d4f87ac5eabdad30af85286a725dd"),
    (
        "term-verifier-v30r-cascade.json",
        853301,
        "d1c6026ac3ae7c4dc42f7d22fb48dbdebc1a6e4164d104887b78600551d91a7b",
    ),
    (
        "term-verifier-v15-gbdt.json",
        161892,
        "669e18d88f790826ec370e8ecd127a427db500ebc9f17bf30c4af72b9da3fa88",
    ),
)


def scan_paths(src: Path) -> tuple[Path, Path]:
    name = src.name
    stem = name[: -len(".zh.txt")] if name.endswith(".zh.txt") else src.stem
    return src.with_name(stem + ".novel-review.txt"), src.with_name(stem + ".novel-reject.txt")


def write_scan_files(
    review_path: Path,
    reject_path: Path,
    review_rows: list[dict],
    reject_rows: list[dict],
) -> None:
    review_path.write_text(_render(_sort_review(review_rows)), encoding="utf-8")
    reject_path.write_text(_render(_sort_reject(reject_rows)), encoding="utf-8")


def _sort_review(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: (-float(row["score"]), -int(row["count"]), row["zh"]))


def _sort_reject(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: (-int(row["count"]), -float(row["score"]), row["zh"]))


def _render(rows: list[dict]) -> str:
    lines = [HEADER]
    for row in rows:
        score = float(row["score"])
        lines.append(
            f"{row['zh']}={row['vi']}\t{row['category']}\t{int(row['count'])}\t{score:.4f}\t{row.get('rules') or ''}"
        )
    return "\n".join(lines) + "\n"


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "vp-cli"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def _cached(cache_dir: Path, name: str, size: int, sha256: str, *, refresh: bool) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / name
    if dest.is_file() and not refresh:
        data = dest.read_bytes()
        if len(data) == size and hashlib.sha256(data).hexdigest() == sha256:
            return dest
        dest.unlink()
    url = PAGE + ("models/" + name if name.endswith(".json") else name)
    data = _download(url)
    if len(data) != size or hashlib.sha256(data).hexdigest() != sha256:
        raise RuntimeError(f"{name}: sai kích thước hoặc SHA-256")
    dest.write_bytes(data)
    return dest


def ensure_assets(cache_dir: Path, *, refresh: bool = False) -> Path:
    root = cache_dir / "novel-scan"
    for name, size, digest in ASSETS:
        _cached(root, name, size, digest, refresh=refresh)
    return root


def _substrings(text: str) -> set[str]:
    chars = list(text)
    found: set[str] = set()
    n = len(chars)
    for i in range(n):
        piece = ""
        for j in range(i, min(n, i + 4)):
            piece += chars[j]
            found.add(piece)
    return found


def annotate_terms(terms: list[dict], dict_dir: Path) -> tuple[list[dict], dict[str, str]]:
    """Attach dict signals. Exact Names.txt hits are left out of review/reject."""
    wanted: set[str] = set()
    for term in terms:
        wanted.update(_substrings(term["zh"]))
    hits: dict[str, tuple[int, str]] = {}
    phienam: dict[str, str] = {}
    for name, kind, priority in DICT_FILES:
        path = dict_dir / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line[0] == "#" or line.startswith("//"):
                continue
            eq = line.find("=")
            if eq < 1:
                continue
            zh = line[:eq].strip()
            vi = line[eq + 1 :].strip()
            if not zh:
                continue
            if name.startswith("ChinesePhienAmWords") and len(zh) == 1 and vi:
                reading = vi.split("/")[0].split("|")[0].strip()
                if reading:
                    phienam[zh] = reading
            if zh not in wanted:
                continue
            prev = hits.get(zh)
            if prev is None or priority >= prev[0]:
                hits[zh] = (priority, kind)
    kept: list[dict] = []
    for term in terms:
        zh = term["zh"]
        chars = list(zh)
        exact = hits.get(zh)
        exact_cls = exact[1] if exact else ""
        if exact_cls == "name":
            continue
        exact_pri = exact[0] if exact else 0
        merged = {"name": 0, "vietphrase": 0, "override": 0, "custom": 0, "other": 0}
        total = 0
        single = 0
        multi = 0
        i = 0
        n = len(chars)
        while i < n:
            matched = 0
            cls = "other"
            for length in range(min(4, n - i), 0, -1):
                row = hits.get("".join(chars[i : i + length]))
                if row is None:
                    continue
                matched = length
                cls = row[1]
                break
            if matched == 0:
                matched = 1
            total += matched
            if matched > 1:
                multi += 1
                merged[cls] = merged.get(cls, 0) + matched
            else:
                single += 1
            i += matched
        anchors = sum(1 for ch in chars if hits.get(ch) is None or hits[ch][0] <= 5)
        features = dict(term.get("features") or {})
        features.update(
            {
                "dictExactFullSpanName": 1 if exact_cls == "name" else 0,
                "dictExactFullSpanVP": 1 if exact_cls == "vietphrase" else 0,
                "dictExactFullSpanQO": 1 if exact_cls == "override" else 0,
                "dictExactFullSpanCustom": 1 if exact_cls == "custom" else 0,
                "dictExactFullSpanOther": 1
                if exact and exact_cls not in ("name", "vietphrase", "override", "custom")
                else 0,
                "dictMergedNameRatio": (merged["name"] / total) if total else 0,
                "dictMergedVPRatio": (merged["vietphrase"] / total) if total else 0,
                "dictMergedOtherRatio": ((merged["override"] + merged["custom"] + merged["other"]) / total)
                if total
                else 0,
                "dictSingleWinnerRatio": (single / total) if total else 0,
                "dictAllSingleRun": 1 if multi == 0 and total >= 2 else 0,
                "dictAnchorCount": anchors,
            }
        )
        term["features"] = features
        term["dict"] = {
            "exactCls": exact_cls,
            "exactPri": exact_pri,
            "allSingleRun": features["dictAllSingleRun"],
            "anchorCount": anchors,
            "singleWinnerRatio": round(features["dictSingleWinnerRatio"], 3),
            "mergedNameRatio": round(features["dictMergedNameRatio"], 3),
            "mergedVPRatio": round(features["dictMergedVPRatio"], 3),
        }
        kept.append(term)
    return kept, phienam


def _run_node(args: list[str]) -> None:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Không thấy node. Cần Node để chạy Novel Scan.")
    if not RUNNER.is_file():
        raise RuntimeError(f"Không thấy {RUNNER}")
    proc = subprocess.run(
        [node, str(RUNNER), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(detail or f"Novel Scan thoát {proc.returncode}")


def scan_source(
    src: Path,
    text: str,
    *,
    dict_dir: Path | None = None,
    cache_dir: Path,
    refresh: bool = False,
) -> tuple[Path, Path, int, int]:
    assets = ensure_assets(cache_dir, refresh=refresh)
    work = assets / "work"
    work.mkdir(parents=True, exist_ok=True)
    text_path = work / "source.txt"
    detected_path = work / "detected.json"
    annotated_path = work / "annotated.json"
    split_path = work / "split.json"
    text_path.write_text(text, encoding="utf-8")
    try:
        _run_node(["detect", str(assets), str(text_path), str(detected_path)])
        detected = json.loads(detected_path.read_text(encoding="utf-8"))
        terms, phienam = annotate_terms(
            detected.get("terms") or [],
            find_local_dict_dir(str(dict_dir) if dict_dir else None),
        )
        annotated_path.write_text(
            json.dumps({"terms": terms, "phienam": phienam}, ensure_ascii=False),
            encoding="utf-8",
        )
        _run_node(["split", str(assets), str(text_path), str(annotated_path), str(split_path)])
        payload = json.loads(split_path.read_text(encoding="utf-8"))
    finally:
        for path in (text_path, detected_path, annotated_path, split_path):
            path.unlink(missing_ok=True)
    review = payload.get("review") or []
    rejected = payload.get("reject") or []
    review_path, reject_path = scan_paths(src)
    write_scan_files(review_path, reject_path, review, rejected)
    return review_path, reject_path, len(review), len(rejected)


def scan_file(
    src: Path,
    *,
    encoding: str = "auto",
    dict_dir: Path | None = None,
    cache_dir: Path,
    refresh: bool = False,
) -> tuple[Path, Path, int, int]:
    text = decode_source(src.read_bytes(), encoding)
    return scan_source(
        src,
        text,
        dict_dir=dict_dir,
        cache_dir=cache_dir,
        refresh=refresh,
    )
