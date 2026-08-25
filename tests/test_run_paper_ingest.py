import json
from unittest.mock import patch

import research.run_paper_ingest as ingest


def _paper(id="1234.5678", title="Momentum Test", published="2026-07-10T00:00:00Z", pdf_url="http://x/1.pdf"):
    return {"id": id, "title": title, "abstract": "a", "published": published, "pdf_url": pdf_url}


def test_process_paper_accepted_writes_module_file(tmp_path):
    with patch.object(ingest, "_HYPOTHESES_DIR", tmp_path), \
         patch.object(ingest, "download_pdf_text", return_value="paper text"), \
         patch.object(ingest, "extract_spec", return_value={"asset_class": "equity_intraday", "signal_description": "d"}), \
         patch.object(ingest, "rejection_reason", return_value=None), \
         patch.object(ingest, "generate_signal_code",
                       return_value="NAME = 'x'\nDESCRIPTION = 'd'\ndef signal_fn(o,f,a,p):\n    return {'entry': [], 'eligible': []}\n"), \
         patch.object(ingest, "smoke_check", return_value=(True, "")):
        status = ingest.process_paper(_paper())
    assert status == "accepted"
    files = list(tmp_path.glob("*.py"))
    assert len(files) == 1
    assert "signal_fn" in files[0].read_text()
    assert "1234.5678" in files[0].read_text()


def test_process_paper_strips_markdown_fence_before_smoke_check_and_write(tmp_path):
    fenced_code = (
        "```python\n"
        "NAME = 'x'\n"
        "DESCRIPTION = 'd'\n"
        "def signal_fn(o,f,a,p):\n"
        "    return {'entry': [], 'eligible': []}\n"
        "```"
    )
    with patch.object(ingest, "_HYPOTHESES_DIR", tmp_path), \
         patch.object(ingest, "download_pdf_text", return_value="paper text"), \
         patch.object(ingest, "extract_spec", return_value={"asset_class": "equity_intraday", "signal_description": "d"}), \
         patch.object(ingest, "rejection_reason", return_value=None), \
         patch.object(ingest, "generate_signal_code", return_value=fenced_code), \
         patch.object(ingest, "smoke_check", return_value=(True, "")):
        status = ingest.process_paper(_paper())
    assert status == "accepted"
    files = list(tmp_path.glob("*.py"))
    assert len(files) == 1
    assert "```" not in files[0].read_text()


def test_process_paper_coverage_reject_logs_and_skips_codegen(tmp_path):
    rejected_path = tmp_path / "rejected.jsonl"
    with patch.object(ingest, "_REJECTED_PATH", rejected_path), \
         patch.object(ingest, "download_pdf_text", return_value="paper text"), \
         patch.object(ingest, "extract_spec", return_value={"asset_class": "options"}), \
         patch.object(ingest, "rejection_reason", return_value="자산군 미지원: 'options'"), \
         patch.object(ingest, "generate_signal_code") as mock_codegen:
        status = ingest.process_paper(_paper())
    assert status == "coverage_reject"
    mock_codegen.assert_not_called()
    logged = json.loads(rejected_path.read_text().strip())
    assert logged["stage"] == "coverage_filter"


def test_process_paper_smoke_reject_does_not_write_file(tmp_path):
    with patch.object(ingest, "_HYPOTHESES_DIR", tmp_path), \
         patch.object(ingest, "_REJECTED_PATH", tmp_path / "rejected.jsonl"), \
         patch.object(ingest, "download_pdf_text", return_value="paper text"), \
         patch.object(ingest, "extract_spec", return_value={"asset_class": "equity_intraday"}), \
         patch.object(ingest, "rejection_reason", return_value=None), \
         patch.object(ingest, "generate_signal_code", return_value="broken code((("), \
         patch.object(ingest, "smoke_check", return_value=(False, "exec 실패")):
        status = ingest.process_paper(_paper())
    assert status == "smoke_reject"
    assert list(tmp_path.glob("*.py")) == []


def test_process_paper_pdf_download_error_logs_and_stops():
    with patch.object(ingest, "_REJECTED_PATH", "unused"), \
         patch.object(ingest, "_log_rejected") as mock_log, \
         patch.object(ingest, "download_pdf_text", side_effect=RuntimeError("404")), \
         patch.object(ingest, "extract_spec") as mock_extract:
        status = ingest.process_paper(_paper())
    assert status == "pdf_error"
    mock_extract.assert_not_called()
    mock_log.assert_called_once()


def test_main_advances_cursor_to_max_published_among_new_papers():
    papers = [_paper(id="1", published="2026-07-10T00:00:00Z"),
              _paper(id="2", published="2026-07-12T00:00:00Z")]
    with patch.object(ingest, "load_cursor", return_value=None), \
         patch.object(ingest, "fetch_papers", return_value=papers), \
         patch.object(ingest, "filter_new_papers", return_value=papers), \
         patch.object(ingest, "process_paper", return_value="accepted") as mock_process, \
         patch.object(ingest, "save_cursor") as mock_save:
        result = ingest.main()
    assert mock_process.call_count == 2
    mock_save.assert_called_once_with("2026-07-12T00:00:00Z", ["2"])
    assert result["counts"] == {"accepted": 2}
    assert result["n_fetched"] == 2
    assert result["n_new"] == 2


def test_main_holds_cursor_at_pdf_error_paper_for_retry_next_cycle():
    papers = [_paper(id="1", published="2026-07-10T00:00:00Z"),
              _paper(id="2", published="2026-07-12T00:00:00Z")]
    with patch.object(ingest, "load_cursor", return_value=None), \
         patch.object(ingest, "fetch_papers", return_value=papers), \
         patch.object(ingest, "filter_new_papers", return_value=papers), \
         patch.object(ingest, "process_paper", side_effect=["accepted", "pdf_error"]), \
         patch.object(ingest, "save_cursor") as mock_save:
        result = ingest.main()
    mock_save.assert_called_once_with("2026-07-10T00:00:00Z", ["1"])
    assert result["counts"] == {"accepted": 1, "pdf_error": 1}


def test_main_does_not_advance_cursor_when_no_new_papers():
    with patch.object(ingest, "load_cursor", return_value="2026-07-12T00:00:00Z"), \
         patch.object(ingest, "fetch_papers", return_value=[]), \
         patch.object(ingest, "filter_new_papers", return_value=[]), \
         patch.object(ingest, "save_cursor") as mock_save:
        result = ingest.main()
    mock_save.assert_not_called()
    assert result["counts"] == {}
