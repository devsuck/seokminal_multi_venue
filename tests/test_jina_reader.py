"""fetch_article_text — Jina Reader(r.jina.ai) 무료 URL→본문텍스트 변환. 실패시 None,
호출부가 summary로 폴백."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from api_server.jina_reader import fetch_article_text


def test_fetch_article_text_returns_body_on_success():
    mock_resp = MagicMock()
    mock_resp.text = "# Headline\n\nArticle body text."
    mock_resp.raise_for_status = MagicMock()
    with patch("api_server.jina_reader.requests.get", return_value=mock_resp) as mock_get:
        result = fetch_article_text("https://example.com/article")

    assert result == "# Headline\n\nArticle body text."
    mock_get.assert_called_once_with(
        "https://r.jina.ai/https://example.com/article", timeout=10
    )


def test_fetch_article_text_returns_none_on_http_error():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("404 Client Error")
    with patch("api_server.jina_reader.requests.get", return_value=mock_resp):
        assert fetch_article_text("https://example.com/missing") is None


def test_fetch_article_text_returns_none_on_timeout():
    with patch("api_server.jina_reader.requests.get", side_effect=requests.Timeout("timed out")):
        assert fetch_article_text("https://example.com/slow") is None


def test_fetch_article_text_returns_none_on_empty_body():
    mock_resp = MagicMock()
    mock_resp.text = "   "
    mock_resp.raise_for_status = MagicMock()
    with patch("api_server.jina_reader.requests.get", return_value=mock_resp):
        assert fetch_article_text("https://example.com/empty") is None


def test_fetch_article_text_respects_custom_timeout():
    mock_resp = MagicMock()
    mock_resp.text = "body"
    mock_resp.raise_for_status = MagicMock()
    with patch("api_server.jina_reader.requests.get", return_value=mock_resp) as mock_get:
        fetch_article_text("https://example.com/article", timeout=3)

    mock_get.assert_called_once_with("https://r.jina.ai/https://example.com/article", timeout=3)


def test_fetch_article_text_returns_none_on_empty_url():
    with patch("api_server.jina_reader.requests.get") as mock_get:
        result = fetch_article_text("")

    assert result is None
    mock_get.assert_not_called()


def test_fetch_article_text_returns_none_on_none_url():
    with patch("api_server.jina_reader.requests.get") as mock_get:
        result = fetch_article_text(None)

    assert result is None
    mock_get.assert_not_called()
