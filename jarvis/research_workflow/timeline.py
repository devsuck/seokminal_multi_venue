"""Research Timeline (P78) — 기존 append-only 원장들에서 연구 타임라인을 **재구성**한다. **새 저장소 없음, 읽기 전용.**

Idea → Hypothesis → Experiment → Backtest → Validation → Failure → Lesson → Portfolio Effect →
Decision Memo → Human Review → Archive. 모든 항목은 이미 기록된 원장(rwf_loops/runs/sessions·ring_·
rmi_·expt_·ras_)에서 결정적으로 파생된다. 새 히스토리 DB 를 만들지 않는다.

원칙(문서 §Constitution, §P78): 통합·시각화만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

# 원장 → 타임라인 스테이지 매핑(문서 파이프라인)
_LOOP_STAGE = {
    "IDEA": "Idea", "HYPOTHESIS": "Hypothesis", "EXPERIMENT_DESIGN": "Experiment",
    "BACKTEST": "Backtest", "VALIDATION": "Validation", "FAILURE_ANALYSIS": "Failure",
    "LESSON": "Lesson", "UPDATED_HYPOTHESIS": "Hypothesis", "NEXT_EXPERIMENT": "Experiment",
}
_LESSON_IMPACT = {"portfolio": "Portfolio Effect", "risk": "Risk", "paper_feedback": "Paper",
                  "hypothesis": "Hypothesis", "autonomous_loop": "Lesson"}
STAGE_ORDER = ("Idea", "Hypothesis", "Experiment", "Backtest", "Validation", "Failure",
               "Lesson", "Portfolio Effect", "Risk", "Paper", "Decision Memo", "Human Review",
               "Archive")


def _ts(rec: dict) -> str:
    return str(rec.get("occurred_at") or rec.get("created_at") or rec.get("timestamp") or "")


def _text(rec: dict) -> str:
    parts = [str(v) for v in rec.values() if isinstance(v, (str, int, float))]
    return " ".join(parts).lower()


def _entry(ts, stage, source, ref, label):
    return {"timestamp": ts, "stage": stage, "source": source, "ref": str(ref),
            "label": str(label)[:120]}


def _read(mod_name, fn_name):
    try:
        mod = __import__(mod_name, fromlist=[fn_name])
        return list(getattr(mod, fn_name)() or [])
    except Exception:  # noqa: BLE001
        return []


def build_timeline(topic: str = "", *, limit: int = 200) -> dict:
    """기존 원장에서 타임라인 재구성(읽기 전용). topic 있으면 텍스트 필터."""
    t = (topic or "").strip().lower()
    entries: list = []

    def add_all(records, mapper):
        for r in records:
            if t and t not in _text(r):
                continue
            e = mapper(r)
            if e:
                entries.append(e)

    # 1) 자율 루프 이벤트(rwf_loops)
    add_all(_read("jarvis.research_workflow.ledger", "read_loops"),
            lambda r: _entry(_ts(r), _LOOP_STAGE.get(r.get("stage"), "Experiment"),
                             "rwf_loops", r.get("loop_id", "?"), r.get("note", r.get("stage", ""))))
    # 2) 워크플로 이벤트(rwf_runs) — Decision / Human Review
    add_all(_read("jarvis.research_workflow.ledger", "read_runs"),
            lambda r: _entry(_ts(r),
                             "Human Review" if r.get("stage") == "HUMAN_DECISION" else
                             "Decision Memo" if r.get("stage") == "DECISION" else None,
                             "rwf_runs", r.get("run_id", "?"), r.get("note", r.get("stage", "")))
            if r.get("stage") in ("HUMAN_DECISION", "DECISION") else None)
    # 3) 세션(rwf_sessions) — Idea(create) / Archive
    add_all(_read("jarvis.research_workflow.ledger", "read_sessions"),
            lambda r: _entry(_ts(r), "Archive" if r.get("kind") == "ARCHIVE" else
                             "Idea" if r.get("kind") == "CREATE" else None,
                             "rwf_sessions", r.get("session_id", "?"), r.get("goal", ""))
            if r.get("kind") in ("CREATE", "ARCHIVE") else None)
    # 4) 수집(ring_) — Backtest
    add_all(_read("jarvis.research_ingestion.ledger", "read_ingestions"),
            lambda r: _entry(_ts(r), "Backtest", "ring_ingestions", r.get("strategy_name", "?"),
                             f"{r.get('strategy_name')} → {r.get('outcome')}"))
    # 5) 실험 실행(expt_)
    add_all(_read("jarvis.experiment_tracking.ledger", "read_runs"),
            lambda r: _entry(_ts(r), "Experiment", "expt_runs", r.get("run_id", "?"),
                             r.get("note", r.get("code_version", ""))))
    # 6) 실패/성공/교훈(rmi_)
    add_all(_read("jarvis.research_memory_intelligence.ledger", "read_failures"),
            lambda r: _entry(_ts(r), "Failure", "rmi_failures", r.get("origin", "?"),
                             r.get("summary", "")))
    add_all(_read("jarvis.research_memory_intelligence.ledger", "read_successes"),
            lambda r: _entry(_ts(r), "Validation", "rmi_successes", r.get("origin", "?"),
                             r.get("summary", "")))
    add_all(_read("jarvis.research_memory_intelligence.ledger", "read_lessons"),
            lambda r: _entry(_ts(r), _LESSON_IMPACT.get(str(r.get("impact", "")), "Lesson"),
                             "rmi_lessons", r.get("origin", "?"), r.get("lesson", "")))
    # 7) 자문 노트(ras_) — Decision Memo
    add_all(_read("jarvis.research_assistant.ledger", "read_notes"),
            lambda r: _entry(_ts(r), "Decision Memo", "ras_notes", r.get("area", "?"),
                             r.get("rationale", ""))
            if str(r.get("area", "")).startswith(("decision:", "council:")) else None)

    entries = [e for e in entries if e]
    entries.sort(key=lambda e: (e["timestamp"], STAGE_ORDER.index(e["stage"])
                                if e["stage"] in STAGE_ORDER else 99, e["source"], e["ref"]))
    entries = entries[:limit]
    by_stage: dict = {}
    for e in entries:
        by_stage[e["stage"]] = by_stage.get(e["stage"], 0) + 1
    return {"topic": topic, "entries": entries, "count": len(entries),
            "by_stage": by_stage, "stage_order": list(STAGE_ORDER),
            "is_advisory": True, "is_decision": False,
            "note": "기존 append-only 원장에서 재구성한 읽기전용 타임라인 — 새 히스토리 저장소 없음."}
