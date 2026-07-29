"""Meta Research Intelligence 원장 (P30) — 6개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 mri_ 접두사(Meta Research Intelligence). 각 레코드: id · timestamp · previous_hash · record_hash.
연구 과정 관찰·기록만 — 자동 최적화·실행 없음. 상위 계층(P10~P29)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

META_METRICS = ("mri_meta_metrics.jsonl", "metric_id")            # 메타 지표
QUALITY = ("mri_quality_records.jsonl", "quality_id")            # 연구 품질
OPPORTUNITIES = ("mri_opportunities.jsonl", "opportunity_id")    # 최적화 기회(적용 없음)
OBSERVATIONS = ("mri_observations.jsonl", "observation_id")      # 메타 관찰
REPORTS = ("mri_reports.jsonl", "report_id")                    # 메타 리포트
ARTIFACTS = ("mri_artifacts.jsonl", "artifact_id")             # 메타 계보

ALL_LEDGERS = (META_METRICS, QUALITY, OPPORTUNITIES, OBSERVATIONS, REPORTS, ARTIFACTS)

# ── 연구 과정 관측 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "autonomous_research": ("ar_cycles.jsonl", "cycle_event_id"),         # P25 (효율/속도)
    "reliability_incidents": ("rel_incidents.jsonl", "incident_event_id"),  # P24 (실패)
    "reliability_checks": ("rel_integrity_checks.jsonl", "check_id"),    # P24 (검증 품질)
    "monitoring": ("rmon_anomalies.jsonl", "anomaly_id"),                # P23 (실패)
    "memory_retrievals": ("rmi_retrievals.jsonl", "retrieval_id"),       # P27 (지식 재사용)
    "insight_intelligence": ("rii_insights.jsonl", "insight_event_id"),  # P28
    "strategy_generation": ("rsg_candidates.jsonl", "candidate_event_id"),  # P29 (속도)
    "research_automation": ("ra_workflows.jsonl", "workflow_event_id"),   # P22
}


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


def source_count(layer) -> int:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return 0
    return len(read_jsonl(spec[0]))


def source_present(layer) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    return os.path.exists(state_path(spec[0]))


def source_records(layer) -> list[dict]:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return []
    return read_jsonl(spec[0])


def all_source_counts() -> dict:
    return {k: source_count(k) for k in sorted(SOURCE_LAYERS)}


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


append_metric, read_meta_metrics, metrics_head, metric_exists = _readers(META_METRICS)
append_quality, read_quality_records, quality_head, quality_exists = _readers(QUALITY)
append_opportunity, read_opportunities, opportunities_head, opportunity_exists = _readers(OPPORTUNITIES)
append_observation, read_observations, observations_head, observation_exists = _readers(OBSERVATIONS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


def metrics_by_name(name) -> list[dict]:
    return [r for r in read_meta_metrics() if r.get("metric_name") == name]
