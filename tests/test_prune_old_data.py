import datetime as dt

from research.prune_old_data import find_expired_files, prune

TODAY = dt.date(2026, 7, 20)


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")


def test_find_expired_files_uses_filename_date_not_mtime(tmp_path):
    old = tmp_path / "cross_venue_skew" / "binance_BTC_2026-01-01.jsonl"
    recent = tmp_path / "cross_venue_skew" / "binance_BTC_2026-07-19.jsonl"
    _touch(old)
    _touch(recent)

    expired = find_expired_files(tmp_path, retention_days=90, today=TODAY)

    assert expired == [old]


def test_find_expired_files_skips_files_without_date(tmp_path):
    no_date = tmp_path / "polymarket_tick" / "README.md"
    _touch(no_date)

    expired = find_expired_files(tmp_path, retention_days=0, today=TODAY)

    assert expired == []


def test_find_expired_files_keeps_exactly_retention_days_old_file(tmp_path):
    # today(2026-07-20) - 90일 = 2026-04-21. 딱 90일 된 파일은 아직 보관 대상(포함),
    # 하루 더 지난 파일부터 삭제 대상.
    cutoff_day = tmp_path / "gex_snapshot" / "snap_2026-04-21.jsonl"
    one_day_older = tmp_path / "gex_snapshot" / "snap_2026-04-20.jsonl"
    _touch(cutoff_day)
    _touch(one_day_older)

    expired = find_expired_files(tmp_path, retention_days=90, today=TODAY)

    assert expired == [one_day_older]


def test_prune_deletes_expired_files(tmp_path):
    old = tmp_path / "cross_venue_skew" / "binance_BTC_2026-01-01.jsonl"
    recent = tmp_path / "cross_venue_skew" / "binance_BTC_2026-07-19.jsonl"
    _touch(old)
    _touch(recent)

    deleted = prune(tmp_path, retention_days=90, dry_run=False)

    assert deleted == [old]
    assert not old.exists()
    assert recent.exists()


def test_prune_dry_run_does_not_delete(tmp_path):
    old = tmp_path / "cross_venue_skew" / "binance_BTC_2026-01-01.jsonl"
    _touch(old)

    deleted = prune(tmp_path, retention_days=90, dry_run=True)

    assert deleted == [old]
    assert old.exists()
