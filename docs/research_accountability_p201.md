# Research Accountability — Forward Prediction Capture (P201)

> Jarvis 를 "연구 보조"에서 **"채점받는 연구 조직"**으로. 연구 산출 시점의 *믿음을 박제*하고
> (사후 편향 차단), horizon 후 결과로 채점한다. **지금은 기록만** — 평가는 달력 시간 확보 후.
> 지금 안 켜면 3개월 뒤에도 forward 데이터가 없다(되돌릴 수 없는 시간).

새 아키텍처 아님 — 기존 `rmi_` 원장 재사용, `ALL_LEDGERS==3` 유지. 지능 추가가 아니라 **책임성 추가.**

## 확정 7제약 (사용자 승인)

1. **evaluation_framework 는 strategy_family 에서 결정적 유도** — capturer 가 못 고른다(골대이동 차단).
2. **결과 4상태**: `RIGHT · WRONG · INVALIDATED · INCONCLUSIVE`. **INVALIDATED 는 실패 아님**(사전 리스크관리 성공). **INCONCLUSIVE 는 데이터/기간 부족**(실패 아님).
3. **모든 예측 기록** — STRONG 만 아님. confidence·source 저장 → 생존편향 차단(안 그러면 "70% 적중" 착각).
4. **사전등록 불변** — success_rule·evaluation_framework·thresholds 는 capture 후 불변(snapshot_hash).
5. **점수 미표시(P205 게이트)** — graded RIGHT/WRONG 표본 < 20 이면 `PROVISIONAL`.
6. **Writer Authority Protocol 경유** — 최소 리스, 저장 백엔드 교체 가능(특정 머신 고정 아님).
7. **기존 원장만 재사용** — 새 ledger/DB/vector 없음.

## 모듈

| 모듈 | 역할 |
|---|---|
| `prediction_registry.py` | 예측 사전등록(capture) · 생명주기(PENDING→ACTIVE→EVALUATED/INVALIDATED/LEARNED) · 동결규칙 채점(evaluate) · 현황(registry_status) |
| `ledger_writer.py` | Writer Authority Protocol — 리스(lease) 기반 단일 활성 writer, `writer_lock.json`, 백엔드 교체 가능 인터페이스(acquire/append/head/verify/release) |

### 평가 프레임워크 (strategy_family → framework, 결정적)

| family | framework | 지표 |
|---|---|---|
| momentum | risk_adjusted_vs_baseline | sharpe vs baseline |
| market_neutral | alpha_tstat | alpha t-stat |
| event | abnormal_return | CAR |
| factor | information_coefficient | IC / decay |
| macro | regime_consistency | regime hit-rate |
| _default(미지) | baseline_relative | baseline 초과 + 논리 유지 |

**성공 규칙의 정신**: "절대적으로 돈 벌었나?"가 아니라 **"당시 논리가 이후에도 유지됐나?"** — baseline 초과 + thesis 유지 + invalidation 미발생.

## 예측 스냅샷 (박제 필드)

```
{ prediction_id, thesis, strategy_id, strategy_family, confidence(HIGH/MEDIUM/LOW),
  source(committee/agent/human_hypothesis/automatic_discovery),
  expected_return, expected_risk, expected_horizon, invalidation_condition, evidence_used[],
  evaluation_framework(유도), success_rule(동결), captured_at, state, outcome, snapshot_hash }
```

## Writer Authority Protocol — "어느 머신"이 아니라 "계약"

특정 머신(맥북) 고정은 미래에 서버/클라우드 생기면 다시 뜯는다. 대신 계약:

- **단일 활성 writer** — 유효 리스 보유자만 append. 다른 노드는 `rejected`.
- 신원: `node_id · session_id · acquired_at · lease_expiry`. 만료 시 핸드오프.
- **백엔드 교체 가능** — 지금 JSONL(`writer_lock.json`), 나중 SQLite/PG는 드라이버 교체.
- 의도적 최소 — 쿠버네티스급 아님. 단일 사용자 규모에 맞춤, 계약만 다중노드 대비.

## 다음 (P202~)

P202 Golden/Characterization 테스트(리팩터링 전 무손실 증명) + Ledger source-of-truth →
P203 Validation 통합(14→5) → P204 Hypothesis 파사드 병합 → **P205 Research Validation Score**
(P201 데이터로, n≥20 전엔 PROVISIONAL) → P206~ KRX/DART 실연결 → Research Factory.

**지금 단계는 "더 똑똑해지기"가 아니라 "틀렸을 때 책임지고 배우기".**
