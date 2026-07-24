"""Research Learning Loop 원장 (P12.8) — 8개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rll_ 접두사(Research Learning Loop) — 기존 rl_ 계층과 구별. 각 레코드: id · timestamp · previous_hash ·
record_hash. 관찰·분석·기록만 — 자동 개선 없음. 상위 계층(P12.7, P10.2~P10.8)은 **READ ONLY** — 파일만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rll_ 접두사)
LOOPS = ("rll_loops.jsonl", "loop_event_id")                 # Learning Loop Registry(event-sourced)
OBSERVATIONS = ("rll_observations.jsonl", "observation_id")  # Observation Records
LESSONS = ("rll_lessons.jsonl", "lesson_id")                 # Lesson Records
IMPROVEMENTS = ("rll_improvements.jsonl", "improvement_id")  # Improvement Candidates
FEEDBACK = ("rll_feedback.jsonl", "feedback_id")             # Feedback Records
PATTERNS = ("rll_patterns.jsonl", "pattern_id")             # Learning Patterns (cycle comparisons)
REPORTS = ("rll_reports.jsonl", "report_id")                 # Learning Reports(generate_report 지원)
ARTIFACTS = ("rll_artifacts.jsonl", "artifact_id")          # Artifact Lineage

ALL_LEDGERS = (LOOPS, OBSERVATIONS, LESSONS, IMPROVEMENTS, FEEDBACK, PATTERNS, REPORTS, ARTIFACTS)

# ── 상위 소스 원장(READ ONLY) — 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "research_governance": ("rg_strategy_versions.jsonl", "version_id"),      # P10.2
    "alpha_intelligence": ("ai_signals.jsonl", "signal_hash"),               # P10.3
    "portfolio_research": ("pr_portfolio_versions.jsonl", "version_id"),      # P10.4
    "research_kg": ("kg_entities.jsonl", "entity_id"),                       # P10.5
    "agent_governance": ("arg_agents.jsonl", "event_id"),                    # P10.6
    "decision_intelligence": ("di_frameworks.jsonl", "framework_id"),        # P10.7
    "simulation_environment": ("sim_runs.jsonl", "event_id"),                # P10.8
    "research_experience_memory": ("rxm_memories.jsonl", "memory_event_id"),  # P12.7
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


# ── Loops (event-sourced) ──
def append_loop_event(rec: dict) -> None:
    _append(LOOPS[0], rec)


def read_loop_events() -> list[dict]:
    return read_jsonl(LOOPS[0])


def loops_head() -> dict | None:
    return _head(LOOPS[0])


def loop_event_exists(loop_event_id: str) -> bool:
    return _exists(LOOPS[0], LOOPS[1], loop_event_id)


def loop_events(loop_id: str) -> list[dict]:
    return [r for r in read_loop_events() if r.get("loop_id") == loop_id]


def loop_ids() -> list[str]:
    return sorted({r.get("loop_id") for r in read_loop_events() if r.get("loop_id")})


# ── Observations ──
def append_observation(rec: dict) -> None:
    _append(OBSERVATIONS[0], rec)


def read_observations() -> list[dict]:
    return read_jsonl(OBSERVATIONS[0])


def observations_head() -> dict | None:
    return _head(OBSERVATIONS[0])


def observation_exists(observation_id: str) -> bool:
    return _exists(OBSERVATIONS[0], OBSERVATIONS[1], observation_id)


def get_observation(observation_id: str) -> dict | None:
    return _get(OBSERVATIONS[0], OBSERVATIONS[1], observation_id)


def loop_observations(loop_id: str) -> list[dict]:
    return [r for r in read_observations() if r.get("loop_id") == loop_id]


# ── Lessons ──
def append_lesson(rec: dict) -> None:
    _append(LESSONS[0], rec)


def read_lessons() -> list[dict]:
    return read_jsonl(LESSONS[0])


def lessons_head() -> dict | None:
    return _head(LESSONS[0])


def lesson_exists(lesson_id: str) -> bool:
    return _exists(LESSONS[0], LESSONS[1], lesson_id)


def get_lesson(lesson_id: str) -> dict | None:
    return _get(LESSONS[0], LESSONS[1], lesson_id)


def loop_lessons(loop_id: str) -> list[dict]:
    return [r for r in read_lessons() if r.get("loop_id") == loop_id]


# ── Improvements ──
def append_improvement(rec: dict) -> None:
    _append(IMPROVEMENTS[0], rec)


def read_improvements() -> list[dict]:
    return read_jsonl(IMPROVEMENTS[0])


def improvements_head() -> dict | None:
    return _head(IMPROVEMENTS[0])


def improvement_exists(improvement_id: str) -> bool:
    return _exists(IMPROVEMENTS[0], IMPROVEMENTS[1], improvement_id)


def get_improvement(improvement_id: str) -> dict | None:
    return _get(IMPROVEMENTS[0], IMPROVEMENTS[1], improvement_id)


def loop_improvements(loop_id: str) -> list[dict]:
    return [r for r in read_improvements() if r.get("loop_id") == loop_id]


# ── Feedback ──
def append_feedback(rec: dict) -> None:
    _append(FEEDBACK[0], rec)


def read_feedback() -> list[dict]:
    return read_jsonl(FEEDBACK[0])


def feedback_head() -> dict | None:
    return _head(FEEDBACK[0])


def feedback_exists(feedback_id: str) -> bool:
    return _exists(FEEDBACK[0], FEEDBACK[1], feedback_id)


def loop_feedback(loop_id: str) -> list[dict]:
    return [r for r in read_feedback() if r.get("loop_id") == loop_id]


# ── Patterns ──
def append_pattern(rec: dict) -> None:
    _append(PATTERNS[0], rec)


def read_patterns() -> list[dict]:
    return read_jsonl(PATTERNS[0])


def patterns_head() -> dict | None:
    return _head(PATTERNS[0])


def pattern_exists(pattern_id: str) -> bool:
    return _exists(PATTERNS[0], PATTERNS[1], pattern_id)


def get_pattern(pattern_id: str) -> dict | None:
    return _get(PATTERNS[0], PATTERNS[1], pattern_id)


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
