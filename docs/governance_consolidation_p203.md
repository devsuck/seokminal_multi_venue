# Governance Consolidation (P203)

> 검증을 **기능별**이 아니라 **검증 목적별**로 통합. P220/P250이 생겨도 `validate(domain=...)`
> 하나만 부르면 되니 새 `*_validation` 모듈이 안 늘어난다. 지능 추가 아니라 아키텍처 단순화.

## 단일 공개 API

```python
from jarvis.research_workflow import governance
governance.validate(domain="architecture" | "safety" | "data" | "research" | "operations")
governance.validate_all()          # 5도메인 집계 → COMPLIANT/REVIEW_REQUIRED
governance.validation_inventory()  # before/after 성과 지표
```

밖에서는 이 2개만. 내부에서만 기존 12개 검증 모듈을 조율한다.

## 검증 목적별 5 도메인 (기능별 아님)

| Domain | 목적 | Consolidate (조율) | Compose (호출) |
|---|---|---|---|
| **architecture** | ledger==3·중복엔진 없음·DB 없음·import·재사용 | system_validation·release_validation·audit_production·architecture_safety | release_v20/v30 |
| **safety** | execute/trade/allocate 금지·AST·human gate·advisory-only | 모든 `*_safety`·autonomy_safety·safety_check·live_execution 검사 | — |
| **data** | provider·freshness·schema·lineage (P206서 확장) | — | data_quality |
| **research** | hypothesis·experiment·validation·quality·memory | agent_validation·brain_validation·intelligence_validation·memory_audit | quality_monitor·validation_gap·paper_validation·knowledge_quality |
| **operations** | scheduler·workflow·dashboard·health·metrics | ops_validation·operational_validation·validate_loop | production_monitor·operational_metrics |

**핵심 구분 2가지:**
- **Consolidate vs Compose** — 자가검증(`validate_*`/`*_safety`)은 도메인으로 통합, 연구 루프 **부품**
  (quality_monitor·validation_gap·paper_validation 등)은 **삭제 안 하고 도메인이 호출**만.
- **`*_safety` 는 전부 Safety** — 지금까지 페이즈별 부분 AST 스캔이던 걸 한 도메인으로 모음(더 강함).
  `architecture_safety` 는 이름은 safety지만 내용이 구조 불변식이라 Architecture.

## 삭제 대신 Deprecated (≥1 릴리스)

기존 12개 모듈(system_validation·release_validation·autonomy_validation·autonomous_validation_v3·
operational_validation·ops_validation·agent_validation·brain_validation·
institutional_intelligence_validation·memory_audit·research_audit·governance)은 **삭제하지 않는다.**
현재는 facade 의 내부 구현으로 **그대로 살아있고**(콘솔·테스트·`__init__` 의존 보존),
"외부 직접 호출 대신 `governance.validate(domain)`" 로 **deprecated 공지**. 실제 forwarding-shim 전환·삭제는
다음 릴리스(의존성 이관 확인 후).

## Validation Inventory

```
Before:  12 governance modules · ~21 public functions
After:    1 facade · 2 public (validate/validate_all) · 5 internal domains
          12 deprecated modules kept (삭제 아님)
Meaning identical ✅   Golden passed ✅   ledger==3 ✅   governance COMPLIANT ✅
```

## 안전 증명 (P202 안전망 사용)

P202 golden(`test_p202_safety_net`)이 이 통합 후에도 `meaning_preserved=True` 를 확인 —
553건 연결(registry→experiments→graph→recall→governance)이 동일 의미 유지. 회귀 296 통과.

## 다음

P204 Research Discovery Facade(같은 방식) → P204.5 Prediction Coverage Audit → P205 Validation Score.
