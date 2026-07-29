# Investment OS — Separate Layer (Research produces, Investment consumes)

> Research OS 는 **불변**. Investment OS 는 **완전히 분리된 별도 계층**.
> **연구는 지식 생산, 투자는 지식 소비.** Investment OS 는 절대 Research OS 를 바꾸지 않고,
> Research OS 는 절대 거래를 실행하지 않는다. 모든 산출은 **추천·시뮬레이션** — 실행 아님.

## 3계층 완전 분리

```
Research OS   (지식 생산)   — 불변, 실행 안 함
    │  read-only
    ▼
Investment OS (지식 소비·추천) — Research 무변경, 실제 배분/주문 안 함
    │
    ▼
Execution     (영구 비활성)   — AUTO_EXECUTION 기본 OFF, 브로커 미연결
```

`jarvis/investment_os/` = 별도 패키지. `separation.validate_separation()` 이 AST 로 강제:
- ① Research OS 는 investment_os 를 import 안 함(연구는 투자를 모름)
- ② Investment OS 는 Research 원장에 쓰지 않음(record_lesson/append_* 호출 0)
- ③④ 실행 def(execute/trade/place_order/allocate/deploy) 0 · 브로커 import 0
- ⑤ AUTO_EXECUTION 영구 비활성 · 사람 승인 필수 · 4 게이트 우회 불가

→ **separated=True, 6 불변식 통과, 0 violations.**

## 책임 (모두 추천/시뮬레이션)

| 책임 | 모듈 | 산출 |
|---|---|---|
| Portfolio construction | portfolio_construction.construct_portfolio | 추천 비중(합=1) |
| Exposure analysis | .analyze_exposure | family/asset/집중도 |
| Position sizing | .recommend_position_sizes | 추천 사이즈(allocates_capital=False) |
| Capital allocation | .recommend_capital_allocation | 추천 자본%(executes_allocation=False) |
| Risk budgeting | risk_budgeting.build_risk_budget | 리스크 기여·상한 |
| Scenario analysis | .analyze_scenarios | 스트레스 시나리오 영향(추정) |
| Compliance | compliance.check_compliance | 집중·레버리지·제한종목(human_can_override=False) |
| Execution planning | execution_planning.plan_execution | 리밸런스 계획(routes_orders=False) |
| Order simulation | .simulate_orders | 가상 체결(is_real_fill=False) |
| Portfolio monitoring | portfolio_monitoring.monitor_portfolio | 드리프트·알림(페이퍼) |

## 실행 사다리 (Execution Layer)

```
PAPER → SHADOW → SMALL_CAPITAL → PRODUCTION_CANDIDATE → (선택) AUTO_EXECUTION
```

- 각 전진에 **사람 승인 필수**(`advance_rung(..., human_approved=True)`). 승인 없으면 blocked.
- 각 전진은 **4 필수 게이트**(Risk·Compliance·Portfolio·Kill switch) 통과 필수 — 우회 불가.
- **AUTO_EXECUTION 은 영구 비활성**(`AUTO_EXECUTION_ENABLED=False`). 사람 승인·게이트 통과와 무관하게 차단.
- **Kill switch**: 걸리면 전부 PAPER 강제.
- Investment OS 는 **주문을 라우팅하지 않는다** — 계획·시뮬레이션만. 실제 라우팅은 별도 브로커(자격증명 없음 → 구조적 실행 불가).

## 안전 요약

```
연구=생산 · 투자=소비 · Research 무변경 · Research 실행 안 함
AUTO_EXECUTION 영구 OFF · 사람 승인 필수 · Risk/Compliance/Portfolio/Kill 우회 불가
모든 산출 is_advisory=True · is_decision=False · requires_human_review=True
```

콘솔: `GET /console/investment-os`.

검증: investment_os 테스트 11 통과 · separation separated=True · Research OS 회귀 353 통과(불변) ·
governance COMPLIANT · ledger==3.

## 지금 상태 (정직)

연구 후보 5개(paper_active) 소비 → 동일가중 추천 포트폴리오. **모두 추천** — 실제 자본은 움직이지 않는다.
사다리는 PAPER 에서 시작하고, 사람이 게이트 통과 후 승인해야만 SHADOW→… 로 오르며, AUTO 는 영구 차단.
실제 운영은 사람이 각 rung 을 승인하며 페이퍼→섀도우→소액으로 신중히 올리는 것.
