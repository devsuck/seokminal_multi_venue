# Data Integration — KRX / OpenDART / SEC EDGAR (Institutional-quality data)

> 프로토타입 데이터 → **기관급**. 깊이 우선(폭 아님). **데이터만 개선 — 지능 추가 없음.**
> jarvis 는 자격증명 없음(Constitution) → 실제 벤더 호출은 기존 Layer A 클라이언트, jarvis 는 raw 주입받아 조율.
> **중복 provider 없음** — 기존 provider 추상화(P112) 재사용.

## 8개 목표 (`data_connection.py`)

| 목표 | 함수 | 동작 |
|---|---|---|
| availability | `availability(name)` | env_key 기반 AVAILABLE / NEEDS_CREDENTIALS / PUBLIC_AVAILABLE (네트워크 없음) |
| freshness | `freshness(name, records)` | 주입 데이터 최신 timestamp → FRESH/STALE, 없으면 UNKNOWN(정직) |
| schema validation | `schema_validation(category, records)` | 카테고리별 필수 필드 검증, valid_pct |
| retry | `with_retry(fn, attempts)` | 결정적 재시도 계수 + 백오프 스케줄 |
| backfill | `backfill(name, batches, connector)` | 주입 connector 로 과거 배치 처리(멱등은 기존 ingestion) |
| gap detection | `detect_gaps(dates, expected)` | 기대 대비 결측 날짜 |
| lineage | `lineage(name)` | vendor→layer_a_client→provider→consumer 체인(카탈로그 구조) |
| quality scoring | `quality_score(...)` | availability·freshness·schema 합성 → GOOD/PARTIAL/LOW |

## 우선순위 3소스 (기존 PROVIDER_CATALOG 재사용)

| 소스 | 카테고리 | 자격증명 | 현재 상태 |
|---|---|---|---|
| **KRX** | market | `KRX_API_KEY` | NEEDS_CREDENTIALS (키 넣으면 AVAILABLE) |
| **OpenDART** | fundamental/insider | `OPENDART_API_KEY` | NEEDS_CREDENTIALS |
| **SEC EDGAR** | fundamental | 공개 | PUBLIC_AVAILABLE |

각 소스는 **availability · freshness · quality · lineage** 를 노출(`connect_source(name)`).

## UNKNOWN 감소

구조적으로 아는 것(availability·lineage)은 즉시 KNOWN, 데이터가 Layer A 클라이언트로 흐르면
freshness·quality 도 KNOWN → UNKNOWN 점진 감소:

```
데이터 없음:        75% dims KNOWN  (availability·lineage·quality-structure)
SEC-EDGAR raw 주입: 83%+ dims KNOWN (freshness·quality 실측 → GOOD)
전 소스 키+데이터:  100% KNOWN
```

키/데이터 없으면 **가짜를 만들지 않고** NEEDS_CREDENTIALS/UNKNOWN 로 정직하게 노출.

## 예측 시계 시작 (`research_capture.py`)

추적 전략(paper_active·watchlist·paper_candidate)의 현재 위원회 평가 → 예측 사전등록(중복 skip).
horizon 후 P205 Validation Score 가 실제 숫자를 내려면 지금 기록해야 함(달력 시간).

```bash
python -c "from jarvis.research_workflow.research_capture import capture_tracked_research as c; print(c(now='...', commit=True))"
```

현재 시드: 5 예측(committee 소스, LOW confidence — 정직한 베이스라인). 실제 평가는 horizon 경과 후 `evaluate()`.

## 콘솔 (READ ONLY)

`GET /console/data-connection` — 3소스 availability/freshness/quality/lineage + 예측 커버리지 + validation status.

## 제약 준수

**새 provider/DB/원장/벡터DB 없음 · 실행 없음 · 포트폴리오 로직 없음 · 지능 추가 없음.** 기존 provider 재사용,
데이터 계층만. 회귀 통과, governance COMPLIANT, ledger==3.

## 다음 (운영)

키 발급(KRX/OpenDART) → Layer A 클라이언트가 raw 주입 → freshness/quality 실측 KNOWN → UNKNOWN 계속 감소.
데이터 depth 확보 후에야 Investment OS 확장.
