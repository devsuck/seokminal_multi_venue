"""KR DART 컨버전스(dart_exec × dart_corp_action) 과거 백필 + forward-return 백테스트.

가설: insider/convergence.py의 score>=2(두 leg가 같은 종목·같은 방향으로 겹침)가
score==1(단일 leg)보다 forward return이 좋은가 — 통합 매매 판단 기능을 만들기 전에
먼저 확인해야 할 전제.

방법: _tag_kr_legs()를 실제 프로덕션과 동일한 주간(7일) 윈도우로 반복 호출해 최근 N개월
백필한다. get_recent_kr_insider_feed/get_recent_kr_corporate_actions의 page-cap(각각
max_corps=20, 3page/300row)을 건드리지 않음 — "라이브 로직이 실제로 보는 것"을 그대로
테스트하는 것이지, 이상적으로 완전한 히스토리를 새로 만드는 게 아니다.

forward return: D+1 시가 진입, 20거래일 종가 청산, 5bps 비용 — form4_forward.py와 동일
컨벤션. 방향성 조정 수익률 = BULLISH면 그대로, BEARISH면 부호 반전(컨버전스 신호를
"매수/회피" 판단에 쓴다고 가정했을 때 실현되는 엣지).

CLI: /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m research.data.kr_dart_convergence_backfill
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import os
import statistics as st
import time

from dotenv import load_dotenv
load_dotenv()

from insider.convergence import _tag_kr_legs

HOLD_DAYS = 20
COST_BPS = 5
STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "kr")
LEGS_PATH = os.path.join(STORE_DIR, "dart_convergence_backfill_legs.jsonl")
REPORT_PATH = os.path.join(STORE_DIR, "dart_convergence_backfill_report.json")


def backfill_legs(months: int = 6, window_days: int = 7, pace_s: float = 0.5) -> list[dict]:
    """dart_autobot이 실제로 쓰는 것과 같은 주간 윈도우를 today부터 거슬러 반복 호출."""
    today = dt.date.today()
    start = today - dt.timedelta(days=int(months * 30.5))
    legs: list[dict] = []
    cur = start
    n_windows = 0
    while cur < today:
        w_end = min(cur + dt.timedelta(days=window_days), today)
        bgn_de, end_de = cur.strftime("%Y%m%d"), w_end.strftime("%Y%m%d")
        try:
            window_legs = _tag_kr_legs(days=window_days, bgn_de=bgn_de, end_de=end_de)
        except Exception as e:
            print(f"  window {bgn_de}~{end_de} 실패: {e}")
            window_legs = []
        legs.extend(window_legs)
        n_windows += 1
        print(f"  [{n_windows}] {bgn_de}~{end_de}: {len(window_legs)} legs (누적 {len(legs)})")
        cur = w_end + dt.timedelta(days=1)
        time.sleep(pace_s)
    return legs


def save_legs(legs: list[dict]) -> str:
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(LEGS_PATH, "w") as f:
        for leg in legs:
            f.write(json.dumps(leg, ensure_ascii=False) + "\n")
    return LEGS_PATH


def load_legs() -> list[dict]:
    if not os.path.exists(LEGS_PATH):
        return []
    return [json.loads(ln) for ln in open(LEGS_PATH) if ln.strip()]


def group_by_ticker_direction(legs: list[dict]) -> list[dict]:
    """convergence.compute_convergence()와 동일한 그룹핑이지만 score==1도 유지(비교 대조군)."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for leg in legs:
        key = (leg["ticker"], leg["direction"])
        groups.setdefault(key, []).append(leg)
    out = []
    for (ticker, direction), group_legs in groups.items():
        score = len({leg["source"] for leg in group_legs})
        signal_date = min(leg["trade_date"] for leg in group_legs if leg.get("trade_date"))
        out.append({
            "ticker": ticker, "direction": direction, "score": score,
            "signal_date": signal_date.replace("-", ""), "n_legs": len(group_legs),
        })
    return out


def _forward_return(code: str, signal_date: str) -> float | None:
    """signal_date(YYYYMMDD) D+1 시가 진입 → 20거래일 후 종가 청산, 5bps 비용."""
    from research.data.kr_data import load_ohlcv
    d = dt.datetime.strptime(signal_date, "%Y%m%d").date()
    start = (d - dt.timedelta(days=5)).strftime("%Y-%m-%d")
    end = (d + dt.timedelta(days=HOLD_DAYS * 2 + 10)).strftime("%Y-%m-%d")
    try:
        df = load_ohlcv(code, start, end)
    except Exception:
        return None
    if df.empty:
        return None
    dates = [ts.strftime("%Y-%m-%d") for ts in df.index]
    j0 = bisect.bisect_right(dates, d.strftime("%Y-%m-%d")) - 1
    i = j0 + 1  # D+1
    if i >= len(dates):
        return None
    entry = float(df["Open"].iloc[i])
    xi = min(i + HOLD_DAYS, len(dates) - 1)
    if entry <= 0 or xi <= i or xi < i + HOLD_DAYS:
        return None
    exit_px = float(df["Close"].iloc[xi])
    return (exit_px / entry - 1) - COST_BPS / 10_000.0


def _stats(rows: list[dict]) -> dict:
    rs = [row["directional_return"] for row in rows]
    if not rs:
        return {"n": 0}
    return {
        "n": len(rs), "mean": round(st.mean(rs), 6), "median": round(st.median(rs), 6),
        "win_rate": round(sum(1 for x in rs if x > 0) / len(rs), 4),
    }


def backtest(groups: list[dict]) -> dict:
    rows = []
    for g in groups:
        r = _forward_return(g["ticker"], g["signal_date"])
        if r is None:
            continue
        directional_r = r if g["direction"] == "BULLISH" else -r
        rows.append({**g, "raw_return": round(r, 6), "directional_return": round(directional_r, 6)})

    single = [r for r in rows if r["score"] == 1]
    converged = [r for r in rows if r["score"] >= 2]
    return {
        "config": {"hold_days": HOLD_DAYS, "cost_bps": COST_BPS, "entry": "D+1_open", "exit": "close"},
        "single_source": _stats(single),
        "converged_2plus": _stats(converged),
        "rows_single": single,
        "rows_converged": converged,
    }


def run(months: int = 6, refresh: bool = True) -> dict:
    if refresh or not load_legs():
        print(f"백필 시작: 최근 {months}개월, 주간 윈도우...")
        legs = backfill_legs(months=months)
        save_legs(legs)
        print(f"leg 수집 완료: {len(legs)}건 → {LEGS_PATH}")
    else:
        legs = load_legs()
        print(f"기존 leg 캐시 사용: {len(legs)}건")

    groups = group_by_ticker_direction(legs)
    n_single = sum(1 for g in groups if g["score"] == 1)
    n_conv = sum(1 for g in groups if g["score"] >= 2)
    print(f"(ticker,direction) 그룹: {len(groups)}개 (score==1: {n_single}, score>=2: {n_conv})")

    result = backtest(groups)
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--no-refresh", action="store_true", help="기존 leg 캐시 재사용(재수집 안 함)")
    args = ap.parse_args()
    r = run(months=args.months, refresh=not args.no_refresh)
    print("\n=== 결과 ===")
    print(f"단일 소스(score==1): {r['single_source']}")
    print(f"컨버전스(score>=2):  {r['converged_2plus']}")
