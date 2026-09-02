"""Run fingerprint (thiet ke muc 8).

SHA-256 cua (source_revision + encoding + parser_version + resolved_config +
base_dictionary_hash + book_glossary_hash + style_profile_hash + router_version
+ qa_version + prompt_schema_hash + model digests + pipeline_version).
M1: model digest = None (khong goi model).
"""
from __future__ import annotations

import hashlib

from .config import (
    PARSER_VERSION,
    PIPELINE_VERSION,
    PROMPT_SCHEMA_VERSION,
    QA_VERSION,
    ROUTER_VERSION,
    Config,
    config_hash,
    style_profile_hash,
)


def build_run_fingerprint(
    *,
    source_revision_hash: str,
    encoding: str,
    dictionary_fingerprint: str,
    book_glossary_hash: str,
    cfg: Config,
    hachimi_digest: str | None = None,
    qwen_digest: str | None = None,
) -> str:
    parts = [
        source_revision_hash,
        encoding,
        PARSER_VERSION,
        config_hash(cfg),
        dictionary_fingerprint,
        book_glossary_hash,
        style_profile_hash(cfg),
        ROUTER_VERSION,
        QA_VERSION,
        PROMPT_SCHEMA_VERSION,
        hachimi_digest or "none",
        qwen_digest or "none",
        PIPELINE_VERSION,
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def block_source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def glossary_file_hash(path) -> str:
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        return hashlib.sha256(b"empty").hexdigest()
    return hashlib.sha256(p.read_bytes()).hexdigest()
