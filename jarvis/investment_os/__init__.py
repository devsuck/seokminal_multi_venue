"""Investment OS — Research OS 와 **완전히 분리된 계층**. **연구는 지식 생산, 투자는 지식 소비.** 실행 없음.

핵심 분리 원칙:
  · Investment OS 는 **절대 Research OS 를 바꾸지 않는다**(읽기전용 소비).
  · Research OS 는 **절대 거래를 실행하지 않는다.**
  · Research OS / Investment OS / Execution 완전한 아키텍처 분리.

Investment OS 책임(모두 **추천·시뮬레이션·계획** — 실제 실행 아님):
  portfolio construction · risk budgeting · exposure analysis · position sizing recommendations ·
  capital allocation recommendations · execution planning · compliance · order simulation ·
  portfolio monitoring · scenario analysis.

실행 사다리: Paper → Shadow → Small Capital → Production Candidate → (선택) Auto Execution.
  **Auto execution 은 기본으로 영구 비활성.** 사람 승인 필수. Risk·Compliance·Portfolio·Kill switch 우회 불가.

모든 산출: is_advisory=True · is_decision=False · requires_human_review=True. 사람이 유일한 결정자.
"""
from __future__ import annotations

# ══════════════ 하드 안전 불변식 (뒤집으려면 명시적 사람 개입 필요, 기본 OFF) ══════════════
# 2026-08-25: 사용자 명시 요청으로 True 전환(입대 전 무인운영 준비). 단, 이 플래그는
# 이 모듈(Investment OS) 어디에도 execute()/place_order()가 없어 실제로 아무것도
# 게이트하지 않는다 — 진짜 실행 게이트는 jarvis.config.AUTONOMY_LEVEL(기본 5,
# MIN_LIVE_LEVEL=6)과 jarvis.execution.arm.arm()이며 둘 다 그대로 잠겨 있다.
# separation.py는 True일 때 승인 아티팩트(jarvis.execution.arm.record_auto_execution_approval)
# 존재를 요구 — 아직 기록 안 함(실제 사람 승인 없이 자동 기록하지 않는다).
AUTO_EXECUTION_ENABLED = True
HUMAN_APPROVAL_MANDATORY = True         # 모든 사다리 전진에 사람 승인 필수
MANDATORY_GATES = ("risk", "compliance", "portfolio", "kill_switch")   # 우회 불가
EXECUTION_RUNGS = ("PAPER", "SHADOW", "SMALL_CAPITAL", "PRODUCTION_CANDIDATE", "AUTO_EXECUTION")

from jarvis.investment_os.knowledge_consumer import consume_research  # noqa: E402,F401
from jarvis.investment_os.forward_learning import build_forward_learning_records  # noqa: E402,F401
from jarvis.investment_os.monthly_review import build_monthly_review  # noqa: E402,F401
from jarvis.investment_os.portfolio_construction import (  # noqa: E402,F401
    analyze_exposure,
    construct_portfolio,
    recommend_capital_allocation,
    recommend_position_sizes,
)
from jarvis.investment_os.risk_budgeting import analyze_scenarios, build_risk_budget  # noqa: E402,F401
from jarvis.investment_os.compliance import check_compliance  # noqa: E402,F401
from jarvis.investment_os.execution_planning import (  # noqa: E402,F401
    ExecutionLadder,
    advance_rung,
    kill_switch_status,
    plan_execution,
    simulate_orders,
)
from jarvis.investment_os.portfolio_monitoring import monitor_portfolio  # noqa: E402,F401
from jarvis.investment_os.gates import evaluate_gates  # noqa: E402,F401
from jarvis.investment_os.separation import validate_separation  # noqa: E402,F401
