import hashlib
import json

from vp.cli import main
from vp.dicts import load_manifest_engine
from vp.textutil import decode_source


def test_decode_gbk_and_big5():
    assert decode_source("你好".encode("gbk"), "auto") == "你好"
    assert decode_source("你好".encode("big5"), "auto") == "你好"
    assert decode_source("你好".encode("utf-8"), "auto") == "你好"


def test_cli_writes_vi_txt(tmp_path):
    dict_dir = tmp_path / "dicts"
    dict_dir.mkdir()
    (dict_dir / "VietPhrase_1.txt").write_text("你好=xin chào\n", encoding="utf-8")
    (dict_dir / "ChinesePhienAmWords.txt").write_text("你=nhân\n好=hảo\n", encoding="utf-8")
    src = tmp_path / "a.txt"
    src.write_bytes("你好。".encode("gbk"))
    custom = tmp_path / "custom.txt"
    custom.write_text("你好=chào riêng\n", encoding="utf-8")
    rc = main(
        [
            "file",
            str(src),
            "--dict-dir",
            str(dict_dir),
            "--custom",
            str(custom),
            "--encoding",
            "gbk",
            "--luat-nhan",
            "0",
        ]
    )
    assert rc == 0
    assert (tmp_path / "a.vi.txt").read_text(encoding="utf-8") == "Chào riêng."


def test_manifest_phienam_map_is_base_not_priority_five(monkeypatch, tmp_path):
    page = "https://example.test/"
    blobs = {
        page + "dicts/manifest.json": None,
        page + "dicts/ChinesePhienAmWords.txt": "他=hắn\n".encode(),
        page + "dicts/trad-simp.txt": b"",
        page + "dict-default.json": json.dumps({"phienam": {"他": "tha"}}, ensure_ascii=False).encode(),
    }
    manifest = {
        "revision": "testrev",
        "files": [
            {
                "id": "phien-am",
                "path": "ChinesePhienAmWords.txt",
                "kind": "phienam",
                "priority": 5,
                "size": len(blobs[page + "dicts/ChinesePhienAmWords.txt"]),
                "sha256": hashlib.sha256(blobs[page + "dicts/ChinesePhienAmWords.txt"]).hexdigest(),
            }
        ],
    }
    blobs[page + "dicts/manifest.json"] = json.dumps(manifest).encode()

    def fake_download(url, timeout=120):
        return blobs[url]

    monkeypatch.setattr("vp.dicts._download", fake_download)
    engine = load_manifest_engine(
        cache_dir=tmp_path / "cache",
        simplified=True,
        luat_nhan=2,
        page=page,
    )
    assert engine.translate("他") == "Hắn"
    assert engine.hanviet("他") == "Tha"
