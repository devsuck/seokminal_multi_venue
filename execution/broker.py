"""벤뉴 무관 집행 추상화 — 기본 페이퍼(dry-run). **실주문 절대 안 나감.**

house 규율: 페이퍼/검증 먼저, 실집행은 엣지가 FDR+walk-forward로 확정된 뒤 별도 태스크.
지금은 검증된 신호를 **안전하게 라우팅할 대상**이 필요하다 — 그게 PaperBroker다. 주문을
저널(research/data/paper_orders/{date}.jsonl)에 기록하고 주문가로 즉시 체결로 시뮬레이션,
포지션을 인메모리로 추적한다. 어떤 벤뉴 API도 건드리지 않는다.

`make_broker(venue, mode)`는 기본 mode="paper". mode="live"는 등록된 실어댑터가 없으면
NotImplementedError로 명확히 거부한다 — 자다가 실주문이 나갈 경로가 구조적으로 없다.
실어댑터(HL/Polymarket/IB)는 이 Broker 프로토콜을 구현해 register_live_adapter로 등록하면
이 시임에 꽂힌다(후속 작업).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Protocol

_JOURNAL_DIR = Path("research/data/paper_orders")


@dataclass
class Order:
    venue: str
    symbol: str
    side: str            # "buy" | "sell"
    qty: float
    price: float         # 지정가/참조가
    ts: float            # epoch(초) — 호출측 주입(결정성)
    order_type: str = "limit"
    client_id: str | None = None

    def signed_qty(self) -> float:
        return self.qty if self.side == "buy" else -self.qty


@dataclass
class OrderResult:
    accepted: bool
    order: Order
    status: str          # "filled" | "rejected"
    fill_price: float | None
    reason: str = ""


@dataclass
class Position:
    symbol: str
    qty: float = 0.0
    avg_price: float = 0.0

    def apply(self, signed_qty: float, price: float) -> float:
        """체결 반영 → 실현손익 반환. 순수 가중평균 회계(증가=가중평균, 감소=실현,
        제로통과 뒤집힘=잔여를 새 진입가로)."""
        if self.qty == 0:                                        # 신규
            self.qty, self.avg_price = signed_qty, price
            return 0.0
        if (self.qty > 0) == (signed_qty > 0):                  # 같은 방향 증가
            new_qty = self.qty + signed_qty
            self.avg_price = (self.avg_price * self.qty + price * signed_qty) / new_qty
            self.qty = new_qty
            return 0.0
        # 반대 방향: 감소/청산/뒤집힘
        closing = min(abs(signed_qty), abs(self.qty))
        realized = closing * (price - self.avg_price) * (1 if self.qty > 0 else -1)
        new_qty = self.qty + signed_qty
        if new_qty == 0:                                        # 정확히 청산
            self.qty, self.avg_price = 0.0, 0.0
        elif (new_qty > 0) == (self.qty > 0):                   # 부분청산(방향 유지)
            self.qty = new_qty                                  # avg_price 불변
        else:                                                   # 제로 통과 뒤집힘
            self.qty, self.avg_price = new_qty, price
        return realized


class Broker(Protocol):
    def place(self, order: Order) -> OrderResult: ...
    def positions(self) -> dict[str, Position]: ...


class PaperBroker:
    """dry-run 페이퍼 브로커. 주문가 즉시 체결 시뮬 + 포지션/실현손익 추적 + 저널 기록.
    벤뉴 API 미접촉. 검증된 신호의 안전한 라우팅 대상."""

    def __init__(self, journal_dir: Path | None = None, persist: bool = True) -> None:
        self._pos: dict[str, Position] = {}
        self.realized_pnl = 0.0
        self._journal_dir = journal_dir or _JOURNAL_DIR
        self._persist = persist

    def place(self, order: Order) -> OrderResult:
        if order.qty <= 0 or order.side not in ("buy", "sell"):
            res = OrderResult(False, order, "rejected", None, "수량<=0 또는 잘못된 side")
            self._journal(res)
            return res
        pos = self._pos.setdefault(order.symbol, Position(order.symbol))
        self.realized_pnl += pos.apply(order.signed_qty(), order.price)
        res = OrderResult(True, order, "filled", order.price)
        self._journal(res)
        return res

    def positions(self) -> dict[str, Position]:
        return {s: p for s, p in self._pos.items() if p.qty != 0}

    def _journal(self, res: OrderResult) -> None:
        if not self._persist:
            return
        try:
            import datetime as dt
            self._journal_dir.mkdir(parents=True, exist_ok=True)
            path = self._journal_dir / f"{dt.datetime.utcfromtimestamp(res.order.ts).date().isoformat()}.jsonl"
            with path.open("a") as f:
                f.write(json.dumps({"result": res.status, "fill_price": res.fill_price,
                                    "reason": res.reason, **asdict(res.order)}, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            pass


# 실집행 어댑터 레지스트리(후속 작업에서 채움). 지금은 비어있음 → live 요청은 거부.
_LIVE_ADAPTERS: dict[str, Callable[[], Broker]] = {}


def register_live_adapter(venue: str, factory: Callable[[], Broker]) -> None:
    """실집행 어댑터 등록(HL/Polymarket/IB). 엣지 확정 후 별도 태스크에서 호출."""
    _LIVE_ADAPTERS[venue] = factory


def make_broker(venue: str = "paper", mode: str = "paper") -> Broker:
    """브로커 팩토리. mode 기본 'paper'. 'live'는 등록된 어댑터 없으면 거부(안전장치)."""
    if mode == "paper":
        return PaperBroker()
    if mode != "live":
        raise ValueError(f"알 수 없는 mode: {mode} (paper|live)")
    factory = _LIVE_ADAPTERS.get(venue)
    if factory is None:
        raise NotImplementedError(
            f"'{venue}' 실집행 어댑터 미구현 — 검증된 엣지 확정 후 별도 태스크. "
            "지금은 페이퍼만. register_live_adapter로 등록되기 전엔 실주문 경로 없음.")
    return factory()
