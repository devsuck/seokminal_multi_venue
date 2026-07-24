"""Research Optimization Engine 원장 (P12.6) — 6개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 roe_ 접두사(Research Optimization Engine). 각 레코드: id · timestamp · previous_hash · record_hash.
최적화 기회 분석·제안 기록만 — 자동 최적화/수정/배포/실행 없음. 상위 계층(P9.8~P12.5)은 **READ ONLY** — 파일만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (roe_ 접두사)
STUDIES = ("roe_studies.jsonl", "study_event_id")            # Optimization Studies(event-sourced)
BOTTLENECKS = ("roe_bottlenecks.jsonl", "bottleneck_id")     # Bottleneck Reports
EFFICIENCY = ("roe_efficiency.jsonl", "efficiency_id")       # Efficiency Analysis
PROPOSALS = ("roe_proposals.jsonl", "proposal_id")           # Optimization Proposals
COMPARISONS = ("roe_comparisons.jsonl", "comparison_id")     # Historical Comparisons
REPORTS = ("roe_reports.jsonl", "report_id")                 # 최적화 리포트(generate_report 지원)

ALL_LEDGERS = (STUDIES, BOTTLENECKS, EFFICIENCY, PROPOSALS, COMPARISONS, REPORTS)

# ── 상위 소스 원장(READ ONLY) — 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "data_governance": ("dg_datasets.jsonl", "dataset_hash"),                 # P9.8
    "model_governance": ("mg_models.jsonl", "model_hash"),                   # P9.9
    "research_organization": ("rorg_organizations.jsonl", "org_event_id"),   # P11.13
    "autonomous_research_pipeline": ("arp_cycles.jsonl", "cycle_id"),        # P12.1
    "autonomous_experiment_scheduler": ("aes_schedules.jsonl", "schedule_event_id"),  # P12.2
    "research_agent_coordinator": ("rac_ownership.jsonl", "ownership_event_id"),  # P12.3
    "adaptive_research_loop": ("arl_proposals.jsonl", "proposal_event_id"),  # P12.4
    "autonomous_research_evaluation": ("are_registry.jsonl", "evaluation_event_id"),  # P12.5
}


def _append(filename: str, record: dict) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename: str) -> list[dict]:
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


def _head(filename: str) -> dict | None:
    recs = read_jsonl(filename)
    return recs[-1] if recs else None


def _exists(filename: str, id_field: str, rid: str) -> bool:
    return any(r.get(id_field) == rid for r in read_jsonl(filename))


def _get(filename: str, id_field: str, rid: str) -> dict | None:
    for r in read_jsonl(filename):
        if r.get(id_field) == rid:
            return r
    return None


# ── 상위 소스 READ ONLY ──
def source_ref_exists(layer: str, ref: str) -> bool:
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return False
    p = state_path(spec[0])
    if not os.path.exists(p):
        return False
    return any(r.get(spec[1]) == ref for r in read_jsonl(spec[0]))


# ── Studies (event-sourced) ──
def append_study_event(rec: dict) -> None:
    _append(STUDIES[0], rec)


def read_study_events() -> list[dict]:
    return read_jsonl(STUDIES[0])


def studies_head() -> dict | None:
    return _head(STUDIES[0])


def study_event_exists(study_event_id: str) -> bool:
    return _exists(STUDIES[0], STUDIES[1], study_event_id)


def study_events(study_id: str) -> list[dict]:
    return [r for r in read_study_events() if r.get("study_id") == study_id]


def study_ids() -> list[str]:
    return sorted({r.get("study_id") for r in read_study_events() if r.get("study_id")})


# ── Bottlenecks ──
def append_bottleneck(rec: dict) -> None:
    _append(BOTTLENECKS[0], rec)


def read_bottlenecks() -> list[dict]:
    return read_jsonl(BOTTLENECKS[0])


def bottlenecks_head() -> dict | None:
    return _head(BOTTLENECKS[0])


def bottleneck_exists(bottleneck_id: str) -> bool:
    return _exists(BOTTLENECKS[0], BOTTLENECKS[1], bottleneck_id)


def get_bottleneck(bottleneck_id: str) -> dict | None:
    return _get(BOTTLENECKS[0], BOTTLENECKS[1], bottleneck_id)


def study_bottlenecks(study_id: str) -> list[dict]:
    return [r for r in read_bottlenecks() if r.get("study_id") == study_id]


# ── Efficiency ──
def append_efficiency(rec: dict) -> None:
    _append(EFFICIENCY[0], rec)


def read_efficiency() -> list[dict]:
    return read_jsonl(EFFICIENCY[0])


def efficiency_head() -> dict | None:
    return _head(EFFICIENCY[0])


def efficiency_exists(efficiency_id: str) -> bool:
    return _exists(EFFICIENCY[0], EFFICIENCY[1], efficiency_id)


def get_efficiency(efficiency_id: str) -> dict | None:
    return _get(EFFICIENCY[0], EFFICIENCY[1], efficiency_id)


def study_efficiency(study_id: str) -> list[dict]:
    return [r for r in read_efficiency() if r.get("study_id") == study_id]


# ── Proposals ──
def append_proposal(rec: dict) -> None:
    _append(PROPOSALS[0], rec)


def read_proposals() -> list[dict]:
    return read_jsonl(PROPOSALS[0])


def proposals_head() -> dict | None:
    return _head(PROPOSALS[0])


def proposal_exists(proposal_id: str) -> bool:
    return _exists(PROPOSALS[0], PROPOSALS[1], proposal_id)


def get_proposal(proposal_id: str) -> dict | None:
    return _get(PROPOSALS[0], PROPOSALS[1], proposal_id)


def study_proposals(study_id: str) -> list[dict]:
    return [r for r in read_proposals() if r.get("study_id") == study_id]


# ── Comparisons ──
def append_comparison(rec: dict) -> None:
    _append(COMPARISONS[0], rec)


def read_comparisons() -> list[dict]:
    return read_jsonl(COMPARISONS[0])


def comparisons_head() -> dict | None:
    return _head(COMPARISONS[0])


def comparison_exists(comparison_id: str) -> bool:
    return _exists(COMPARISONS[0], COMPARISONS[1], comparison_id)


def get_comparison(comparison_id: str) -> dict | None:
    return _get(COMPARISONS[0], COMPARISONS[1], comparison_id)


def study_comparisons(study_id: str) -> list[dict]:
    return [r for r in read_comparisons() if r.get("study_id") == study_id]


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)
