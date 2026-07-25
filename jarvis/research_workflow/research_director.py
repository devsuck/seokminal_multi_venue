"""Research Director Agent (P122) — 연구 목표를 받아 계획을 세우고 전문가를 배정한다. **분석만, 투자추천 없음.**

책임: 연구 목표 접수·워크플로 선택·전문가 태스크 배정·진행 추적·상태 요약. 출력: Research Plan
{objective, hypothesis, required_data, assigned_agents, validation_plan}. **재사용**: hypothesis_generator(P73)·
experiment_planner(P74)·research_prioritizer(P76)·session_manager(P66, rwf_sessions). 새 원장/메모리 없음.

원칙(문서 §Constitution, §P122): 통합·조율만. 결정적. 거래·집행 없음. **투자 추천 없음.** 사람 승인 필수.
"""
from __future__ import annotations


class ResearchDirector:
    """연구 디렉터 — 목표 → 연구 계획(가설·데이터·배정·검증). RESEARCH_ONLY. 결정하지 않는다."""

    role = "director"
    level = "RESEARCH_ONLY"

    def __init__(self, assistant=None) -> None:
        self._asst = assistant

    def _assistant(self):
        if self._asst is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            self._asst = ResearchAssistantEngine()
        return self._asst

    def plan(self, objective: str, *, limit: int = 3) -> dict:
        """연구 목표 → Research Plan(가설·필요데이터·배정·검증). 결정적·읽기전용."""
        obj = (objective or "").strip()
        assistant = self._assistant()

        # 1) 가설 — hypothesis_generator 재사용
        hypotheses = []
        try:
            from jarvis.research_workflow.hypothesis_generator import HypothesisGenerator
            hyps = HypothesisGenerator(assistant=assistant).generate(obj, limit=limit)
            hypotheses = [h.to_dict() for h in hyps]
        except Exception:  # noqa: BLE001
            pass
        top_hyp = hypotheses[0] if hypotheses else {"statement": obj}

        # 2) 우선순위 — research_prioritizer 재사용(다음 연구 추천)
        ranked = {}
        try:
            from jarvis.research_workflow.research_prioritizer import ResearchPrioritizer
            ranked = ResearchPrioritizer(assistant=assistant).prioritize(hypotheses or [top_hyp]).to_dict()
        except Exception:  # noqa: BLE001
            pass

        # 3) 필요 데이터 + 검증계획 — experiment_planner 재사용
        required_data, validation_plan = [], []
        try:
            from jarvis.research_workflow.experiment_planner import ExperimentPlanner
            spec = ExperimentPlanner().plan(top_hyp)
            required_data = list(spec.feature_set)
            validation_plan = [c["metric"] if isinstance(c, dict) else c
                               for c in spec.validation_checklist]
        except Exception:  # noqa: BLE001
            pass

        # 4) 전문가 배정(워크플로 선택) — 목표 키워드 기반 결정적 배정
        assigned = self._assign(obj)

        return {"objective": obj, "hypothesis": top_hyp.get("statement", obj),
                "hypotheses": hypotheses, "required_data": required_data,
                "assigned_agents": assigned, "validation_plan": validation_plan,
                "priority": ranked.get("recommended", {}),
                "workflow": "Director→Analyst→StrategyResearcher→Critic→Writer",
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": ("Research Plan(읽기전용) — 가설·데이터·배정·검증. 투자 추천 아님. "
                         "기존 엔진 재사용, 새 메모리 없음. 사람 승인 필수.")}

    def _assign(self, objective: str) -> list:
        """목표 → 전문가 에이전트 배정(결정적). 항상 Critic·Writer 포함."""
        low = (objective or "").lower()
        agents = []
        if any(k in low for k in ("market", "regime", "macro", "sector", "index", "시장", "매크로")):
            agents.append({"agent": "MarketAnalyst", "task": "시장 상황·이벤트·컨텍스트 요약"})
        if any(k in low for k in ("company", "earnings", "revenue", "fundamental", "기업", "실적", "재무")):
            agents.append({"agent": "CompanyAnalyst", "task": "재무·실적·이벤트·경쟁지위 분석"})
        # 전략/실험은 기본 포함
        agents.append({"agent": "StrategyResearcher", "task": "가설·실험 설계·과거 연구 분석"})
        if not any(a["agent"] == "MarketAnalyst" for a in agents):
            agents.insert(0, {"agent": "MarketAnalyst", "task": "시장 컨텍스트 요약"})
        agents.append({"agent": "ResearchReviewer", "task": "편향·과적합·검증품질 비판"})
        agents.append({"agent": "ResearchWriter", "task": "연구 리포트 작성(신뢰도·한계 포함)"})
        return agents

    def track(self, objective: str, *, goals=None, now: str = "", commit: bool = False) -> dict:
        """진행 추적 — 기존 session_manager(rwf_sessions)로 세션 생성(새 원장 없음). commit=False=프리뷰."""
        try:
            from jarvis.research_workflow.session_manager import ResearchSessionManager
            st = ResearchSessionManager().create_session(objective, goals=goals or [], now=now,
                                                        commit=commit)
            sd = st.to_dict() if hasattr(st, "to_dict") else dict(st)
            return {"session_id": sd.get("session_id"), "goal": sd.get("goal"),
                    "state": sd.get("state"), "committed": commit,
                    "is_advisory": True, "is_decision": False,
                    "note": "진행 추적 — 기존 rwf_sessions 원장 재사용, 새 원장 없음."}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e), "is_advisory": True, "is_decision": False}


def plan(objective: str, *, assistant=None, limit: int = 3) -> dict:
    """모듈 진입점 — ResearchDirector.plan 래퍼."""
    return ResearchDirector(assistant=assistant).plan(objective, limit=limit)
