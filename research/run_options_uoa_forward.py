"""옵션 UOA 사후수익률 라벨링 — 2단계(수집→라벨링→임계값스윕/BH-FDR 중 두번째).

1단계(`run_options_uoa_collect.py`)가 이상옵션거래 이벤트만 쌓아뒀다. 여기선 각 이벤트에
**기초자산의 사후 수익률**을 붙인다. 임계값 스윕·BH-FDR 등록은 표본이 쌓인 뒤 별도로.

규약:
  - 진입은 탐지일 **다음 거래일 시가** — 탐지가 장중/장마감후라 당일 종가 진입은 lookahead.
  - 방향은 계약 종류: call=롱, put=숏(숏은 부호 반전). 같은 티커·같은 날 call/put이 동시에
    뜨면 **서로 다른 신호로 따로 집계**한다(방향이 반대라 합치면 상쇄됨).
  - 통계 단위는 (티커, 탐지일, 방향) — 같은 날 같은 티커에서 계약 20개가 잡혀도 기초자산
    수익률은 하나다. 계약별로 세면 같은 관측을 20번 센 셈(pseudo-replication)이라 집계한다.

출력은 `research/data/options_uoa_forward/labels.jsonl`. 수집 디렉터리와 분리한 이유:
함대 헬스가 `options_uoa/*.jsonl` mtime으로 수집기 생존을 재는데, 여기서 파일을 쓰면
수집기가 죽어도 살아있는 것처럼 보인다.

실행: PYTHONPATH=. python3 research/run_options_uoa_forward.py
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import statistics as _st
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

from research import jsonl_dates

load_dotenv()   # 알파카 키는 .env에만 있음 — api_server 밖에서 도는 스크립트라 직접 로드

_EVENT_DIR = Path("research/data/options_uoa")
_OUT_DIR = Path("research/data/options_uoa_forward")
_OUT_PATH = _OUT_DIR / "labels.jsonl"

HORIZONS = (1, 3, 5)          # 보유 거래일
MIN_VOL_OI = 0.0              # 라벨링 단계에선 필터 안 함(임계값 스윕은 다음 단계)


def load_events(event_dir: Path = _EVENT_DIR) -> list[dict]:
    """수집기가 쌓은 이벤트 전부. 파일명(YYYY-MM-DD.jsonl)이 아니라 detected_at을 신뢰."""
    return jsonl_dates.iter_all_rows(event_dir)


def group_signals(events: list[dict], min_vol_oi: float = MIN_VOL_OI) -> list[dict]:
    """(티커, 탐지일, 방향)으로 집계. 계약 수와 최대 vol/oi를 신호 강도로 남긴다."""
    buckets: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for e in events:
        if e.get("vol_oi_ratio", 0) < min_vol_oi or not e.get("detected_at"):
            continue
        buckets[(e["ticker"], e["detected_at"][:10], e["type"])].append(e)
    out = []
    for (ticker, date, side), rows in sorted(buckets.items()):
        out.append({
            "ticker": ticker, "date": date, "side": side,
            "n_contracts": len(rows),
            "max_vol_oi": max(r["vol_oi_ratio"] for r in rows),
            "sum_volume": sum(r["volume"] for r in rows),
            "min_dte": min(r["dte"] for r in rows),
            "max_moneyness_pct": max(r["moneyness_pct"] for r in rows),
        })
    return out


def _daily_bars(symbol: str, client, lookback_days: int = 120) -> dict | None:
    """알파카 일봉(날짜·시가·종가). 무료 플랜이라 IEX 피드 — alpaca_shared와 동일 제약."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    req = StockBarsRequest(
        symbol_or_symbols=symbol.upper(), timeframe=TimeFrame.Day,
        start=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days),
        feed=DataFeed.IEX,
    )
    bars = list(client.get_stock_bars(req).data.get(symbol.upper(), []))
    if not bars:
        return None
    return {
        "dates": [b.timestamp.strftime("%Y-%m-%d") for b in bars],
        "open": [float(b.open) for b in bars],
        "close": [float(b.close) for b in bars],
    }


def forward_return(bars: dict, date: str, hold: int, side: str) -> float | None:
    """탐지일 다음 거래일 시가 진입 → hold 거래일 뒤 종가. 아직 안 지났으면 None."""
    j = bisect.bisect_right(bars["dates"], date)      # date 초과 첫 인덱스 = 다음 거래일
    xi = j + hold
    if j >= len(bars["dates"]) or xi >= len(bars["dates"]):
        return None                                   # 미래 바 부족 — 라벨 미완성
    entry = bars["open"][j]
    if entry <= 0:
        return None
    r = bars["close"][xi] / entry - 1
    return -r if side == "put" else r                 # put은 숏 방향


def label_signals(signals: list[dict], bars_by_ticker: dict[str, dict | None]) -> list[dict]:
    out = []
    for s in signals:
        bars = bars_by_ticker.get(s["ticker"])
        if bars is None:
            continue
        rets = {f"fwd_{h}d": forward_return(bars, s["date"], h, s["side"]) for h in HORIZONS}
        out.append({**s, **rets})
    return out


def summarize(labeled: list[dict]) -> dict:
    """지평선별 n·평균·중앙값·승률. 라벨 없는(아직 미래) 건은 제외."""
    res = {}
    for h in HORIZONS:
        key = f"fwd_{h}d"
        vals = [r[key] for r in labeled if r.get(key) is not None]
        res[key] = {
            "n": len(vals),
            "mean": round(_st.mean(vals), 5) if vals else None,
            "median": round(_st.median(vals), 5) if vals else None,
            "win_rate": round(sum(v > 0 for v in vals) / len(vals), 3) if vals else None,
        }
    return res


def main() -> None:
    events = load_events()
    signals = group_signals(events)
    tickers = sorted({s["ticker"] for s in signals})
    print("=" * 72)
    print("OPTIONS UOA 사후수익률 라벨링 (RESEARCH — 판정 아님)")
    print(f"이벤트 {len(events)}건 → 신호 {len(signals)}건 (티커 {len(tickers)})")
    print("=" * 72)

    from api_server.routers.alpaca_shared import _data_client
    client = _data_client()  # 티커마다 새로 만들면 TCP 커넥션이 매번 새로 열려 연쇄 refused 유발 — 재사용

    bars_by_ticker: dict[str, dict | None] = {}
    for t in tickers:
        try:
            bars_by_ticker[t] = _daily_bars(t, client)
        except Exception as e:
            time.sleep(2)  # 순간 refused 대비 1회 재시도
            try:
                bars_by_ticker[t] = _daily_bars(t, client)
            except Exception as e2:
                print(f"  {t}: 일봉 조회 실패(재시도 포함) — {e2}")
                bars_by_ticker[t] = None

    labeled = label_signals(signals, bars_by_ticker)
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _OUT_PATH.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in labeled) + "\n")

    summary = summarize(labeled)
    for key, s in summary.items():
        if not s["n"]:
            print(f"{key}: 라벨 0건 — 보유기간이 아직 안 지남(수집 더 필요)")
        else:
            print(f"{key}: n={s['n']} mean={s['mean']:+.4f} median={s['median']:+.4f} 승률={s['win_rate']}")
    print(f"\n저장: {_OUT_PATH} ({len(labeled)}행)")
    print("주의: 표본 부족 구간에선 평균 부호를 신호로 읽지 말 것. 임계값 스윕·BH-FDR은 다음 단계.")


if __name__ == "__main__":
    main()
