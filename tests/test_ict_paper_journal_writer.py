import csv

from research.ict.paper.journal_writer import append_trade_row


def test_append_trade_row_creates_file_with_header_and_row(tmp_path):
    path = str(tmp_path / "journal.csv")
    append_trade_row(
        path, entered_ts=1700000000.0, symbol="BTC.HL", direction="long",
        ict_context="CISD+OB", of_trigger="absorption", level_basis="OB",
        entry=101.0, stop=99.0, target=105.0, risk_r=1.0, result_r=2.0, note="test",
    )
    with open(path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTC.HL"
    assert rows[0]["direction"] == "long"
    assert rows[0]["result_r"] == "2.0"


def test_append_trade_row_appends_without_duplicating_header(tmp_path):
    path = str(tmp_path / "journal.csv")
    for i in range(2):
        append_trade_row(
            path, entered_ts=1700000000.0 + i, symbol="BTC.HL", direction="long",
            ict_context="CISD+OB", of_trigger="absorption", level_basis="OB",
            entry=101.0, stop=99.0, target=105.0, risk_r=1.0, result_r=2.0, note="",
        )
    with open(path) as f:
        lines = f.readlines()
    assert lines[0].startswith("datetime,")
    assert len(lines) == 3  # 헤더 1 + 행 2
