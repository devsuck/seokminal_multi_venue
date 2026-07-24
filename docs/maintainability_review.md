# Jarvis 플랫폼 유지보수 진단 (Maintainability Review)

> 생성: P41 `integration_audit` 실데이터 + 판단. 읽기전용 분석 — 이 문서는 코드를 바꾸지 않는다.
> 결론 요약: **기능이 부족한 게 아니라, 같은 책임이 너무 많은 독립 패키지로 쪼개져 있다.** 정리(통합) 대상.

---

## 1. 규모 진단 (지금 상태)

| 지표 | 값 |
|---|---|
| jarvis 하위 패키지 | **144개** |
| 완결형 패키지(engine+ledger+models) | 105개 |
| 전체 코드 라인 | 약 **223,800** |
| `research_*` 패키지 | **48개** |
| `research_*` 코드 라인 | 약 **108,000 (전체의 ~48%)** |
| 중복/과중복 계열 | 18개 |
| 다른 모듈이 import 안 하는 패키지 | 112개 |
| 총 커밋 | 189 |

**한 줄 요약:** 플랫폼 코드의 **절반이 `research_*` 계열**에 있고, 그 대부분은 서로를 참조하지 않는 독립 섬이다.

---

## 2. 과잉 추가된 기능 (over-added) — 핵심 문제

`research_*` 48개를 책임(테마)별로 묶으면 **같은 일을 하는 모듈이 겹겹이** 쌓여 있다:

| 테마 | 개수 | 모듈 |
|---|---|---|
| **조율/관리** | **9** | research_agents, research_coordinator, research_council, research_organization, research_orchestration, research_operations, research_manager, research_control, research_collaboration |
| **감독/거버넌스** | **5** | research_governance, research_compliance, research_reviewer, research_validation, research_reliability |
| **관측(observability)** | **3** | research_observability, research_observatory, research_monitoring |
| **자기개선** | **4** | research_evolution, research_improvement, research_learning, research_lifecycle |
| **지식/기억** | 3+ | research_memory, research_kg, research_literature (+ research_memory_intelligence, research_memory_system) |

> "연구 에이전트를 조율한다"는 **한 가지 책임**에 9개의 독립 패키지가 있다. 감독 5개, 관측 3개도 마찬가지.
> 이건 기능 부족이 아니라 **책임 경계의 과분할(over-fragmentation)** 이다.

---

## 3. 불필요/의심 기능 (dead/suspect) — 단, "삭제 목록" 아님

- 112개 패키지가 다른 모듈에서 import 되지 않는다.
- **주의(중요):** 이 시스템의 계층은 대부분 **Python import 가 아니라 원장 파일(JSONL)로 느슨하게 결합**된다.
  따라서 "import 0" 이 곧 "죽은 코드"는 아니다 — 런타임에서 원장으로만 연결되는 정상 모듈이 섞여 있다
  (예: `execution`, `paper`, `cache` 등은 api_server 런타임에서 다르게 쓰인다).
- **진짜 의심 후보(표본 검증: import 0 + API 참조 0 + 서로 책임 중복):**
  `research_council`, `research_observatory`, `research_coordinator`, `research_operations`,
  `research_organization`, `governance_memory` 류 — **아무도 소비하지 않고 서로 겹친다.**

---

## 4. 강화해야 할 기능 (strengthen)

실제로 **라이브에 연결된 소수**는 얇게 두지 말고 깊게 가야 한다:

- **`console_api` 표면** (`/console/*`) — 대시보드가 실제로 쓰는 유일한 통로. 여기에 힘을 실어야 한다.
- **`status` / `registry` / `paper` / `paper_execution`** — `boot()`/런타임이 실제로 시드·소비. 핵심 경로.
- **P44 `research_assistant` · P45 `local_automation`** — 엔진은 완성됐지만 **라이브 원장이 비어 값이 0**.
  강화 포인트 = 실제 실험/실패/자동화 데이터를 이 원장에 흘려보내는 파이프 연결.
- **P41 `integration_audit`** — 이 진단을 낳은 도구. CI 게이트로 승격하면 재발 방지 자산이 된다.

---

## 5. 유지보수 위해 덜어낼 부분 (trim) — 안전한 방법

**하드 삭제는 금지.** 기존 시스템은 프리즈 대상이고, 원장 결합 때문에 삭제는 위험하다. 대신 3단계 전략:

1. **파사드 통합 (권장 1순위)**
   계열별로 공용 진입점 하나를 만들고, 개별 패키지는 그 뒤로 숨긴다.
   - 예: `research_coordination` 파사드 → 9개 조율 모듈의 단일 API. 개별 모듈은 `@deprecated` 표식.
   - 코드·원장은 유지(무손실) → 신규 개발/문서/온보딩은 파사드 하나만 보면 됨.

2. **archive 이동 (2순위)**
   진짜 안 쓰는 의심 후보를 `jarvis/_archive/` 로 옮긴다(삭제 아님, 활성 트리에서만 제외).
   대상: import 0 + API 참조 0 + 책임 중복이 확인된 것부터.

3. **동결 + 문서화 (3순위)**
   당장 못 건드리는 프리즈 모듈은 "동결(frozen, 신규 참조 금지)" 로 명시.

### 구체 통합 후보 (1차)

| 통합 목표(파사드) | 흡수 대상 | 절감 |
|---|---|---|
| `research_coordination` | research_coordinator, research_council, research_organization, research_orchestration, research_operations, research_manager, research_control | 9→1 진입점 |
| `research_oversight` | research_governance, research_compliance, research_reviewer, research_validation | 5→1 진입점 |
| `research_observability`(대표) | research_observatory, research_monitoring | 3→1 진입점 |
| `research_self_improvement` | research_evolution, research_improvement, research_learning, research_lifecycle | 4→1 진입점 |

> 실행 시 예상 효과: **신규 진입점 4개**로 **21개 패키지의 표면을 덮음** → 온보딩·문서·검색 부담이 크게 감소.
> 원장/기존 API 무변경(무손실). 회귀 테스트 그대로 통과 유지.

---

## 6. 근본 원인 & 재발 방지

**근본 원인:** P1~P45를 관통한 규칙 — *"기존 것 불변, 추가만, 마이그레이션 금지"* — 이 25개 페이즈(189 커밋)에
걸쳐 엄격히 적용되면서, **모든 새 능력이 기존 확장 대신 신규 독립 패키지로** 만들어졌다.
안전성엔 최적이었지만 **응집도(cohesion)를 희생**했다. (이 세션의 P21~P45 배치도 상당수를 보탰음 — 솔직히 인정.)

**재발 방지:**
- 새 패키지 만들기 전 게이트: *"이 기능이 이미 있는가? 기존을 확장할 수 있는가? 복잡도가 줄어드는가?"* (P41 원칙)
- CI에 `integration_audit` 임계 경고: 동일 계열이 N개를 넘으면 리뷰 필수.
- 파사드 우선: 새 능력은 계열 파사드 아래에 추가.

---

## 7. 권고 우선순위 (다음 액션)

1. **[분석 완료]** 이 진단 자체 — 근거 데이터 확보 ✅
2. **[승인 필요]** `research_coordination` 파사드 시범 통합(9→1) — 무손실, 회귀 유지 확인 후 확대
3. **[선택]** archive 이동: 표본 검증된 의심 후보부터
4. **[선택]** CI 게이트로 `integration_audit` 승격

> 이 문서는 **권고**다. 프리즈된 기존 시스템의 실제 통합/이동은 **명시적 승인 후** 진행한다.
