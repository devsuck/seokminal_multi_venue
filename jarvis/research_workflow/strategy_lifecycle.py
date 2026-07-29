"""Strategy Lifecycle Management (P105) — 연구 상태를 추적한다. **연구 상태만 — 트레이딩 상태 아님.** 읽기전용.

DISCOVERED → HYPOTHESIS → EXPERIMENT → BACKTEST → PAPER → REVIEW → ARCHIVED. 상태는 기존 append-only 원장에서
**결정적으로 파생**된다(timeline.build_timeline 재사용) — 새 상태 저장소를 만들지 않는다. 이것은 연구 진행
상태이지, 자본이 투입된 트레이딩 상태가 아니다.

원칙(문서 §Constitution, §P105): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations

# 연구 생애주기 상태(순서 = 진행도)
LIFECYCLE = ("DISCOVERED", "HYPOTHESIS", "EXPERIMENT", "BACKTEST", "PAPER", "REVIEW", "ARCHIVED")

# timeline 스테이지 → 생애주기 상태(결정적)
_STAGE_TO_STATE = {
    "Idea": "DISCOVERED", "Hypothesis": "HYPOTHESIS", "Experiment": "EXPERIMENT",
    "Backtest": "BACKTEST", "Validation": "PAPER", "Paper": "PAPER", "Failure": "PAPER",
    "Lesson": "REVIEW", "Portfolio Effect": "REVIEW", "Risk": "REVIEW",
    "Decision Memo": "REVIEW", "Human Review": "REVIEW", "Archive": "ARCHIVED",
}
_ORDER = {s: i for i, s in enumerate(LIFECYCLE)}


def _entries(strategy: str) -> list:
    from jarvis.research_workflow.timeline import build_timeline
    return build_timeline(strategy).get("entries", [])


def lifecycle_state(strategy: str) -> dict:
    """전략 이름 → 현재 연구 생애주기 상태(도달한 가장 앞선 상태) + 각 단계 완료 여부. 결정적."""
    name = (strategy or "").strip()
    reached = {s: False for s in LIFECYCLE}
    stage_refs: dict = {}
    for e in _entries(name):
        st = _STAGE_TO_STATE.get(e.get("stage"))
        if st:
            reached[st] = True
            stage_refs.setdefault(st, []).append({"source": e.get("source"), "ref": e.get("ref"),
                                                  "timestamp": e.get("timestamp")})
    # DISCOVERED 는 어떤 흔적이라도 있으면 True
    if any(reached.values()):
        reached["DISCOVERED"] = True
    current = "DISCOVERED"
    for s in LIFECYCLE:
        if reached[s]:
            current = s
    return {"strategy": name, "current_state": current,
            "reached": reached, "stage_evidence": stage_refs,
            "checklist": [{"state": s, "done": reached[s], "current": s == current} for s in LIFECYCLE],
            "is_advisory": True, "is_decision": False,
            "note": "연구 생애주기 상태(읽기전용, 기존 원장 파생) — 트레이딩 상태 아님, 새 저장소 없음."}


def _known_strategies(limit: int = 50) -> list:
    """기존 원장에서 전략 이름 후보를 결정적으로 수집(중복 제거)."""
    names: list = []
    seen = set()

    def add(n):
        n = (n or "").strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            names.append(n)

    def read(mod, fn):
        try:
            m = __import__(mod, fromlist=[fn])
            return list(getattr(m, fn)() or [])
        except Exception:  # noqa: BLE001
            return []

    for r in read("jarvis.research_ingestion.ledger", "read_ingestions"):
        add(r.get("strategy_name"))
    for r in read("jarvis.research_memory_intelligence.ledger", "read_lessons"):
        add(r.get("origin"))
    for r in read("jarvis.research_memory_intelligence.ledger", "read_failures"):
        add(r.get("origin"))
    return names[:limit]


def board(*, strategies: list | None = None, limit: int = 30) -> dict:
    """전략 생애주기 보드 — 각 전략의 현재 상태(읽기전용). strategies 미지정 시 원장에서 파생."""
    names = strategies if strategies else _known_strategies(limit)
    rows = [lifecycle_state(n) for n in names]
    by_state: dict = {}
    for r in rows:
        by_state[r["current_state"]] = by_state.get(r["current_state"], 0) + 1
    return {"lifecycle": list(LIFECYCLE),
            "strategies": [{"strategy": r["strategy"], "current_state": r["current_state"],
                            "checklist": r["checklist"]} for r in rows],
            "count": len(rows), "by_state": by_state,
            "is_advisory": True, "is_decision": False,
            "note": "생애주기 보드(읽기전용, 기존 원장 파생) — 연구 상태만, 새 저장소 없음."}
