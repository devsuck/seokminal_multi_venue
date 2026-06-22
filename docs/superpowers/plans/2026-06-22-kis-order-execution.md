# KIS Order Execution Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Place, query, and cancel a stock order against KIS's mock-trading
(모의투자) account for `005930`, and prove the full place → query → cancel →
query flow works end to end via a console script.

**Architecture:** A single `KISOrderClient` (mirroring sub-project 1's
`KISClient`/`KISAuth` pattern) wraps three KIS REST endpoints — place, query,
cancel — sharing one retry/error-handling helper. `place_test_order.py` wires
it together: look up a recent close price via the existing `KISClient`, place
a limit buy below that price (so it won't fill immediately), query it, cancel
it, query it again.

**Tech Stack:** `requests` (already a dependency), `python-dotenv` (already a
dependency), `pytest`/`unittest.mock` (already configured).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-22-kis-order-execution-design.md`.
- Environment: KIS mock trading (모의투자) only. Base URL
  `https://openapivts.koreainvestment.com:29443` for order endpoints
  (`KISClient`'s quotation endpoints stay on the existing real-domain default
  `https://openapi.koreainvestment.com:9443` — KIS quotation data is the same
  on both domains, only order placement requires the mock domain).
- TR IDs: `VTTC0802U` (buy), `VTTC0801U` (sell), `VTTC8001R` (daily order/fill
  inquiry), `VTTC0803U` (cancel/modify, with `RVSE_CNCL_DVSN_CD="02"` for
  cancel). **Unverified against a live connection — see spec's Known Risk
  section.** Task 3 of this plan confirms or fixes them.
- Instrument/size: `005930`, quantity `1` (fixed, per spec).
- Order types: `"LIMIT"` and `"MARKET"`, mapped to KIS `ORD_DVSN` codes `"00"`
  and `"01"` respectively.
- New `.env` entries required: `KIS_CANO` (8-digit account number),
  `KIS_ACNT_PRDT_CD` (2-digit product code, typically `"01"`) — for the user's
  mock-trading account. `.env` is gitignored; Task 2 instructs editing it
  directly, never committing it.
- No Nautilus `ExecutionEngine`/`Order` integration in this sub-project (per
  spec's "Out of scope").

---

### Task 1: `KISOrderClient` — place, query, cancel

**Files:**
- Create: `backends/kis/order_client.py`
- Test: `tests/test_order_client.py`

**Interfaces:**
- Consumes: `backends.kis.auth.KISAuth` (existing, from sub-project 1) for
  token caching/401-retry-after-refresh — same class `KISClient` already uses.
- Produces:
  - `KISOrderClient(app_key: str, app_secret: str, cano: str, acnt_prdt_cd: str, auth: KISAuth | None = None, base_url: str = "https://openapivts.koreainvestment.com:29443", session: requests.Session | None = None)`
  - `place_order(self, code: str, side: str, quantity: int, order_division: str, price: int | None = None) -> dict`
  - `get_order_status(self, order_date: str, order_no: str) -> dict | None`
  - `cancel_order(self, order_date: str, order_no: str, code: str, quantity: int) -> dict`

  Task 2 consumes all three exact signatures.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_order_client.py
from unittest.mock import MagicMock

import pytest
import requests

from backends.kis.order_client import KISOrderClient


def _mock_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _mock_401_response() -> MagicMock:
    response = MagicMock()
    response.status_code = 401
    response.json.return_value = {"rt_cd": "1", "msg1": "token expired"}
    error = requests.HTTPError("401 Client Error")
    error.response = response
    response.raise_for_status.side_effect = error
    return response


def _client(session, auth=None):
    auth = auth or MagicMock()
    auth.get_access_token.return_value = "tok"
    return KISOrderClient(
        app_key="key",
        app_secret="secret",
        cano="12345678",
        acnt_prdt_cd="01",
        auth=auth,
        session=session,
    ), auth


def test_place_order_buy_limit_sends_expected_request_and_returns_payload():
    session = MagicMock()
    session.post.return_value = _mock_response(
        {"rt_cd": "0", "msg1": "success", "output": {"ODNO": "0000001234"}}
    )
    client, _ = _client(session)

    result = client.place_order(
        code="005930", side="BUY", quantity=1, order_division="LIMIT", price=65000
    )

    assert result["output"]["ODNO"] == "0000001234"
    session.post.assert_called_once()
    call = session.post.call_args
    assert call.args[0].endswith("/uapi/domestic-stock/v1/trading/order-cash")
    assert call.kwargs["headers"]["tr_id"] == "VTTC0802U"
    assert call.kwargs["json"]["CANO"] == "12345678"
    assert call.kwargs["json"]["ACNT_PRDT_CD"] == "01"
    assert call.kwargs["json"]["PDNO"] == "005930"
    assert call.kwargs["json"]["ORD_DVSN"] == "00"
    assert call.kwargs["json"]["ORD_QTY"] == "1"
    assert call.kwargs["json"]["ORD_UNPR"] == "65000"


def test_place_order_sell_market_uses_sell_tr_id_and_zero_price():
    session = MagicMock()
    session.post.return_value = _mock_response(
        {"rt_cd": "0", "msg1": "success", "output": {"ODNO": "0000005678"}}
    )
    client, _ = _client(session)

    client.place_order(code="005930", side="SELL", quantity=1, order_division="MARKET")

    call = session.post.call_args
    assert call.kwargs["headers"]["tr_id"] == "VTTC0801U"
    assert call.kwargs["json"]["ORD_DVSN"] == "01"
    assert call.kwargs["json"]["ORD_UNPR"] == "0"


def test_place_order_raises_runtime_error_on_nonzero_rt_cd():
    session = MagicMock()
    session.post.return_value = _mock_response({"rt_cd": "1", "msg1": "insufficient cash"})
    client, _ = _client(session)

    with pytest.raises(RuntimeError, match="insufficient cash"):
        client.place_order(code="005930", side="BUY", quantity=1, order_division="LIMIT", price=65000)


def test_place_order_raises_key_error_when_odno_missing():
    session = MagicMock()
    session.post.return_value = _mock_response({"rt_cd": "0", "msg1": "success", "output": {}})
    client, _ = _client(session)

    with pytest.raises(KeyError):
        client.place_order(code="005930", side="BUY", quantity=1, order_division="LIMIT", price=65000)


def test_place_order_retries_once_after_401_then_succeeds():
    session = MagicMock()
    session.post.side_effect = [
        _mock_401_response(),
        _mock_response({"rt_cd": "0", "msg1": "success", "output": {"ODNO": "0000001234"}}),
    ]
    auth = MagicMock()
    auth.get_access_token.side_effect = ["stale-tok", "fresh-tok"]
    client, auth = _client(session, auth=auth)

    result = client.place_order(code="005930", side="BUY", quantity=1, order_division="LIMIT", price=65000)

    assert result["output"]["ODNO"] == "0000001234"
    assert session.post.call_count == 2
    auth.invalidate.assert_called_once()


def test_get_order_status_returns_matching_row():
    session = MagicMock()
    session.get.return_value = _mock_response(
        {
            "rt_cd": "0",
            "msg1": "success",
            "output1": [
                {"ODNO": "0000001234", "ORD_DVSN": "00"},
                {"ODNO": "0000009999", "ORD_DVSN": "00"},
            ],
        }
    )
    client, _ = _client(session)

    result = client.get_order_status(order_date="20240603", order_no="0000001234")

    assert result == {"ODNO": "0000001234", "ORD_DVSN": "00"}
    call = session.get.call_args
    assert call.args[0].endswith("/uapi/domestic-stock/v1/trading/inquire-daily-ccld")
    assert call.kwargs["headers"]["tr_id"] == "VTTC8001R"
    assert call.kwargs["params"]["CANO"] == "12345678"
    assert call.kwargs["params"]["INQR_STRT_DT"] == "20240603"
    assert call.kwargs["params"]["INQR_END_DT"] == "20240603"


def test_get_order_status_returns_none_when_not_found():
    session = MagicMock()
    session.get.return_value = _mock_response(
        {"rt_cd": "0", "msg1": "success", "output1": [{"ODNO": "0000009999"}]}
    )
    client, _ = _client(session)

    result = client.get_order_status(order_date="20240603", order_no="0000001234")

    assert result is None


def test_cancel_order_sends_expected_request_and_returns_payload():
    session = MagicMock()
    session.post.return_value = _mock_response(
        {"rt_cd": "0", "msg1": "success", "output": {"ODNO": "0000001234"}}
    )
    client, _ = _client(session)

    result = client.cancel_order(order_date="20240603", order_no="0000001234", code="005930", quantity=1)

    assert result["output"]["ODNO"] == "0000001234"
    call = session.post.call_args
    assert call.args[0].endswith("/uapi/domestic-stock/v1/trading/order-rvsecncl")
    assert call.kwargs["headers"]["tr_id"] == "VTTC0803U"
    assert call.kwargs["json"]["ORGN_ODNO"] == "0000001234"
    assert call.kwargs["json"]["RVSE_CNCL_DVSN_CD"] == "02"
    assert call.kwargs["json"]["ORD_QTY"] == "1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_order_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backends.kis.order_client'`

- [ ] **Step 3: Implement `backends/kis/order_client.py`**

```python
# backends/kis/order_client.py
import requests

from backends.kis.auth import KISAuth

ORDER_CASH_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
ORDER_INQUIRE_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
ORDER_CANCEL_PATH = "/uapi/domestic-stock/v1/trading/order-rvsecncl"

BUY_TR_ID = "VTTC0802U"
SELL_TR_ID = "VTTC0801U"
INQUIRE_TR_ID = "VTTC8001R"
CANCEL_TR_ID = "VTTC0803U"

ORDER_DIVISION_CODES = {"LIMIT": "00", "MARKET": "01"}


class KISOrderClient:
    """Client for KIS mock-trading (모의투자) order placement, query, and cancel."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        cano: str,
        acnt_prdt_cd: str,
        auth: KISAuth | None = None,
        base_url: str = "https://openapivts.koreainvestment.com:29443",
        session: requests.Session | None = None,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._cano = cano
        self._acnt_prdt_cd = acnt_prdt_cd
        self._base_url = base_url
        self._session = session or requests.Session()
        self._auth = auth or KISAuth(app_key, app_secret, base_url, self._session)

    def place_order(
        self,
        code: str,
        side: str,
        quantity: int,
        order_division: str,
        price: int | None = None,
    ) -> dict:
        tr_id = BUY_TR_ID if side == "BUY" else SELL_TR_ID
        ord_unpr = str(price) if order_division == "LIMIT" else "0"
        payload = self._call(
            "POST",
            ORDER_CASH_PATH,
            tr_id,
            json_body={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "PDNO": code,
                "ORD_DVSN": ORDER_DIVISION_CODES[order_division],
                "ORD_QTY": str(quantity),
                "ORD_UNPR": ord_unpr,
            },
        )
        _ = payload["output"]["ODNO"]  # fail loud if the order number is missing
        return payload

    def get_order_status(self, order_date: str, order_no: str) -> dict | None:
        payload = self._call(
            "GET",
            ORDER_INQUIRE_PATH,
            INQUIRE_TR_ID,
            params={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "INQR_STRT_DT": order_date,
                "INQR_END_DT": order_date,
                "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "00",
                "PDNO": "",
                "CCLD_DVSN": "00",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        for row in payload.get("output1", []):
            if row.get("ODNO") == order_no:
                return row
        return None

    def cancel_order(self, order_date: str, order_no: str, code: str, quantity: int) -> dict:
        return self._call(
            "POST",
            ORDER_CANCEL_PATH,
            CANCEL_TR_ID,
            json_body={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "KRX_FWDG_ORD_ORGNO": "",
                "ORGN_ODNO": order_no,
                "ORD_DVSN": "00",
                "RVSE_CNCL_DVSN_CD": "02",
                "ORD_QTY": str(quantity),
                "ORD_UNPR": "0",
                "QTY_ALL_ORD_YN": "Y",
            },
        )

    def _call(
        self,
        method: str,
        path: str,
        tr_id: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict:
        try:
            response = self._send(method, path, tr_id, params=params, json_body=json_body)
            response.raise_for_status()
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 401:
                raise
            self._auth.invalidate()
            response = self._send(method, path, tr_id, params=params, json_body=json_body)
            response.raise_for_status()

        payload = response.json()
        if payload.get("rt_cd") != "0":
            raise RuntimeError(f"KIS API error rt_cd={payload.get('rt_cd')}: {payload.get('msg1')}")
        return payload

    def _send(
        self,
        method: str,
        path: str,
        tr_id: str,
        *,
        params: dict | None,
        json_body: dict | None,
    ) -> requests.Response:
        token = self._auth.get_access_token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
            "tr_id": tr_id,
        }
        url = f"{self._base_url}{path}"
        if method == "POST":
            headers["custtype"] = "P"
            return self._session.post(url, headers=headers, json=json_body)
        return self._session.get(url, headers=headers, params=params)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_order_client.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add backends/kis/order_client.py tests/test_order_client.py
git commit -m "feat: add KIS mock-trading order place/query/cancel client"
```

---

### Task 2: `place_test_order.py` entry script and `.env` setup

**Files:**
- Create: `place_test_order.py`
- Modify: `.env` (add two new keys — local edit only, gitignored, no commit)

**Interfaces:**
- Consumes: `backends.kis.client.KISClient.get_daily_price` (existing, from
  sub-project 1) for the reference price; `backends.kis.order_client.KISOrderClient.place_order`/`get_order_status`/`cancel_order` (Task 1).
- Produces: `main() -> None`. No other code depends on this script.

- [ ] **Step 1: Add the new `.env` entries**

Open `.env` (already gitignored, already has `KIS_APP_KEY`/`KIS_APP_SECRET`
from sub-project 1) and add two lines with your KIS mock-trading account's
values:

```
KIS_CANO=your8digitaccountnumber
KIS_ACNT_PRDT_CD=01
```

(`KIS_ACNT_PRDT_CD` is almost always `"01"` for a standard account — confirm
against your KIS mock-trading account details if unsure.)

- [ ] **Step 2: Write `place_test_order.py`**

```python
# place_test_order.py
import datetime as dt
import os

from dotenv import load_dotenv

from backends.kis.client import KISClient
from backends.kis.order_client import KISOrderClient


def main() -> None:
    load_dotenv()

    code = "005930"
    quantity = 1
    app_key = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]
    cano = os.environ["KIS_CANO"]
    acnt_prdt_cd = os.environ["KIS_ACNT_PRDT_CD"]

    # Quotation endpoints are the same on KIS's real domain regardless of
    # whether orders go to the mock-trading domain, so KISClient keeps its
    # default base_url here.
    price_client = KISClient(app_key=app_key, app_secret=app_secret)
    today = dt.date.today()
    start = (today - dt.timedelta(days=10)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    rows = price_client.get_daily_price(code, start, end)
    last_close = int(rows[-1]["stck_clpr"])
    limit_price = int(last_close * 0.9)
    print(f"last close: {last_close}, limit price (90%): {limit_price}")

    order_client = KISOrderClient(
        app_key=app_key, app_secret=app_secret, cano=cano, acnt_prdt_cd=acnt_prdt_cd
    )
    order_date = today.strftime("%Y%m%d")

    placed = order_client.place_order(
        code=code, side="BUY", quantity=quantity, order_division="LIMIT", price=limit_price
    )
    order_no = placed["output"]["ODNO"]
    print("placed:", placed)

    status = order_client.get_order_status(order_date=order_date, order_no=order_no)
    print("status after place:", status)

    cancelled = order_client.cancel_order(
        order_date=order_date, order_no=order_no, code=code, quantity=quantity
    )
    print("cancelled:", cancelled)

    status_after_cancel = order_client.get_order_status(order_date=order_date, order_no=order_no)
    print("status after cancel:", status_after_cancel)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the full test suite to confirm nothing broke**

Run: `pytest -v`
Expected: all tests pass (existing suite + Task 1's new tests; this script
has no unit test of its own — it is exercised manually in Task 3, the same
way `live_trade_stream.py` and `live_trade_stream_ib.py` were)

- [ ] **Step 4: Commit**

```bash
git add place_test_order.py
git commit -m "feat: add KIS mock-trading order place/query/cancel entry script"
```

(Do not `git add .env` — it is gitignored and must stay that way.)

---

### Task 3: Manual end-to-end verification against the real KIS mock-trading account

**Files:** none (manual verification step, no code changes — except fixes to
TR IDs/field names in `backends/kis/order_client.py`, described in Step 3, if
the real API disagrees with the documented assumption)

**Interfaces:**
- Consumes: `main()` from `place_test_order.py` (Task 2), the real KIS
  mock-trading account (`.env`'s `KIS_CANO`/`KIS_ACNT_PRDT_CD`, set up in
  Task 2).

- [ ] **Step 1: Run the script during KRX market hours (weekday, 09:00-15:30 KST)**

Run: `python3 place_test_order.py`
Expected: prints the reference price, the placement response (containing an
`ODNO`), the status-after-place response, the cancellation response, and the
status-after-cancel response, with no unhandled exceptions.

- [ ] **Step 2: Sanity-check each printed step**

Confirm: the placement response contains a non-empty `ODNO`; the
status-after-place lookup finds a row for that `ODNO` (confirms
`get_order_status`'s field names/TR ID are correct); the cancellation response
succeeds (`rt_cd == "0"`, visible in the printed dict); and the
status-after-cancel lookup's row for that `ODNO` shows it is no longer an
open/resting order — note whatever field signals this in the real response
(e.g. a cancelled-quantity or status field) so it can be documented here for
future reference.

- [ ] **Step 3: Fix TR IDs or field names if the real API disagrees**

If any step raises (e.g. `RuntimeError` from a nonzero `rt_cd`, or a `KeyError`
from a missing field), read the error's `msg1` (KIS's own error text) to
identify the wrong TR ID or field name, fix it in
`backends/kis/order_client.py`, update the corresponding test(s) in
`tests/test_order_client.py` to match, re-run `pytest -v` to confirm
everything still passes, and commit:

```bash
git add backends/kis/order_client.py tests/test_order_client.py
git commit -m "fix: correct KIS order TR ID/field name against live mock-trading API"
```

If everything already matches (no fix needed), skip the commit — this task
ends with just the manual confirmation in Step 2.

- [ ] **Step 4: Update the progress ledger**

Append to `.superpowers/sdd/progress.md`:
`Task 3 (sub-project 4): complete (manual verification, real KIS mock-trading account, <what you observed>)`

- [ ] **Step 5: Dispatch the final whole-branch review**

Per `superpowers:subagent-driven-development`'s process: use the commit
before Task 1 (the spec+plan commit, `6d5d4d5`) as the base. Run
`scripts/review-package 6d5d4d5 HEAD` (from the `subagent-driven-development`
skill's directory) as the diff package, dispatch a code-reviewer subagent on
the most capable available model per that skill's `code-reviewer.md`
template, and resolve any Critical/Important findings before considering
sub-project 4 complete.

## Out of scope (reminder, per spec)

Do not add: IB order execution, order modification (정정), multiple concurrent
orders, multi-instrument support, position/balance queries, or any Nautilus
`ExecutionEngine`/`TradingNode`/`Order` integration. These belong to later
sub-projects.
