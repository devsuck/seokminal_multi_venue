"""Continuous Learning (P82) — 연구가 끝나면 **기존 메모리를 자동 갱신**한다. **새 저장소 없음.**

완료된 연구(백테스트+선택 포트폴리오/페이퍼)를 기존 write 경로로 흘려보낸다:
research_ingestion.ingest(교훈/실패/성공) + PaperTradingFeedback.record_feedback +
PortfolioIntelligence.record_portfolio_impact + StrategyRiskReasoner.record_risk_report.
그 결과 recall/failure_intelligence/knowledge graph/priority 가 모두 갱신된다. **모두 rmi_ 재사용.**

원칙(문서 §Constitution, §P82): 새 저장소·새 엔진 없음 — 기존 write 경로 조율. 결정적. 거래·집행 없음.
"""
from __future__ import annotations


def on_research_complete(backtest: dict, *, portfolio=None, paper=None, experiment_id="",
                         now="", commit=False) -> dict:
    """연구 완료 → 기존 메모리 전 채널 갱신(조율). 반환 = 갱신된 채널 요약. 자문·사람 결정."""
    bt = backtest or {}
    name = str(bt.get("strategy_name", "") or "research")
    updated: list = []

    # 1) 핵심: 수집 파이프라인(교훈/실패/성공 + ring_ 감사) 재사용
    from jarvis.research_ingestion.engine import ResearchIngestionEngine
    ing = ResearchIngestionEngine().ingest(bt, now, commit=commit)
    updated.append({"channel": "ingestion", "outcome": ing.outcome,
                    "memory_written": ing.memory_written, "experiment_id": ing.experiment_id})
    exp_id = experiment_id or ing.experiment_id

    # 2) 리스크 리포트 → rmi_ 교훈
    try:
        from jarvis.research_risk_intelligence.failure_reasoning import StrategyRiskReasoner
        rr = StrategyRiskReasoner()
        rep = rr.risk_report(name, bt.get("metrics"))
        rr.record_risk_report(rep, experiment_id=exp_id, now=now, commit=commit)
        updated.append({"channel": "risk", "main_risk": rep.main_risk})
    except Exception as e:  # noqa: BLE001
        updated.append({"channel": "risk", "error": str(e)})

    # 3) 포트폴리오 영향(있으면) → rmi_ 교훈
    if portfolio is not None and bt.get("new_strategy"):
        try:
            from jarvis.portfolio_research.intelligence import PortfolioIntelligence
            pi = PortfolioIntelligence()
            rep = pi.exposure_analysis(bt["new_strategy"], portfolio)
            pi.record_portfolio_impact(name, exp_id, rep.to_dict(), now=now, commit=commit)
            updated.append({"channel": "portfolio", "flags": len(rep.risk_flags)})
        except Exception as e:  # noqa: BLE001
            updated.append({"channel": "portfolio", "error": str(e)})

    # 4) 페이퍼 피드백(있으면) → rmi_ 교훈/실패
    if paper is not None:
        try:
            from jarvis.research_ingestion.paper_feedback import PaperTradingFeedback
            res = PaperTradingFeedback().record_feedback(name, bt, paper, experiment_id=exp_id,
                                                         now=now, commit=commit)
            updated.append({"channel": "paper", "memory_written": res.memory_written})
        except Exception as e:  # noqa: BLE001
            updated.append({"channel": "paper", "error": str(e)})

    return {"strategy": name, "committed": commit, "updated_channels": updated,
            "channels_touched": [u["channel"] for u in updated],
            "note": ("연구 완료 → recall/failure_intelligence/knowledge graph/priority 반영 "
                     "(기존 rmi_ 재사용, 새 저장소 없음)."),
            "is_advisory": True, "is_decision": False}


def learning_status() -> dict:
    """지속 학습 커버리지(읽기 전용) — 각 메모리 채널의 축적량."""
    def _n(mod, fn):
        try:
            m = __import__(mod, fromlist=[fn])
            return len(list(getattr(m, fn)() or []))
        except Exception:  # noqa: BLE001
            return 0
    channels = {
        "lessons": _n("jarvis.research_memory_intelligence.ledger", "read_lessons"),
        "failures": _n("jarvis.research_memory_intelligence.ledger", "read_failures"),
        "successes": _n("jarvis.research_memory_intelligence.ledger", "read_successes"),
        "ingestions": _n("jarvis.research_ingestion.ledger", "read_ingestions"),
    }
    return {"channels": channels, "total": sum(channels.values()),
            "is_advisory": True, "is_decision": False,
            "note": "기존 메모리 채널 축적량 — 새 저장소 없음."}
