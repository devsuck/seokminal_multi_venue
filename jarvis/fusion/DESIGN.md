# Signal Fusion Layer — 설계 (Priority 1)

검증 통과 전략들의 신호를 **설명가능한 단일 합성신호**로 결합한다.
Fusion은 **주문을 내지 않는다.** `FusionSignal`(자문)만 산출하며,
하류(Meta Portfolio → Execution proposal)가 소비한다. 기존 게이트가 결정한다.

## 불변식(그대로 유지)
- append-only 원장(`fusion_signals.jsonl`), 삭제/재작성 없음.
- FUSION_AGENT = PAPER_ONLY. 자기 권한 확장 불가. 원장 write는 `require(write_fusion_signal)`.
- Fusion은 registry/validation/risk/execution 로직을 건드리지 않는다(읽기+계산만).

## 점진 구현(각 버전 validation 통과 후 다음)
- **v1 `v1_risk_adjusted`** — 리스크조정 가중투표. (본 구현)
- v2 `v2_regime_aware` — 레짐 조건부 가중. (pending)
- v3 `v3_bayesian` — 베이지안 갱신. (pending)
- v4 `v4_meta_learning` — 메타러닝. (pending)

pending 스킴은 `engine_pending` 패턴대로 `NotImplementedError`(가짜결과 금지).

## 인터페이스
- `StrategySignal(strategy_id, instrument, direction∈{-1,0,1}, strength∈[0,1], as_of, source, meta)`
- `StrategyPerf(strategy_id, score≥0, sharpe, volatility, observation_count, underpowered, source)`
- `SignalProvider` — `signals(as_of) -> list[StrategySignal]`
- `WeightingScheme.weights(perfs) -> dict[sid, weight]` (합 1, 음수 없음)
- `FusionEngine.fuse(signals, perfs, as_of) -> list[FusionSignal]`
- `FusionSignal(instrument, direction, confidence∈[0,1], score, scheme, contributions[...])`

## v1 가중식 (리스크조정 가중투표)
```
sharpe_eff = max(0, sharpe or 0)              # 손실전략(음 Sharpe)=0표
shrink     = min(1, n_obs / MIN_OBS)          # 소표본 수축(MIN_OBS=30)
score      = sharpe_eff * shrink              # 표 가중치
weight_i   = score_i / Σ score                # 정규화(합 1)
```
계기별 합성:
```
net        = Σ_i weight_i * direction_i * strength_i   (해당 계기에 신호 낸 전략만)
wsum       = Σ_i weight_i  (동일)
confidence = |net| / wsum                       ∈ [0,1]
direction  = sign(net)  (deadband 1e-9)
```
`contributions[]`에 전략별 weight/direction/strength/signed_contribution 기록 = 설명가능.

## 정직한 현주소
`PROVIDER_REGISTRY`는 비어 있음(= 아직 라이브 계기신호를 내보내는 검증전략 어댑터 미배선).
`agent_gate.PROFILE_TO_STRATEGY`가 비어 있는 것과 같은 원칙 — 어댑터가 붙기 전엔
`run`이 "fusion-eligible 신호 없음"을 정직하게 보고한다. 엔진/가중/검증은 완결·테스트됨.

## Validation (CLI)
`python -m jarvis.fusion validate` — 결정적 속성검사(가중합=1, 단조성, 손실전략=0표,
수축, degenerate 무크래시, 방향정합). 통과해야 해당 버전 "passed".
