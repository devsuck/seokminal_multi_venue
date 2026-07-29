"""Autonomous Research OS 원장 (P13) — 6개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 aros_ 접두사(Autonomous Research OS). 각 레코드: id · timestamp · previous_hash · record_hash. 모든 하위
계층을 **READ ONLY** 로 연결·집계만 한다 — 거래/주문/배포/승격/권한 없음. 하위 계층 원장에 **절대 쓰지 않는다**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 계층 소유 원장 (aros_ 접두사)
REGISTRY = ("aros_registry.jsonl", "os_event_id")     # Research OS Registry(event-sourced)
EPISODES = ("aros_episodes.jsonl", "episode_id")      # Research Episodes
SNAPSHOTS = ("aros_snapshots.jsonl", "snapshot_id")   # System Snapshots
VIEWS = ("aros_views.jsonl", "view_id")               # Knowledge Views
REPORTS = ("aros_reports.jsonl", "report_id")         # Operational Reports
ARTIFACTS = ("aros_artifacts.jsonl", "artifact_id")   # Artifact Lineage

ALL_LEDGERS = (REGISTRY, EPISODES, SNAPSHOTS, VIEWS, REPORTS, ARTIFACTS)

# ── 하위 소스 원장(READ ONLY) — 연결·집계 대상. import 결합 없음, 파일만 읽는다. 절대 쓰지 않는다. ──
SOURCE_LAYERS = {
    "decision_intelligence": ("di_frameworks.jsonl", "framework_id"),          # P10.7
    "autonomous_research_pipeline": ("arp_cycles.jsonl", "cycle_id"),          # P12.1
    "autonomous_experiment_scheduler": ("aes_registry.jsonl", "schedule_id"),  # P12.2
    "research_agent_coordinator": ("rac_registry.jsonl", "agent_registration_id"),  # P12.3
    "adaptive_research_loop": ("arl_cycles.jsonl", "cycle_id"),                # P12.4
    "autonomous_research_evaluation": ("are_registry.jsonl", "evaluation_event_id"),  # P12.5
    "research_optimization_engine": ("roe_studies.jsonl", "study_event_id"),   # P12.6
    "research_experience_memory": ("rxm_memories.jsonl", "memory_event_id"),   # P12.7
    "research_learning": ("rll_loops.jsonl", "loop_event_id"),                 # P12.8
    "research_manager": ("rmgr_plans.jsonl", "plan_event_id"),                 # P12.9
    "research_control": ("rctl_states.jsonl", "state_event_id"),               # P12.10
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


# ── 하위 소스 READ ONLY ──
def source_count(layer: str) -> int:
    """소스 계층 원장 레코드 수(READ ONLY). 파일만 읽는다."""
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return 0
    return len(read_jsonl(spec[0]))


def source_ref_exists(layer: str, ref: str) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    p = state_path(spec[0])
    if not os.path.exists(p):
        return False
    return any(r.get(spec[1]) == ref for r in read_jsonl(spec[0]))


def all_layer_counts() -> dict:
    """모든 하위 계층의 레코드 수(결정적, READ ONLY)."""
    return {layer: source_count(layer) for layer in sorted(SOURCE_LAYERS)}


# ── Registry (event-sourced) ──
def append_os_event(rec: dict) -> None:
    _append(REGISTRY[0], rec)


def read_os_events() -> list[dict]:
    return read_jsonl(REGISTRY[0])


def registry_head() -> dict | None:
    return _head(REGISTRY[0])


def os_event_exists(oid: str) -> bool:
    return _exists(REGISTRY[0], REGISTRY[1], oid)


def os_events(os_id: str) -> list[dict]:
    return [r for r in read_os_events() if r.get("os_id") == os_id]


def os_ids() -> list[str]:
    return sorted({r.get("os_id") for r in read_os_events() if r.get("os_id")})


# ── Episodes ──
def append_episode(rec: dict) -> None:
    _append(EPISODES[0], rec)


def read_episodes() -> list[dict]:
    return read_jsonl(EPISODES[0])


def episodes_head() -> dict | None:
    return _head(EPISODES[0])


def episode_exists(eid: str) -> bool:
    return _exists(EPISODES[0], EPISODES[1], eid)


def os_episodes(os_id: str) -> list[dict]:
    return [r for r in read_episodes() if r.get("os_id") == os_id]


# ── Snapshots ──
def append_snapshot(rec: dict) -> None:
    _append(SNAPSHOTS[0], rec)


def read_snapshots() -> list[dict]:
    return read_jsonl(SNAPSHOTS[0])


def snapshots_head() -> dict | None:
    return _head(SNAPSHOTS[0])


def snapshot_exists(sid: str) -> bool:
    return _exists(SNAPSHOTS[0], SNAPSHOTS[1], sid)


# ── Views ──
def append_view(rec: dict) -> None:
    _append(VIEWS[0], rec)


def read_views() -> list[dict]:
    return read_jsonl(VIEWS[0])


def views_head() -> dict | None:
    return _head(VIEWS[0])


def view_exists(vid: str) -> bool:
    return _exists(VIEWS[0], VIEWS[1], vid)


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(rid: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], rid)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(aid: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], aid)
