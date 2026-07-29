# Research Accountability Loop — Research Becomes Measurable

> 연구 회계 루프를 닫는다. 연구가 **측정 가능**해야 한다.
> P201(예측 박제)이 시계를 시작했고, 여기서 **채점**한다.

## 구현

- **Forward evaluation** — forward 결과로 예측 채점(`evaluate_forward`, `evaluate_forward_batch`).
- **Prediction registry 통합** — P201 registry 재사용(capture/lifecycle/evaluate).
- **Research batting average** — RIGHT/(RIGHT+WRONG). INVALIDATED/INCONCLUSIVE 제외.
- **Calibration** — confidence 버킷별 표명확률 vs 실제 적중률(P205 재사용).
- **Edge score** — 합성 점수(graded<20 이면 PROVISIONAL, 숫자 없음).
- **Confidence decay** — 미평가로 horizon 초과 시 신뢰 감쇠(오래된 미확인 베팅).
- **Prediction lifecycle** — RIGHT · WRONG · INVALIDATED · INCONCLUSIVE.

## 철칙 — frozen rule 만, 골대 이동 없음

**평가는 항상 예측 시점에 박제된 frozen success_rule 로만.** 사후 평가 없음. 골대 이동 없음.

증명(테스트): forward_result 에 새 `success_rule` 을 주입해도 **무시** — 결과는 스냅샷의 frozen rule 로만 결정.
`baseline 미달 + 주입규칙이 baseline 불요` → 그래도 **WRONG**(frozen rule 이 baseline 요구).

## 절대 pending 숨기지 않음

리포트는 **항상 4버킷 분리**:

```
Pending      (아직 평가 안 됨 — 숨기지 않음)
Evaluated    (RIGHT + WRONG)
Invalidated  (kill 조건 발동 — 실패 아님, 사전 리스크관리 성공)
Inconclusive (데이터/기간 부족 — 실패 아님)
```

`hides_pending = False` 를 명시. 생존편향 차단.

## Confidence decay (신규)

```
age <= horizon        → factor 1.0  (WITHIN_HORIZON)
age > horizon         → factor = 1 - overdue/horizon  (DECAYING)
age >= 2×horizon      → factor 0.0  (EXPIRED)
effective_confidence = stated_prob × factor
```

horizon 넘겨 미확인으로 남은 베팅은 시간이 갈수록 신뢰가 감쇠 — "오래된 미평가 예측을 계속 믿지 않는다."

## API

```python
from jarvis.research_workflow import research_accountability as ra
ra.evaluate_forward(prediction_id, forward_result, commit=True)   # frozen rule 채점
ra.evaluate_forward_batch({pid: forward_result, ...})
ra.confidence_decay(prediction, now=...)
ra.accountability_report(now=...)   # 회계 루프 전체
```

forward_result 관측 필드: `baseline_outperformance · thesis_held · invalidation_triggered · insufficient_data`.
**규칙은 못 바꾼다** — 관측만 제공, 판정은 frozen rule.

콘솔: `GET /console/research-accountability`.

## 제약 준수

**frozen rule 만(사후·골대이동 없음) · pending 숨김 없음 · 실행 로직 없음 · 새 원장 없음(rmi_ 재사용).**
회귀 353 통과 · golden meaning 보존 · governance COMPLIANT · ledger==3.

## 지금 상태 (정직)

시드 예측 5건 = 전부 PENDING(within horizon), evaluated 0 → batting average None, edge score PROVISIONAL.
**정상** — horizon(3M) 경과 후 forward 결과로 `evaluate_forward` 하면 채점 시작. graded>=20 이면 edge score 공개.
지금 억지 숫자를 만들지 않는다.
