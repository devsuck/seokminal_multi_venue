"""System Integration 원장 (P35) — 4개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 sysint_ 접두사(SYStem INTegration). 각 레코드: id · timestamp · previous_hash · record_hash. 검증 실행·
발견·시스템 리포트 기록만 — 계층 변경 없음. 검증 대상 계층(P21~P34)은 정적 검사·파일 읽기만(import 결합 없음, 변경 없음).
"""
from __future__ import annotations


from jarvis.ledger_io import append as _append, read_jsonl, head as _head, exists as _exists

VALIDATIONS = ("sysint_validations.jsonl", "validation_id")      # 검증 실행 기록
FINDINGS = ("sysint_findings.jsonl", "finding_id")              # 개별 발견
REPORTS = ("sysint_reports.jsonl", "report_id")                # 시스템 리포트
ARTIFACTS = ("sysint_artifacts.jsonl", "artifact_id")         # 계보

ALL_LEDGERS = (VALIDATIONS, FINDINGS, REPORTS, ARTIFACTS)


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


append_validation, read_validations, validations_head, validation_exists = _readers(VALIDATIONS)
append_finding, read_findings, findings_head, finding_exists = _readers(FINDINGS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)
