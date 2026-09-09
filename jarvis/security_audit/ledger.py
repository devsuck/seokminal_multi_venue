"""Security Audit 원장 (P38) — 4개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 secaud_ 접두사(SECurity AUDit). 각 레코드: id · timestamp · previous_hash · record_hash. 감사 실행·발견·
보안 리포트 기록만 — 실행·변경 없음. 감사 대상 계층은 정적 검사만(import 결합 없음, 변경 없음).
"""
from __future__ import annotations


from jarvis.ledger_io import append as _append, read_jsonl, head as _head, exists as _exists

AUDITS = ("secaud_audits.jsonl", "audit_id")
FINDINGS = ("secaud_findings.jsonl", "finding_id")
REPORTS = ("secaud_reports.jsonl", "report_id")
ARTIFACTS = ("secaud_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (AUDITS, FINDINGS, REPORTS, ARTIFACTS)


def _readers(spec):
    fname, idf = spec

    def append(rec):
        _append(fname, rec)

    def read():
        return read_jsonl(fname)

    def head():
        return _head(fname)

    def exists(rid):
        return _exists(fname, idf, rid)

    return append, read, head, exists


append_audit, read_audits, audits_head, audit_exists = _readers(AUDITS)
append_finding, read_findings, findings_head, finding_exists = _readers(FINDINGS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)
