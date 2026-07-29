"""Multi-Agent Research Workflow (P128) — 연구 에이전트들을 연결한다. **분석만, 결정 없음.**

체인: Director → Analyst(Market/Company) → Strategy Researcher → Critic(Reviewer) → Writer.
**재사용**: research_workflow orchestration + session_manager(rwf_sessions, 진행 추적) + record_advisory
(ras_notes, 자문 기록). **기존 원장만 사용 — 새 메모리 없음.**

원칙(문서 §Constitution, §P128): 통합·조율만. 결정적. 거래·집행 없음. 사람 승인 필수.
"""
from __future__ import annotations


def run(objective: str, *, company: str = "", events=None, financials=None, headlines=None,
        assistant=None, now: str = "", commit: bool = False) -> dict:
    """연구 목표 → 다중 에이전트 연구(Director→Analyst→Strategy→Critic→Writer). 결정적·읽기전용.

    commit=True 시 진행을 기존 rwf_sessions 에, 자문 요약을 기존 ras_notes 에 기록(새 원장 없음). 기본=프리뷰.
    """
    obj = (objective or "").strip()
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()

    stages = []

    # 1) Director — 연구 계획
    from jarvis.research_workflow.research_director import ResearchDirector
    director = ResearchDirector(assistant=assistant).plan(obj)
    stages.append({"agent": "ResearchDirector", "role": "director", "ok": True})

    # 2) Analysts — Market(+Company)
    from jarvis.research_workflow.market_analyst import MarketAnalyst
    market_memo = MarketAnalyst(assistant=assistant).memo(topic=obj, events=events)
    memos = {"market": market_memo}
    stages.append({"agent": "MarketAnalyst", "role": "specialist", "ok": True})
    if company or financials or headlines:
        from jarvis.research_workflow.company_analyst import CompanyAnalyst
        memos["company"] = CompanyAnalyst(assistant=assistant).memo(
            company or obj, financials=financials, headlines=headlines)
        stages.append({"agent": "CompanyAnalyst", "role": "specialist", "ok": True})

    # 3) Strategy Researcher — 가설·실험·백테스트잡
    from jarvis.research_workflow.strategy_researcher import StrategyResearcher
    strategy = StrategyResearcher(assistant=assistant).plan(obj)
    memos["strategy"] = strategy
    stages.append({"agent": "StrategyResearcher", "role": "specialist", "ok": True})

    # 4) Critic — 실험 스펙 리뷰
    from jarvis.research_workflow.research_reviewer import ResearchReviewer
    spec = strategy.get("experiment", {}) or {"strategy_name": obj}
    review = ResearchReviewer(assistant=assistant).review(spec, metrics=spec.get("metrics"))
    stages.append({"agent": "ResearchReviewer", "role": "critic", "ok": True})

    # 5) Writer — 7섹션 리포트
    from jarvis.research_workflow.research_writer import ResearchWriter
    report = ResearchWriter(assistant=assistant).write(obj, director=director, memos=memos, review=review)
    stages.append({"agent": "ResearchWriter", "role": "report", "ok": True})

    # 진행/자문 기록 — 기존 원장만(rwf_sessions + ras_notes), 새 메모리 없음
    ledger_writes = _record(assistant, obj, review, commit=commit, now=now)

    return {"objective": obj, "pipeline": ["Director", "Analyst", "StrategyResearcher", "Critic", "Writer"],
            "stages": stages, "director_plan": director, "specialist_memos": memos,
            "review": review, "report": report,
            "human_review_queue": [{"objective": obj, "verdict": review.get("verdict"),
                                    "confidence": report.get("confidence")}],
            "ledger_writes": ledger_writes, "committed": commit,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("다중 에이전트 연구(읽기전용) — Director→Analyst→Strategy→Critic→Writer. "
                     "기존 rwf_/ras_ 원장만, 새 메모리 없음. 분석만, 사람이 모든 결정.")}


def _record(assistant, objective, review, *, commit, now) -> dict:
    """진행=rwf_sessions, 자문 요약=ras_notes(record_advisory) — 기존 원장 재사용. 기본 프리뷰."""
    writes = {}
    try:
        from jarvis.research_workflow.session_manager import ResearchSessionManager
        st = ResearchSessionManager().create_session(f"agent-research: {objective}",
                                                    now=now, commit=commit)
        writes["session"] = getattr(st, "session_id", None) or st.to_dict().get("session_id")
    except Exception as e:  # noqa: BLE001
        writes["session_error"] = str(e)
    try:
        note = assistant.record_advisory(area=f"agent-research:{objective}",
                                         rationale=f"verdict={review.get('verdict')}",
                                         evidence_count=len(review.get("critique", {}).get("critiques", [])),
                                         now=now, commit=commit)
        writes["advisory_note"] = note.note_id if hasattr(note, "note_id") else None
    except Exception as e:  # noqa: BLE001
        writes["advisory_error"] = str(e)
    return writes
