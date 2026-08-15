import gzip
import json
from pathlib import Path

from research.jsonl_dates import iter_all_rows, list_dates, open_stem


def _touch(path, content="x\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _touch_gz(path, content="x\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        f.write(content)


def test_list_dates_sees_both_plain_and_gz(tmp_path):
    _touch(tmp_path / "2026-08-13.jsonl")
    _touch_gz(tmp_path / "2026-08-01.jsonl.gz")

    assert list_dates(tmp_path) == ["2026-08-01", "2026-08-13"]


def test_list_dates_respects_glob_prefix(tmp_path):
    _touch(tmp_path / "hl_BTC_2026-08-13.jsonl")
    _touch_gz(tmp_path / "binance_BTC_2026-08-01.jsonl.gz")

    assert list_dates(tmp_path, glob_prefix="hl_BTC_") == ["2026-08-13"]


def test_list_dates_missing_dir_returns_empty():
    assert list_dates(Path("/no/such/dir")) == []


def test_open_stem_prefers_plain_over_gz(tmp_path):
    _touch(tmp_path / "2026-08-13.jsonl", "plain\n")
    _touch_gz(tmp_path / "2026-08-13.jsonl.gz", "gz\n")

    with open_stem(tmp_path, "2026-08-13") as f:
        assert f.read() == "plain\n"


def test_open_stem_falls_back_to_gz(tmp_path):
    _touch_gz(tmp_path / "2026-08-01.jsonl.gz", "gz\n")

    with open_stem(tmp_path, "2026-08-01") as f:
        assert f.read() == "gz\n"


def test_open_stem_returns_none_when_missing(tmp_path):
    assert open_stem(tmp_path, "2026-08-01") is None


def test_iter_all_rows_merges_plain_and_gz_in_filename_order(tmp_path):
    _touch(tmp_path / "2026-08-13.jsonl", json.dumps({"d": "13"}) + "\n")
    _touch_gz(tmp_path / "2026-08-01.jsonl.gz", json.dumps({"d": "01"}) + "\n")

    rows = iter_all_rows(tmp_path)

    assert rows == [{"d": "01"}, {"d": "13"}]


def test_iter_all_rows_missing_dir_returns_empty():
    assert iter_all_rows(Path("/no/such/dir")) == []
