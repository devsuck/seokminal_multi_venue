"""ICT 프리미티브 자유조합 백테스트 라우트 — 탐색용(정식 후보 아님, research/ict/combinator.py 참고).

데이터: research/data/intraday_store.py(평범 parquet, data/intraday/{SYMBOL}_{TF}.parquet).
Nautilus 카탈로그(/bars 등)는 1-DAY 고정이라 killzone(시간대) 프리미티브에 못 씀 — 별도 소스 사용.

타임프레임 확장: 크립토(LIQUID_PERPS)는 HL API 라이브조회로 모든 tf 즉시 확보·캐시.
주식/ETF는 15m 원본에서 1h/4h만 리샘플 합성(1m/5m은 소스 없음 — IB TWS 필요, 여기선 미지원).
"""
import datetime as dt
import glob
import os
import re

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from research.data.hl_candle_loader import fetch as hl_fetch
from research.data.hl_funding_loader import LIQUID_PERPS
from research.data.intraday_store import STORE_DIR, load_df, save_bars
from research.ict.combinator import PRIMITIVE_IDS, detect_events, evaluate_combo

router = APIRouter()

_FILE_RE = re.compile(r"^(.+)_(\d+[mhd])\.parquet$")
_RESAMPLE_TF = {"1h", "4h"}   # 주식/ETF: 15m → 리샘플 합성 가능한 tf


def _resample_from_15m(symbol: str, tf: str) -> pd.DataFrame:
    base = load_df(symbol, "15m")
    if len(base) < 50:
        return base.iloc[0:0]
    d = base.copy()
    d["dt"] = pd.to_datetime(d["ts_utc"], unit="s", utc=True)
    d = d.set_index("dt")
    agg = (
        d.resample(tf)
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
        .reset_index()
    )
    agg["ts_utc"] = (agg["dt"].astype("int64") // 10**9).astype("int64")
    return agg[["ts_utc", "open", "high", "low", "close", "volume"]]


def _load_or_synthesize(symbol: str, tf: str) -> pd.DataFrame:
    """직접저장 → (크립토)HL 라이브조회+캐시 → (주식/ETF, 1h/4h만)15m 리샘플 → 실패시 빈 프레임."""
    df = load_df(symbol, tf)
    if len(df):
        return df
    if symbol in LIQUID_PERPS:
        rows = hl_fetch(symbol, tf, years=3.0)
        if rows:
            save_bars(symbol, tf, rows)
        return load_df(symbol, tf)
    if tf in _RESAMPLE_TF:
        return _resample_from_15m(symbol, tf)
    return df


class IctBacktestRequest(BaseModel):
    symbol: str
    timeframe: str = "15m"
    start: str | None = None   # ISO date, 미지정시 전체 구간
    end: str | None = None
    primitives: list[str]
    direction: str = "bullish"       # bullish | bearish
    hold: int = 8
    cost_bps: float = 5.0
    lookback: int = 10
    swing_k: int = 2
    kz_start_hour: float = 13.5
    kz_end_hour: float = 15.0
    window: int = 8      # ote/ifvg 되돌림 확인 lookahead
    near: int = 3        # unicorn OB↔FVG 근접 허용봉수
    min_run: int = 2     # cisd 연속캔들 최소길이
    confirm: int = 3     # turtle_soup 가짜돌파 후 복귀 확인 lookahead


class IctBacktestResponse(BaseModel):
    n_entries: int
    n_eligible: int | None = None
    net: float | None = None
    percentile: float | None = None
    p: float | None = None
    rand_median: float | None = None
    wf_first: float | None = None
    wf_second: float | None = None
    entries_ts: list[int] = []
    verdict: str | None = None


class IctBar(BaseModel):
    ts: int
    o: float
    h: float
    l: float
    c: float


class IctEventsResponse(BaseModel):
    bars: list[IctBar]
    events: dict[str, list[dict]]


@router.get("/ict/primitives")
def list_ict_primitives() -> dict:
    return {"primitives": list(PRIMITIVE_IDS)}


@router.get("/ict/symbols")
def list_ict_symbols() -> dict:
    """symbols: data/intraday에 실제 적재된 심볼+타임프레임.
    live_symbols: 캐시 없어도 HL API로 즉시 전체 tf 조회 가능한 크립토(LIQUID_PERPS)."""
    out: dict[str, list[str]] = {}
    for f in sorted(glob.glob(os.path.join(STORE_DIR, "*.parquet"))):
        m = _FILE_RE.match(os.path.basename(f))
        if m:
            out.setdefault(m.group(1), []).append(m.group(2))
    return {"symbols": out, "live_symbols": list(LIQUID_PERPS)}


def _load_filtered(symbol: str, timeframe: str, start: str | None, end: str | None) -> dict:
    df = _load_or_synthesize(symbol, timeframe)
    if start:
        start_ts = int(dt.datetime.combine(dt.date.fromisoformat(start), dt.time.min, tzinfo=dt.timezone.utc).timestamp())
        df = df[df["ts_utc"] >= start_ts]
    if end:
        end_ts = int(dt.datetime.combine(dt.date.fromisoformat(end), dt.time.min, tzinfo=dt.timezone.utc).timestamp()) + 86400
        df = df[df["ts_utc"] < end_ts]
    if len(df) < 50:
        raise HTTPException(
            status_code=400,
            detail=f"봉 부족(n={len(df)}) — {symbol}/{timeframe} 데이터 없음. "
                   f"1m/5m은 주식·ETF는 미지원(크립토만 라이브조회 가능)",
        )
    return {
        "ts": df["ts_utc"].astype("int64").tolist(),
        "o": df["open"].astype(float).tolist(),
        "h": df["high"].astype(float).tolist(),
        "l": df["low"].astype(float).tolist(),
        "c": df["close"].astype(float).tolist(),
    }


@router.post("/ict/backtest", response_model=IctBacktestResponse)
def run_ict_backtest(req: IctBacktestRequest) -> IctBacktestResponse:
    bad = [p for p in req.primitives if p not in PRIMITIVE_IDS]
    if bad:
        raise HTTPException(status_code=400, detail=f"미지원 프리미티브: {bad}")
    if not req.primitives:
        raise HTTPException(status_code=400, detail="프리미티브 최소 1개 선택")
    if req.direction not in ("bullish", "bearish"):
        raise HTTPException(status_code=400, detail="direction은 bullish|bearish")

    bars_dict = _load_filtered(req.symbol, req.timeframe, req.start, req.end)

    res = evaluate_combo(
        bars_dict, req.primitives, direction=req.direction, hold=req.hold,
        cost_bps=req.cost_bps, lookback=req.lookback, swing_k=req.swing_k,
        kz=(req.kz_start_hour, req.kz_end_hour),
        window=req.window, near=req.near, min_run=req.min_run, confirm=req.confirm,
    )
    if res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])

    entries_ts = [bars_dict["ts"][i] for i in res.get("entries_idx", [])]
    return IctBacktestResponse(
        n_entries=res["n_entries"], n_eligible=res.get("n_eligible"),
        net=res.get("net"), percentile=res.get("percentile"), p=res.get("p"),
        rand_median=res.get("rand_median"), wf_first=res.get("wf_first"), wf_second=res.get("wf_second"),
        entries_ts=entries_ts, verdict=res.get("verdict"),
    )


@router.post("/ict/events", response_model=IctEventsResponse)
def get_ict_events(req: IctBacktestRequest) -> IctEventsResponse:
    """차트 오버레이용 원본 프리미티브 이벤트/존(AND결합 전, 개별 노출) + 원본 봉."""
    bad = [p for p in req.primitives if p not in PRIMITIVE_IDS]
    if bad:
        raise HTTPException(status_code=400, detail=f"미지원 프리미티브: {bad}")
    if not req.primitives:
        raise HTTPException(status_code=400, detail="프리미티브 최소 1개 선택")
    if req.direction not in ("bullish", "bearish"):
        raise HTTPException(status_code=400, detail="direction은 bullish|bearish")

    bars_dict = _load_filtered(req.symbol, req.timeframe, req.start, req.end)

    events = detect_events(
        bars_dict, req.primitives, direction=req.direction,
        lookback=req.lookback, swing_k=req.swing_k,
        kz=(req.kz_start_hour, req.kz_end_hour),
        window=req.window, near=req.near, min_run=req.min_run, confirm=req.confirm,
    )

    bars = [
        IctBar(ts=t, o=o, h=h, l=l, c=c)
        for t, o, h, l, c in zip(bars_dict["ts"], bars_dict["o"], bars_dict["h"], bars_dict["l"], bars_dict["c"])
    ]
    return IctEventsResponse(bars=bars, events=events)
