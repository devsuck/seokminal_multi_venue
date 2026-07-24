"""P15 security 테스트 — 시크릿 탐지·마스킹·정적 분석·경로조작·통합 리포트·보안.

주: 테스트 내 자격증명은 모두 합성(정규식 문자클래스 만족용 더미)이며 실제 유효 키가 아니다.
"""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.security import report as REP
from jarvis.security import secrets as SEC
from jarvis.security import static as ST
from jarvis.security.secrets import redact, scan_report, scan_text, shannon_entropy
from jarvis.security.static import analyze_report, analyze_source, detect_path_traversal

# 합성 더미 토큰(실제 자격증명 아님) — 32~40 길이 문자클래스 충족용
_A = "A" * 16
_HEX40 = "b" * 40
_LONG = "x" * 36


# ═══════════════ 시크릿: 탐지 ═══════════════
def test_detect_aws_access_key():
    out = scan_text(f"key = 'AKIA{_A}'")
    assert any(f.rule == "aws_access_key" for f in out)


def test_detect_openai_key():
    out = scan_text("k = 'sk-" + "a" * 24 + "'")
    assert any(f.rule == "openai_key" for f in out)


def test_detect_github_token():
    out = scan_text("t = 'ghp_" + "a" * 36 + "'")
    assert any(f.rule == "github_token" for f in out)


def test_detect_slack_token():
    out = scan_text("t = 'xoxb-" + "1" * 12 + "'")
    assert any(f.rule == "slack_token" for f in out)


def test_detect_jwt():
    jwt = "eyJ" + "a" * 12 + ".eyJ" + "b" * 12 + "." + "c" * 12
    out = scan_text(f"tok = '{jwt}'")
    assert any(f.rule == "jwt" for f in out)


def test_detect_private_key_block():
    out = scan_text("-----BEGIN RSA PRIVATE KEY-----")
    assert any(f.rule == "private_key_block" for f in out)


def test_detect_ssh_key():
    out = scan_text("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert any(f.rule in ("ssh_private_key", "private_key_block") for f in out)


def test_detect_generic_api_key():
    out = scan_text("api_key = 'abcd1234efgh5678ij'")
    assert any(f.rule == "generic_api_key" for f in out)


def test_detect_password():
    out = scan_text("password = 'sup3rs3cret'")
    assert any(f.rule == "hardcoded_password" for f in out)


def test_detect_google_api_key():
    out = scan_text("k = 'AIza" + "a" * 35 + "'")
    assert any(f.rule == "google_api_key" for f in out)


def test_detect_bearer():
    out = scan_text("Authorization: Bearer " + "a" * 24)
    assert any(f.rule == "bearer_token" for f in out)


def test_detect_generic_secret():
    out = scan_text("secret = 'abcdefghij1234567890'")
    assert any(f.rule == "generic_secret" for f in out)


# ═══════════════ 시크릿: 오탐 억제 ═══════════════
def test_placeholder_ignored():
    out = scan_text("api_key = 'YOUR_API_KEY_HERE'")
    assert out == []


def test_placeholder_example_ignored():
    out = scan_text("password = 'example_password'")
    assert out == []


def test_placeholder_disabled():
    out = scan_text("api_key = 'YOUR_API_KEY_HERE'", ignore_placeholders=False)
    assert len(out) >= 1


def test_clean_text():
    out = scan_text("x = 1\ny = 'hello world'")
    assert out == []


# ═══════════════ 마스킹 ═══════════════
def test_allowlist_pragma_suppresses():
    out = scan_text("api_key = 'abcd1234efgh5678ij'  # pragma: allowlist secret")
    assert out == []


def test_nosec_suppresses():
    out = scan_text("password = 'realsecret123'  # nosec")
    assert out == []


def test_allowlist_only_that_line():
    text = ("api_key = 'abcd1234efgh5678ij'  # pragma: allowlist secret\n"
            "password = 'anothersecret1'")
    out = scan_text(text)
    assert len(out) == 1
    assert out[0].line == 2


def test_p15_secrets_self_scan_clean():
    import jarvis.security.secrets as mod
    src = open(mod.__file__).read()
    assert scan_report(src)["clean"] is True


def test_redact_long():
    r = redact("AKIA1234567890ABCDEF")
    assert r.startswith("AKIA")
    assert "*" in r
    assert not r.endswith("CDEF")


def test_redact_short():
    r = redact("abc")
    assert r.startswith("a")
    assert r.count("*") == 2


def test_redact_no_full_secret():
    secret = "sk-abcdefghij1234567890"
    r = redact(secret)
    assert secret not in r


@pytest.mark.parametrize("secret", ["AKIA1234567890ABCDEF", "ghp_" + "a" * 36, "x" * 50])
def test_redact_masks(secret):
    assert "*" in redact(secret)


# ═══════════════ 엔트로피 ═══════════════
def test_entropy_zero_single_char():
    assert shannon_entropy("aaaa") == 0.0


def test_entropy_high_random():
    assert shannon_entropy("aB3xZ9qL") > 2.0


def test_entropy_empty():
    assert shannon_entropy("") == 0.0


# ═══════════════ 시크릿 리포트 ═══════════════
def test_scan_report_clean():
    assert scan_report("x = 1")["clean"] is True


def test_scan_report_counts():
    text = f"a = 'AKIA{_A}'\npassword = 'longenough'"
    rep = scan_report(text)
    assert rep["count"] >= 2


def test_scan_report_by_severity():
    rep = scan_report(f"a = 'AKIA{_A}'")
    assert rep["by_severity"].get("CRITICAL", 0) >= 1


def test_scan_report_deterministic():
    text = f"a = 'AKIA{_A}'"
    assert scan_report(text) == scan_report(text)


def test_scan_report_line_numbers():
    text = "x=1\ny=2\npassword = 'secretvalue'"
    rep = scan_report(text)
    assert rep["findings"][0]["line"] == 3


def test_finding_frozen():
    f = SEC.SecretFinding("r", "HIGH", 1, 1, "x")
    with pytest.raises(Exception):
        f.rule = "y"


# ═══════════════ 정적: 위험 호출 ═══════════════
def test_static_eval():
    out = analyze_source("eval('1+1')")
    assert any(f.rule == "unsafe_eval" for f in out)


def test_static_exec():
    out = analyze_source("exec('x=1')")
    assert any(f.rule == "unsafe_exec" for f in out)


def test_static_os_system():
    out = analyze_source("import os\nos.system('ls')")
    assert any(f.rule == "os_system" for f in out)


def test_static_pickle_loads():
    out = analyze_source("import pickle\npickle.loads(b'')")
    assert any(f.rule == "unsafe_deserialization" for f in out)


def test_static_marshal():
    out = analyze_source("import marshal\nmarshal.loads(b'')")
    assert any(f.rule == "unsafe_deserialization" for f in out)


def test_static_subprocess_shell_true():
    out = analyze_source("import subprocess\nsubprocess.run('ls', shell=True)")
    assert any(f.rule == "subprocess_shell_true" for f in out)


def test_static_subprocess_no_shell():
    out = analyze_source("import subprocess\nsubprocess.run(['ls'])")
    assert any(f.rule == "subprocess_use" for f in out)
    assert not any(f.rule == "subprocess_shell_true" for f in out)


def test_static_yaml_load_unsafe():
    out = analyze_source("import yaml\nyaml.load(x)")
    assert any(f.rule == "unsafe_yaml_load" for f in out)


def test_static_yaml_safe_loader_ok():
    out = analyze_source("import yaml\nyaml.load(x, Loader=yaml.SafeLoader)")
    assert not any(f.rule == "unsafe_yaml_load" for f in out)


def test_static_dynamic_import():
    out = analyze_source("__import__('os')")
    assert any(f.rule == "dynamic_import" for f in out)


def test_static_compile_exec():
    out = analyze_source("compile(src, 'f', mode='exec')")
    assert any(f.rule == "compile_exec" for f in out)


def test_static_clean():
    out = analyze_source("x = 1\ndef f():\n    return x + 1")
    assert out == []


def test_static_syntax_error():
    out = analyze_source("def (:")
    assert any(f.rule == "syntax_error" for f in out)


# ═══════════════ 정적: path traversal ═══════════════
def test_path_traversal():
    out = detect_path_traversal("p = '../../etc/passwd'")
    assert len(out) == 1
    assert out[0]["rule"] == "path_traversal"


def test_path_traversal_clean():
    assert detect_path_traversal("p = 'data/file.txt'") == []


def test_path_traversal_windows():
    out = detect_path_traversal(r"p = '..\\windows'")
    assert len(out) == 1


# ═══════════════ 정적 리포트 ═══════════════
def test_analyze_report_clean():
    assert analyze_report("x = 1")["clean"] is True


def test_analyze_report_critical():
    rep = analyze_report("eval('x')")
    assert rep["critical"] >= 1
    assert rep["ok"] is False


def test_analyze_report_deterministic():
    src = "eval('x')\nos.system('y')"
    assert analyze_report(src) == analyze_report(src)


def test_analyze_report_by_rule():
    rep = analyze_report("eval('a')\neval('b')")
    assert rep["by_rule"]["unsafe_eval"] == 2


def test_analyze_report_ok_when_no_critical():
    rep = analyze_report("__import__('os')")  # MEDIUM only
    assert rep["ok"] is True


# ═══════════════ 통합 리포트 ═══════════════
def test_scan_source_combined():
    src = f"api_key = 'abcd1234efgh5678ij'\neval('x')"
    rep = REP.scan_source(src)
    assert rep["secrets"]["count"] >= 1
    assert rep["static"]["count"] >= 1
    assert rep["clean"] is False


def test_scan_source_clean():
    assert REP.scan_source("x = 1")["clean"] is True


def test_scan_files():
    files = {"a.py": "eval('x')", "b.py": "x = 1"}
    rep = REP.scan_files(files)
    assert rep["file_count"] == 2
    assert rep["total_static"] >= 1


def test_scan_files_deterministic():
    files = {"a.py": "password = 'longsecret'"}
    assert REP.scan_files(files) == REP.scan_files(files)


def test_scan_files_clean():
    assert REP.scan_files({"a.py": "x=1"})["clean"] is True


# ═══════════════ 파라미터화 ═══════════════
@pytest.mark.parametrize("code,rule", [
    ("eval('x')", "unsafe_eval"),
    ("exec('x')", "unsafe_exec"),
    ("os.system('x')", "os_system"),
    ("pickle.loads(b'')", "unsafe_deserialization"),
    ("__import__('x')", "dynamic_import"),
])
def test_static_rules_param(code, rule):
    assert any(f.rule == rule for f in analyze_source(code))


@pytest.mark.parametrize("prefix", ["AKIA", "ASIA"])
def test_aws_prefixes(prefix):
    out = scan_text(f"k = '{prefix}{_A}'")
    assert any(f.rule == "aws_access_key" for f in out)


@pytest.mark.parametrize("gh", ["ghp_", "gho_", "ghs_", "ghu_", "ghr_"])
def test_github_prefixes(gh):
    out = scan_text(f"t = '{gh}{'a' * 36}'")
    assert any(f.rule == "github_token" for f in out)


# ═══════════════ 자기 보안(P15 security 소스는 실제 시크릿/위험 호출 없음) ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN = ("jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
              "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order")


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN), node.module


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_self_no_dangerous_calls(path):
    # P15 security 소스는 eval/exec/os.system/pickle.loads 를 실제로 호출하지 않는다
    rep = analyze_report(open(path).read())
    assert rep["critical"] == 0, rep["findings"]
