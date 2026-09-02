# 멀티브로커 포트폴리오 뷰 — 설계

2026-09-02. iOS 리모컨 앱 탭 구조 개편(Agents/PnL/Bots/HL 4탭 → Agents/Portfolio
2탭) + 신규 백엔드 포트폴리오 집계 계층. HL/KIS 계좌를 live/paper 구분해서
합산 총자산·수익률·보유종목 파이·계좌별 카드·거래내역으로 보여준다.

## 배경

기존 iOS 앱은 HL 포지션 하나만 `/hl/positions`로 보여주는 정도였고, KIS
계좌는 주문만 나가고 잔고/보유종목을 앱에서 확인할 방법이 없었다. 사용자가
"연결된 계좌(HL/KIS/IB) 다 확인하고, 라이브/페이퍼 구분해서, 포트폴리오
전체 수익률·보유종목 파이차트·계좌별 거래내역까지 보고 싶다"고 요청.

탐색 결과 상당 부분이 이미 존재:
- `jarvis/broker_readonly/provider.py`의 `BrokerReadOnlyProvider` 인터페이스
  (account_snapshot/positions/balances/orders_history/health_check) — 지금
  요구사항(계좌 연동 확인)과 정확히 일치하는 설계인데 KIS/IB는
  `_UnconfiguredBroker` 스텁만 있고 미구현.
- `backends/kis/order_client.py`의 `KISOrderClient.get_balance()` /
  `.get_holdings()` — KIS 실전/모의 계좌 잔고·보유종목 API 이미 동작.
- `hyperliquid/trader.py:get_positions(paper=bool)` — HL 쪽은 이미 완비.
- `data/order_audit.jsonl` 같은 JSONL append-only 파일이 이 레포의 durable
  storage 관례 (`api_server/oms.py`는 프로세스 인메모리, `order_audit.py`가
  재시작 넘어 살아남는 쪽).

IB는 `.env`에 `IB_PORT`만 있고 계좌/호스트 정보가 없어 이번 스코프에서 제외
— `IBReadOnlyProvider`는 스텁 그대로 두고 `health_check()`가 `connected=false`
로 정직하게 "미연동" 표시만 하도록 남긴다. 나중에 IB 붙일 때는 이 인터페이스에
어댑터 하나만 추가하면 되는 구조로 설계.

**이 세션에서 겪은 사고와 직결된 설계 원칙**: 오늘 `alert_push_loop`이 EDGAR/
Alpaca 호출을 이벤트루프에서 직접(또는 timeout 없이) 돌려서 서버 전체가 여러
차례 먹통이 났다(HL SDK, EDGAR, Alpaca 세 곳 모두 `requests`에 timeout 인자
누락 — `socket.setdefaulttimeout(15)`로 전역 방어 추가). 이 포트폴리오 기능은
브로커 API를 주기적으로(일일 스냅샷) + 요청마다(summary 조회) 호출하므로,
**같은 사고가 재발하지 않게 하는 것 자체가 설계 요구사항**이다: 모든 브로커
호출은 `asyncio.to_thread`로 이벤트루프 밖에서 실행하고, 한 계좌 실패가 전체
응답을 막지 않는다(부분 실패 허용).

## 스코프

- 대상 계좌: HL-live, HL-paper(testnet), KIS-live(실전), KIS-paper(모의) — 4개.
- IB: 제외 (health_check만 "미연동"으로 표시).
- 거래내역: OMS(`api_server/oms.py`)에 기록된, 이 플랫폼을 통해 나간 주문만.
  브로커가 직접 보고하는 전체 체결 내역(HL/KIS 원본 API)은 스코프 밖.
- 수익률 그래프: 오늘부터 매일 1회 스냅샷 적재. 과거 데이터 없음(첫 주는
  그래프가 짧다).
- 기본 통화: USD (KIS 쪽 KRW는 `USDKRW=X` 티커로 변환해 합산).

## 컴포넌트

### 1. `jarvis/broker_readonly/adapters.py` (기존 파일 확장)

`_UnconfiguredBroker` 스텁 대신 실제 provider 4개 구현. 생성자에서 어떤
클라이언트를 쓸지만 결정하고, 실제 I/O는 전부 하위 클라이언트(`KISOrderClient`,
`hyperliquid.trader`)에 위임 — 이 파일 자체는 얇은 어댑터로 유지.

```python
class HLReadOnlyProvider(BrokerReadOnlyProvider):
    source_name = "hyperliquid"

    def __init__(self, paper: bool = False) -> None:
        self._paper = paper

    def account_snapshot(self) -> AccountSnapshot | None:
        from hyperliquid.trader import get_positions
        data = get_positions(paper=self._paper)  # 이미 timeout=10 걸려있음(오늘 수정)
        ms = data["margin_summary"]
        return AccountSnapshot(
            cash=float(ms.get("spotUsdcBalance", 0)),
            equity=float(ms.get("accountValue", 0)),
            buying_power=float(ms.get("accountValue", 0)),
            timestamp=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        )

    def positions(self) -> list[BrokerPosition]:
        from hyperliquid.trader import get_positions
        data = get_positions(paper=self._paper)
        out = []
        for p in data.get("asset_positions", []):
            pos = p.get("position", p)
            out.append(BrokerPosition(
                symbol=pos.get("coin", ""),
                quantity=float(pos.get("szi", 0)),
                avg_price=float(pos.get("entryPx", 0) or 0),
                market_value=float(pos.get("positionValue", 0) or 0),
                timestamp=_dt.datetime.now(_dt.timezone.utc).isoformat(),
            ))
        return out

    def balances(self) -> dict:
        snap = self.account_snapshot()
        return snap.to_dict() if snap else {}

    def orders_history(self) -> list[dict]:
        from api_server import oms
        return oms.list_orders(venue="HL_PAPER" if self._paper else "HL")

    def health_check(self) -> BrokerHealth:
        try:
            self.account_snapshot()
            return BrokerHealth(connected=True, stale=False, error=None,
                                 timestamp=_dt.datetime.now(_dt.timezone.utc).isoformat())
        except Exception as exc:
            return BrokerHealth(connected=False, stale=False, error=str(exc),
                                 timestamp=_dt.datetime.now(_dt.timezone.utc).isoformat())


class KISReadOnlyProvider(BrokerReadOnlyProvider):
    source_name = "kis"

    def __init__(self, paper: bool = False) -> None:
        self._paper = paper

    def _client(self):
        from backends.kis.order_client import KISOrderClient
        import os
        if self._paper:
            return KISOrderClient(
                os.environ["KIS_MOCK_APP_KEY"], os.environ["KIS_MOCK_APP_SECRET"],
                os.environ["KIS_MOCK_CANO"], os.environ["KIS_ACNT_PRDT_CD"], mock=True)
        return KISOrderClient(
            os.environ["KIS_APP_KEY"], os.environ["KIS_APP_SECRET"],
            os.environ["KIS_CANO"], os.environ["KIS_ACNT_PRDT_CD"], mock=False)

    def account_snapshot(self) -> AccountSnapshot | None:
        bal = self._client().get_balance()
        return AccountSnapshot(
            cash=bal["deposit"], equity=bal["net_asset"], buying_power=bal["deposit"],
            timestamp=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        )

    def positions(self) -> list[BrokerPosition]:
        holdings = self._client().get_holdings()
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        return [BrokerPosition(symbol=h["code"], quantity=h["qty"], avg_price=h["avg_price"],
                                market_value=h["qty"] * h["current"], timestamp=now)
                for h in holdings]

    def balances(self) -> dict:
        return self._client().get_balance()

    def orders_history(self) -> list[dict]:
        from api_server import oms
        return oms.list_orders(venue="KR")  # paper/live는 client_order_id 접두사로 이미 구분됨(확인 필요)

    def health_check(self) -> BrokerHealth:
        try:
            self._client().get_balance()
            return BrokerHealth(connected=True, stale=False, error=None,
                                 timestamp=_dt.datetime.now(_dt.timezone.utc).isoformat())
        except Exception as exc:
            return BrokerHealth(connected=False, stale=False, error=str(exc),
                                 timestamp=_dt.datetime.now(_dt.timezone.utc).isoformat())
```

주의: `KIS_ENV_KEY_ERROR` — 위 `os.environ[...]`는 키 없으면 바로 KeyError.
`health_check()`가 이걸 잡아서 "미설정"으로 보여줘야 하므로, 실제 구현 시
`os.environ["..."]` 대신 `os.environ.get("...", "")` + 값 없으면
`raise ValueError("KIS 모의 계좌 키 미설정")`으로 명시적 에러를 던지는 편이
낫다(불명확한 KeyError보다 진단하기 쉬움).

`oms.list_orders(venue=...)`가 live/paper를 구분해서 필터링할 수 있는지는
현재 `venue` 값 스킴 확인 필요(place_order 호출부에서 실제로 어떤 venue
문자열을 넘기는지 구현 시점에 재확인) — 스펙 단계에서 가정만 적어둠.

### 2. `jarvis/portfolio/aggregator.py` (신규)

```python
class PortfolioAggregator:
    def __init__(self, providers: dict[str, BrokerReadOnlyProvider]) -> None:
        self._providers = providers  # {"hl": ..., "kis": ...}

    async def summary(self, base_ccy: str = "USD") -> dict:
        results = await asyncio.gather(
            *[asyncio.to_thread(self._one, name, p) for name, p in self._providers.items()],
            return_exceptions=True,
        )
        accounts = []
        total_equity_usd = 0.0
        holdings: dict[str, float] = {}
        fx = await asyncio.to_thread(_usdkrw_rate)  # 기존 FX 조회 함수 재사용
        for (name, _), res in zip(self._providers.items(), results):
            if isinstance(res, Exception):
                accounts.append({"account": name, "connected": False, "error": str(res)})
                continue
            snap, positions, health = res
            eq_usd = snap.equity / fx if name.startswith("kis") else snap.equity
            total_equity_usd += eq_usd
            for pos in positions:
                holdings[f"{name}:{pos.symbol}"] = holdings.get(f"{name}:{pos.symbol}", 0) + pos.market_value
            accounts.append({
                "account": name, "connected": health.connected, "error": health.error,
                "cash": snap.cash, "equity": snap.equity, "equity_usd": eq_usd,
                "positions": [p.to_dict() for p in positions],
            })
        return {"total_equity_usd": total_equity_usd, "accounts": accounts,
                "holdings_breakdown": holdings, "fx_usdkrw": fx}

    def _one(self, name, provider):
        return provider.account_snapshot(), provider.positions(), provider.health_check()
```

`return_exceptions=True` + per-provider try 없이도 `asyncio.gather`가 개별
실패를 잡아주므로, 한 계좌(KIS 타임아웃 등) 죽어도 나머지는 정상 리턴 —
오늘 사고의 핵심 교훈(부분 실패 허용) 그대로 반영.

### 3. `jarvis/portfolio/snapshot_job.py` (신규)

```python
_SNAPSHOT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "portfolio_snapshots.jsonl"
_SNAPSHOT_INTERVAL_SEC = 24 * 3600

async def snapshot_loop() -> None:
    while True:
        for mode in ("live", "paper"):
            try:
                agg = _aggregator_for(mode)  # live→HL-live+KIS-live, paper→HL-paper+KIS-paper
                summary = await agg.summary()
                with open(_SNAPSHOT_PATH, "a") as f:
                    f.write(json.dumps({
                        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "mode": mode, "total_equity_usd": summary["total_equity_usd"],
                    }) + "\n")
            except Exception:
                pass
        await asyncio.sleep(_SNAPSHOT_INTERVAL_SEC)
```

`api_server/main.py`의 startup 블록에 `asyncio.create_task(snapshot_loop())`
로 등록 — 기존 `alert_push_loop`/`gex_poll_loop`과 같은 패턴.

### 4. `api_server/main.py` 신규 엔드포인트 (얇은 라우터)

```python
@app.get("/portfolio/summary")
async def portfolio_summary(mode: Literal["live", "paper"] = "live") -> dict:
    agg = _aggregator_for(mode)
    return await agg.summary()

@app.get("/portfolio/history")
def portfolio_history(mode: Literal["live", "paper"] = "live", days: int = 30) -> dict:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    points = []
    with open(_SNAPSHOT_PATH) as f:
        for line in f:
            row = json.loads(line)
            if row["mode"] == mode and dt.datetime.fromisoformat(row["ts"]) >= cutoff:
                points.append(row)
    return {"mode": mode, "points": points}

@app.get("/portfolio/trades")
def portfolio_trades(mode: Literal["live", "paper"] = "live",
                      account: Literal["hl", "kis"] | None = None) -> dict:
    from api_server import oms
    venues = {"hl": "HL", "kis": "KR"}  # paper 접미사는 구현 시점에 실제 스킴 확인
    venue = venues.get(account) if account else None
    return {"orders": oms.list_orders(venue=venue, limit=500)}
```

`portfolio_summary`는 `async def`라 이벤트루프에서 직접 도는데, 내부
`agg.summary()`가 이미 `to_thread`로 브로커 호출을 다 격리하므로 이벤트루프
자체는 블락 안 됨 — `alert_push_loop` 고칠 때와 동일한 원칙.

### 5. iOS (`ios-remote`)

- **Agents탭**: 기존 `AgentsView`/`BotsView`를 감싸는 컨테이너 뷰 신설,
  상단 `Picker`(세그먼트, "에이전트"/"봇")로 전환. 각 뷰 내부 로직·API 호출
  변경 없음.
- **Portfolio탭** (신규, PnL탭/HL탭 대체): 상단 `Picker`(Live/Paper) →
  `/portfolio/summary?mode=` 호출 → 총자산 큰 숫자 + 수익률(전일 대비, history
  최근 2포인트로 계산) → `Charts` 프레임워크(iOS17 네이티브) `SectorMark`로
  `holdings_breakdown` 파이 → `LineMark`로 `/portfolio/history` 라인그래프 →
  `accounts` 배열을 카드 리스트로(연동 상태 뱃지 = `connected` bool, 현금/평가
  금액) → 카드 탭 시 `/portfolio/trades?account=` drill-in 리스트.
- 스타일: 기존 앱 톤(다크, 큰 숫자, 얇은 구분선) 유지, Robinhood/Toss류
  증권 앱 참고 — 카드 리스트 중심, 장식 최소화.

## 에러 처리

- 계좌 하나(예: KIS 타임아웃) 실패해도 `/portfolio/summary`는 200 리턴,
  해당 계좌만 `connected: false` + `error` 메시지. 전체 500 금지.
- 모든 브로커 I/O는 `asyncio.to_thread` 안에서 실행 — 이벤트루프 직접 호출
  금지(오늘 사고 재발 방지가 이 스펙의 불변식).
- `socket.setdefaulttimeout(15)`(오늘 추가됨, `api_server/main.py`)가 이미
  전역 안전망이므로 신규 코드에서 추가 timeout 설정 불필요.
- `snapshot_loop` 실패는 조용히 삼키고 다음 주기 재시도 — 그래프에 구멍
  하루 생기는 게 서버 전체 먹통보다 훨씬 낫다.

## 테스트

- `jarvis/broker_readonly/adapters.py`: 기존 `MockBrokerProvider` 패턴으로
  `HLReadOnlyProvider`/`KISReadOnlyProvider`의 `account_snapshot`/`positions`
  파싱 로직 단위테스트(HL/KIS 응답 fixture 넣고 필드 매핑 검증).
  `pytest tests/ -q` (asyncio_mode=auto, `@pytest.mark.asyncio` 금지).
- `PortfolioAggregator.summary()`: provider 중 하나가 예외 던지는 케이스
  포함해서 부분 실패 시나리오 테스트 (핵심 불변식 검증).
- `snapshot_job`: JSONL 포맷 왕복(쓰고 다시 읽었을 때 필드 일치) 정도만.
- iOS: 테스트 타겟 없음 — 앱 직접 실행해서 4탭(Agents/Bots 세그먼트,
  Portfolio Live/Paper 세그먼트) 다 확인.

## 미결/구현 시 재확인 사항

- `oms.list_orders(venue=...)`가 KIS live/paper, HL live/paper를 각각 다른
  venue 문자열로 구분해서 저장하는지 실제 `place_order`/`place_kr_order`
  호출부 확인 필요 (스펙 단계에서 가정만 해둠).
- KIS 미설정 시(`.env` 키 없음) `health_check()`가 명확한 에러 메시지를
  주도록 `os.environ[...]` 대신 명시적 검증 필요 (컴포넌트 1 참고).
