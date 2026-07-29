"""Alpaca Autopilot Router — 하위호환 shim.

원래 이 파일 하나(1700줄+)에 계좌/시세/주문 + 터미널(tmux/ttyd) + shutdown/update +
멀티에이전트 CRUD/틱/성과가 다 들어있었다. api_server/routers/ 하위 도메인별
모듈(alpaca_shared, alpaca_account, terminal, agents)로 분리했고, 이 파일은
api_server/main.py의 기존 import(`from api_server.router_autopilot import router,
agents_router, place_order, OrderRequest`)가 계속 동작하도록 재수출만 한다.

라우터 2개(alpaca_account.router + terminal.router)는 둘 다 prefix="/alpaca"라서
그대로는 못 합친다 — main.py가 기대하는 하나의 `router`로 병합해 재수출.
"""
from fastapi import APIRouter

from api_server.routers.agents import agents_router
from api_server.routers.alpaca_account import place_order
from api_server.routers.alpaca_account import router as _alpaca_account_router
from api_server.routers.alpaca_shared import OrderRequest
from api_server.routers.terminal import router as _terminal_router

# 서브 라우터 둘 다 이미 prefix="/alpaca"를 갖고 있으니 여기엔 prefix를 또 붙이면 안 됨
# (붙이면 /alpaca/alpaca/... 로 두 번 겹침).
router = APIRouter()
router.include_router(_alpaca_account_router)
router.include_router(_terminal_router)

__all__ = ["router", "agents_router", "place_order", "OrderRequest"]
