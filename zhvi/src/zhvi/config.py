"""Resolved configuration: defaults <- project zhvi.toml <- env <- CLI flags (thiet ke muc 33/41)."""
from __future__ import annotations

import hashlib
import json
import os
import tomllib
from dataclasses import asdict, dataclass, replace
from pathlib import Path

PARSER_VERSION = "zhvi-parser-1"
SEGMENTER_VERSION = "zhvi-segmenter-1"
ROUTER_VERSION = "zhvi-router-1"  # M1: VP-only router
QA_VERSION = "zhvi-qa-1"
PROMPT_SCHEMA_VERSION = "none-m1"
PIPELINE_VERSION = "zhvi-m1-0.1.0"

# Base dictionary files, in load order (same layout as crawler/vietphrase/dicts).
BASE_DICT_FILES = (
    "ChinesePhienAmWords.txt",
    "VietPhrase_1.txt",
    "VietPhrase_2.txt",
    "VietPhrase_3.txt",
    "LuatNhan.txt",
    "Names.txt",
    "QualityOverrides.txt",
)
TRAD_SIMP_FILE = "trad-simp.txt"
CUSTOM_FILE = "Custom.txt"

DEFAULT_DICT_DIR = "crawler/vietphrase/dicts"
# Glossary chuan toan cuc (moi truyen dung chung): ~/.config/zhvi/glossary.manual.tsv
DEFAULT_GLOBAL_GLOSSARY = "~/.config/zhvi/glossary.manual.tsv"


@dataclass(frozen=True)
class Config:
    # style / pipeline / policy (muc 33)
    style: str = "convert-qt"
    pipeline: str = "balanced"
    output_policy: str = "strict-final"
    learning: str = "safe"
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
    # routing (M2 placeholders, fixed in fingerprint)
    audit_direct_vp_rate: float = 0.0
    # runtime (M2 placeholders)
    qwen_concurrency: int = 1
    hachimi_device: str = "cpu"

    def to_dict(self) -> dict:
        return asdict(self)

    def json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)


def config_hash(cfg: Config) -> str:
    return hashlib.sha256(cfg.json().encode("utf-8")).hexdigest()


def style_profile_hash(cfg: Config) -> str:
    return hashlib.sha256(f"{cfg.style}:{cfg.pipeline}".encode()).hexdigest()


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
    for name in ("input", "routing", "runtime"):
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
    rt = sections.get("runtime", {})
    if "qwen_concurrency" in rt:
        updates["qwen_concurrency"] = int(rt["qwen_concurrency"])
    if "hachimi_device" in rt:
        updates["hachimi_device"] = str(rt["hachimi_device"])
    routing = sections.get("routing", {})
    if "audit_direct_vp_rate" in routing:
        updates["audit_direct_vp_rate"] = float(routing["audit_direct_vp_rate"])
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


PROJECT_TOML_TEMPLATE = """# zhvi project config (thiet ke v2.0, muc 33/41)
style = "convert-qt"
pipeline = "balanced"
output_policy = "strict-final"
learning = "safe"
collapse_repetitions = true  # loai lap artifact ('có chút có chút') giua 2 span khac nhau; giu reduplication goc (慢慢→chậm chậm)
qa_strip_junk = true  # strip rac truyen web (watermark ⓣⓣⓚ, bookmark, anti-leech) tren source truoc khi dich
global_glossary = "~/.config/zhvi/glossary.manual.tsv"  # term chuan moi truyen (Tieu Ban...); book manual van override duoc

[input]
encoding = "utf-8"
chapter_detection = "auto"
# chapter_regex = ""

[routing]
audit_direct_vp_rate = 0.0

[runtime]
qwen_concurrency = 1
hachimi_device = "cpu"
"""
