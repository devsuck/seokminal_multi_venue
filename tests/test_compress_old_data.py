import datetime as dt
import gzip

from research.compress_old_data import compress, find_compressible_files

TODAY = dt.date(2026, 7, 30)


def _touch(path, content="x\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_find_compressible_files_uses_filename_date_not_mtime(tmp_path):
    old = tmp_path / "cross_venue_skew" / "binance_BTC_2026-07-20.jsonl"
    recent = tmp_path / "cross_venue_skew" / "binance_BTC_2026-07-29.jsonl"
    _touch(old)
    _touch(recent)

    targets = find_compressible_files(tmp_path, keep_recent_days=2, today=TODAY)

    assert targets == [old]


def test_find_compressible_files_skips_files_without_date(tmp_path):
    no_date = tmp_path / "polymarket_tick" / "README.md"
    _touch(no_date)

    targets = find_compressible_files(tmp_path, keep_recent_days=0, today=TODAY)

    assert targets == []


def test_find_compressible_files_skips_already_gz(tmp_path):
    already = tmp_path / "polymarket_tick" / "2026-07-01.jsonl.gz"
    _touch(already)

    targets = find_compressible_files(tmp_path, keep_recent_days=2, today=TODAY)

    assert targets == []


def test_find_compressible_files_keeps_recent_days(tmp_path):
    # today(2026-07-30) - keep_recent_days(2) = 2026-07-28 미만만 압축 대상.
    kept = tmp_path / "polymarket_tick" / "2026-07-28.jsonl"
    compressible = tmp_path / "polymarket_tick" / "2026-07-27.jsonl"
    _touch(kept)
    _touch(compressible)

    targets = find_compressible_files(tmp_path, keep_recent_days=2, today=TODAY)

    assert targets == [compressible]


def test_compress_gzips_and_removes_original(tmp_path):
    old = tmp_path / "cross_venue_skew" / "binance_BTC_2026-07-20.jsonl"
    _touch(old, content='{"ts": 1.0}\n{"ts": 2.0}\n')

    compressed = compress(tmp_path, keep_recent_days=2, dry_run=False, today=TODAY)

    assert compressed == [old]
    assert not old.exists()
    gz_path = old.with_suffix(old.suffix + ".gz")
    assert gz_path.exists()
    with gzip.open(gz_path, "rt") as f:
        assert f.read() == '{"ts": 1.0}\n{"ts": 2.0}\n'


def test_compress_dry_run_does_not_modify(tmp_path):
    old = tmp_path / "cross_venue_skew" / "binance_BTC_2026-07-20.jsonl"
    _touch(old)

    compressed = compress(tmp_path, keep_recent_days=2, dry_run=True, today=TODAY)

    assert compressed == [old]
    assert old.exists()
    assert not old.with_suffix(old.suffix + ".gz").exists()
