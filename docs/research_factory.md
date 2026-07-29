# Research Factory — Reject Weak Ideas Earlier

> 목표는 아이디어를 **더 발견**하는 게 아니라 **약한 걸 더 일찍 REJECT** 하는 것.
> 살아남은 연구만 진행. 기관 리서치 공장의 본질 = 깔때기(funnel).

## 깔때기 (각 게이트가 REJECT)

```
Idea
 ↓ Economic rationale   ← LLM 심판(유일한 LLM 사용처)
 ↓ Novelty              (semantic_recall — 과다연구 기각)
 ↓ Similarity           (research_similarity — 중복 기각)
 ↓ Data availability    (provider catalog — 데이터 없으면 기각)
 ↓ Experiment design    (experiment_designer — 설계 불가 기각)
 ↓ Backtest             (외부/사람 — 음수 기각, 자동 실행 없음)
 ↓ Walk-forward         (OOS 붕괴 = overfit 기각)
 ↓ Multiple testing     (BH-FDR — 유의성 못 넘으면 기각)
 ↓ Capacity             (용량 부족 기각)
 ↓ Slippage             (비용 후 음수 기각)
 ↓ Failure analysis     (기각 사유 자동 분류)
 ↓ Paper Candidate      ← 전 게이트 통과한 것만
```

## LLM 사용 규칙 (엄격)

- **LLM 은 절대 아이디어 생성기가 아니다.**
- **LLM 은 오직 economic rationale 심판이다.**
- 프롬프트(고정): *"경제적 메커니즘을 설명하라. 설득력 있는 메커니즘이 없으면 기각하라."*
- judge 는 주입(credential-free). 없으면 rationale 유무만 결정적 사전심사 — **가짜 통과 없음**
  (rationale 없으면 REJECT, 있으면 HELD=심판 대기).
- **그 외 전부 결정적.**

## 실증 (실제 55개 전략)

```
run_on_registry(judge=economic_judge):
  entered: 55  →  paper_candidates: 4  (survival 7.3%)
  rejected_by_gate: economic_rationale 48 · novelty 1 · similarity 1
```

**87%가 첫 게이트(economic)에서 죽는다** — 백테스트 compute 를 쓰기 전에. 이것이 "약한 아이디어 조기 REJECT"의
핵심 가치. 무한 가설 생성 + 무한 백테스트 = 데이터 마이닝 기계 → 방지.

## API

```python
from jarvis.research_workflow import research_factory as rf
rf.run_factory(ideas, judge=llm_economic_judge)   # 아이디어 리스트
rf.run_on_registry(judge=...)                      # 실제 전략 이력에 적용
# 개별 게이트도 호출 가능: economic_rationale_gate·novelty_gate·... (진단용)
```

judge 시그니처: `({thesis, rationale, prompt}) -> {convincing: bool, mechanism, reason}`. **오직 심판.**

콘솔: `GET /console/research-factory` — 깔때기 통계(게이트별 REJECT/HELD).

## 제약 준수

**LLM=심판 전용(생성 절대 아님) · 그 외 결정적 · 자동 백테스트 없음(외부/사람) · 실행/배분/포트폴리오 없음 ·
새 엔진/원장 없음(기존 semantic_recall·similarity·designer·backtest_bridge·failure taxonomy 재사용).**
회귀 343 통과 · golden meaning 보존 · governance COMPLIANT · ledger==3.

## BH-FDR (다중검정 보정)

`_bh_fdr(pvals, alpha=0.1)` — Benjamini-Hochberg. 배치 게이트로 적용(family-wise). 통계 프리미티브(엔진 아님).
데이터 스누핑/다중검정 문제 방어 — 개별 p<0.05 로는 부족, 묶음 FDR 생존만 통과.
