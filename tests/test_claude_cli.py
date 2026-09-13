"""api_server.claude_cli — API/CLI 이중 경로 테스트. 실호출 없음, 전부 monkeypatch."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import api_server.claude_cli as cc


def test_claude_available_true_with_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(cc, "claude_bin", lambda: None)
    assert cc.claude_available() is True


def test_claude_available_true_with_cli_only(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cc, "claude_bin", lambda: "/usr/local/bin/claude")
    assert cc.claude_available() is True


def test_claude_available_false_with_neither(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cc, "claude_bin", lambda: None)
    assert cc.claude_available() is False


def test_call_claude_prefers_api_when_key_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    block = MagicMock(type="text", text="api result")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(content=[block])
    with patch("subprocess.run") as mock_run:
        with patch("anthropic.Anthropic", return_value=mock_client) as mock_ctor:
            out = cc.call_claude("/usr/local/bin/claude", "hello", timeout=42)
    assert out == "api result"
    mock_run.assert_not_called()
    assert mock_ctor.call_args.kwargs["api_key"] == "sk-test"
    assert mock_client.messages.create.call_args.kwargs["model"] == cc._MODEL


def test_call_claude_falls_back_to_cli_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    proc = MagicMock(stdout="cli result\n")
    with patch("subprocess.run", return_value=proc) as mock_run:
        out = cc.call_claude("/usr/local/bin/claude", "hello", timeout=42)
    assert out == "cli result"
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["timeout"] == 42


def test_call_claude_returns_empty_with_neither(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = cc.call_claude(None, "hello")
    assert out == ""


def test_call_claude_returns_empty_on_api_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with patch("anthropic.Anthropic", side_effect=RuntimeError("boom")):
        out = cc.call_claude("/usr/local/bin/claude", "hello")
    assert out == ""
