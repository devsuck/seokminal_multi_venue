"""AST 회귀 가드 — 브로커 SDK를 직접 import하는 파일이 허용목록 밖으로 늘어나지 않게 막는다.

패턴은 jarvis/research_workflow/agent_validation.py의 agent_safety()를 재사용:
모듈을 AST로 파싱해 금지된 import를 찾는다. 거기는 blocklist(에이전트 모듈은
브로커를 아예 못 씀)였고 여기는 allowlist(브로커는 이 파일들만 씀) — 나머지
전부가 잠재적 우회 경로라 반대 방향이 맞다.

새 파일이 브로커 SDK를 직접 import해야 하면: jarvis.execution.broker_bridge를
거치도록 고치거나(권장), 정말 예외적 사유(하드코딩 paper/청산전용/이미 다른
risk_guard 경로로 게이트됨)면 이 파일의 ALLOWLIST에 사유 주석과 함께 추가한다.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 브로커 주문을 실제로 낼 수 있는 SDK/모듈. 이걸 직접 import하면 risk_guard를
# 우회할 수 있다 — 원칙적으로 broker_bridge.py 하나만 import해야 한다.
FORBIDDEN_IMPORT_PREFIXES = (
    "backends.kis.order_client",   # KIS 주문 클라이언트 (place_order/cancel_order 등)
    "backends.ib.order_client",    # IB 주문 클라이언트
    "hyperliquid.trader",          # HL place_order/close_position/set_leverage
    "alpaca.trading.client",       # Alpaca TradingClient(submit_order/close_position)
)
# backends.kis.client / backends.ib.client / backends.kis.ws_* 는 시세·잔고 조회
# 전용(주문 API 없음) — 안전 스코프 밖이라 이 테스트가 검사할 필요 없음.

# 브로커 SDK를 직접 import해도 되는 파일 (repo-relative). 각 항목은 이유가 있어야
# 함 — 어댑터 자체이거나, 하드코딩 paper/청산전용이거나, risk_guard로 이미 게이트됨.
ALLOWLIST = {
    "jarvis/execution/broker_bridge.py",       # 이 시스템의 유일한 집행 chokepoint
    "backends/kis/order_client.py",            # KIS 어댑터 자체
    "backends/kis/client.py",
    "backends/ib/order_client.py",             # IB 어댑터 자체
    "hyperliquid/trader.py",                   # HL 어댑터 자체
    "live_engine/kis_broker.py",               # live_engine의 브로커 구현체
    "live_engine/ib_broker.py",
    "live_engine/engine.py",                   # place_order 전에 validate_order() 게이트함
    "jarvis/live_execution/engine.py",         # 사람 ARM+readiness 게이트 (jarvis 자체 안전계층, 별도 관리)
    "api_server/main.py",                      # /orders/kr,us,/hl/order = _check_risk 게이트;
                                                # /copytrade/*,/dart/mirror = 하드코딩 paper/청산전용(주석 참고)
    "api_server/vrp_bot.py",                   # validate_defined_risk_spread로 진입 게이트됨
    "api_server/copytrade_autobot.py",         # 하드코딩 paper=True, 청산 전용
    "place_test_order.py",                     # 사람이 손으로 돌리는 CLI 스크립트, 서버에서 도달 불가
    "place_test_order_ib.py",
    "api_server/dart_autobot.py",              # 주문은 route_order() 경유. KISOrderClient는
                                                # get_holdings/cancel_order/get_order_status(읽기·취소)만 남음
    "api_server/routers/agents.py",            # 주문/청산은 route_order/route_close/route_order_ib 경유.
                                                # KIS/IB/HL 클라이언트는 포지션·잔고·캔들 조회에만 씀
    "api_server/routers/alpaca_shared.py",     # broker_bridge가 쓰는 _trading_client() 팩토리 자체
                                                # (계좌/포지션 조회 엔드포인트도 같이 씀 — 주문은 broker_bridge 경유)
    "api_server/risk_state.py",                # TradingClient.get_portfolio_history()만 — 읽기 전용
    "insider/options_uoa_client.py",           # TradingClient.get_option_contracts()만 — 읽기 전용
                                                # (insider 전략은 애초에 live 집행에 안 붙음)
    "jarvis/execution/live_router.py",         # 주문은 broker_bridge.route_order() 경유(line ~129).
                                                # KISOrderClient는 get_holdings()로 중복매매 방지 조회만
}

# tests/**, __pycache__ 등은 전부 스캔에서 제외
_EXCLUDE_DIR_PARTS = {"tests", "__pycache__", ".git", "node_modules", "docs"}


def _iter_py_files():
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT)
        if _EXCLUDE_DIR_PARTS & set(rel.parts):
            continue
        yield rel, p


def _violations() -> list[dict]:
    violations = []
    for rel, p in _iter_py_files():
        rel_str = rel.as_posix()
        if rel_str in ALLOWLIST:
            continue
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name.startswith(pre) for pre in FORBIDDEN_IMPORT_PREFIXES):
                        violations.append({"file": rel_str, "kind": "import", "detail": alias.name})
                continue
            if module and any(module.startswith(pre) for pre in FORBIDDEN_IMPORT_PREFIXES):
                violations.append({"file": rel_str, "kind": "import", "detail": module})
    return violations


def test_only_chokepoint_imports_broker_sdks():
    violations = _violations()
    assert not violations, (
        "브로커 SDK를 직접 import하는 파일이 허용목록 밖에서 발견됨 — "
        "risk_guard를 우회할 수 있는 새 주문 경로 가능성. "
        "jarvis.execution.broker_bridge를 거치도록 고치거나, 정말 예외면 "
        "tests/test_execution_chokepoint.py의 ALLOWLIST에 사유와 함께 추가할 것.\n"
        f"{violations}"
    )


def test_allowlist_entries_still_exist():
    """허용목록에 있는 파일이 삭제/이동됐으면 allowlist가 죽은 채로 남는 걸 방지."""
    missing = [f for f in ALLOWLIST if not (ROOT / f).exists()]
    assert not missing, f"ALLOWLIST에 있지만 실제로 없는 파일: {missing}"


if __name__ == "__main__":
    v = _violations()
    print(f"violations: {v}")
    assert not v
    print("ok")
