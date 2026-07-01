"""Order audit trail: append-only JSONL with read-back."""
from api_server.order_audit import read_recent, record_order


def test_record_and_read_back(tmp_path):
    p = tmp_path / "audit.jsonl"
    record_order(
        venue="US", request={"symbol": "AAPL", "side": "BUY", "quantity": 10},
        result={"order_id": 1, "status": "Submitted"}, status="submitted", path=p,
    )
    entries = read_recent(path=p)
    assert len(entries) == 1
    assert entries[0]["venue"] == "US"
    assert entries[0]["status"] == "submitted"
    assert entries[0]["request"]["symbol"] == "AAPL"
    assert "ts" in entries[0]


def test_appends_multiple_newest_last(tmp_path):
    p = tmp_path / "audit.jsonl"
    for i in range(3):
        record_order(
            venue="KR", request={"code": "005930", "quantity": i + 1},
            result=None, status="rejected", path=p,
        )
    entries = read_recent(path=p)
    assert len(entries) == 3
    assert entries[-1]["request"]["quantity"] == 3


def test_read_recent_limit(tmp_path):
    p = tmp_path / "audit.jsonl"
    for i in range(10):
        record_order(venue="HL", request={"n": i}, result=None, status="submitted", path=p)
    entries = read_recent(limit=4, path=p)
    assert len(entries) == 4
    assert entries[-1]["request"]["n"] == 9


def test_read_missing_file_returns_empty(tmp_path):
    assert read_recent(path=tmp_path / "nope.jsonl") == []
