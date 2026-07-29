# Research Discovery Facade + Call Graph Golden (P204)

> 가설 발견 3겹(hypothesis_generator·creative_hypothesis·hypothesis_discovery + search/expansion/critic/
> priority)을 **단일 공개 namespace** `research_discovery` 로 묶는다. 내부 모듈은 **유지·deprecated**.
> 그리고 meaning 뿐 아니라 **호출 구조**까지 보존하는지 Call Graph Golden 으로 검증.

## 단일 파사드 — 실제 연구 흐름

```python
from jarvis.research_workflow import research_discovery as rd
rd.generate(topic, mode="recall_first"|"creative"|"template")   # 발견
rd.expand(hypothesis, scale=False|True)                          # 확장(트리/대규모)
rd.criticize(hypothesis_or_spec)                                 # 비판(PASS/WARN/BLOCK)
rd.rank(candidates)                                              # 선택(우선순위)
rd.discover(topic)                                               # 편의: generate→rank
```

밖에서는 이것만. 내부에서만 기존 모듈 조율(모두 살아있음, deprecated):
hypothesis_discovery·creative_hypothesis·hypothesis_generator·research_search·research_expansion·
research_critic·research_priority.

## Call Graph Golden — "의미"에 더해 "호출 구조" 보존

meaning golden(`output≠output, meaning==meaning`)만으로는 파사드가 내부 모듈을 **재구현**했는지
**조율**했는지 구분 못 한다. Call Graph Golden 이 그걸 잡는다.

```
build_call_graph()  → {module: sorted[참조하는 형제 모듈]}  (AST, 결정적)
compare_call_graph(golden) → call_graph_identical
```

현재 지문(golden `tests/golden/call_graph.json`):
```
research_discovery   → creative_hypothesis · hypothesis_discovery · hypothesis_generator ·
                       research_critic · research_expansion · research_priority · research_search
hypothesis_discovery → creative_hypothesis
creative_hypothesis  → hypothesis_generator
research_expansion   → research_search
research_priority    → experiment_prioritization
```

→ `research_discovery` 가 7개 내부 모듈을 **참조**한다 = 재구현이 아니라 조율. 리팩터링이 이 위상을 바꾸면
(예: 파사드가 내부를 우회·재구현) `graph_hash` 가 달라져 **즉시 감지**.

## 두 골든이 함께 지킴

| Golden | 검증 | 파일 |
|---|---|---|
| Meaning | 553건 연결 의미 동일 | `golden/research_meaning.json` |
| Call Graph | 호출/조율 구조 동일 | `golden/call_graph.json` |

P204 후 둘 다 통과 확인 — `meaning_preserved=True` + `call_graph_identical=True`. 회귀 307 통과.

## 삭제 대신 Deprecated (≥1 릴리스)

hypothesis 관련 내부 모듈 전부 그대로 살아있고 import 가능(테스트 확인). `research_discovery` 는
조율만 추가. 물리 삭제·forwarding-shim 전환은 의존성 이관 확인 후 다음 릴리스.

## 다음

P204.5 Prediction Coverage Audit(capture rate·source·confidence·missing invalidation·duplicate·
pending/evaluated) → 90% 넘으면 **P205 Research Validation Score**(n<20 PROVISIONAL).
