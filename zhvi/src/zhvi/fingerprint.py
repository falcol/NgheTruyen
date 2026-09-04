"""Run fingerprint (thiet ke muc 8, SPEC AD-11/AD-18).

SHA-256 cua (source_revision + encoding + parser_version + segmenter_version +
resolved_config + base_dictionary_hash + book_glossary_hash + qa_version +
pipeline_version). Story 1.2: khong con thanh phan prompt/model/router —
fingerprint chi chua nhung gi thuc su anh huong output VP.
"""
from __future__ import annotations

import hashlib

from .config import (
    PARSER_VERSION,
    PIPELINE_VERSION,
    QA_VERSION,
    SEGMENTER_VERSION,
    Config,
    config_hash,
)


def build_run_fingerprint(
    *,
    source_revision_hash: str,
    encoding: str,
    dictionary_fingerprint: str,
    book_glossary_hash: str,
    cfg: Config,
) -> str:
    parts = [
        source_revision_hash,
        encoding,
        PARSER_VERSION,
        SEGMENTER_VERSION,
        config_hash(cfg),
        dictionary_fingerprint,
        book_glossary_hash,
        QA_VERSION,
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
