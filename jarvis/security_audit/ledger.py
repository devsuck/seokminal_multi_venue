"""Security Audit 원장 (P38) — 4개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 secaud_ 접두사(SECurity AUDit). 각 레코드: id · timestamp · previous_hash · record_hash. 감사 실행·발견·
보안 리포트 기록만 — 실행·변경 없음. 감사 대상 계층은 정적 검사만(import 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

AUDITS = ("secaud_audits.jsonl", "audit_id")
FINDINGS = ("secaud_findings.jsonl", "finding_id")
REPORTS = ("secaud_reports.jsonl", "report_id")
ARTIFACTS = ("secaud_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (AUDITS, FINDINGS, REPORTS, ARTIFACTS)


def _append(filename, record) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename) -> list[dict]:
    p = state_path(filename)
    if not os.path.exists(p):
        return []
    out: list[dict] = []
    with open(p) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except (ValueError, json.JSONDecodeError):
                continue
    return out


def _head(filename):
    recs = read_jsonl(filename)
    return recs[-1] if recs else None


def _exists(filename, id_field, rid) -> bool:
    return any(r.get(id_field) == rid for r in read_jsonl(filename))


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
