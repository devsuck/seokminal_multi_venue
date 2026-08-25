import json
from unittest.mock import patch, MagicMock, call

import pytest
import requests

from research.papers.arxiv_fetcher import (
    load_cursor, save_cursor, fetch_papers, filter_new_papers,
)

_ATOM_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2601.00001v1</id>
    <title>Momentum Signals in Intraday Equity Markets</title>
    <summary>We study intraday momentum signals.</summary>
    <published>2026-07-10T00:00:00Z</published>
    <link title="pdf" href="http://arxiv.org/pdf/2601.00001v1" rel="related" type="application/pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2601.00002v1</id>
    <title>Options Volatility Risk Premium</title>
    <summary>We study the vol risk premium.</summary>
    <published>2026-07-11T00:00:00Z</published>
    <link title="pdf" href="http://arxiv.org/pdf/2601.00002v1" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""


def test_load_cursor_returns_none_when_file_missing(tmp_path):
    path = str(tmp_path / "cursor.json")
    assert load_cursor(path) is None


def test_save_and_load_cursor_roundtrip(tmp_path):
    path = str(tmp_path / "cursor.json")
    save_cursor("2026-07-11T00:00:00Z", path=path)
    assert load_cursor(path) == "2026-07-11T00:00:00Z"


def test_fetch_papers_parses_atom_feed():
    resp = MagicMock(text=_ATOM_RESPONSE, status_code=200)
    resp.raise_for_status = MagicMock()
    with patch("requests.get", return_value=resp):
        papers = fetch_papers(max_results=10)
    assert len(papers) == 2
    assert papers[0]["id"] == "2601.00001v1"
    assert papers[0]["title"] == "Momentum Signals in Intraday Equity Markets"
    assert papers[0]["pdf_url"] == "http://arxiv.org/pdf/2601.00001v1"
    assert papers[0]["published"] == "2026-07-10T00:00:00Z"


def test_fetch_papers_retries_on_failure_then_succeeds():
    resp_ok = MagicMock(text=_ATOM_RESPONSE, status_code=200)
    resp_ok.raise_for_status = MagicMock()
    with patch("requests.get", side_effect=[requests.ConnectionError("boom"), resp_ok]) as mock_get, \
         patch("time.sleep"):
        papers = fetch_papers(max_results=10)
    assert len(papers) == 2
    assert mock_get.call_count == 2


def test_fetch_papers_raises_after_max_retries():
    with patch("requests.get", side_effect=requests.ConnectionError("boom")) as mock_get, \
         patch("time.sleep") as mock_sleep:
        with pytest.raises(RuntimeError):
            fetch_papers(max_results=10)
    assert mock_get.call_count == 4
    assert mock_sleep.call_args_list == [call(1), call(2), call(4)]


def test_download_pdf_text_extracts_and_joins_pages():
    resp = MagicMock(content=b"fake-pdf-bytes")
    resp.raise_for_status = MagicMock()
    page1 = MagicMock()
    page1.extract_text.return_value = "Page one text"
    page2 = MagicMock()
    page2.extract_text.return_value = "Page two text"
    mock_pdf = MagicMock()
    mock_pdf.pages = [page1, page2]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    with patch("requests.get", return_value=resp), \
         patch("pdfplumber.open", return_value=mock_pdf):
        from research.papers.arxiv_fetcher import download_pdf_text
        text = download_pdf_text("http://arxiv.org/pdf/2601.00001v1")
    assert text == "Page one text\nPage two text"


def test_filter_new_papers_keeps_only_after_cursor():
    papers = [
        {"id": "1", "published": "2026-07-10T00:00:00Z"},
        {"id": "2", "published": "2026-07-12T00:00:00Z"},
    ]
    out = filter_new_papers(papers, last_seen="2026-07-11T00:00:00Z")
    assert [p["id"] for p in out] == ["2"]


def test_filter_new_papers_keeps_all_when_no_cursor():
    papers = [{"id": "1", "published": "2026-07-10T00:00:00Z"}]
    out = filter_new_papers(papers, last_seen=None)
    assert [p["id"] for p in out] == ["1"]
