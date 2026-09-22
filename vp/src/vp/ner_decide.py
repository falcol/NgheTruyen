"""Pick proper names from NER-B spans, using the site's deep-scan thresholds."""

from __future__ import annotations

import re
from dataclasses import dataclass

CJK_SURFACE_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]{2,6}$")
CJK_NAME_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]{2,4}$")
GROUP_SUFFIX_RE = re.compile(r"[族帮幫宗盟门門派阁閣军軍隊隊]$")
PLACE_SUFFIX_RE = re.compile(r"[郡县縣州府省村镇鎮乡鄉]$")
TITLE_SUFFIX_RE = re.compile(r"[师師父傅]$")

TITLE_EXACT = frozenset(
    {
        "师父",
        "師父",
        "师傅",
        "師傅",
        "老师",
        "老師",
        "师兄",
        "師兄",
        "师姐",
        "師姐",
        "师弟",
        "師弟",
        "师妹",
        "師妹",
        "前辈",
        "前輩",
        "大人",
        "公子",
        "姑娘",
        "夫人",
        "小姐",
        "先生",
    }
)
NOISE_EXACT = frozenset(
    {
        "年轻",
        "年輕",
        "武修",
        "少年",
        "少女",
        "弟子",
        "凡人",
        "强者",
        "強者",
        "高手",
        "废物",
        "廢物",
        "修士",
        "修炼",
        "修煉",
        "功法",
        "神通",
        "时候",
        "時候",
        "自己",
        "他们",
        "他們",
        "什么",
        "什麼",
    }
)

TAG_CATEGORY = {"Nh": "character", "Ns": "location", "Ni": "sect_org"}
MIN_COUNT = 3
MIN_SHARE = 0.8
MAX_TERMS = 300
CHUNK_SIZE = 1800


def is_noise(zh: str) -> bool:
    zh = zh.strip()
    if not zh or zh in NOISE_EXACT or zh in TITLE_EXACT:
        return True
    if TITLE_SUFFIX_RE.search(zh):
        return True
    if len(zh) >= 3 and zh.endswith("者"):
        return True
    return False


def is_name_candidate(zh: str, category: str) -> bool:
    if category != "character" or not CJK_NAME_RE.match(zh) or is_noise(zh):
        return False
    if len(zh) >= 3 and (GROUP_SUFFIX_RE.search(zh) or PLACE_SUFFIX_RE.search(zh)):
        return False
    return True


@dataclass(slots=True)
class FoundName:
    zh: str
    vi: str
    category: str
    status: str
    count: int
    share: float


@dataclass(slots=True)
class ScanStats:
    chunks: int
    entities: int
    new_terms: int
    approved: int
    pending: int
    provider: str = ""


def chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    text = text or ""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + size, n)
        if end < n:
            for cursor in range(end, i + size // 2, -1):
                if text[cursor - 1] in "。！？!?…\n":
                    end = cursor
                    break
        out.append(text[i:end])
        i = end
    return out


def select_names(
    spans: list[tuple[str, str]],
    suggest,
    *,
    known: set[str] | None = None,
    min_count: int = MIN_COUNT,
    min_share: float = MIN_SHARE,
) -> tuple[list[FoundName], ScanStats]:
    """spans are (surface, tag). Approved rows are characters the model saw often enough."""
    known = known or set()
    buckets: dict[str, dict[str, int]] = {}
    order: list[str] = []
    for surface, tag in spans:
        zh = surface.strip()
        if not zh:
            continue
        row = buckets.get(zh)
        if row is None:
            row = {"count": 0}
            buckets[zh] = row
            order.append(zh)
        row["count"] += 1
        if tag:
            row[tag] = row.get(tag, 0) + 1
    ranked = sorted(order, key=lambda zh: (-buckets[zh]["count"], zh))
    found: list[FoundName] = []
    approved = 0
    for zh in ranked:
        row = buckets[zh]
        if zh in known:
            continue
        count = row["count"]
        if count < min_count or not CJK_SURFACE_RE.match(zh) or is_noise(zh):
            continue
        top = ""
        best = 0
        for tag in ("Nh", "Ns", "Ni"):
            votes = row.get(tag, 0)
            if votes > best:
                best = votes
                top = tag
        category = TAG_CATEGORY.get(top, "")
        if not category:
            continue
        if category == "character" and not is_name_candidate(zh, category):
            continue
        share = best / count if count else 0.0
        status = "approved" if category == "character" and share >= min_share else "pending"
        vi = suggest(zh) if status == "approved" else ""
        if status == "approved" and not vi:
            status = "pending"
        found.append(FoundName(zh, vi, category, status, count, share))
        if status == "approved":
            approved += 1
        if len(found) >= MAX_TERMS:
            break
    stats = ScanStats(0, len(spans), len(found), approved, len(found) - approved)
    return found, stats
