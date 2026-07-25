"""Research Operations Event System (P107) — 기존 이벤트 계층을 **운영 이벤트**로 연결한다. **읽기 전용.**

운영 이벤트: new hypothesis · backtest completed · validation failed · paper divergence detected ·
human review required. 모두 기존 append-only 원장(rwf_loops/runs·ring_·rmi_)에서 **결정적으로 파생**된다 —
**새 알림 데이터베이스를 만들지 않는다**.

원칙(문서 §Constitution, §P107): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations

# 운영 이벤트 유형
E_NEW_HYPOTHESIS = "NEW_HYPOTHESIS"
E_BACKTEST_COMPLETED = "BACKTEST_COMPLETED"
E_VALIDATION_FAILED = "VALIDATION_FAILED"
E_PAPER_DIVERGENCE = "PAPER_DIVERGENCE"
E_HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
OPS_EVENT_TYPES = (E_NEW_HYPOTHESIS, E_BACKTEST_COMPLETED, E_VALIDATION_FAILED,
                   E_PAPER_DIVERGENCE, E_HUMAN_REVIEW_REQUIRED)

_PAPER_MARKER = "PAPER vs BACKTEST"


def _ts(r: dict) -> str:
    return str(r.get("occurred_at") or r.get("created_at") or r.get("timestamp") or "")


def _read(mod, fn):
    try:
        m = __import__(mod, fromlist=[fn])
        return list(getattr(m, fn)() or [])
    except Exception:  # noqa: BLE001
        return []


def _ev(ts, etype, source, ref, label, *, needs_review=False):
    return {"timestamp": ts, "event_type": etype, "source": source, "ref": str(ref),
            "label": str(label)[:140], "requires_human_review": bool(needs_review)}


def ops_events(*, limit: int = 100) -> dict:
    """기존 원장 → 운영 이벤트 스트림(읽기전용). 새 알림 DB 없음 — 파생만."""
    events: list = []

    # new hypothesis — rwf_loops(HYPOTHESIS/UPDATED_HYPOTHESIS)
    for r in _read("jarvis.research_workflow.ledger", "read_loops"):
        if str(r.get("stage", "")).upper() in ("HYPOTHESIS", "UPDATED_HYPOTHESIS"):
            events.append(_ev(_ts(r), E_NEW_HYPOTHESIS, "rwf_loops", r.get("loop_id", "?"),
                              r.get("note", r.get("stage", ""))))

    # backtest completed / validation failed — ring_ingestions
    for r in _read("jarvis.research_ingestion.ledger", "read_ingestions"):
        outcome = str(r.get("outcome", "")).upper()
        if outcome == "FAILURE":
            events.append(_ev(_ts(r), E_VALIDATION_FAILED, "ring_ingestions", r.get("strategy_name", "?"),
                              f"{r.get('strategy_name')} → {outcome} ({r.get('failure_category', '')})",
                              needs_review=True))
        else:
            events.append(_ev(_ts(r), E_BACKTEST_COMPLETED, "ring_ingestions", r.get("strategy_name", "?"),
                              f"{r.get('strategy_name')} → {outcome or 'INGESTED'}"))

    # validation failed — rmi_failures
    for r in _read("jarvis.research_memory_intelligence.ledger", "read_failures"):
        events.append(_ev(_ts(r), E_VALIDATION_FAILED, "rmi_failures", r.get("origin", "?"),
                          r.get("summary", ""), needs_review=True))

    # paper divergence — rmi_lessons(PAPER vs BACKTEST 마커)
    for r in _read("jarvis.research_memory_intelligence.ledger", "read_lessons"):
        if _PAPER_MARKER in str(r.get("lesson", "")):
            events.append(_ev(_ts(r), E_PAPER_DIVERGENCE, "rmi_lessons", r.get("origin", "?"),
                              r.get("lesson", ""), needs_review=True))

    # human review required — rwf_runs(HUMAN_DECISION/DECISION)
    for r in _read("jarvis.research_workflow.ledger", "read_runs"):
        if str(r.get("stage", "")).upper() in ("HUMAN_DECISION", "DECISION"):
            events.append(_ev(_ts(r), E_HUMAN_REVIEW_REQUIRED, "rwf_runs", r.get("run_id", "?"),
                              r.get("note", r.get("stage", "")), needs_review=True))

    events.sort(key=lambda e: e["timestamp"], reverse=True)
    events = events[:limit]
    by_type: dict = {}
    for e in events:
        by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1
    return {"events": events, "count": len(events), "by_type": by_type,
            "event_types": list(OPS_EVENT_TYPES),
            "review_queue": [e for e in events if e["requires_human_review"]][:limit],
            "is_advisory": True, "is_decision": False,
            "note": "운영 이벤트(읽기전용, 기존 이벤트 계층 파생) — 새 알림 DB 없음, 거래·집행 없음."}
