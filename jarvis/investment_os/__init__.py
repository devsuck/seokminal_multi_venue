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
AUTO_EXECUTION_ENABLED = False          # ★ 영구 비활성(기본). 코드로 자동 True 금지.
HUMAN_APPROVAL_MANDATORY = True         # 모든 사다리 전진에 사람 승인 필수
MANDATORY_GATES = ("risk", "compliance", "portfolio", "kill_switch")   # 우회 불가
EXECUTION_RUNGS = ("PAPER", "SHADOW", "SMALL_CAPITAL", "PRODUCTION_CANDIDATE", "AUTO_EXECUTION")

from jarvis.investment_os.knowledge_consumer import consume_research  # noqa: E402,F401
from jarvis.investment_os.forward_learning import build_forward_learning_records  # noqa: E402,F401
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
