"""Backtest Auto-Ingestion Adapter (P54) — 완료된 백테스트를 연구 메모리로 자동 흘려보내는 **얇은 어댑터**. **실행 없음.**

`backtest_runner`(runner.py / simple_runner.py) 및 `jarvis.agents.backtest` 의 **완료 시점 결과 dict** 를
P53 `research_ingestion` 스키마로 매핑하고, 기존 `ResearchIngestionEngine.ingest()` 로 흘려보낸다.

핵심 원칙(문서 §Constitution — Integration over Expansion):
  · **새 저장소/새 실험 시스템을 만들지 않는다.** 기존 P53 파이프라인(→ expt_/rmi_ 원장)만 재사용.
  · **실행 경로를 복제하지 않는다.** 백테스트는 이미 끝났고, 그 산출 dict 만 받는다(계산 없음, 순수 매핑).
  · **멱등.** 동일 백테스트 재수집은 no-op(P53 backtest_hash 기반 중복탐지).
  · 거래·집행·배포·자본배분 없음. 사람 판단은 항상 필수(연구 메모리는 자문일 뿐).

두 가지 완료-시점 출력 형태를 지원한다:
  (a) 평면형 — run_backtest / run_simple_backtest 반환:
      {sharpe_ratio, max_drawdown, total_pnl_pct, volatility, win_rate, trades, ...}
  (b) 중첩형 — jarvis.agents.backtest.run 반환:
      {strategy_id, metrics: {sharpe, ann_return, wf_first, wf_second, ...}, provenance: {...}}

원본 백테스트에 없는 **필수 검증지표**(walk_forward·out_of_sample·cost_impact·parameter_stability·
random_baseline)는 검증 하네스(research/validation)가 산출한 값을 `context["metrics"]` 로 보강한다.
보강이 없으면 수집은 정상 진행되되 결과는 INCOMPLETE 로 판정된다(누락을 숨기지 않음).
"""
from __future__ import annotations

from jarvis.research_ingestion.models import IngestionResult, _num

# ── 평면형(backtest_runner) 성능지표 → 표준 스키마 키 별칭 ──
# 값 계산은 하지 않는다. 존재하는 키를 표준 이름으로 옮길 뿐(순수 매핑).
_METRIC_ALIASES = {
    "return": ("return", "total_pnl_pct", "ann_return", "annual_return"),
    "sharpe": ("sharpe", "sharpe_ratio"),
    "max_drawdown": ("max_drawdown", "mdd"),
    "volatility": ("volatility", "vol_annualized"),
    "walk_forward": ("walk_forward", "wf_consistency", "wf_first"),
    "out_of_sample": ("out_of_sample", "oos", "wf_second"),
    "cost_impact": ("cost_impact",),
    "parameter_stability": ("parameter_stability",),
    "random_baseline": ("random_baseline", "random_percentile"),
}

# context 로 넘어올 수 있는 연구 메타데이터(백테스트 산출에는 없는 값)
_CONTEXT_META = (
    "strategy_name", "strategy_version", "hypothesis", "universe", "period",
    "features", "entry_rules", "exit_rules", "risk_rules", "source",
)
# 결과 판정에 영향을 주는 선택적 통과 필드
_CONTEXT_PASSTHROUGH = ("outcome", "root_cause", "failure_reason", "lesson")


def _first(src: dict, *keys):
    """src 에서 keys 순서로 처음 발견되는 non-None 값 반환(계산 없음)."""
    for k in keys:
        if k in src and src[k] is not None:
            return src[k]
    return None


def _provenance(raw: dict) -> dict:
    prov = raw.get("provenance")
    return dict(prov) if isinstance(prov, dict) else {}


def _extract_metrics(raw: dict) -> dict:
    """완료-시점 dict 에서 표준 성능지표를 뽑아낸다(평면형·중첩형 모두). 순수 매핑."""
    nested = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else None
    src = {**raw, **(nested or {})}   # 중첩형이면 metrics 를 위로 병합(평면 키도 함께 탐색)
    out: dict = {}
    for std, aliases in _METRIC_ALIASES.items():
        val = _first(src, *aliases)
        num = _num(val)
        if num is not None:
            out[std] = num
    # 레짐 의존 플래그(실패 자동분류에서 사용) — 있으면 metrics 로 전달
    if src.get("regime_dependent") is True:
        out["regime_dependent"] = True
    return out


def adapt(backtest_output: dict, *, context: dict | None = None) -> dict:
    """백테스트 완료-시점 dict → P53 research_ingestion 스키마 dict. **순수 매핑, 계산·실행 없음.**

    context: 백테스트 산출에 없는 연구 메타데이터·검증지표를 보강한다.
      context["metrics"] = 검증 하네스가 산출한 검증지표(walk_forward/out_of_sample/…) 보강.
      나머지 키(strategy_name, hypothesis, universe, period, features, *_rules, source, outcome, …).
    """
    raw = backtest_output or {}
    ctx = dict(context or {})

    metrics = _extract_metrics(raw)
    # 검증 하네스 산출 지표 보강(원본에 없을 때만 — 원본을 덮어쓰지 않음)
    for k, v in (ctx.get("metrics") or {}).items():
        num = v if k == "regime_dependent" else _num(v)
        if num is not None and metrics.get(k) is None:
            metrics[k] = num

    prov = _provenance(raw)
    schema = {
        "strategy_name": (ctx.get("strategy_name") or raw.get("strategy_id")
                          or raw.get("instrument_id") or "unknown_strategy"),
        "strategy_version": str(ctx.get("strategy_version")
                                or prov.get("code_version") or ""),
        "hypothesis": ctx.get("hypothesis", ""),
        "universe": ctx.get("universe") or raw.get("instrument_id") or "",
        "period": ctx.get("period") or {},
        "features": list(ctx.get("features") or []),
        "entry_rules": ctx.get("entry_rules", ""),
        "exit_rules": ctx.get("exit_rules", ""),
        "risk_rules": ctx.get("risk_rules", ""),
        "metrics": metrics,
        "source": ctx.get("source") or raw.get("source") or "backtest_runner",
    }
    for k in _CONTEXT_PASSTHROUGH:
        if ctx.get(k) not in (None, ""):
            schema[k] = ctx[k]
    if prov:
        schema["provenance"] = prov   # 감사 추적(data_version·code_version·config_hash·seed·ts)
    return schema


def ingest_backtest(backtest_output: dict, *, context: dict | None = None,
                    engine=None, now: str = "", commit: bool = False,
                    strict: bool = False) -> IngestionResult:
    """완료된 백테스트 1건 → 연구 메모리 **자동 수집 훅**. 얇은 어댑터 → 기존 P53 ingest().

    이것이 '백테스트 완료 → 연구 기억' 자동 연결의 단일 진입점이다.
    · 완료-시점 dict 를 P53 스키마로 매핑(adapt) 후 ResearchIngestionEngine.ingest() 호출.
    · **멱등** — 동일 백테스트 재호출은 no-op(deduplicated=True). append-only 해시체인 보존.
    · commit=False = 드라이런(판정 프리뷰, 기록 없음). commit=True = 기존 원장에 기록.
    · 실행·집행·배포 없음. 반환은 자문(is_advisory=True). 사람 판단 필수.
    """
    if engine is None:
        from jarvis.research_ingestion.engine import ResearchIngestionEngine
        engine = ResearchIngestionEngine()
    schema = adapt(backtest_output, context=context)
    return engine.ingest(schema, now, commit=commit, strict=strict)


def ingest_backtests(backtest_outputs, *, contexts=None, engine=None,
                     now: str = "", commit: bool = False) -> list:
    """여러 백테스트 일괄 수집(과거 백테스트 백필용). 각 건 멱등."""
    outs = list(backtest_outputs or [])
    ctxs = list(contexts or [])
    results = []
    for i, bt in enumerate(outs):
        ctx = ctxs[i] if i < len(ctxs) else None
        results.append(ingest_backtest(bt, context=ctx, engine=engine, now=now, commit=commit))
    return results
