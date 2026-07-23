"""Agent Research Governance 원장 (P10.6) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일은 arg_ 접두사(P9.10 access_governance 의 ag_ 와 충돌 회피). 각 레코드: id · previous_hash ·
record_hash. 에이전트 거버넌스 기록만 — 주문/배포/실행 없음. 상위 레이어(P9.8~P10.5) 원장은 READ ONLY.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (arg_ 접두사)
AGENTS = ("arg_agents.jsonl", "event_id")               # 이벤트 소싱
CAPABILITIES = ("arg_capabilities.jsonl", "capability_id")
REQUESTS = ("arg_requests.jsonl", "event_id")           # 이벤트 소싱
PROPOSALS = ("arg_proposals.jsonl", "event_id")         # 이벤트 소싱
ACTIONS = ("arg_actions.jsonl", "action_id")
REVIEWS = ("arg_reviews.jsonl", "review_id")
BUDGETS = ("arg_budgets.jsonl", "event_id")             # LIMIT + USAGE 이벤트
ARTIFACTS = ("arg_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (AGENTS, CAPABILITIES, REQUESTS, PROPOSALS, ACTIONS, REVIEWS, BUDGETS, ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "data_governance": ("dg_datasets.jsonl", "dg_schema_versions.jsonl",
                        "dg_quality_reports.jsonl"),
    "model_governance": ("mg_models.jsonl",),
    "research_data": ("datasets.jsonl", "features.jsonl"),
    "research_governance": ("rg_strategies.jsonl", "rg_experiments.jsonl"),
    "alpha_intelligence": ("ai_signals.jsonl", "ai_experiments.jsonl"),
    "portfolio_research": ("pr_portfolios.jsonl",),
    "research_kg": ("kg_entities.jsonl", "kg_relationships.jsonl"),
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


# ── 상위 레이어 READ ONLY 소스 ──
def read_source(filename: str) -> list[dict]:
    """상위 레이어 원장을 읽기 전용으로 로드. 절대 쓰지 않는다."""
    return read_jsonl(filename)


# ── Agents (event-sourced) ──
def append_agent_event(rec: dict) -> None:
    _append(AGENTS[0], rec)


def read_agent_events() -> list[dict]:
    return read_jsonl(AGENTS[0])


def agents_head() -> dict | None:
    return _head(AGENTS[0])


def agent_event_exists(event_id: str) -> bool:
    return _exists(AGENTS[0], AGENTS[1], event_id)


def agent_events_for(agent_id: str) -> list[dict]:
    return [r for r in read_agent_events() if r.get("agent_id") == agent_id]


def distinct_agents() -> list[dict]:
    out: dict = {}
    for r in read_agent_events():
        aid = r.get("agent_id")
        if aid not in out:
            out[aid] = r
    return list(out.values())


# ── Capabilities ──
def append_capability(rec: dict) -> None:
    _append(CAPABILITIES[0], rec)


def read_capabilities() -> list[dict]:
    return read_jsonl(CAPABILITIES[0])


def capabilities_head() -> dict | None:
    return _head(CAPABILITIES[0])


def capability_exists(capability_id: str) -> bool:
    return _exists(CAPABILITIES[0], CAPABILITIES[1], capability_id)


# ── Requests (event-sourced) ──
def append_request_event(rec: dict) -> None:
    _append(REQUESTS[0], rec)


def read_request_events() -> list[dict]:
    return read_jsonl(REQUESTS[0])


def requests_head() -> dict | None:
    return _head(REQUESTS[0])


def request_event_exists(event_id: str) -> bool:
    return _exists(REQUESTS[0], REQUESTS[1], event_id)


def request_events_for(request_id: str) -> list[dict]:
    return [r for r in read_request_events() if r.get("request_id") == request_id]


def distinct_requests() -> list[dict]:
    out: dict = {}
    for r in read_request_events():
        rid = r.get("request_id")
        if rid not in out:
            out[rid] = r
    return list(out.values())


# ── Proposals (event-sourced) ──
def append_proposal_event(rec: dict) -> None:
    _append(PROPOSALS[0], rec)


def read_proposal_events() -> list[dict]:
    return read_jsonl(PROPOSALS[0])


def proposals_head() -> dict | None:
    return _head(PROPOSALS[0])


def proposal_event_exists(event_id: str) -> bool:
    return _exists(PROPOSALS[0], PROPOSALS[1], event_id)


def proposal_events_for(proposal_id: str) -> list[dict]:
    return [r for r in read_proposal_events() if r.get("proposal_id") == proposal_id]


def distinct_proposals() -> list[dict]:
    out: dict = {}
    for r in read_proposal_events():
        pid = r.get("proposal_id")
        if pid not in out:
            out[pid] = r
    return list(out.values())


# ── Actions ──
def append_action(rec: dict) -> None:
    _append(ACTIONS[0], rec)


def read_actions() -> list[dict]:
    return read_jsonl(ACTIONS[0])


def actions_head() -> dict | None:
    return _head(ACTIONS[0])


def action_exists(action_id: str) -> bool:
    return _exists(ACTIONS[0], ACTIONS[1], action_id)


# ── Reviews ──
def append_review(rec: dict) -> None:
    _append(REVIEWS[0], rec)


def read_reviews() -> list[dict]:
    return read_jsonl(REVIEWS[0])


def reviews_head() -> dict | None:
    return _head(REVIEWS[0])


def review_exists(review_id: str) -> bool:
    return _exists(REVIEWS[0], REVIEWS[1], review_id)


def reviews_for(proposal_id: str) -> list[dict]:
    return [r for r in read_reviews() if r.get("proposal_id") == proposal_id]


# ── Budgets (event-sourced: LIMIT + USAGE) ──
def append_budget(rec: dict) -> None:
    _append(BUDGETS[0], rec)


def read_budgets() -> list[dict]:
    return read_jsonl(BUDGETS[0])


def budgets_head() -> dict | None:
    return _head(BUDGETS[0])


def budget_event_exists(event_id: str) -> bool:
    return _exists(BUDGETS[0], BUDGETS[1], event_id)


def budget_records_for(budget_key: str) -> list[dict]:
    return [r for r in read_budgets() if r.get("budget_key") == budget_key]


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
