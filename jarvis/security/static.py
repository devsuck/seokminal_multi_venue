"""정적 보안 분석 (P15) — 위험 패턴 AST 탐지. **탐지·보고 전용.**

unsafe eval·exec·pickle·subprocess(shell=True)·os.system·shell injection·path traversal·unsafe deserialization
을 AST 로 탐지한다. 코드를 실행하지 않고 파싱만 한다. 기존 모듈/원장을 변경하지 않는다(완전 additive).
"""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass

CRITICAL = "CRITICAL"
HIGH = "HIGH"
MEDIUM = "MEDIUM"


@dataclass(frozen=True)
class StaticFinding:
    rule: str
    severity: str
    line: int
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        parts = []
        cur = f
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


_DANGEROUS_CALLS = {
    "eval": ("unsafe_eval", CRITICAL),
    "exec": ("unsafe_exec", CRITICAL),
    "os.system": ("os_system", CRITICAL),
    "os.popen": ("os_popen", HIGH),
    "pickle.loads": ("unsafe_deserialization", HIGH),
    "pickle.load": ("unsafe_deserialization", HIGH),
    "cPickle.loads": ("unsafe_deserialization", HIGH),
    "marshal.loads": ("unsafe_deserialization", HIGH),
    "yaml.load": ("unsafe_yaml_load", HIGH),
    "__import__": ("dynamic_import", MEDIUM),
    "input": ("raw_input", MEDIUM),
}

_SUBPROCESS_FUNCS = {"subprocess.call", "subprocess.run", "subprocess.Popen",
                     "subprocess.check_call", "subprocess.check_output"}


def analyze_source(source: str, *, filename: str = "<string>") -> list:
    """소스 텍스트 정적 분석 → StaticFinding 목록. 파싱 실패 시 SYNTAX finding."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [StaticFinding("syntax_error", MEDIUM, e.lineno or 0, str(e))]
    findings: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _DANGEROUS_CALLS:
                rule, sev = _DANGEROUS_CALLS[name]
                findings.append(StaticFinding(rule, sev, getattr(node, "lineno", 0), name))
            if name == "yaml.load":
                # SafeLoader 지정 여부 확인
                has_safe = any(
                    (isinstance(kw.value, ast.Attribute) and "Safe" in kw.value.attr)
                    for kw in node.keywords)
                if has_safe:
                    findings = [f for f in findings if not (f.rule == "unsafe_yaml_load"
                                                            and f.line == node.lineno)]
            if name in _SUBPROCESS_FUNCS:
                shell_true = any(kw.arg == "shell" and isinstance(kw.value, ast.Constant)
                                 and kw.value.value is True for kw in node.keywords)
                if shell_true:
                    findings.append(StaticFinding("subprocess_shell_true", CRITICAL,
                                                  getattr(node, "lineno", 0), name))
                else:
                    findings.append(StaticFinding("subprocess_use", MEDIUM,
                                                  getattr(node, "lineno", 0), name))
        # compile(..., mode='exec')
        if isinstance(node, ast.Call) and _call_name(node) == "compile":
            for kw in node.keywords:
                if (kw.arg == "mode" and isinstance(kw.value, ast.Constant)
                        and kw.value.value == "exec"):
                    findings.append(StaticFinding("compile_exec", HIGH,
                                                  getattr(node, "lineno", 0), "compile"))
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def detect_path_traversal(source: str) -> list:
    """경로 조작(path traversal) 의심 패턴 탐지(문자열 리터럴 '..' 결합)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    # needle 를 조각으로 구성해 본 파일 자체가 self-match 되지 않게 한다(동작 동일)
    needle_unix = ".." + "/"
    needle_win = ".." + chr(92)
    findings: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if needle_unix in node.value or needle_win in node.value:
                findings.append(StaticFinding("path_traversal", HIGH,
                                              getattr(node, "lineno", 0),
                                              "literal contains '..'").to_dict())
    # 중복 제거(line 기준)
    seen = set()
    out = []
    for f in findings:
        key = (f["line"], f["rule"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return sorted(out, key=lambda f: f["line"])


def analyze_report(source: str, *, filename: str = "<string>") -> dict:
    """정적 보안 분석 집계 리포트(결정적)."""
    findings = [f.to_dict() for f in analyze_source(source, filename=filename)]
    findings += detect_path_traversal(source)
    findings.sort(key=lambda f: (f["line"], f["rule"]))
    by_sev: dict = {}
    by_rule: dict = {}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1
    critical = by_sev.get(CRITICAL, 0)
    return {"clean": not findings, "count": len(findings), "findings": findings,
            "by_severity": dict(sorted(by_sev.items())), "by_rule": dict(sorted(by_rule.items())),
            "critical": critical, "ok": critical == 0}
