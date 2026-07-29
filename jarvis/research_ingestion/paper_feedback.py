"""Paper Trading Feedback Loop (P63) — 페이퍼 트레이딩 결과를 연구 메모리로 되먹인다. **실행 없음.**

백테스트 → 메모리(P54) 를 넘어 백테스트 기대 → 페이퍼 결과 → 차이 분석 → 교훈 으로 확장한다.
페이퍼(모의) 결과 dict 를 입력받아 백테스트 기대와 비교하고, 결정적 원인 추론 + 교훈을 기존 rmi_ 메모리에
연결한다(Experiment·Strategy·Risk·Lesson). 그 결과 recall/assistant 가 "이 전략, 백테스트 밖에서도 됐어?"
에 답할 수 있다.

절대 원칙(문서 §P63):
  · **페이퍼 트레이딩만.** 라이브 브로커·집행·자본배분 없음. 이 모듈은 페이퍼를 실행하지 않고 그 **결과만** 소비.
  · **새 DB 없음.** 기존 rmi_(append-only 해시체인)에 교훈/기억으로 저장(재사용). recall 이 찾는다.
  · 결정적. 산출은 자문 — 사람 결정.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

PAPER_MARKER = "PAPER vs BACKTEST"
_GAP_SEVERE = 0.5      # |상대 격차| 이 이상이면 심각(실패 메모리로도 기록)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _metrics(d: dict) -> dict:
    d = d or {}
    return d.get("metrics") if isinstance(d.get("metrics"), dict) else d


@dataclass(frozen=True)
class DifferenceAnalysis:
    return_gap: float | None
    sharpe_gap: float | None
    drawdown_gap: float | None
    gap_ratio: float | None       # 상대 격차(기대 대비)
    cause: str
    severity: str                 # LOW | MEDIUM | HIGH

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FeedbackResult:
    strategy: str
    experiment_id: str
    difference: dict
    lesson: str
    memory_written: str           # lesson | lesson+failure | none
    is_advisory: bool = True
    is_decision: bool = False
    requires_human_review: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def _infer_cause(exp_m: dict, paper_m: dict, ret_gap, dd_gap) -> tuple:
    """결정적 원인 추론 — 어떤 지표가 벌어졌는지로 판단. 지어내지 않음."""
    cost_p = _num(paper_m.get("cost_impact"))
    cost_e = _num(exp_m.get("cost_impact"))
    turnover = _num(paper_m.get("turnover"))
    if ret_gap is not None and ret_gap < 0:
        # 비용/유동성 격차가 두드러지면 그 원인
        if (cost_p is not None and (cost_e is None or cost_p > cost_e)) or \
           (turnover is not None and turnover >= 0.5):
            return ("Higher transaction impact — backtest underestimated liquidity cost", "HIGH")
        if dd_gap is not None and dd_gap < -0.05:
            return ("Realized drawdown worse than backtest — regime/risk underestimated", "HIGH")
        return ("Performance shortfall vs backtest — investigate before proceeding", "MEDIUM")
    if ret_gap is not None and ret_gap > 0:
        return ("Paper outperformed backtest — verify not a small-sample artifact", "LOW")
    return ("Insufficient comparison data", "LOW")


class PaperTradingFeedback:
    """페이퍼 결과 → 백테스트 대비 차이 분석 → rmi_ 교훈. 페이퍼 실행 안 함. 실행 권한 없음."""

    def __init__(self, memory_engine=None, assistant=None) -> None:
        self._mem = memory_engine
        self._asst = assistant

    def _memory(self):
        if self._mem is None:
            from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
            self._mem = ResearchMemoryIntelligenceEngine()
        return self._mem

    def _assistant(self):
        if self._asst is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            self._asst = ResearchAssistantEngine()
        return self._asst

    def compare(self, backtest_expected: dict, paper_actual: dict) -> DifferenceAnalysis:
        """백테스트 기대 vs 페이퍼 결과 차이 분석(결정적)."""
        e, p = _metrics(backtest_expected), _metrics(paper_actual)
        er, pr = _num(e.get("return")), _num(p.get("return"))
        es, ps = _num(e.get("sharpe")), _num(p.get("sharpe"))
        ed, pd = _num(e.get("max_drawdown")), _num(p.get("max_drawdown"))
        ret_gap = round(pr - er, 4) if (er is not None and pr is not None) else None
        sharpe_gap = round(ps - es, 4) if (es is not None and ps is not None) else None
        dd_gap = round(pd - ed, 4) if (ed is not None and pd is not None) else None
        gap_ratio = None
        if ret_gap is not None and er not in (None, 0):
            gap_ratio = round(ret_gap / abs(er), 4)
        cause, severity = _infer_cause(e, p, ret_gap, dd_gap)
        return DifferenceAnalysis(return_gap=ret_gap, sharpe_gap=sharpe_gap,
                                  drawdown_gap=dd_gap, gap_ratio=gap_ratio,
                                  cause=cause, severity=severity)

    def record_feedback(self, strategy: str, backtest_expected: dict, paper_actual: dict,
                        *, experiment_id: str = "", risk_ref: str = "", now: str = "",
                        commit: bool = False) -> FeedbackResult:
        """차이 분석 → 교훈을 rmi_ 에 저장(Experiment·Strategy·Risk·Lesson 연결). 멱등 아님(관찰 이벤트)."""
        diff = self.compare(backtest_expected, paper_actual)
        name = str(strategy or "unknown_strategy")
        e, p = _metrics(backtest_expected), _metrics(paper_actual)
        lesson = (f"{PAPER_MARKER} [{name}] — expected return={e.get('return')} "
                  f"paper return={p.get('return')} (gap={diff.return_gap}) → {diff.cause}")
        mem = self._memory()
        ev = {"strategy": name, "experiment_id": experiment_id, "risk_ref": risk_ref,
              "backtest": e, "paper": p, "difference": diff.to_dict(), "marker": PAPER_MARKER}
        mem.record_lesson(origin=experiment_id or name, lesson=lesson, evidence=ev,
                          impact="paper_feedback", now=now, commit=commit)
        written = "lesson"
        # 심각한 하회는 실패 메모리로도 연결 → failure_intelligence 가 인지
        if diff.gap_ratio is not None and diff.gap_ratio <= -_GAP_SEVERE:
            mem.record_failure(origin=experiment_id or name,
                               summary=f"{PAPER_MARKER} [{name}] shortfall — {diff.cause}",
                               evidence=ev, now=now, commit=commit)
            written = "lesson+failure"
        return FeedbackResult(strategy=name, experiment_id=experiment_id,
                              difference=diff.to_dict(), lesson=lesson, memory_written=written)

    def did_it_work_outside_backtest(self, topic: str) -> dict:
        """'이 전략, 백테스트 밖(페이퍼)에서도 됐어?' — rmi_ 의 페이퍼 피드백을 회수(recall 재사용). 자문."""
        r = self._assistant().recall(topic)
        paper_hits = []
        for src, hits in (r.source_hits or {}).items():
            for h in hits:
                if PAPER_MARKER.lower() in str(h.get("text", "")).lower():
                    paper_hits.append({"source": src, **h})
        has = bool(paper_hits)
        if not str(topic or "").strip():
            headline = "검색어가 비어 있습니다."
        elif has:
            headline = (f"'{topic}' 페이퍼 관찰 {len(paper_hits)}건 — 백테스트 밖 성과 기록 있음. "
                        "사람 검토 필요.")
        else:
            headline = f"'{topic}' 페이퍼(백테스트 밖) 관찰 없음 — 아직 페이퍼 검증 안 됨."
        return {"topic": topic, "has_paper_evidence": has, "paper_observations": paper_hits,
                "headline": headline, "is_advisory": True, "is_decision": False}
