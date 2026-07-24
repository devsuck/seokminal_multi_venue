"""Research Event Bus 원장 (P11.11) — 11개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 reb_ 접두사(Research Event Bus). 각 레코드: id · timestamp · previous_hash · record_hash. 내부 연구
이벤트 통신 — 발행·소비·라우팅·이력 기록만, 실행/배포/전략·모델 수정/자본 배분/권한 변경/자동 승인 없음.
상위 계층(P10.2~P10.8, P11.1~P11.10)은 **READ ONLY** — 소스 참조는 파일만 읽고 절대 쓰지 않는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (reb_ 접두사)
REGISTRY = ("reb_registry.jsonl", "event_type_id")       # Event Registry (event types)
SOURCES = ("reb_sources.jsonl", "source_record_id")      # 인가 소스(register_source 지원)
STREAMS = ("reb_streams.jsonl", "stream_id")             # Event Streams
EVENTS = ("reb_events.jsonl", "event_lifecycle_id")      # Event Messages (event-sourced lifecycle)
SUBSCRIBERS = ("reb_subscribers.jsonl", "subscriber_id")  # Event Subscribers
CONSUMERS = ("reb_consumers.jsonl", "consumer_record_id")  # Event Consumers (delivery+consume)
ROUTES = ("reb_routes.jsonl", "route_id")                # Event Routing Rules
SNAPSHOTS = ("reb_snapshots.jsonl", "snapshot_id")       # Event Snapshots
REPORTS = ("reb_reports.jsonl", "report_id")             # Event Reports
ARTIFACTS = ("reb_artifacts.jsonl", "artifact_id")       # Event Artifacts
LINEAGE = ("reb_lineage.jsonl", "lineage_id")            # Event Lineage

ALL_LEDGERS = (REGISTRY, SOURCES, STREAMS, EVENTS, SUBSCRIBERS, CONSUMERS, ROUTES, SNAPSHOTS,
               REPORTS, ARTIFACTS, LINEAGE)

# ── 상위 소스 원장(READ ONLY) — 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "research_governance": ("rg_strategy_versions.jsonl", "version_id"),      # P10.2
    "alpha_intelligence": ("ai_signals.jsonl", "signal_hash"),               # P10.3
    "portfolio_research": ("pr_portfolio_versions.jsonl", "version_id"),      # P10.4
    "research_kg": ("kg_entities.jsonl", "entity_id"),                       # P10.5
    "agent_governance": ("arg_agents.jsonl", "event_id"),                    # P10.6
    "decision_intelligence": ("di_frameworks.jsonl", "framework_id"),        # P10.7
    "simulation_environment": ("sim_runs.jsonl", "event_id"),                # P10.8
    "research_agents": ("ragt_reports.jsonl", "report_id"),                  # P11.1
    "research_task_planner": ("rtp_tasks.jsonl", "task_id"),                 # P11.2
    "research_literature": ("rli_papers.jsonl", "paper_id"),                 # P11.3
    "experiment_manager": ("exm_experiments.jsonl", "event_id"),             # P11.4
    "research_reviewer": ("rvw_reviews.jsonl", "review_id"),                 # P11.5
    "research_council": ("cnl_consensus.jsonl", "consensus_id"),             # P11.6
    "research_coordinator": ("rco_reports.jsonl", "report_id"),              # P11.7
    "knowledge_sharing": ("ksh_entries.jsonl", "entry_id"),                  # P11.8
    "research_conflict_resolution": ("crf_outcomes.jsonl", "resolution_id"),  # P11.9
    "research_improvement": ("rimp_registry.jsonl", "registry_id"),          # P11.10
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


# ── Registry (event types) ──
def append_type(rec: dict) -> None:
    _append(REGISTRY[0], rec)


def read_types() -> list[dict]:
    return read_jsonl(REGISTRY[0])


def types_head() -> dict | None:
    return _head(REGISTRY[0])


def type_exists(event_type_id: str) -> bool:
    return _exists(REGISTRY[0], REGISTRY[1], event_type_id)


def get_type(event_type_id: str) -> dict | None:
    return _get(REGISTRY[0], REGISTRY[1], event_type_id)


# ── Sources ──
def append_source(rec: dict) -> None:
    _append(SOURCES[0], rec)


def read_sources() -> list[dict]:
    return read_jsonl(SOURCES[0])


def sources_head() -> dict | None:
    return _head(SOURCES[0])


def source_exists(source_record_id: str) -> bool:
    return _exists(SOURCES[0], SOURCES[1], source_record_id)


def get_source(source_record_id: str) -> dict | None:
    return _get(SOURCES[0], SOURCES[1], source_record_id)


def source_registered(source_layer: str, source_id: str) -> bool:
    return any(r.get("source_layer") == source_layer and r.get("source_id") == source_id
               for r in read_sources())


# ── Streams ──
def append_stream(rec: dict) -> None:
    _append(STREAMS[0], rec)


def read_streams() -> list[dict]:
    return read_jsonl(STREAMS[0])


def streams_head() -> dict | None:
    return _head(STREAMS[0])


def stream_exists(stream_id: str) -> bool:
    return _exists(STREAMS[0], STREAMS[1], stream_id)


def get_stream(stream_id: str) -> dict | None:
    return _get(STREAMS[0], STREAMS[1], stream_id)


# ── Events (event-sourced lifecycle) ──
def append_event(rec: dict) -> None:
    _append(EVENTS[0], rec)


def read_events() -> list[dict]:
    return read_jsonl(EVENTS[0])


def events_head() -> dict | None:
    return _head(EVENTS[0])


def event_lifecycle_exists(event_lifecycle_id: str) -> bool:
    return _exists(EVENTS[0], EVENTS[1], event_lifecycle_id)


def event_records(event_id: str) -> list[dict]:
    return [r for r in read_events() if r.get("event_id") == event_id]


def event_ids() -> list[str]:
    return sorted({r.get("event_id") for r in read_events() if r.get("event_id")})


def type_events(event_type: str) -> list[str]:
    return sorted({r.get("event_id") for r in read_events()
                   if r.get("event_type") == event_type and r.get("event_id")})


# ── Subscribers ──
def append_subscriber(rec: dict) -> None:
    _append(SUBSCRIBERS[0], rec)


def read_subscribers() -> list[dict]:
    return read_jsonl(SUBSCRIBERS[0])


def subscribers_head() -> dict | None:
    return _head(SUBSCRIBERS[0])


def subscriber_exists(subscriber_id: str) -> bool:
    return _exists(SUBSCRIBERS[0], SUBSCRIBERS[1], subscriber_id)


def get_subscriber(subscriber_id: str) -> dict | None:
    return _get(SUBSCRIBERS[0], SUBSCRIBERS[1], subscriber_id)


# ── Consumers (delivery + consumption records) ──
def append_consumer(rec: dict) -> None:
    _append(CONSUMERS[0], rec)


def read_consumers() -> list[dict]:
    return read_jsonl(CONSUMERS[0])


def consumers_head() -> dict | None:
    return _head(CONSUMERS[0])


def consumer_exists(consumer_record_id: str) -> bool:
    return _exists(CONSUMERS[0], CONSUMERS[1], consumer_record_id)


def event_consumers(event_id: str) -> list[dict]:
    return [r for r in read_consumers() if r.get("event_id") == event_id]


# ── Routes ──
def append_route(rec: dict) -> None:
    _append(ROUTES[0], rec)


def read_routes() -> list[dict]:
    return read_jsonl(ROUTES[0])


def routes_head() -> dict | None:
    return _head(ROUTES[0])


def route_exists(route_id: str) -> bool:
    return _exists(ROUTES[0], ROUTES[1], route_id)


def type_routes(event_type: str) -> list[dict]:
    return [r for r in read_routes() if r.get("event_type") == event_type]


# ── Snapshots ──
def append_snapshot(rec: dict) -> None:
    _append(SNAPSHOTS[0], rec)


def read_snapshots() -> list[dict]:
    return read_jsonl(SNAPSHOTS[0])


def snapshots_head() -> dict | None:
    return _head(SNAPSHOTS[0])


def snapshot_exists(snapshot_id: str) -> bool:
    return _exists(SNAPSHOTS[0], SNAPSHOTS[1], snapshot_id)


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Artifacts (lineage tree) ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)


# ── Lineage (event parent edges) ──
def append_lineage(rec: dict) -> None:
    _append(LINEAGE[0], rec)


def read_lineage() -> list[dict]:
    return read_jsonl(LINEAGE[0])


def lineage_head() -> dict | None:
    return _head(LINEAGE[0])


def lineage_exists(lineage_id: str) -> bool:
    return _exists(LINEAGE[0], LINEAGE[1], lineage_id)
