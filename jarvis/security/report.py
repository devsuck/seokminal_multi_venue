"""보안 통합 리포트 (P15) — 시크릿 + 정적 분석 집계. **탐지·보고 전용·결정적.**"""
from __future__ import annotations

from jarvis.security import secrets as _sec
from jarvis.security import static as _stat


def scan_source(source: str, *, ignore_placeholders: bool = True) -> dict:
    """단일 소스에 대한 시크릿+정적 통합 리포트."""
    secret = _sec.scan_report(source, ignore_placeholders=ignore_placeholders)
    static = _stat.analyze_report(source)
    total = secret["count"] + static["count"]
    return {"clean": total == 0, "total_findings": total, "secrets": secret, "static": static,
            "ok": static["ok"]}


def scan_files(files: dict, *, ignore_placeholders: bool = True) -> dict:
    """다중 파일 스캔. files: {path: source} → 결정적 집계 리포트."""
    per_file = {}
    total_secrets = 0
    total_static = 0
    for path in sorted(files):
        rep = scan_source(files[path], ignore_placeholders=ignore_placeholders)
        per_file[path] = rep
        total_secrets += rep["secrets"]["count"]
        total_static += rep["static"]["count"]
    return {"file_count": len(files), "total_secrets": total_secrets,
            "total_static": total_static, "clean": total_secrets == 0 and total_static == 0,
            "files": per_file}
