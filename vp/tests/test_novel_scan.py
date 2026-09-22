from vp.dicts import read_overlay
from vp.novel_scan import scan_paths, write_scan_files


def test_scan_paths_strip_zh_suffix(tmp_path):
    src = tmp_path / "manh-nhat-from-1012.zh.txt"
    review, reject = scan_paths(src)
    assert review.name == "manh-nhat-from-1012.novel-review.txt"
    assert reject.name == "manh-nhat-from-1012.novel-reject.txt"


def test_write_scan_files_sorts_and_keeps_columns(tmp_path):
    review = tmp_path / "a.novel-review.txt"
    reject = tmp_path / "a.novel-reject.txt"
    write_scan_files(
        review,
        reject,
        [
            {"zh": "乙", "vi": "Ất", "category": "item", "count": 2, "score": 0.2, "rules": ""},
            {"zh": "甲", "vi": "Giáp", "category": "character", "count": 9, "score": 0.9, "rules": "xbVeto"},
        ],
        [
            {"zh": "丙", "vi": "Bính", "category": "character", "count": 4, "score": 0.01, "rules": ""},
            {"zh": "丁", "vi": "Đinh", "category": "other", "count": 8, "score": 0.0, "rules": ""},
        ],
    )
    assert review.read_text(encoding="utf-8").splitlines() == [
        "# zh=vi\tloại\tsố_lần\tđiểm\tluật",
        "甲=Giáp\tcharacter\t9\t0.9000\txbVeto",
        "乙=Ất\titem\t2\t0.2000\t",
    ]
    assert reject.read_text(encoding="utf-8").splitlines()[1] == "丁=Đinh\tother\t8\t0.0000\t"


def test_overlay_reads_review_file_by_category(tmp_path):
    path = tmp_path / "review.txt"
    path.write_text(
        "# zh=vi\tloại\tsố_lần\tđiểm\tluật\n"
        "甲=Giáp\tcharacter\t3\t0.5000\t\n"
        "乙刀=Ất Đao\titem\t2\t0.4000\txbVeto\n"
        "刀=đao\tphrase\n"
        "名=Tên\n",
        encoding="utf-8",
    )
    assert read_overlay(path) == [
        ("甲", "Giáp", 30),
        ("乙刀", "Ất Đao", 25),
        ("刀", "đao", 25),
        ("名", "Tên", 30),
    ]
