"""Isolate default workspace so tests khong ghi vao zhvi/workspace/."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_default_workspace(tmp_path, monkeypatch, request):
    if request.node.get_closest_marker("keep_default_workspace"):
        return
    monkeypatch.setenv("ZHVI_PROJECT", str(tmp_path / "zhvi-workspace"))
