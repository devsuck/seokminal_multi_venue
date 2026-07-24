"""시크릿 스캐너 (P15) — 하드코딩 자격증명 탐지. **탐지·보고 전용, 값 마스킹.**

API 키·비밀번호·개인키·토큰·AWS/OpenAI/GitHub/Slack 자격증명·JWT·SSH 키를 정규식으로 탐지하고, 발견 값은 마스킹하여
보고한다. 자격증명을 저장·전송·실행하지 않는다. 기존 모듈/원장을 변경하지 않는다(완전 additive).
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass

CRITICAL = "CRITICAL"
HIGH = "HIGH"
MEDIUM = "MEDIUM"

# (rule, severity, compiled pattern) — 정규식은 문자 클래스라 자체가 시크릿이 아니다
_PATTERNS = [
    ("aws_access_key", CRITICAL, re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("aws_secret_key", CRITICAL,
     re.compile(r"(?i)aws.{0,20}?(secret|key).{0,5}?[=:]\s*['\"][A-Za-z0-9/+=]{40}['\"]")),
    ("openai_key", CRITICAL, re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("github_token", CRITICAL,
     re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("slack_token", HIGH, re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google_api_key", HIGH, re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("jwt", HIGH, re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("private_key_block", CRITICAL,
     re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),  # pragma: allowlist secret
    ("ssh_private_key", CRITICAL,
     re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----")),  # pragma: allowlist secret
    ("generic_api_key", HIGH,
     re.compile(r"(?i)(api[_-]?key|apikey|access[_-]?token)\s*[=:]\s*['\"][A-Za-z0-9_\-]{16,}['\"]")),
    ("hardcoded_password", HIGH,
     re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"][^'\"]{6,}['\"]")),
    ("bearer_token", MEDIUM, re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.=]{20,}")),
    ("generic_secret", HIGH,
     re.compile(r"(?i)(secret|token)\s*[=:]\s*['\"][A-Za-z0-9_\-]{16,}['\"]")),
]

# 인라인 억제 마커(detect-secrets 관례) — 해당 줄의 시크릿 발견 무시
_ALLOWLIST = re.compile(r"#\s*(pragma:\s*allowlist\s*secret|nosec|nosecret)")

# 명백한 플레이스홀더(오탐 억제)
_PLACEHOLDERS = re.compile(
    r"(?i)(\byour\b|_here\b|example|placeholder|xxxx|<[^>]+>|\$\{[^}]+\}|dummy|changeme|redacted|"
    r"todo|fixme|test[_-]?key|fake|sample|insert[_-]?|my[_-]?(key|secret|token))")


@dataclass(frozen=True)
class SecretFinding:
    rule: str
    severity: str
    line: int
    column: int
    redacted: str

    def to_dict(self) -> dict:
        return asdict(self)


def redact(secret: str) -> str:
    """시크릿 마스킹: 앞 4 · 뒤 2 문자만 노출, 중간 '*'."""
    s = secret.strip().strip("'\"")
    if len(s) <= 8:
        return s[0] + "*" * (len(s) - 1) if s else ""
    return s[:4] + "*" * (len(s) - 6) + s[-2:]


def shannon_entropy(s: str) -> float:
    """샤논 엔트로피(비트/문자). 고엔트로피 토큰 판별 보조."""
    if not s:
        return 0.0
    counts: dict = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return round(-sum((c / n) * math.log2(c / n) for c in counts.values()), 6)


def _is_placeholder(text: str) -> bool:
    return bool(_PLACEHOLDERS.search(text))


def scan_line(line: str, lineno: int = 1, *, ignore_placeholders: bool = True) -> list:
    """한 줄 스캔 → SecretFinding 목록. `# pragma: allowlist secret`/`# nosec` 줄은 억제."""
    if _ALLOWLIST.search(line):
        return []
    findings = []
    for rule, sev, pat in _PATTERNS:
        for m in pat.finditer(line):
            token = m.group(0)
            if ignore_placeholders and _is_placeholder(token):
                continue
            findings.append(SecretFinding(rule=rule, severity=sev, line=lineno,
                                          column=m.start() + 1, redacted=redact(token)))
    return findings


def scan_text(text: str, *, ignore_placeholders: bool = True) -> list:
    """멀티라인 텍스트 스캔 → SecretFinding 목록(줄 순)."""
    out = []
    for i, line in enumerate(text.splitlines(), start=1):
        out.extend(scan_line(line, i, ignore_placeholders=ignore_placeholders))
    return out


def scan_report(text: str, *, ignore_placeholders: bool = True) -> dict:
    """시크릿 스캔 집계 리포트(결정적)."""
    findings = [f.to_dict() for f in scan_text(text, ignore_placeholders=ignore_placeholders)]
    findings.sort(key=lambda f: (f["line"], f["column"], f["rule"]))
    by_sev: dict = {}
    by_rule: dict = {}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1
    return {"clean": not findings, "count": len(findings), "findings": findings,
            "by_severity": dict(sorted(by_sev.items())), "by_rule": dict(sorted(by_rule.items()))}
