# Research Ledger Backfill & Sync (운영 룬북)

> 아키텍처 동결(v2.0) 이후 작업 = **operations · data quality**. 이 문서는 신규 기능이 아니라,
> **기존 실험 이력을 Research OS 연구 원장에 채우는 재실행 가능한 절차**다.

## 무엇을 하는가

기존 트레이딩 플랫폼의 **실제 실험 이력**(`research.agents.experiment_registry`)을 읽어,
이미 존재하는 P53 수집 파이프라인(`ResearchIngestionEngine`)으로 흘려보낸다. 그 결과
Research OS 의 아래가 **실데이터**로 채워진다:

- `expt_*` 원장 — 실험/실행/파라미터/결과 (experiment_tracking)
- `rmi_*` 원장 — 실패·성공·교훈 (research_memory_intelligence)
- `ring_ingestions` 원장 — 수집 감사(해시체인)

→ knowledge-graph, semantic recall, failure-intelligence, strategy-lifecycle, conflict-detection 이
비어있지 않고 실제 연구 history 로 동작한다.

## 원칙 (Constitution 준수)

- **통합만.** 기존 registry(읽기) + 기존 `ResearchIngestionEngine`(쓰기)만 재사용. **새 원장/엔진 없음.**
- **날조 없음.** 각 실험의 **실제 status/verdict** 를 연구-메모리 결과로 **충실히 번역**할 뿐이다.
  없는 검증지표(volatility·cost_impact·parameter_stability 등)는 정직하게 비운다(UNKNOWN).
- **멱등.** 동일 실험 재수집은 no-op(P53 backtest_hash 기반 중복탐지). 안전하게 반복 실행 가능.
- **결정적.** 동일 입력 → 동일 출력(실험 자기 timestamp 를 감사시각으로 사용).
- **거래·집행·배포·자본배분 없음.** 산출은 자문. 사람 판단 필수.

### status → 연구-메모리 결과 매핑 (충실한 번역)

| 원본 status | 결과 | 메모리 |
|---|---|---|
| `rejected`, `no_effect`, `research_negative_drift` | FAILURE | 실패 + 교훈(원문 verdict/note 보존) |
| `paper_candidate*` | SUCCESS | 성공 |
| `candidate`, `v2_shadow`, `watchlist` | PARTIAL | 없음(미확정) |
| `weak`, `underpowered`, `inconclusive`, `blocked_by_data`, `analysis`, (미지) | INCOMPLETE | 없음(정직한 미완) |

### 중복 축소 (무언 절삭 금지)

전략별로 **distinct verdict 당 최신 1건**만 채택. 자동스캔 반복 로깅(예: `auto_fac_*` 158회 동일 verdict)은
1건으로 접히고, 실제 반복 실험(서로 다른 verdict)은 각각 보존된다. 접힌 건수는 결과에 `rows_collapsed_by_verdict_dedup` 로 명시된다.

## 실행

```bash
# 드라이런(원장 무변경, 미리보기)
python -m jarvis.research_workflow.backfill
python -m jarvis.local_runtime sync --dry-run

# 수집(기존 원장에 기록, 멱등)
python -m jarvis.research_workflow.backfill --commit
python -m jarvis.local_runtime sync
```

현재 스냅샷 기준 결과: **68 records** (FAILURE 38 · PARTIAL 12 · INCOMPLETE 13 · SUCCESS 5),
55개 전략, 485개 반복-로깅 행 축소.

## 자동 트리거 (auto-populate)

세 경로 모두 같은 멱등 `sync()` 를 부른다:

1. **로컬 런타임 부팅** — `python -m jarvis.local_runtime start --commit` (또는 `restart --commit`) 시
   부팅 훅이 `sync()` 를 best-effort 로 호출(실패해도 런타임 무중단).
2. **일간 연구 사이클** — `research_scheduler` 의 `daily` 태스크에 `research_ledger_sync` 포함.
   주기 실행은 외부(cron/launchd/사람)가 호출.
3. **명시 호출** — 위 CLI.

### macOS 정기 실행 예시 (cron)

```cron
# 평일 08:00 KST 연구 원장 동기화(멱등)
0 8 * * 1-5 cd /path/to/seokminal_multi_venue && /usr/bin/env python -m jarvis.local_runtime sync >> ~/jarvis_sync.log 2>&1
```

## MacBook 업데이트 흐름

- **코드**(backfill 룬북·트리거 배선)는 `git pull` 로 갱신된다.
- **데이터**(`_state/expt_*·rmi_*·ring_*` 원장)는 이 저장소가 `_state/*.jsonl` 을 git 추적하므로
  `git pull` 로 함께 내려온다. 즉 커밋된 68 records 는 pull 만으로 반영된다.
- pull 이후 로컬에 더 최신 실험 이력이 있으면 `python -m jarvis.local_runtime sync` 한 번으로
  신규분만 멱등 흡수된다(기존분은 no-op).
