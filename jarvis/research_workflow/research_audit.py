"""Research Audit & History (P109) — 모든 전략의 완전한 연구 계보를 보장한다. **읽기 전용, 새 감사 DB 없음.**

전략마다: origin event · hypothesis · experiments · parameters · results · failures · lessons 를
기존 append-only 원장(rwf_·ring_·expt_·rmi_·ras_)에서 **재구성**한다(timeline.build_timeline 재사용).
새 감사 데이터베이스를 만들지 않는다 — 진실은 이미 원장에 있다.

원칙(문서 §Constitution, §P109): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

# 감사 섹션 → timeline 스테이지(결정적)
_SECTIONS = {
    "origin_event": ("Idea",),
    "hypothesis": ("Hypothesis",),
    "experiments": ("Experiment",),
    "backtests": ("Backtest",),
    "results": ("Validation",),
    "failures": ("Failure",),
    "lessons": ("Lesson", "Risk", "Portfolio Effect", "Paper"),
    "decisions": ("Decision Memo", "Human Review"),
    "archive": ("Archive",),
}
# 완결성에 필요한 핵심 섹션
_REQUIRED = ("origin_event", "hypothesis", "experiments", "backtests", "lessons")


def audit_strategy(strategy: str) -> dict:
    """전략 이름 → 완전한 연구 감사(origin·가설·실험·파라미터·결과·실패·교훈). 결정적·읽기전용."""
    name = (strategy or "").strip()
    from jarvis.research_workflow.timeline import build_timeline
    entries = build_timeline(name).get("entries", [])

    sections: dict = {k: [] for k in _SECTIONS}
    for e in entries:
        for sec, stages in _SECTIONS.items():
            if e.get("stage") in stages:
                sections[sec].append({"timestamp": e.get("timestamp"), "source": e.get("source"),
                                      "ref": e.get("ref"), "label": e.get("label")})

    # 파라미터 — expt_parameters(있으면) 재사용
    parameters = _parameters_for(name)

    present = {k: bool(v) for k, v in sections.items()}
    missing = [k for k in _REQUIRED if not present.get(k)]
    complete = not missing
    return {"strategy": name, "sections": sections, "parameters": parameters,
            "completeness": {"complete": complete, "present": present, "missing_sections": missing},
            "entry_count": len(entries),
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": "연구 감사(읽기전용, 기존 append-only 원장 재구성) — 새 감사 DB 없음."}


def _parameters_for(name: str) -> list:
    """expt_ 원장에서 전략 관련 파라미터를 결정적으로 수집(있으면). 없으면 빈 리스트."""
    try:
        from jarvis.experiment_tracking import ledger as el
        runs = [r for r in (el.read_jsonl(el.RUNS[0]) or [])
                if name.lower() in " ".join(str(v) for v in r.values()).lower()]
        run_ids = {r.get("run_id") for r in runs}
        params = [p for p in (el.read_jsonl(el.PARAMETERS[0]) or []) if p.get("run_id") in run_ids]
        return [{"run_id": p.get("run_id"), "key": p.get("key"), "value": p.get("value")}
                for p in params][:50]
    except Exception:  # noqa: BLE001
        return []


def audit_coverage(*, limit: int = 30) -> dict:
    """전 전략 감사 완결성 요약(읽기전용) — 계보가 불완전한 전략을 표시."""
    from jarvis.research_workflow.strategy_lifecycle import _known_strategies
    names = _known_strategies(limit)
    rows = []
    for n in names:
        a = audit_strategy(n)
        rows.append({"strategy": n, "complete": a["completeness"]["complete"],
                     "missing_sections": a["completeness"]["missing_sections"]})
    complete_n = sum(1 for r in rows if r["complete"])
    return {"strategies": rows, "count": len(rows), "complete_count": complete_n,
            "incomplete": [r for r in rows if not r["complete"]],
            "is_advisory": True, "is_decision": False,
            "note": "감사 커버리지(읽기전용) — 불완전 계보 표시. 새 저장소 없음."}
