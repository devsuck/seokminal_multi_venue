"""Evidence gathering (P64-67 공용) — 기존 서브시스템을 **읽기 전용**으로 조율해 근거 번들을 만든다. **실행 없음.**

research_assistant(recall/failure)·research_council·research_queue·portfolio_research·
research_risk_intelligence·research_ingestion(validate)·paper_feedback 를 조합한다. 아무 것도 기록/집행하지 않는다.
결정적. 새 지능 없음 — 순수 조율.
"""
from __future__ import annotations


def _assistant(assistant, reader):
    if assistant is not None:
        return assistant
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    return ResearchAssistantEngine(reader)


def gather_evidence(topic, *, assistant=None, reader=None, metrics=None, new_strategy=None,
                    portfolio=None, strategies=None, backtest=None) -> dict:
    """주제(+선택 입력)에 대해 기존 서브시스템에서 근거를 결정적으로 수집(읽기 전용, 무기록)."""
    asst = _assistant(assistant, reader)
    ev: dict = {"topic": topic}

    # 1) 메모리 회상(과거 실험/성공/실패) + 실패 지능
    recall = asst.recall(topic)
    ev["recall"] = recall.to_dict() if hasattr(recall, "to_dict") else recall
    ev["mistake_check"] = asst.mistake_check(topic)
    ev["failure_intelligence"] = asst.failure_intelligence().to_dict()

    # 2) 연구 협의체(다관점 + 상충)
    from jarvis.research_assistant.council import ResearchCouncilEngine
    ev["council"] = ResearchCouncilEngine(assistant=asst).deliberate(topic).to_dict()

    # 3) 리스크 리포트(주요 리스크·강점·약점·신뢰도)
    from jarvis.research_risk_intelligence.failure_reasoning import StrategyRiskReasoner
    ev["risk"] = StrategyRiskReasoner().risk_report(topic, metrics or {}).to_dict()

    # 4) 포트폴리오 영향(노출/집중/상관) — 입력 있을 때만
    if new_strategy is not None and portfolio is not None:
        from jarvis.portfolio_research.intelligence import PortfolioIntelligence
        ev["portfolio"] = PortfolioIntelligence().exposure_analysis(new_strategy, portfolio).to_dict()
    if strategies:
        from jarvis.portfolio_research.intelligence import PortfolioIntelligence
        ev["combination"] = PortfolioIntelligence().combination_analysis(strategies).to_dict()

    # 5) 검증 완전성(누락 검증 노출 — 조작 없음)
    if backtest is not None:
        from jarvis.research_ingestion.models import validate_backtest
        ev["validation"] = validate_backtest(backtest)

    # 6) 페이퍼(백테스트 밖) 성과 관찰
    from jarvis.research_ingestion.paper_feedback import PaperTradingFeedback
    ev["paper"] = PaperTradingFeedback(assistant=asst).did_it_work_outside_backtest(topic)

    # 7) 다음 연구 제안(미탐색/실패 강건화) — 사람 승인 필요
    from jarvis.research_assistant.research_queue import ResearchQueueEngine
    ev["queue"] = ResearchQueueEngine(assistant=asst).generate(limit=5).to_dict()
    return ev


def historical_cases(evidence: dict, limit: int = 8) -> list:
    """recall 결과에서 실제 과거 실험/기록 참조를 뽑아낸다(설명가능성·유사 사례)."""
    out = []
    src_hits = (evidence.get("recall") or {}).get("source_hits") or {}
    for src in ("experiments", "experiment_runs", "successes", "failures", "lessons", "memories"):
        for h in src_hits.get(src, []):
            out.append({"source": src, "ref": h.get("ref", "?"), "text": h.get("text", "")})
            if len(out) >= limit:
                return out
    return out


def _council_args(evidence: dict) -> tuple:
    c = evidence.get("council") or {}
    supporting, counter = [], []
    for ln in c.get("lenses", []):
        stance = ln.get("stance")
        item = {"lens": ln.get("lens"), "rationale": ln.get("rationale", "")}
        if stance in ("SUPPORT", "INFO"):
            supporting.append(item)
        elif stance in ("CAUTION", "OPPOSE"):
            counter.append(item)
    return supporting, counter


def _alternatives(evidence: dict) -> list:
    c = evidence.get("council") or {}
    return [f"{cf.get('support')} supports while {cf.get('caution')} cautions — interpretation depends on regime"
            for cf in c.get("conflicts", [])]


def remaining_unknowns(evidence: dict) -> list:
    unknowns = []
    val = evidence.get("validation")
    if val and not val.get("validation_complete", True):
        unknowns.append(f"Incomplete validation: missing {val.get('missing_validations')}")
    paper = evidence.get("paper") or {}
    if not paper.get("has_paper_evidence"):
        unknowns.append("No paper (out-of-backtest) confirmation yet")
    council = evidence.get("council") or {}
    if council.get("recommendation", "").startswith("INSUFFICIENT"):
        unknowns.append("Insufficient accumulated evidence — hypothesis/experiment first")
    if not historical_cases(evidence, limit=1):
        unknowns.append("No historical precedent found in memory")
    return unknowns


def aggregate_confidence(evidence: dict) -> tuple:
    """여러 근거를 결정적으로 종합한 신뢰도(HIGH/MEDIUM/LOW) + 요인별 분해."""
    breakdown = {}
    score = 0

    # 검증 완전성
    val = evidence.get("validation")
    if val is None:
        breakdown["validation"] = "unknown"
    elif val.get("validation_complete"):
        breakdown["validation"] = "complete"; score += 2
    else:
        breakdown["validation"] = "incomplete"

    # 협의체 합의
    council = evidence.get("council") or {}
    if council.get("conflicts"):
        breakdown["council"] = "conflict"
    elif council.get("consensus"):
        breakdown["council"] = "consensus"; score += 1
    else:
        breakdown["council"] = "mixed"

    # 리스크 리포트 신뢰도
    rc = (evidence.get("risk") or {}).get("confidence", "LOW")
    breakdown["risk_confidence"] = rc
    score += {"HIGH": 2, "MEDIUM": 1, "LOW": 0}.get(rc, 0)

    # 과거 근거
    hits = (evidence.get("recall") or {}).get("total_hits", 0)
    breakdown["historical_evidence"] = hits
    score += 1 if hits >= 3 else 0

    # 페이퍼 확인
    paper_ok = (evidence.get("paper") or {}).get("has_paper_evidence", False)
    breakdown["paper_confirmation"] = bool(paper_ok)
    score += 1 if paper_ok else 0

    # 과거 실패 반복 위험(감점)
    mc = evidence.get("mistake_check") or {}
    if mc.get("made_this_mistake"):
        breakdown["repeat_failure_risk"] = mc.get("failure_count", 0)
        score -= 1

    label = "HIGH" if score >= 5 else "MEDIUM" if score >= 2 else "LOW"
    return label, breakdown
