"""Portfolio Intelligence Layer (P61) — 연구 아이디어가 **포트폴리오에 미치는 영향**을 이해한다. **실행 없음.**

전략 → 성과지표(과거) 를 넘어서 전략 → 포트폴리오 맥락 → 리스크 영향 으로 확장한다. 노출(섹터/자산/국가/
팩터/상관) 분석과 전략 조합(상관/중복/드로다운 유사/레짐 의존) 분석을 결정적으로 수행하고, 관찰을 기존
연구 메모리(rmi_)에 교훈으로 연결한다(Strategy → Experiment → Portfolio Effect → Lesson).

원칙(문서 §Constitution — Integration over Expansion, §P61):
  · **새 DB 없음.** 기존 portfolio_research 패키지에 분석 계층을 추가하고, 관찰은 rmi_ 교훈으로 저장(재사용).
  · **거래·집행·자본배분 없음.** 입력은 호출자가 제공한 노출/수익률(의사결정 지원용) — 라이브 데이터 아님.
  · 결정적(LLM/랜덤 없음). 산출은 자문 — 사람이 최종 결정.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

_CONC_THRESHOLD = 0.40      # 단일 노출이 이 이상이면 집중 경보
_CORR_HIGH, _CORR_MED = 0.60, 0.30
DIMENSIONS = ("sector", "asset", "country", "factor")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pearson(a, b) -> float | None:
    """두 수익률 계열의 피어슨 상관(순수 파이썬, 결정적). 길이 불일치/무분산이면 None."""
    xs = [_num(x) for x in (a or [])]
    ys = [_num(y) for y in (b or [])]
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 2:
        return None
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    if sxx <= 1e-12 or syy <= 1e-12:
        return None
    return round(sxy / math.sqrt(sxx * syy), 4)


def _corr_label(c) -> str:
    if c is None:
        return "UNKNOWN"
    ac = abs(c)
    return "HIGH" if ac >= _CORR_HIGH else "MEDIUM" if ac >= _CORR_MED else "LOW"


@dataclass(frozen=True)
class ExposureReport:
    strategy: str
    weight_new: float
    by_dimension: dict           # dim -> {key: {before, after, delta, concentration}}
    top_concentration: dict      # {dimension, key, after}
    additional_correlation: str  # HIGH | MEDIUM | LOW | UNKNOWN
    risk_flags: list
    verdict: str
    requires_human_review: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CombinationReport:
    strategies: list
    pairs: list                  # [{a,b,correlation,overlap,drawdown_similarity,regime_overlap,diversification}]
    verdict: str
    requires_human_review: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class PortfolioIntelligence:
    """포트폴리오 영향·조합 분석 + 관찰의 메모리 연결. 결정적. 실행 권한 없음."""

    def __init__(self, memory_engine=None) -> None:
        self._mem = memory_engine

    def _memory(self):
        if self._mem is None:
            from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
            self._mem = ResearchMemoryIntelligenceEngine()
        return self._mem

    # ── 노출 분석: 새 전략이 기존 포트폴리오 노출에 미치는 영향 ──
    def exposure_analysis(self, new_strategy: dict, portfolio: dict) -> ExposureReport:
        """새 전략을 weight_new 만큼 편입할 때 섹터/자산/국가/팩터 노출 변화·집중·상관 영향(결정적)."""
        ns = new_strategy or {}
        pf = portfolio or {}
        name = str(ns.get("name", "")).strip() or "unknown_strategy"
        w = _num(pf.get("weight_new", ns.get("weight", 0.1))) or 0.0
        w = max(0.0, min(1.0, w))
        ns_exp = ns.get("exposures") or {}
        pf_exp = pf.get("exposures") or {}
        by_dim: dict = {}
        flags: list = []
        top = {"dimension": "", "key": "", "after": 0.0}
        for dim in DIMENSIONS:
            keys = set((ns_exp.get(dim) or {})) | set((pf_exp.get(dim) or {}))
            dim_out = {}
            for k in sorted(keys):
                before = _num((pf_exp.get(dim) or {}).get(k, 0.0)) or 0.0
                new_i = _num((ns_exp.get(dim) or {}).get(k, 0.0)) or 0.0
                after = round(before * (1 - w) + w * new_i, 4)   # 편입 후 재정규화(합 보존)
                delta = round(after - before, 4)
                conc = after >= _CONC_THRESHOLD and delta > 0
                dim_out[k] = {"before": round(before, 4), "after": after,
                              "delta": delta, "concentration": conc}
                if conc:
                    flags.append(f"Concentration increase: {dim}/{k} {before:.0%}→{after:.0%}")
                if after > top["after"]:
                    top = {"dimension": dim, "key": k, "after": after}
            if dim_out:
                by_dim[dim] = dim_out
        # 추가 상관: 명시값 우선, 없으면 수익률로 계산
        corr = _num(pf.get("correlation"))
        if corr is None:
            corr = pearson(ns.get("returns"), pf.get("returns"))
        corr_label = _corr_label(corr)
        if corr_label == "HIGH":
            flags.append(f"High correlation to existing portfolio ({corr})")
        if flags:
            verdict = "집중/상관 증가 — 분산 효과 제한. 사람 검토 필요."
        else:
            verdict = "분산에 기여 — 다만 사람 검토 후 결정."
        return ExposureReport(
            strategy=name, weight_new=round(w, 4), by_dimension=by_dim, top_concentration=top,
            additional_correlation=corr_label, risk_flags=flags, verdict=verdict)

    # ── 전략 조합 분석: 상관/중복/드로다운 유사/레짐 의존 ──
    def combination_analysis(self, strategies: list) -> CombinationReport:
        """여러 전략의 쌍별 상관·중복·드로다운 유사·레짐 중복 → 분산 이점 여부(결정적)."""
        strats = [s for s in (strategies or []) if isinstance(s, dict)]
        names = [str(s.get("name", f"S{i}")) for i, s in enumerate(strats)]
        pairs = []
        div_pairs = 0
        for i in range(len(strats)):
            for j in range(i + 1, len(strats)):
                a, b = strats[i], strats[j]
                corr = pearson(a.get("returns"), b.get("returns"))
                if corr is None:
                    corr = _num((a.get("correlation_to") or {}).get(names[j]))
                ha, hb = set(a.get("holdings") or a.get("universe_set") or []), \
                    set(b.get("holdings") or b.get("universe_set") or [])
                overlap = round(len(ha & hb) / len(ha | hb), 4) if (ha | hb) else None
                dda, ddb = _num(a.get("max_drawdown")), _num(b.get("max_drawdown"))
                dd_sim = round(1 - min(1.0, abs(dda - ddb)), 4) if (dda is not None and ddb is not None) else None
                ra, rb = set(a.get("regimes") or []), set(b.get("regimes") or [])
                regime_overlap = round(len(ra & rb) / len(ra | rb), 4) if (ra | rb) else None
                if corr is not None and abs(corr) < _CORR_MED:
                    div = "BENEFIT"
                    div_pairs += 1
                elif corr is not None and abs(corr) >= _CORR_HIGH:
                    div = "REDUNDANT"
                else:
                    div = "MODERATE"
                pairs.append({"a": names[i], "b": names[j], "correlation": corr,
                              "overlap": overlap, "drawdown_similarity": dd_sim,
                              "regime_overlap": regime_overlap, "diversification": div})
        if div_pairs and div_pairs == len(pairs):
            verdict = "낮은 상관 — 분산 이점 가능(사람 검토)."
        elif any(p["diversification"] == "REDUNDANT" for p in pairs):
            verdict = "높은 상관 쌍 존재 — 중복/집중 주의(사람 검토)."
        else:
            verdict = "혼재 — 쌍별 상관 확인 후 사람 판단."
        return CombinationReport(strategies=names, pairs=pairs, verdict=verdict)

    # ── 포트폴리오 메모리: 관찰을 rmi_ 교훈으로 연결(Strategy→Experiment→Portfolio Effect→Lesson) ──
    def record_portfolio_impact(self, strategy: str, experiment_id: str, impact: dict,
                                *, lesson: str = "", now: str = "", commit: bool = False):
        """포트폴리오 영향 관찰을 기존 rmi_ 교훈으로 저장(새 저장소 없음). recall 이 찾는다. 자문일 뿐."""
        eff = impact or {}
        summary = (f"PORTFOLIO IMPACT [{strategy}] — "
                   f"{eff.get('verdict', '')} | flags={list(eff.get('risk_flags', []))[:3]}")
        les = lesson or summary
        mem = self._memory()
        rec = mem.record_lesson(origin=experiment_id or strategy, lesson=les,
                                evidence={"strategy": strategy, "portfolio_effect": eff},
                                impact="portfolio", now=now, commit=commit)
        return rec.to_dict() if hasattr(rec, "to_dict") else rec
