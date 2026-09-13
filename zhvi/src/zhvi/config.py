"""Resolved configuration: defaults <- project zhvi.toml <- env <- CLI flags (thiet ke muc 33/41)."""
from __future__ import annotations

import hashlib
import json
import os
import tomllib
from dataclasses import asdict, dataclass, replace
from pathlib import Path

PARSER_VERSION = "zhvi-parser-1"
SEGMENTER_VERSION = "zhvi-segmenter-3"  # Custom name collision + ordinal title
QA_VERSION = "zhvi-qa-1"
PIPELINE_VERSION = "zhvi-m3-0.1.0"
# Version cua logic nap tu dien / render target — tham gia canonical manifest
# cua revision (SPEC AD-15 buoc 5): doi logic nap/render phai tao revision moi.
LOADER_VERSION = "zhvi-loader-6"  # {p} P_STOP + 上里后 (Adj+N neo)
RENDERER_VERSION = "zhvi-renderer-8"  # sense lattice/commit 79ccba80
# Version cua preprocessing view (junk strip + repetition collapse rules,
# AD-18/FR13) — tham gia run fingerprint + block cache key; doi rule strip/
# collapse phai bump nay (run/cache cu tu invalid).
PREPROCESS_VERSION = "zhvi-preprocess-1"
# Route duy nhat cua duong dich VP-only (SPEC CAP-9: run moi chi ghi route nay).
ROUTE_VIETPHRASE = "VIETPHRASE"

# Base dictionary files, in load order (same layout as crawler/vietphrase/dicts).
BASE_DICT_FILES = (
    "ChinesePhienAmWords.txt",
    "ChinesePhienAmWords_2.txt",
    "VietPhrase_1.txt",
    "VietPhrase_2.txt",
    "VietPhrase_3.txt",
    "VietPhrase_4.txt",
    "LuatNhan.txt",
    "Names.txt",
    "Names_2.txt",
    "QualityOverrides.txt",
    "ContextPatterns.txt",
)
TRAD_SIMP_FILE = "trad-simp.txt"
CUSTOM_FILE = "Custom.txt"

DEFAULT_DICT_DIR = "crawler/vietphrase/dicts"
# Glossary chuan toan cuc (moi truyen dung chung): ~/.config/zhvi/glossary.manual.tsv
DEFAULT_GLOBAL_GLOSSARY = "~/.config/zhvi/glossary.manual.tsv"


@dataclass(frozen=True)
class LearningConfig:
    """Nguong learning (SPEC pipeline-contract 'Config schema du kien').

    Default khoi tao an toan — khong phai invariant (SPEC Assumptions).
    Logic learner thuoc epic 3/4; day chi la config schema.
    """

    enabled: bool = True
    auto_scope: str = "book"  # book | global
    max_phrase_chars: int = 8
    min_name_occurrences: int = 3
    min_term_occurrences: int = 5
    min_chapters: int = 2
    require_unambiguous_target: bool = True
    require_affected_block_isolation: bool = True
    global_min_books: int = 3
    global_min_occurrences: int = 20
    global_require_golden_suite: bool = True


@dataclass(frozen=True)
class RuntimeConfig:
    checkpoint_blocks: int = 50


@dataclass(frozen=True)
class Config:
    # style / policy
    style: str = "convert-qt"
    output_policy: str = "strict-final"
    # input
    encoding: str = "utf-8"
    chapter_detection: str = "auto"  # auto | strict | none
    chapter_regex: str = ""
    # dictionaries
    dict_dir: str = DEFAULT_DICT_DIR
    global_glossary: str = DEFAULT_GLOBAL_GLOSSARY
    # segmentation / lattice
    block_max_chars: int = 2000
    lattice_beam: int = 4
    collapse_repetitions: bool = True
    qa_strip_junk: bool = True
    pattern_rules: bool = True  # luat nhan {s}/{n} trong LuatNhan.txt (muc 11.1)
    # sections
    learning: LearningConfig = LearningConfig()
    runtime: RuntimeConfig = RuntimeConfig()

    def to_dict(self) -> dict:
        return asdict(self)

    def json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)


def config_hash(cfg: Config) -> str:
    return hashlib.sha256(cfg.json().encode("utf-8")).hexdigest()


def load_project_config(project_root: Path) -> Config:
    """Merge defaults with zhvi.toml at project root (if present)."""
    path = project_root / "zhvi.toml"
    if not path.is_file():
        return Config()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return apply_toml(Config(), raw)


def apply_toml(cfg: Config, raw: dict) -> Config:
    known = {k: v for k, v in raw.items() if k in cfg.to_dict() and not isinstance(v, dict)}
    sections: dict = {}
    for name in ("input", "learning", "runtime"):
        if isinstance(raw.get(name), dict):
            sections[name] = raw[name]
    updates = dict(known)
    inp = sections.get("input", {})
    if "encoding" in inp:
        updates["encoding"] = str(inp["encoding"])
    if "chapter_detection" in inp:
        updates["chapter_detection"] = str(inp["chapter_detection"])
    if "chapter_regex" in inp:
        updates["chapter_regex"] = str(inp["chapter_regex"])
    learn_raw = sections.get("learning", {})
    if learn_raw:
        learn = {k: v for k, v in learn_raw.items() if k in LearningConfig.__dataclass_fields__}
        updates["learning"] = replace(cfg.learning, **learn)
    rt_raw = sections.get("runtime", {})
    if rt_raw:
        rt = {k: v for k, v in rt_raw.items() if k in RuntimeConfig.__dataclass_fields__}
        updates["runtime"] = replace(cfg.runtime, **rt)
    return replace(cfg, **updates)


def resolve_config(
    project_root: Path | None,
    *,
    dict_dir: str | None = None,
    overrides: dict | None = None,
) -> Config:
    """Precedence (muc 33): CLI -> env -> project config -> defaults."""
    cfg = load_project_config(project_root) if project_root else Config()
    env_dict = os.environ.get("ZHVI_DICT_DIR")
    if env_dict:
        cfg = replace(cfg, dict_dir=env_dict)
    env_global = os.environ.get("ZHVI_GLOBAL_GLOSSARY")
    if env_global is not None:
        cfg = replace(cfg, global_glossary=env_global)
    if dict_dir:
        cfg = replace(cfg, dict_dir=dict_dir)
    if overrides:
        cfg = replace(cfg, **{k: v for k, v in overrides.items() if v is not None})
    return cfg


PROJECT_TOML_TEMPLATE = """# zhvi project config (SPEC zhvi-vietphrase-only, pipeline-contract 'Config schema')
style = "convert-qt"
output_policy = "strict-final"
collapse_repetitions = true  # loai lap artifact ('có chút có chút') giua 2 span khac nhau; giu reduplication goc (慢慢→chậm chậm)
qa_strip_junk = true  # strip rac truyen web (watermark ⓣⓣⓚ, bookmark, anti-leech) tren source truoc khi dich
pattern_rules = true  # luat nhan {s}/{n} (so/danh tu) trong LuatNhan.txt duoc match regex + dien capture
global_glossary = "~/.config/zhvi/glossary.manual.tsv"  # term chuan moi truyen (Tieu Ban...); book manual van override duoc

[input]
encoding = "utf-8"
chapter_detection = "auto"
# chapter_regex = ""

[learning]
enabled = true
auto_scope = "book"
max_phrase_chars = 8
min_name_occurrences = 3
min_term_occurrences = 5
min_chapters = 2
require_unambiguous_target = true
require_affected_block_isolation = true
global_min_books = 3
global_min_occurrences = 20
global_require_golden_suite = true

[runtime]
checkpoint_blocks = 50
"""
