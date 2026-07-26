# Migration Safety Net (P202)

> P203(validation 통합)·P204(hypothesis 파사드) 리팩터링 **전에** 까는 안전망.
> 지금 단계 목표는 "더 똑똑한 Jarvis"가 아니라 **"망가지지 않는 Jarvis"**.
> P201이 시계를 시작했고, P202는 그 시계를 깨뜨리지 않는 안전장치.

## 왜 지금

553건 실험 → knowledge graph → recall → agent memory → committee → forward capture 의 **연결 구조**를
건드리는 게 리팩터링이다. characterization test 없이는 "테스트 통과 = 함수 실행됨 + 타입 맞음"일 뿐,
**"과거 연구 결과와 의미가 동일하다"**는 보장이 아니다. `output == output` 이 아니라 `meaning == meaning`.

## 3개 구성 (사용자 P202 확정)

### P202-1 Golden Research Snapshot (`characterization.py`)
연구 **의미 지문**을 고정한다. 두 계층:
- **data_meaning** (예측 무관, 영구 하드 불변): registry(61전략·상태) · experiment_registry(55전략·553행·verdict 지문) · ingestion(by_outcome).
- **composed_meaning** (리팩터링이 깰 수 있는 지점): knowledge_graph(160노드/802엣지) · knowledge_health(grade, lessons ex-predictions) · recall(고정 질의 3개의 tried_before/made_this_mistake/failures/conclusions) · hypothesis_discovery(count/recall_first) · governance(COMPLIANT).

`compare_to_golden()` → `data_meaning` 하드 동일 + `composed` 불변식(recall 연결 보존·governance·hypothesis 안정·knowledge grade). 골든: `tests/golden/research_meaning.json`.

**예측 누적에 강건**: lesson 수치는 `impact=prediction*` 제외 → 예측 캡처가 안전망을 거짓 발동시키지 않음(검증 완료).

### P202-2 Prediction Capture Hook (`prediction_capture_hook.py`)
committee·agent·hypothesis 산출 → `capture_prediction()`. **전달만** — scoring·evaluation·ranking·dashboard 없음.
confidence 정규화(0~1 또는 HIGH/MED/LOW), framework 는 strategy_family 로 결정적 유도(hook 도 못 고름).
'나중에 붙이자'로 미루면 시계가 안 돈다 → 인터페이스는 지금 확정.

### P202-3 Ledger Source-of-Truth 계약 (`ledger_writer.py` 확장)
`LedgerBackend` 추상 계약: `append · read · head · verify`. `JsonlLedgerBackend` 참조 구현(해시체인 검증).
**backend 독립** — 오늘 JSONL, 나중 SQLite/PG 는 드라이버 교체(Research OS 입장에선 같은 ledger).
P201의 WriterAuthority(lease: 단일 활성 writer)와 합쳐 "어느 머신"이 아니라 "계약"으로 source-of-truth 확보.

## 리팩터링 절차 (P203/P204 진입 시)

```
1. python -c "... build_meaning_snapshot()" → 골든 최신화(필요 시)
2. 리팩터링(validation 통합 / hypothesis 파사드)
3. pytest test_p202_safety_net.py → meaning_preserved=True 확인
4. 실패하면 = 연결이 깨진 것 → 되돌린다
```

## 다음

P203 Governance Consolidation(14→5) → P204 Research Discovery Facade → **Prediction Coverage Audit**
(무엇을 기록 중인가: source별 커버리지·confidence 분포·invalidation 결측률) → P205 Research Validation Score(n≥20 전 PROVISIONAL) → P206~ KRX/DART.
