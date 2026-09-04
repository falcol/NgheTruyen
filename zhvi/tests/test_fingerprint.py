"""Fingerprint stability + sensitivity voi input thuc su anh hanh output (muc 8)."""
from __future__ import annotations

from zhvi.config import Config
from zhvi.fingerprint import build_run_fingerprint


def _fp(**kw) -> str:
    base = dict(
        source_revision_hash="rev1",
        encoding="utf-8",
        dictionary_fingerprint="dict1",
        book_glossary_hash="g1",
        cfg=Config(),
    )
    base.update(kw)
    return build_run_fingerprint(**base)


def test_fingerprint_stable():
    assert _fp() == _fp()


def test_fingerprint_changes_with_dictionary():
    assert _fp() != _fp(dictionary_fingerprint="dict2")


def test_fingerprint_changes_with_source_revision():
    assert _fp() != _fp(source_revision_hash="rev2")


def test_fingerprint_changes_with_style_config():
    """style khac -> config hash doi -> fingerprint doi."""
    assert _fp(cfg=Config(style="convert-tt")) != _fp(cfg=Config())
