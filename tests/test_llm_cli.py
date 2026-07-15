import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from research.papers.llm_cli import call_claude, LLMCallError


def _cli_payload(result="Yo.", is_error=False):
    return json.dumps({
        "type": "result", "subtype": "success", "is_error": is_error,
        "duration_ms": 2592, "result": result, "session_id": "abc",
        "total_cost_usd": 0.1057719,
    })


def test_call_claude_extracts_result_field():
    proc = MagicMock(stdout=_cli_payload(result="hello world"), returncode=0)
    with patch("subprocess.run", return_value=proc) as mock_run:
        out = call_claude("say hi")
    assert out == "hello world"
    args, kwargs = mock_run.call_args
    assert args[0] == ["claude", "-p", "say hi", "--output-format", "json", "--allowedTools", ""]
    assert kwargs["timeout"] == 300


def test_call_claude_custom_timeout_passed_through():
    proc = MagicMock(stdout=_cli_payload(), returncode=0)
    with patch("subprocess.run", return_value=proc) as mock_run:
        call_claude("say hi", timeout=60)
    assert mock_run.call_args.kwargs["timeout"] == 60


def test_call_claude_raises_on_is_error_true():
    proc = MagicMock(stdout=_cli_payload(is_error=True), returncode=0)
    with patch("subprocess.run", return_value=proc):
        with pytest.raises(LLMCallError):
            call_claude("say hi")


def test_call_claude_raises_on_malformed_json():
    proc = MagicMock(stdout="not json{{{", returncode=0)
    with patch("subprocess.run", return_value=proc):
        with pytest.raises(LLMCallError):
            call_claude("say hi")


def test_call_claude_raises_on_missing_result_field():
    proc = MagicMock(stdout=json.dumps({"type": "result", "is_error": False}), returncode=0)
    with patch("subprocess.run", return_value=proc):
        with pytest.raises(LLMCallError):
            call_claude("say hi")


def test_call_claude_raises_on_subprocess_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=300)):
        with pytest.raises(LLMCallError):
            call_claude("say hi")


def test_call_claude_raises_on_nonzero_exit():
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "claude")):
        with pytest.raises(LLMCallError):
            call_claude("say hi")


def test_call_claude_raises_on_missing_binary():
    with patch("subprocess.run", side_effect=FileNotFoundError("claude: command not found")):
        with pytest.raises(LLMCallError):
            call_claude("say hi")
