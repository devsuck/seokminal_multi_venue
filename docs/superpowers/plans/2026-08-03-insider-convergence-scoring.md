# 내부자거래 컨버전스 스코어링 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/insider`의 5개 소스(DART 임원/기업행위, SEC Form4, 의회매매, 옵션 UOA)를 같은 티커·같은 방향으로 교차 집계해 컨버전스 스코어를 매기고, 대시보드 신규 탭 + 기존 알림 폴링에 노출한다.

**Architecture:** `insider/convergence.py`의 순수함수 `compute_convergence()`가 기존 leg 함수들을 그대로 호출해 결과를 방향 태깅→그룹핑→스코어링한다. 새 API 엔드포인트 하나, `get_triggered_alerts()`에 병합 로직 하나, 프론트 신규 탭 하나로 노출한다. 새 수집기/DB/폴링루프 없음 — 순수 집계 레이어.

**Tech Stack:** FastAPI, pytest (`/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest`), Next.js/React (`app/insider/page.tsx`), TypeScript.

## Global Constraints

- 새 외부 API 호출/수집기 추가 금지 — 기존 leg 함수만 재사용.
- v1은 leg 개수 카운트만, 임의 가중치 없음(과최적화 회피).
- gov-contracts는 컨버전스 leg에서 제외(티커 필드 없음) — `compute_convergence`가 호출 자체를 안 함.
- score < 2인 그룹은 결과에서 드롭.
- 프론트 디자인 토큰만 사용 (`bg-bg/panel/panel-2`, `border-border`, `text-text-1/2/3`, `text-accent/pos/neg/warn/info`), raw `fetch` 금지(`lib/api.ts` 경유), `style={{}}` 금지.
- Python 인터프리터: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`.
- `pytest.ini`에 `asyncio_mode="auto"` — `@pytest.mark.asyncio` 데코레이터 절대 쓰지 말 것.

---

### Task 1: `compute_convergence()` 순수함수 + 유닛테스트

**Files:**
- Create: `insider/convergence.py`
- Test: `tests/test_convergence.py`

**Interfaces:**
- Consumes: 기존 leg 함수 시그니처(변경 없음, 그대로 호출):
  - `insider.dart_client.get_recent_kr_insider_feed(days: int = 30, max_corps: int = 20) -> list[dict]` — row keys: `trade_type`, `stock_code`, `corp_name`, `rcept_dt`, `dart_url`, `role`, `event_cause`
  - `insider.dart_client.get_recent_kr_corporate_actions(days: int = 30, max_items: int = 40) -> list[dict]` — row keys: `trade_type`, `ticker`, `corp_name`, `trade_date`, `dart_url`, `event_cause`
  - `insider.edgar_client.get_recent_form4_feed(days: int = 7, max_filings: int = 40) -> list[dict]` — row keys: `trade_type`, `ticker`, `issuer`, `filing_date`, `transaction_date`
  - `insider.congress_client.get_congress_trades(limit: int = 80) -> list[dict]` — row keys: `trade_type`, `ticker`, `trade_date`, `chamber`, `owner`, `link`
  - `insider.options_uoa_client.get_unusual_options_activity(tickers: list[str], ...) -> list[dict]` — row keys: `type` (`"call"|"put"`), `ticker`, `expiration_date`, `strike`
- Produces:
  ```python
  def compute_convergence(market: str, days: int = 30) -> list[dict]:
      """market: "kr" | "us". 반환: score desc 정렬된 ConvergenceSignal list."""
  ```
  `ConvergenceSignal` shape (plain dict, no pydantic — pydantic model lives in `api_server/main.py` per Task 2):
  ```python
  {
    "ticker": str,
    "market": "kr" | "us",
    "direction": "BULLISH" | "BEARISH",
    "score": int,
    "legs": [
      {"source": str, "trade_date": str, "detail": str, "url": str | None},
      ...
    ],
  }
  ```
  `source` values: `"dart_exec"`, `"dart_corp_action"`, `"form4"`, `"congress"`, `"options_uoa"` — later tasks (API/frontend icon mapping) key off these exact strings.

**Note on options UOA and `days`:** `get_unusual_options_activity` takes `tickers: list[str]`, not `days`. Since v1 has no external ticker universe to scan blindly, `compute_convergence` builds the UOA ticker list from the *other* legs already collected in the same call (dedup'd tickers from DART/Form4/congress rows for that market) and passes those to `get_unusual_options_activity`. If that ticker list is empty, skip the UOA call entirely (`get_unusual_options_activity([])` — don't rely on internal default behavior, guard explicitly). This keeps UOA scoped to tickers with existing signal, consistent with "score>=2 needs 2+ *different* leg sources" — UOA can never be the sole leg contributing to a ticker under this construction, which is fine since it only ever adds to a group that already has ≥1 other leg.

- [ ] **Step 1: Write the failing tests**

```python
"""컨버전스 스코어링 순수함수 테스트 — 각 leg를 mock row로 주입."""
from unittest.mock import patch

from insider.convergence import compute_convergence


def _corp_action_row(ticker="005930", trade_type="BUYBACK", trade_date="2026-08-01"):
    return {"trade_type": trade_type, "ticker": ticker, "corp_name": "삼성전자",
            "trade_date": trade_date, "dart_url": "https://dart.fss.or.kr/x", "event_cause": "자사주"}


def _exec_row(stock_code="005930", trade_type="BUY", rcept_dt="2026-08-01"):
    return {"trade_type": trade_type, "stock_code": stock_code, "corp_name": "삼성전자",
            "rcept_dt": rcept_dt, "dart_url": "https://dart.fss.or.kr/y", "role": "대표이사", "event_cause": "장내매수"}


def test_single_leg_below_score_threshold_dropped():
    with patch("insider.convergence.get_recent_kr_insider_feed", return_value=[_exec_row()]), \
         patch("insider.convergence.get_recent_kr_corporate_actions", return_value=[]):
        result = compute_convergence("kr", days=30)
    assert result == []


def test_two_legs_same_direction_score_two():
    with patch("insider.convergence.get_recent_kr_insider_feed", return_value=[_exec_row(trade_type="BUY")]), \
         patch("insider.convergence.get_recent_kr_corporate_actions", return_value=[_corp_action_row(trade_type="BUYBACK")]):
        result = compute_convergence("kr", days=30)
    assert len(result) == 1
    sig = result[0]
    assert sig["ticker"] == "005930"
    assert sig["direction"] == "BULLISH"
    assert sig["score"] == 2
    assert {leg["source"] for leg in sig["legs"]} == {"dart_exec", "dart_corp_action"}


def test_two_legs_opposite_direction_not_convergence():
    with patch("insider.convergence.get_recent_kr_insider_feed", return_value=[_exec_row(trade_type="BUY")]), \
         patch("insider.convergence.get_recent_kr_corporate_actions", return_value=[_corp_action_row(trade_type="DISPOSAL")]):
        result = compute_convergence("kr", days=30)
    assert result == []


def test_same_source_multiple_rows_counts_once():
    rows = [_exec_row(trade_type="BUY", rcept_dt="2026-08-01"), _exec_row(trade_type="BUY", rcept_dt="2026-07-30")]
    with patch("insider.convergence.get_recent_kr_insider_feed", return_value=rows), \
         patch("insider.convergence.get_recent_kr_corporate_actions", return_value=[_corp_action_row(trade_type="BUYBACK")]):
        result = compute_convergence("kr", days=30)
    assert len(result) == 1
    assert result[0]["score"] == 2  # 2 sources, not 3 rows
    assert len(result[0]["legs"]) == 3  # all rows still listed


def test_excluded_trade_types_dropped_from_grouping():
    with patch("insider.convergence.get_recent_kr_insider_feed", return_value=[_exec_row(trade_type="HOLD_REPORT")]), \
         patch("insider.convergence.get_recent_kr_corporate_actions", return_value=[_corp_action_row(trade_type="RIGHTS_ISSUE")]):
        result = compute_convergence("kr", days=30)
    assert result == []


def test_us_market_form4_and_congress_converge():
    form4_row = {"trade_type": "SELL", "ticker": "TSLA", "issuer": "Tesla Inc",
                 "filing_date": "2026-08-01", "transaction_date": "2026-07-30"}
    congress_row = {"trade_type": "SELL", "ticker": "TSLA", "trade_date": "2026-07-29",
                    "chamber": "senate", "owner": "spouse", "link": "https://example.com/x"}
    with patch("insider.convergence.get_recent_form4_feed", return_value=[form4_row]), \
         patch("insider.convergence.get_congress_trades", return_value=[congress_row]), \
         patch("insider.convergence.get_unusual_options_activity", return_value=[]):
        result = compute_convergence("us", days=30)
    assert len(result) == 1
    assert result[0]["direction"] == "BEARISH"
    assert result[0]["score"] == 2


def test_options_uoa_adds_third_leg_to_existing_group():
    form4_row = {"trade_type": "BUY", "ticker": "TSLA", "issuer": "Tesla Inc",
                 "filing_date": "2026-08-01", "transaction_date": "2026-07-30"}
    congress_row = {"trade_type": "BUY", "ticker": "TSLA", "trade_date": "2026-07-29",
                    "chamber": "house", "owner": "self", "link": "https://example.com/y"}
    uoa_row = {"type": "call", "ticker": "TSLA", "expiration_date": "2026-08-15", "strike": 300.0}
    with patch("insider.convergence.get_recent_form4_feed", return_value=[form4_row]), \
         patch("insider.convergence.get_congress_trades", return_value=[congress_row]), \
         patch("insider.convergence.get_unusual_options_activity", return_value=[uoa_row]) as mock_uoa:
        result = compute_convergence("us", days=30)
    assert len(result) == 1
    assert result[0]["score"] == 3
    assert {leg["source"] for leg in result[0]["legs"]} == {"form4", "congress", "options_uoa"}
    mock_uoa.assert_called_once_with(["TSLA"])


def test_empty_ticker_universe_skips_uoa_call():
    with patch("insider.convergence.get_recent_form4_feed", return_value=[]), \
         patch("insider.convergence.get_congress_trades", return_value=[]), \
         patch("insider.convergence.get_unusual_options_activity") as mock_uoa:
        result = compute_convergence("us", days=30)
    assert result == []
    mock_uoa.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_convergence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'insider.convergence'`

- [ ] **Step 3: Write `insider/convergence.py`**

```python
"""leg별 신호를 (ticker, direction)으로 교차집계해 컨버전스 스코어를 매기는 순수 집계 레이어.
새 외부 API 호출 없음 — 기존 leg 함수를 그대로 재사용한다.
"""
from insider.dart_client import get_recent_kr_insider_feed, get_recent_kr_corporate_actions
from insider.edgar_client import get_recent_form4_feed
from insider.congress_client import get_congress_trades
from insider.options_uoa_client import get_unusual_options_activity

_DART_EXEC_DIRECTION = {"BUY": "BULLISH", "SELL": "BEARISH", "CANCELLATION": "BULLISH"}
_DART_CORP_ACTION_DIRECTION = {"BUYBACK": "BULLISH", "PAID_IN": "BEARISH", "DISPOSAL": "BEARISH"}
_US_TRADE_DIRECTION = {"BUY": "BULLISH", "SELL": "BEARISH"}
_UOA_DIRECTION = {"call": "BULLISH", "put": "BEARISH"}


def _tag_kr_legs(days: int) -> list[dict]:
    legs = []
    for row in get_recent_kr_insider_feed(days=days):
        direction = _DART_EXEC_DIRECTION.get(row.get("trade_type", ""))
        if direction is None or not row.get("stock_code"):
            continue
        legs.append({
            "source": "dart_exec",
            "ticker": row["stock_code"],
            "direction": direction,
            "trade_date": row.get("rcept_dt", ""),
            "detail": f"{row.get('corp_name', '')} {row.get('role', '')} {row.get('event_cause', '')}".strip(),
            "url": row.get("dart_url"),
        })
    for row in get_recent_kr_corporate_actions(days=days):
        direction = _DART_CORP_ACTION_DIRECTION.get(row.get("trade_type", ""))
        if direction is None or not row.get("ticker"):
            continue
        legs.append({
            "source": "dart_corp_action",
            "ticker": row["ticker"],
            "direction": direction,
            "trade_date": row.get("trade_date", ""),
            "detail": f"{row.get('corp_name', '')} {row.get('event_cause', '')}".strip(),
            "url": row.get("dart_url"),
        })
    return legs


def _tag_us_legs_without_uoa(days: int) -> list[dict]:
    legs = []
    for row in get_recent_form4_feed(days=days):
        direction = _US_TRADE_DIRECTION.get(row.get("trade_type", ""))
        if direction is None or not row.get("ticker"):
            continue
        legs.append({
            "source": "form4",
            "ticker": row["ticker"],
            "direction": direction,
            "trade_date": row.get("transaction_date") or row.get("filing_date", ""),
            "detail": f"{row.get('issuer', '')} Form4 {row.get('trade_type', '')}".strip(),
            "url": None,
        })
    for row in get_congress_trades(limit=80):
        direction = _US_TRADE_DIRECTION.get(row.get("trade_type", ""))
        if direction is None or not row.get("ticker"):
            continue
        legs.append({
            "source": "congress",
            "ticker": row["ticker"],
            "direction": direction,
            "trade_date": row.get("trade_date", ""),
            "detail": f"{row.get('chamber', '')} {row.get('owner', '')}".strip(),
            "url": row.get("link"),
        })
    return legs


def _tag_uoa_legs(tickers: list[str]) -> list[dict]:
    if not tickers:
        return []
    legs = []
    for row in get_unusual_options_activity(tickers):
        direction = _UOA_DIRECTION.get(row.get("type", ""))
        if direction is None or not row.get("ticker"):
            continue
        legs.append({
            "source": "options_uoa",
            "ticker": row["ticker"],
            "direction": direction,
            "trade_date": row.get("expiration_date", ""),
            "detail": f"UOA {row.get('type', '')} strike={row.get('strike', '')}",
            "url": None,
        })
    return legs


def compute_convergence(market: str, days: int = 30) -> list[dict]:
    if market == "kr":
        legs = _tag_kr_legs(days)
    elif market == "us":
        legs = _tag_us_legs_without_uoa(days)
        uoa_tickers = sorted({leg["ticker"] for leg in legs})
        legs += _tag_uoa_legs(uoa_tickers)
    else:
        raise ValueError(f"unknown market: {market!r}")

    groups: dict[tuple[str, str], list[dict]] = {}
    for leg in legs:
        key = (leg["ticker"], leg["direction"])
        groups.setdefault(key, []).append(leg)

    signals = []
    for (ticker, direction), group_legs in groups.items():
        score = len({leg["source"] for leg in group_legs})
        if score < 2:
            continue
        signals.append({
            "ticker": ticker,
            "market": market,
            "direction": direction,
            "score": score,
            "legs": [{"source": l["source"], "trade_date": l["trade_date"], "detail": l["detail"], "url": l["url"]} for l in group_legs],
        })

    signals.sort(key=lambda s: s["score"], reverse=True)
    return signals
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_convergence.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add insider/convergence.py tests/test_convergence.py
git commit -m "feat: add compute_convergence pure aggregation layer"
```

---

### Task 2: `GET /insider/convergence` 엔드포인트

**Files:**
- Modify: `api_server/main.py`

**Interfaces:**
- Consumes: `insider.convergence.compute_convergence(market: str, days: int = 30) -> list[dict]` from Task 1.
- Produces: `GET /insider/convergence?market=kr|us&days=30` returning `list[ConvergenceSignalOut]` — later tasks (Task 3 alert merge, Task 4 frontend) rely on this exact response shape and the `ConvergenceSignalOut`/`ConvergenceLegOut` pydantic model field names below.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_insider.py` (follow the file's existing `TestClient(app)` + `patch("api_server.main._<alias>")` convention):

```python
def test_insider_convergence_kr_ok():
    mock_signals = [{
        "ticker": "005930", "market": "kr", "direction": "BULLISH", "score": 2,
        "legs": [
            {"source": "dart_exec", "trade_date": "2026-08-01", "detail": "삼성전자 대표이사 장내매수", "url": "https://dart.fss.or.kr/x"},
            {"source": "dart_corp_action", "trade_date": "2026-08-01", "detail": "삼성전자 자사주", "url": "https://dart.fss.or.kr/y"},
        ],
    }]
    with patch("api_server.main._convergence_compute", return_value=mock_signals):
        r = client.get("/insider/convergence?market=kr&days=30")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["ticker"] == "005930"
    assert body[0]["score"] == 2
    assert len(body[0]["legs"]) == 2


def test_insider_convergence_empty():
    with patch("api_server.main._convergence_compute", return_value=[]):
        r = client.get("/insider/convergence?market=us&days=30")
    assert r.status_code == 200
    assert r.json() == []


def test_insider_convergence_invalid_market_returns_422():
    r = client.get("/insider/convergence?market=eu&days=30")
    assert r.status_code == 422
```

(Confirm the top of `tests/test_insider.py` already has `from unittest.mock import patch` and `from fastapi.testclient import TestClient` / `client = TestClient(app)` — if not already imported, add them following the file's existing header.)

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_insider.py -k convergence -v`
Expected: FAIL with 404 (endpoint doesn't exist) or `AttributeError` on `_convergence_compute`

- [ ] **Step 3: Add the endpoint to `api_server/main.py`**

Add the import near the other insider imports (`api_server/main.py:3705-3708` area):

```python
from insider.convergence import compute_convergence as _convergence_compute
```

Add these pydantic models near `TriggeredAlertOut`/`TriggeredAlertsResponse` (`api_server/main.py:3524-3536` area):

```python
class ConvergenceLegOut(BaseModel):
    source: str
    trade_date: str
    detail: str
    url: str | None = None


class ConvergenceSignalOut(BaseModel):
    ticker: str
    market: str
    direction: str
    score: int
    legs: list[ConvergenceLegOut]
```

Add the endpoint near the other `/insider/*` routes:

```python
@app.get("/insider/convergence", response_model=list[ConvergenceSignalOut])
def insider_convergence(
    market: Literal["kr", "us"] = Query(...),
    days: int = Query(30, ge=1, le=180),
) -> list[ConvergenceSignalOut]:
    signals = _convergence_compute(market, days=days)
    return [ConvergenceSignalOut(**s) for s in signals]
```

(If `Literal` isn't already imported at the top of `api_server/main.py`, add `from typing import Literal` to the existing `typing` import line.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_insider.py -k convergence -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add api_server/main.py tests/test_insider.py
git commit -m "feat: add GET /insider/convergence endpoint"
```

---

### Task 3: 컨버전스 신호를 `/alerts/triggered`에 병합

**Files:**
- Modify: `api_server/main.py`

**Interfaces:**
- Consumes: `_convergence_compute("kr"|"us", days=30) -> list[dict]` from Task 1/2, `_recently_triggered(rule_id: str) -> bool` (`api_server/main.py:3637`), `_triggered_alerts: list[TriggeredAlertOut]`, `_MAX_TRIGGERED` (existing module globals).
- Produces: `_check_insider_convergence()` function, called from inside `get_triggered_alerts()`'s `with _alert_lock:` block — later tasks don't consume this directly (frontend polls `/alerts/triggered` which already exists), but the `rule_id` format `f"insider-convergence:{market}:{ticker}:{direction}"` and `bot_id="insider-convergence"` are relied on by Task 5's `linkFor()` prefix match.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_alerts_api.py` (follow its `setup_function` clearing `_alert_rules`/`_triggered_alerts`, and `patch("api_server.main.live_engine")` convention):

```python
def test_triggered_includes_insider_convergence_signal():
    mock_signals_kr = [{
        "ticker": "005930", "market": "kr", "direction": "BULLISH", "score": 2,
        "legs": [
            {"source": "dart_exec", "trade_date": "2026-08-01", "detail": "d1", "url": None},
            {"source": "dart_corp_action", "trade_date": "2026-08-01", "detail": "d2", "url": None},
        ],
    }]
    with patch("api_server.main.live_engine") as mock_engine, \
         patch("api_server.main._convergence_compute", side_effect=lambda market, days=30: mock_signals_kr if market == "kr" else []):
        mock_engine.get_all_statuses.return_value = {}
        r = client.get("/alerts/triggered")
    assert r.status_code == 200
    triggered = r.json()["triggered"]
    conv = [t for t in triggered if t["bot_id"] == "insider-convergence"]
    assert len(conv) == 1
    assert conv[0]["rule_id"] == "insider-convergence:kr:005930:BULLISH"
    assert "005930" in conv[0]["detail"]


def test_triggered_convergence_dedup_within_window():
    mock_signals_kr = [{
        "ticker": "005930", "market": "kr", "direction": "BULLISH", "score": 2,
        "legs": [{"source": "dart_exec", "trade_date": "2026-08-01", "detail": "d1", "url": None}],
    }]
    with patch("api_server.main.live_engine") as mock_engine, \
         patch("api_server.main._convergence_compute", side_effect=lambda market, days=30: mock_signals_kr if market == "kr" else []):
        mock_engine.get_all_statuses.return_value = {}
        client.get("/alerts/triggered")
        r2 = client.get("/alerts/triggered")
    conv = [t for t in r2.json()["triggered"] if t["bot_id"] == "insider-convergence"]
    assert len(conv) == 1  # 두번째 폴링에서 중복 추가 안됨 (300s dedup window)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_alerts_api.py -k convergence -v`
Expected: FAIL — `conv` list is empty (no merge logic yet)

- [ ] **Step 3: Add `_check_insider_convergence()` and call it from `get_triggered_alerts()`**

Add this function right after `_check_sharp_wallet_entries()` (`api_server/main.py:3574` area), following its exact append/cap pattern:

```python
def _check_insider_convergence() -> None:
    """compute_convergence(kr/us)를 매 폴링마다 재계산해 score>=2 신호를 합성 alert로 편입.
    순수 재계산이라 신규-여부 커서 없이 _recently_triggered()의 300s dedup에 그대로 태운다.
    """
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    for market in ("kr", "us"):
        for sig in _convergence_compute(market, days=30):
            rule_id = f"insider-convergence:{market}:{sig['ticker']}:{sig['direction']}"
            if _recently_triggered(rule_id):
                continue
            dir_label = "상승" if sig["direction"] == "BULLISH" else "하락"
            _triggered_alerts.append(TriggeredAlertOut(
                rule_id=rule_id,
                rule_label=f"컨버전스 {dir_label}: {sig['ticker']}",
                condition_type="insider_convergence",
                bot_id="insider-convergence",
                detail=f"{sig['ticker']} score={sig['score']} legs={','.join(l['source'] for l in sig['legs'])}",
                triggered_at=now_iso,
            ))
            if len(_triggered_alerts) > _MAX_TRIGGERED:
                _triggered_alerts.pop(0)
```

Call it inside `get_triggered_alerts()`, alongside `_check_sharp_wallet_entries()`:

```python
    with _alert_lock:
        _check_sharp_wallet_entries()
        _check_insider_convergence()
        for rule in list(_alert_rules.values()):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_alerts_api.py -v`
Expected: PASS (all tests including the 2 new ones — verify no existing alert tests broke)

- [ ] **Step 5: Commit**

```bash
git add api_server/main.py tests/test_alerts_api.py
git commit -m "feat: merge insider convergence signals into /alerts/triggered"
```

---

### Task 4: 백엔드 전체 테스트 스위트 확인

**Files:** none (verification-only task)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue && /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: all tests pass, no pre-existing-failure regressions (per `seokminal/CLAUDE.md`, baseline is 0 known-failing as of 2026-07-30 — any new failure here is caused by Tasks 1-3, not pre-existing).

- [ ] **Step 2: If failures found, fix and re-run per Task 1-3's own steps**

No commit for this task — it's a checkpoint, not a deliverable. If fixes were needed, they get folded into an amendment commit on the relevant task above (a new commit, not `--amend`, per this repo's git conventions).

---

### Task 5: `lib/api.ts` — `getInsiderConvergence()` + 타입

**Files:**
- Modify: `lib/api.ts`

**Interfaces:**
- Consumes: `GET /insider/convergence?market=kr|us&days=30` from Task 2, response shape `ConvergenceSignalOut[]` (`ticker`, `market`, `direction`, `score`, `legs: {source, trade_date, detail, url}[]`).
- Produces: `getInsiderConvergence(market: "kr"|"us", days: number, signal?: AbortSignal): Promise<ConvergenceSignal[]>`, exported types `ConvergenceSignal` and `ConvergenceLeg` — Task 7 (frontend tab) imports these exact names.
- Also widens `AlertConditionType` to include `"insider_convergence"` (Task 3's backend `condition_type` value) so `TriggeredAlert.condition_type` type-checks.

**Step 1: Add the type + fetch function**, right after `getOptionsUOA` (`lib/api.ts:2195-2199`):

```ts
export interface ConvergenceLeg {
  source: string;
  trade_date: string;
  detail: string;
  url: string | null;
}

export interface ConvergenceSignal {
  ticker: string;
  market: "kr" | "us";
  direction: "BULLISH" | "BEARISH";
  score: number;
  legs: ConvergenceLeg[];
}

export async function getInsiderConvergence(market: "kr" | "us", days = 30, signal?: AbortSignal): Promise<ConvergenceSignal[]> {
  const r = await fetch(`${API_URL}/insider/convergence?market=${market}&days=${days}`, { signal });
  return handleResponse<ConvergenceSignal[]>(r);
}
```

**Step 2: Widen `AlertConditionType`** (`lib/api.ts:1936-1942`):

```ts
export type AlertConditionType =
  | "price_above"
  | "price_below"
  | "pnl_above"
  | "pnl_below"
  | "bot_error"
  | "bot_stopped"
  | "insider_convergence";
```

**Step 3: Typecheck**

Run: `cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-dashboard && npx tsc --noEmit`
Expected: no new errors introduced by this change (pre-existing unrelated errors, if any, are out of scope).

**Step 4: Commit**

```bash
git add lib/api.ts
git commit -m "feat: add getInsiderConvergence API client function"
```

---

### Task 6: `AlertPoller.tsx` — `linkFor()` 라우팅 한 줄

**Files:**
- Modify: `components/AlertPoller.tsx`

**Interfaces:**
- Consumes: `bot_id="insider-convergence"` string prefix from Task 3.
- Produces: nothing consumed by later tasks — this is a leaf change.

**Step 1: Edit `linkFor()`** (`components/AlertPoller.tsx:9-13`):

```ts
function linkFor(botId: string): { href: string; label: string } {
  if (botId.startsWith("insider-convergence")) return { href: "/insider?tab=convergence", label: "내부자 컨버전스" };
  if (botId.startsWith("polymarket")) return { href: "/polymarket", label: "폴리마켓 대시보드" };
  if (botId.startsWith("mlb")) return { href: "/mlb", label: "MLB 대시보드" };
  return { href: "/agents", label: "에이전트 목록" };
}
```

**Step 2: Typecheck**

Run: `cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-dashboard && npx tsc --noEmit`
Expected: no new errors.

**Step 3: Commit**

```bash
git add components/AlertPoller.tsx
git commit -m "feat: route insider-convergence alerts to /insider?tab=convergence"
```

---

### Task 7: `/insider` 페이지 — 컨버전스 탭 + 카드 리스트 + 드로어

**Files:**
- Modify: `app/insider/page.tsx`

**Interfaces:**
- Consumes: `getInsiderConvergence`, `type ConvergenceSignal`, `type ConvergenceLeg` from Task 5.
- Produces: nothing consumed by later tasks — this is the final leaf.

This page currently has no `useSearchParams`/`Suspense` wrapper (confirmed: `export default function InsiderPage()` at line 480 is a plain client component). Since `?tab=convergence` deep-linking requires `useSearchParams`, and Next.js requires a `Suspense` boundary around any component using it (see existing precedent at `app/market/page.tsx:18-19`: `export default function MarketPage() { return <Suspense><MarketPageInner /></Suspense>; }`), this task renames the current default export to an inner component and adds the wrapper.

- [ ] **Step 1: Add imports** — extend the existing import block (`app/insider/page.tsx:1-23`):

```tsx
"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ApiError,
  getInsiderKR,
  getInsiderKRRecent,
  getInsiderKRReportLag,
  getInsiderUS,
  getInsiderUSRecent,
  getInsiderCongress,
  getGovContracts,
  getOptionsUOA,
  getInsiderConvergence,
  searchDartCompany,
  type DartCompany,
  type InsiderTrade,
  type InsiderTradeType,
  type CongressTrade,
  type GovContract,
  type OptionsUOA,
  type ConvergenceSignal,
} from "@/lib/api";
import { Panel } from "@/components/ui/Panel";
import { Button, SegmentedToggle } from "@/components/ui";

type Market = "us" | "kr" | "congress" | "gov" | "options" | "convergence";
```

- [ ] **Step 2: Rename `InsiderPage` to `InsiderPageInner` and add the `Suspense`-wrapped default export**

At line 480, change:
```tsx
export default function InsiderPage() {
```
to:
```tsx
function InsiderPageInner() {
```

At the very end of the file (after the closing `}` of the component, currently line 899), add:

```tsx

export default function InsiderPage() {
  return <Suspense><InsiderPageInner /></Suspense>;
}
```

- [ ] **Step 3: Read `?tab=` on mount and add convergence state**, inside `InsiderPageInner`, right after the existing `useState` declarations (after line 484's `const [days] = useState(30);`):

```tsx
  const searchParams = useSearchParams();
  const router = useRouter();
  const [market, setMarketState] = useState<Market>(
    (searchParams.get("tab") as Market) === "convergence" ? "convergence" : "us"
  );
  const setMarket = useCallback((m: Market) => {
    setMarketState(m);
    router.replace(m === "convergence" ? "/insider?tab=convergence" : "/insider", { scroll: false });
  }, [router]);
```

Remove the now-duplicate original `const [market, setMarket] = useState<Market>("us");` line (was line 481) — the block above replaces it.

Add convergence-specific state near the other leg state blocks (after the "Options UOA state" block, around line 515):

```tsx
  // Convergence state
  const [convMarket, setConvMarket] = useState<"kr" | "us">("kr");
  const [convData, setConvData] = useState<ConvergenceSignal[]>([]);
  const [convLoading, setConvLoading] = useState(false);
  const [convError, setConvError] = useState<string | null>(null);
  const [convDrawer, setConvDrawer] = useState<ConvergenceSignal | null>(null);
  const convCtrl = useRef<AbortController | null>(null);

  const fetchConvergence = useCallback(async (m: "kr" | "us") => {
    convCtrl.current?.abort();
    const ctrl = new AbortController();
    convCtrl.current = ctrl;
    setConvLoading(true); setConvError(null); setConvData([]);
    try {
      const res = await getInsiderConvergence(m, 30, ctrl.signal);
      if (!ctrl.signal.aborted) setConvData(res);
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      if (!ctrl.signal.aborted) setConvError(e instanceof ApiError ? e.message : "조회 실패");
    } finally {
      if (!ctrl.signal.aborted) setConvLoading(false);
    }
  }, []);
```

- [ ] **Step 4: Wire up cleanup + auto-load effects**

Extend the abort-on-unmount effect (line 553):
```tsx
  useEffect(() => () => { usCtrl.current?.abort(); krCtrl.current?.abort(); congCtrl.current?.abort(); govCtrl.current?.abort(); uoaCtrl.current?.abort(); convCtrl.current?.abort(); }, []);
```

Extend the auto-load effect (lines 638-645):
```tsx
  useEffect(() => {
    if (market === "us") fetchUSRecent(days);
    else if (market === "kr") fetchKRRecent(days);
    else if (market === "congress") fetchCongress();
    else if (market === "gov") fetchGov();
    else if (market === "convergence") fetchConvergence(convMarket);
    else fetchUOA();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market, days]);

  useEffect(() => {
    if (market === "convergence") fetchConvergence(convMarket);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [convMarket]);
```

- [ ] **Step 5: Add the tab option to `SegmentedToggle`** (`app/insider/page.tsx:686-692`):

```tsx
            options={[
              { value: "us", label: "🇺🇸 US", activeClass: "border-accent bg-accent text-black" },
              { value: "kr", label: "🇰🇷 KR", activeClass: "border-accent bg-accent text-black" },
              { value: "congress", label: "🏛 의회", activeClass: "border-accent bg-accent text-black" },
              { value: "gov", label: "📋 정부계약", activeClass: "border-accent bg-accent text-black" },
              { value: "options", label: "🎯 옵션 UOA", activeClass: "border-accent bg-accent text-black" },
              { value: "convergence", label: "🔥 컨버전스", activeClass: "border-accent bg-accent text-black" },
            ]}
```

- [ ] **Step 6: Add card list + drawer render block**, after the "Options UOA" block (after line 861, before the "US/KR Error" comment):

```tsx
      {/* ── Convergence ─────────────────────────────────────────────────── */}
      {market === "convergence" && (
        <>
          <div className="flex items-center gap-3 bg-panel border border-border rounded-lg px-4 py-3">
            <span className="text-text-3 text-xs shrink-0">마켓:</span>
            <SegmentedToggle
              value={convMarket}
              onChange={setConvMarket}
              size="sm"
              options={[
                { value: "kr", label: "🇰🇷 KR", activeClass: "border-accent bg-accent text-black" },
                { value: "us", label: "🇺🇸 US", activeClass: "border-accent bg-accent text-black" },
              ]}
            />
            <span className="text-text-3 text-xs ml-auto">서로 다른 leg가 같은 티커·같은 방향으로 겹치면 표시 (score = 겹친 leg 종류 수)</span>
          </div>
          {convError && <p className="text-neg text-sm px-1">{convError}</p>}
          {convLoading && <p className="text-text-3 text-sm px-1">로딩 중…</p>}
          {!convLoading && convData.length === 0 && !convError && (
            <Panel className="p-12 text-center">
              <p className="text-text-3 text-sm">컨버전스 신호 없음</p>
            </Panel>
          )}
          {!convLoading && convData.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {convData.map(sig => (
                <button
                  key={`${sig.market}:${sig.ticker}:${sig.direction}`}
                  onClick={() => setConvDrawer(sig)}
                  className="text-left bg-panel border border-border rounded-lg p-4 hover:border-accent transition-colors">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-text-1 font-data font-semibold">{sig.ticker}</span>
                    <span className={`text-xs font-bold rounded px-1.5 py-0.5 border ${sig.market === "kr" ? "bg-info/15 text-info border-info/25" : "bg-panel-2 text-text-3 border-border"}`}>
                      {sig.market === "kr" ? "🇰🇷 KR" : "🇺🇸 US"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`text-xs font-bold rounded px-1.5 py-0.5 border ${sig.direction === "BULLISH" ? "bg-pos/15 text-pos border-pos/25" : "bg-neg/15 text-neg border-neg/25"}`}>
                      {sig.direction === "BULLISH" ? "🟢 상승" : "🔴 하락"}
                    </span>
                    <span className={`text-xs font-bold rounded px-1.5 py-0.5 border ${sig.score >= 3 ? "bg-accent/15 text-accent border-accent/25" : "bg-warn/15 text-warn border-warn/25"}`}>
                      score {sig.score} {sig.score >= 3 ? "강함" : "주의"}
                    </span>
                  </div>
                  <div className="text-text-3 text-xs">
                    {Array.from(new Set(sig.legs.map(l => l.source))).join(" · ")}
                  </div>
                </button>
              ))}
            </div>
          )}
          {convDrawer && (
            <div className="fixed inset-0 z-50 flex justify-end" onClick={() => setConvDrawer(null)}>
              <div className="absolute inset-0 bg-black/50" />
              <div className="relative w-full max-w-md bg-panel border-l border-border h-full overflow-y-auto p-4" onClick={e => e.stopPropagation()}>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-text-1 font-semibold font-data">{convDrawer.ticker} — {convDrawer.direction === "BULLISH" ? "🟢 상승" : "🔴 하락"}</h2>
                  <button onClick={() => setConvDrawer(null)} className="text-text-3 hover:text-text-1">✕</button>
                </div>
                <div className="space-y-3">
                  {convDrawer.legs.map((leg, i) => (
                    <div key={i} className="bg-panel-2 border border-border rounded-lg p-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-text-1 text-xs font-semibold">{leg.source}</span>
                        <span className="text-text-3 text-xs font-data">{leg.trade_date}</span>
                      </div>
                      <p className="text-text-2 text-xs">{leg.detail}</p>
                      {leg.url && (
                        <a href={leg.url} target="_blank" rel="noopener noreferrer" className="text-accent text-xs hover:underline mt-1 inline-block">
                          원문 보기 →
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}

```

- [ ] **Step 7: Typecheck**

Run: `cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-dashboard && npx tsc --noEmit`
Expected: no new errors. Fix any if introduced (e.g. `SegmentedToggle`'s generic `onChange`/`value` typing against the narrower `"kr"|"us"` union for `convMarket` — check `components/ui/SegmentedToggle`'s prop types if this doesn't typecheck cleanly, and adjust the generic invocation accordingly).

- [ ] **Step 8: Manual browser verification**

Start the backend (`bash scripts/restart_api.sh` from `seokminal-multi-venue`) and frontend (`npm run dev` from `seokminal-dashboard`, port 3000). Navigate to `http://localhost:3000/insider?tab=convergence` and confirm:
- Tab auto-selects "🔥 컨버전스" from the URL param
- KR/US toggle switches `convMarket` and refetches
- Card grid renders (or "컨버전스 신호 없음" if no live data crosses score>=2 — expected on a quiet day, not a bug)
- Clicking a card opens the drawer with leg details and a working "원문 보기" link where `url` is non-null
- Clicking the SegmentedToggle "US"/"KR" top-level market tabs away from convergence and back preserves correct state

- [ ] **Step 9: Commit**

```bash
git add app/insider/page.tsx
git commit -m "feat: add convergence tab with card list and detail drawer to /insider"
```

---

## Self-Review Notes

- **Spec coverage:** 방향 태깅 표(Task 1) ✓, 스코어링 알고리즘(Task 1) ✓, API(Task 2) ✓, 알림 연동(Task 3) ✓, 대시보드 UI(Task 7) ✓, 테스트 계획 6항목 전부 Task 1 테스트에 1:1 대응 ✓, gov-contracts 제외(Task 1 — `compute_convergence`가 애초에 `get_recent_contracts`를 import하지 않음) ✓.
- **UOA `days` 파라미터 spec 갭:** 스펙엔 명시 안 됐지만 `get_unusual_options_activity`가 `days`가 아닌 `tickers` 파라미터라 뭔가 유니버스 결정 로직이 필요했음 — Task 1에서 "다른 leg가 이미 잡은 티커만 UOA로 재확인"으로 명시적으로 좁힘(스펙의 "새 외부 API 호출 없음" 제약과 정합).
- **Type consistency:** `ConvergenceSignal`(Task 1 dict shape) → `ConvergenceSignalOut`(Task 2 pydantic) → `ConvergenceSignal`(Task 5 TS interface) → 프론트 사용(Task 7) 전부 `ticker/market/direction/score/legs` 필드명 일치 확인. `source` 값(`dart_exec`/`dart_corp_action`/`form4`/`congress`/`options_uoa`)은 Task 1에서 정의, Task 7 카드에서 그대로 표시(별도 아이콘 매핑 없이 raw 문자열 join — 스펙의 "기여 leg 아이콘 나열"보다 단순하지만 v1 범위로 충분, 아이콘 매핑은 필요시 추후 확장).
