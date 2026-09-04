"""Run fingerprint (thiet ke muc 8, SPEC AD-11/AD-18).

SHA-256 cua (source_revision + encoding + parser_version + segmenter_version +
resolved_config + dictionary_revision_id + qa_version + pipeline_version).
Story 1.2: khong con thanh phan prompt/model/router. Story 2.3: glossary
manual nam trong revision manifest — fingerprint chi chua revision id thay
vi hash file rieng (doi file giua chang khong fork run; revision moi moi fork).
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
    cfg: Config,
) -> str:
    parts = [
        source_revision_hash,
        encoding,
        PARSER_VERSION,
        SEGMENTER_VERSION,
        config_hash(cfg),
        dictionary_fingerprint,
        QA_VERSION,
        PIPELINE_VERSION,
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def block_source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
