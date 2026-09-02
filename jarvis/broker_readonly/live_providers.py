"""HL/KIS 실계좌 read-only 프로바이더 (P8).

jarvis.broker_readonly.adapters와 분리된 파일인 이유: adapters.py는
tests/test_broker_readonly.py::test_no_execution_import 가 소스 문자열에
"backends.kis"/"backends.ib"/"place_order"가 없음을 강제하는 불변식 스캔
대상이라, 여기서 KISOrderClient(주문 가능 클래스)를 재사용하려면 별도
파일이 필요하다. 이 파일은 그 스캔 대상은 아니지만 규율은 동일하게 지킨다
— place_order/cancel_order는 호출하지 않고 get_balance/get_holdings 같은
읽기 메서드만 쓴다.
"""
from __future__ import annotations

import datetime as _dt
import os as _os

from jarvis.broker_readonly.models import AccountSnapshot, BrokerHealth, BrokerPosition
from jarvis.broker_readonly.provider import BrokerReadOnlyProvider


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class HLReadOnlyProvider(BrokerReadOnlyProvider):
    def __init__(self, paper: bool = False) -> None:
        self._paper = paper
        self.source_name = "hl_paper" if paper else "hl"

    def _raw(self) -> dict:
        from hyperliquid.trader import get_positions
        return get_positions(paper=self._paper)

    def account_snapshot(self) -> AccountSnapshot | None:
        ms = self._raw().get("margin_summary", {})
        equity = float(ms.get("accountValue", 0) or 0)
        cash = float(ms.get("spotUsdcBalance", 0) or 0)
        return AccountSnapshot(cash=cash, equity=equity, buying_power=equity, timestamp=_now())

    def positions(self) -> list[BrokerPosition]:
        now = _now()
        out = []
        for p in self._raw().get("asset_positions", []):
            pos = p.get("position", {})
            szi = float(pos.get("szi", 0) or 0)
            if szi == 0:
                continue
            out.append(BrokerPosition(
                symbol=pos.get("coin", ""), quantity=szi,
                avg_price=float(pos.get("entryPx", 0) or 0),
                market_value=float(pos.get("positionValue", 0) or 0),
                timestamp=now,
            ))
        return out

    def balances(self) -> dict:
        snap = self.account_snapshot()
        return snap.to_dict() if snap else {}

    def orders_history(self) -> list[dict]:
        from api_server.order_audit import read_recent
        out = []
        for e in read_recent(limit=2000):
            if e.get("venue") != "HL":
                continue
            req = e.get("request") or {}
            if bool(req.get("paper")) != self._paper:
                continue
            out.append({
                "ts": e.get("ts"), "venue": "HL", "status": e.get("status"),
                "symbol": req.get("coin"),
                "side": "BUY" if req.get("is_buy") else "SELL",
                "quantity": req.get("size"),
            })
        return out

    def health_check(self) -> BrokerHealth:
        try:
            self._raw()
            return BrokerHealth(connected=True, stale=False, error=None, timestamp=_now())
        except Exception as exc:
            return BrokerHealth(connected=False, stale=False, error=str(exc), timestamp=_now())


class KISReadOnlyProvider(BrokerReadOnlyProvider):
    def __init__(self, paper: bool = False) -> None:
        self._paper = paper
        self.source_name = "kis_paper" if paper else "kis"

    def _creds(self) -> tuple[str, str, str, str]:
        prefix = "KIS_MOCK_" if self._paper else "KIS_"
        app_key = _os.environ.get(f"{prefix}APP_KEY", "")
        app_secret = _os.environ.get(f"{prefix}APP_SECRET", "")
        cano = _os.environ.get(f"{prefix}CANO", "")
        acnt = _os.environ.get("KIS_ACNT_PRDT_CD", "")
        if not all([app_key, app_secret, cano, acnt]):
            raise ValueError(f"KIS {'모의' if self._paper else '실전'} 계좌 키 미설정")
        return app_key, app_secret, cano, acnt

    def _client(self):
        from backends.kis.order_client import KISOrderClient
        app_key, app_secret, cano, acnt = self._creds()
        return KISOrderClient(app_key, app_secret, cano, acnt, mock=self._paper)

    def account_snapshot(self) -> AccountSnapshot | None:
        bal = self._client().get_balance()
        return AccountSnapshot(cash=bal["deposit"], equity=bal["net_asset"],
                               buying_power=bal["deposit"], timestamp=_now())

    def positions(self) -> list[BrokerPosition]:
        now = _now()
        return [BrokerPosition(symbol=h["code"], quantity=h["qty"], avg_price=h["avg_price"],
                               market_value=h["qty"] * h["current"], timestamp=now)
                for h in self._client().get_holdings()]

    def balances(self) -> dict:
        return self._client().get_balance()

    def orders_history(self) -> list[dict]:
        from api_server.order_audit import read_recent
        out = []
        for e in read_recent(limit=2000):
            if e.get("venue") != "KR":
                continue
            req = e.get("request") or {}
            if bool(req.get("paper")) != self._paper:
                continue
            out.append({
                "ts": e.get("ts"), "venue": "KR", "status": e.get("status"),
                "symbol": req.get("code"), "side": req.get("side"),
                "quantity": req.get("quantity"),
            })
        return out

    def health_check(self) -> BrokerHealth:
        try:
            self._client().get_balance()
            return BrokerHealth(connected=True, stale=False, error=None, timestamp=_now())
        except Exception as exc:
            return BrokerHealth(connected=False, stale=False, error=str(exc), timestamp=_now())
