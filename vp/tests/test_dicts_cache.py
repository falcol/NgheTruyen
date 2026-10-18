from vp.dicts import load_local_engine


def test_local_engine_pickle_cache_roundtrip(tmp_path):
    dict_dir = tmp_path / "dicts"
    dict_dir.mkdir()
    (dict_dir / "VietPhrase_1.txt").write_text("你好=xin chào\n", encoding="utf-8")
    (dict_dir / "Names.txt").write_text("凌天=Lăng Thiên\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"

    first = load_local_engine(dict_dir, simplified=True, luat_nhan=2, cache_dir=cache_dir)
    assert len(list(cache_dir.glob("engine-*.pkl"))) == 1

    second = load_local_engine(dict_dir, simplified=True, luat_nhan=2, cache_dir=cache_dir)
    assert first.translate("凌天你好。") == second.translate("凌天你好。")

    # A different build knob gets its own fingerprint; saving prunes the stale one.
    third = load_local_engine(dict_dir, simplified=True, luat_nhan=0, cache_dir=cache_dir)
    assert third.luat_nhan == 0
    assert len(list(cache_dir.glob("engine-*.pkl"))) == 1
