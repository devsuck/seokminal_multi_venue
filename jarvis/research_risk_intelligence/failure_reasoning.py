"""Risk Intelligence — Strategy Risk Reasoning (P62). 전략마다 **"무엇이 이걸 실패시키는가?"** 에 답한다. **실행 없음.**

기존 research_risk_intelligence(리스크 평가 엔진)·research_assistant(실패 분류체계)·rmi_(메모리)를 재사용해
6개 리스크 범주(Market/Liquidity/Model/Data/Regime/Concentration)로 실패 시나리오를 도출하고 전략 Risk Report
(강점/약점/주요 리스크/신뢰도)를 만든다.

원칙(문서 §Constitution, §P62):
  · **새 DB 없음.** 기존 패키지에 추론 계층 추가, 관찰은 rmi_ 교훈으로 저장(재사용).
  · **거래·집행·자본배분 없음.** 결정적(LLM/랜덤 없음). 산출은 자문 — 사람 결정.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# 6개 리스크 범주(문서 §P62)
R_MARKET, R_LIQUIDITY, R_MODEL, R_DATA, R_REGIME, R_CONCENTRATION = (
    "MARKET", "LIQUIDITY", "MODEL", "DATA", "REGIME", "CONCENTRATION")
RISK_CATEGORIES = (R_MARKET, R_LIQUIDITY, R_MODEL, R_DATA, R_REGIME, R_CONCENTRATION)

_REQUIRED_VALIDATIONS = ("return", "sharpe", "max_drawdown", "volatility", "walk_forward",
                         "out_of_sample", "cost_impact", "parameter_stability", "random_baseline")

# 전략 유형 휴리스틱(이름 키워드 → 강점/약점/주요 리스크) — 결정적
_TYPE_PROFILES = (
    (("momentum", "tsmom", "trend", "breakout", "orb"),
     {"type": "trend", "strength": "Trend persistence",
      "weakness": "Fast reversals / whipsaw", "main": R_REGIME,
      "main_label": "Regime transition"}),
    (("reversion", "mean", "vwap", "pairs", "stat_arb", "statarb"),
     {"type": "mean_reversion", "strength": "Mean-reversion edge in ranges",
      "weakness": "Persistent trends", "main": R_REGIME, "main_label": "Trend regime shift"}),
    (("value", "quality", "factor", "carry", "size"),
     {"type": "factor", "strength": "Factor premium",
      "weakness": "Factor crowding / drawdowns", "main": R_CONCENTRATION,
      "main_label": "Crowded factor positioning"}),
    (("vol", "variance", "gamma", "option"),
     {"type": "volatility", "strength": "Convexity capture",
      "weakness": "Vol regime shifts", "main": R_MARKET, "main_label": "Volatility expansion"}),
)
_DEFAULT_PROFILE = {"type": "generic", "strength": "Documented edge",
                    "weakness": "Unverified robustness", "main": R_MODEL,
                    "main_label": "Model/validation risk"}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _profile(strategy: str) -> dict:
    low = (strategy or "").lower()
    for keys, prof in _TYPE_PROFILES:
        if any(k in low for k in keys):
            return prof
    return _DEFAULT_PROFILE


@dataclass(frozen=True)
class FailureScenario:
    category: str
    scenario: str
    trigger: str
    severity: str                # LOW | MEDIUM | HIGH

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StrategyRiskReport:
    strategy: str
    strategy_type: str
    strength: str
    weakness: str
    main_risk: str               # category
    main_risk_label: str
    confidence: str              # LOW | MEDIUM | HIGH
    scenarios: list = field(default_factory=list)
    category_flags: dict = field(default_factory=dict)
    requires_human_review: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scenarios"] = [s.to_dict() if isinstance(s, FailureScenario) else s
                          for s in self.scenarios]
        return d


class StrategyRiskReasoner:
    """전략별 실패 시나리오·Risk Report. 기존 리스크/분류/메모리 재사용. 실행 권한 없음."""

    def __init__(self, memory_engine=None) -> None:
        self._mem = memory_engine

    def _memory(self):
        if self._mem is None:
            from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
            self._mem = ResearchMemoryIntelligenceEngine()
        return self._mem

    def _confidence(self, metrics: dict) -> str:
        m = metrics or {}
        present = sum(1 for k in _REQUIRED_VALIDATIONS if k in m)
        frac = present / len(_REQUIRED_VALIDATIONS)
        sharpe = _num(m.get("sharpe"))
        if frac >= 0.9 and sharpe is not None and sharpe >= 0.5:
            return "HIGH"
        if frac >= 0.5:
            return "MEDIUM"
        return "LOW"

    def failure_scenarios(self, strategy: str, metrics: dict | None = None) -> list:
        """'무엇이 이걸 실패시키는가?' — 6범주 실패 시나리오(결정적, 지표 트리거 기반)."""
        m = metrics or {}
        prof = _profile(strategy)
        vol = _num(m.get("volatility"))
        cost = _num(m.get("cost_impact"))
        wf = _num(m.get("walk_forward"))
        oos = _num(m.get("out_of_sample"))
        sharpe = _num(m.get("sharpe"))
        pstab = _num(m.get("parameter_stability"))
        conc = _num(m.get("concentration"))
        sc: list = []

        def add(cat, scenario, trigger, sev):
            sc.append(FailureScenario(category=cat, scenario=scenario, trigger=trigger, severity=sev))

        # MARKET
        add(R_MARKET, "Sudden volatility expansion",
            f"volatility={vol}" if vol is not None else "directional exposure",
            "HIGH" if (vol is not None and vol < 0.1) or prof["type"] in ("trend", "volatility") else "MEDIUM")
        # REGIME
        regime_dep = m.get("regime_dependent") is True or prof["main"] == R_REGIME or (wf is not None and wf < 0.5)
        add(R_REGIME, "Market regime reversal",
            "regime-dependent edge" if regime_dep else "regime sensitivity",
            "HIGH" if regime_dep else "MEDIUM")
        # CONCENTRATION
        crowded = (conc is not None and conc >= 0.4) or prof["type"] == "factor"
        add(R_CONCENTRATION, "Crowded positioning",
            f"concentration={conc}" if conc is not None else "shared factor exposure",
            "HIGH" if crowded else "LOW")
        # LIQUIDITY
        add(R_LIQUIDITY, "Transaction cost / liquidity increase",
            f"cost_impact={cost}" if cost is not None else "turnover sensitivity",
            "HIGH" if (cost is not None and cost >= 0.3) else "MEDIUM")
        # MODEL
        overfit = (wf is not None and wf < 0.5) or (pstab is not None and pstab <= 0.3) or \
                  (sharpe is not None and oos is not None and (sharpe - oos) >= 0.5)
        add(R_MODEL, "Overfitting / parameter instability",
            "weak walk-forward/OOS" if overfit else "model assumptions",
            "HIGH" if overfit else "MEDIUM")
        # DATA
        missing = [k for k in _REQUIRED_VALIDATIONS if k not in m]
        add(R_DATA, "Data quality / look-ahead",
            f"missing validations: {len(missing)}" if missing else "data pipeline integrity",
            "MEDIUM" if missing else "LOW")
        return sc

    def risk_report(self, strategy: str, metrics: dict | None = None) -> StrategyRiskReport:
        """전략 Risk Report — 강점/약점/주요 리스크/신뢰도 + 실패 시나리오. 결정적. 자문."""
        prof = _profile(strategy)
        scenarios = self.failure_scenarios(strategy, metrics)
        flags = {}
        for s in scenarios:
            cur = flags.get(s.category)
            rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
            if cur is None or rank[s.severity] > rank[cur]:
                flags[s.category] = s.severity
        # 주요 리스크: 프로파일 우선, 단 HIGH 심각도가 다른 범주에 있으면 그쪽으로 승격
        main_cat, main_label = prof["main"], prof["main_label"]
        highs = [s for s in scenarios if s.severity == "HIGH"]
        if highs and not any(s.category == main_cat and s.severity == "HIGH" for s in scenarios):
            main_cat, main_label = highs[0].category, highs[0].scenario
        return StrategyRiskReport(
            strategy=str(strategy or "unknown_strategy"), strategy_type=prof["type"],
            strength=prof["strength"], weakness=prof["weakness"], main_risk=main_cat,
            main_risk_label=main_label, confidence=self._confidence(metrics or {}),
            scenarios=scenarios, category_flags=flags)

    def record_risk_report(self, report: StrategyRiskReport, experiment_id: str = "",
                           *, now: str = "", commit: bool = False):
        """Risk Report 관찰을 기존 rmi_ 교훈으로 저장(새 저장소 없음). recall 이 찾는다. 자문일 뿐."""
        les = (f"RISK REPORT [{report.strategy}] — main={report.main_risk}"
               f"({report.main_risk_label}) · strength={report.strength} · "
               f"weakness={report.weakness} · confidence={report.confidence}")
        rec = self._memory().record_lesson(
            origin=experiment_id or report.strategy, lesson=les,
            evidence={"strategy": report.strategy, "risk_report": report.to_dict()},
            impact="risk", now=now, commit=commit)
        return rec.to_dict() if hasattr(rec, "to_dict") else rec
