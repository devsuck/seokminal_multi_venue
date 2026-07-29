"""Forward Testing Intelligence (P94) — 페이퍼 피드백 고도화. **읽기 전용 분석 + 기존 메모리 학습.**

백테스트 기대 vs 페이퍼 실제를 비교해 성과차·슬리피지·비용가정 오류·레짐 불일치·데이터 누설을 분석하고
학습 피드백을 생성한다. **재사용**: PaperTradingFeedback(P63)·ResearchCritic(P75). 학습은 기존 rmi_ 로.

원칙(문서 §Constitution, §P94): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def analyze(backtest: dict, paper: dict, *, spec: dict | None = None) -> dict:
    """백테스트 vs 페이퍼 심층 분석(결정적) — 차이·슬리피지·비용오류·레짐·누설 + 학습 피드백."""
    from jarvis.research_ingestion.paper_feedback import PaperTradingFeedback
    diff = PaperTradingFeedback().compare(backtest, paper).to_dict()

    bm = (backtest or {}).get("metrics") or backtest or {}
    pm = (paper or {}).get("metrics") or paper or {}
    # 슬리피지/비용 가정 오류
    cost_e, cost_p = _num(bm.get("cost_impact")), _num(pm.get("cost_impact"))
    slippage = round((cost_p - cost_e), 4) if (cost_e is not None and cost_p is not None) else None
    cost_error = bool(slippage is not None and slippage > 0.05)
    # 레짐 불일치
    regime_mismatch = bool((backtest or {}).get("regime") and (paper or {}).get("regime")
                           and backtest["regime"] != paper["regime"])
    # 데이터 누설 의심 — 페이퍼가 백테스트보다 크게 하회하면 인샘플 과적합/누설 신호
    ret_e, ret_p = _num(bm.get("return")), _num(pm.get("return"))
    leakage_suspected = bool(ret_e is not None and ret_p is not None and ret_e > 0
                             and ret_p < ret_e * 0.3)

    findings = []
    if cost_error:
        findings.append(f"비용 가정 오류 — 실현 비용이 백테스트보다 큼(Δ{slippage})")
    if regime_mismatch:
        findings.append("레짐 불일치 — 백테스트/페이퍼 레짐 상이")
    if leakage_suspected:
        findings.append("데이터 누설/과적합 의심 — 페이퍼 성과가 기대 대비 급감")
    if not findings:
        findings.append("특이 차이 없음 — 다만 표본 크기·기간 확인")

    learning = (f"FORWARD TEST — gap={diff.get('return_gap')} cause={diff.get('cause')} · "
                f"{'; '.join(findings)}")
    return {"difference": diff, "slippage": slippage, "cost_assumption_error": cost_error,
            "regime_mismatch": regime_mismatch, "data_leakage_suspected": leakage_suspected,
            "findings": findings, "learning_feedback": learning,
            "is_advisory": True, "is_decision": False,
            "note": "포워드 테스트 분석 — 학습은 기존 rmi_ 로(record_learning). 거래·집행 없음."}


def record_learning(strategy: str, backtest: dict, paper: dict, *, experiment_id: str = "",
                    now: str = "", commit: bool = False) -> dict:
    """학습 피드백을 기존 페이퍼 피드백 경로(rmi_)로 저장 — 새 저장소 없음."""
    from jarvis.research_ingestion.paper_feedback import PaperTradingFeedback
    res = PaperTradingFeedback().record_feedback(strategy, backtest, paper,
                                                 experiment_id=experiment_id, now=now, commit=commit)
    an = analyze(backtest, paper)
    return {"strategy": strategy, "memory_written": res.memory_written,
            "findings": an["findings"], "is_advisory": True, "is_decision": False,
            "note": "학습 → 기존 rmi_ 메모리(future research improvement). 새 저장소 없음."}
