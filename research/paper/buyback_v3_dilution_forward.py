"""buyback v3(CB/BW 희석 리스크필터) forward 모니터 — in-sample vs forward(OOS) 분리.

v3 = 이벤트 이전 LOOKBACK일 내 같은 종목 CB/BW(전환사채) 발행공시가 있으면 제외.
근거: run_cb_issuance_pit.py에서 CB/BW 발행 자체가 공시후 하위5% 음의 드리프트로 확인됨(2026-07초 검증) —
buyback 매수신호 종목이 최근 희석발행까지 겹치면 리스크 오버행으로 buyback 엣지가 훼손될 가능성.
v1 동결(buyback_forward.py), v3은 shadow. 등록일(FROZEN_DATE) 이후 이벤트만 forward(OOS).
실행: PYTHONPATH=. python3 research/paper/buyback_v3_dilution_forward.py
"""
from __future__ import annotations

import bisect
import datetime as _dt
import glob
import os
import statistics as _st

FROZEN_DATE = "2026-08-25"   # v3 희석필터 사전등록일
HOLD = 20
COST = 40.0
LOOKBACK_DAYS = 90   # 이벤트 이전 며칠 내 CB/BW 발행이면 오버행으로 간주


def _series():
    from research.data.krx_api import build_series, market_dir
    s = build_series("KOSDAQ", min_bars=90)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=90))
    return s


def _fwd(b, ed):
    j = bisect.bisect_right(b["dates"], ed)
    if j >= len(b["dates"]):
        return None
    entry = b["open"][j]; xi = min(j + HOLD, len(b["dates"]) - 1)
    if entry <= 0 or xi <= j:
        return None
    return (b["close"][xi] / entry - 1) - COST / 10_000.0


def _cb_dates_by_stock(cb_events: list) -> dict:
    out: dict = {}
    for e in cb_events:
        out.setdefault(e["stock_code"], []).append(e["date"])
    for k in out:
        out[k].sort()
    return out


def _has_dilution_overhang(cb_dates: list, event_date: str) -> bool:
    """event_date 이전 LOOKBACK_DAYS일 내 CB/BW 발행공시 존재 여부."""
    if not cb_dates:
        return False
    j = bisect.bisect_right(cb_dates, event_date)
    if j == 0:
        return False
    last_cb = cb_dates[j - 1]
    ed = _dt.date.fromisoformat(event_date)
    cd = _dt.date.fromisoformat(last_cb)
    return (ed - cd).days <= LOOKBACK_DAYS


def _seg(rows, cb_by_stock):
    """세그먼트 요약: v1(전체)·v3(희석오버행 제외) net·승률·n."""
    v1 = [n for _, _, _, n in rows]
    v3 = [n for _, sc, ed, n in rows if not _has_dilution_overhang(cb_by_stock.get(sc, []), ed)]

    def wr(v):
        return round(sum(1 for x in v if x > 0) / len(v), 4) if v else None

    return {"n_v1": len(v1), "n_v3": len(v3),
            "v1_net": round(_st.mean(v1), 6) if v1 else None, "v3_net": round(_st.mean(v3), 6) if v3 else None,
            "v1_winrate": wr(v1), "v3_winrate": wr(v3),
            "v3_improves": (bool(v1 and v3 and _st.mean(v3) > _st.mean(v1) and (wr(v3) or 0) > (wr(v1) or 0)))}


def generate(write: bool = False) -> dict:
    from research.data.kr_dart_events import load_events
    series = _series()
    bb = load_events("buyback")
    cb = load_events("cb_issue")
    cb_by_stock = _cb_dates_by_stock(cb)

    rows = []  # (date, stock_code, event_date, net)
    for e in bb:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        net = _fwd(b, e["date"])
        if net is not None:
            rows.append((e["date"], e["stock_code"], e["date"], net))

    insample = [r for r in rows if r[0] < FROZEN_DATE]
    forward = [r for r in rows if r[0] >= FROZEN_DATE]

    result = {
        "hypothesis_id": "kr_buyback_v3_dilution_shadow", "status": "v3_shadow",
        "frozen_date": FROZEN_DATE, "lookback_days": LOOKBACK_DAYS,
        "rule": f"이벤트일 이전 {LOOKBACK_DAYS}일 내 같은 종목 CB/BW 발행공시 있으면 제외",
        "in_sample": _seg(insample, cb_by_stock),
        "forward": _seg(forward, cb_by_stock),
        "forward_note": ("forward 이벤트 0 — 등록 직후. 새 buyback 공시 쌓이면 채워짐."
                         if not forward else f"forward {len(forward)}건 누적 중"),
        "discipline": "v1 동결. forward가 in-sample 개선 재현해야 승격. 그 전 live/paper 금지.",
    }
    if write:
        import json
        p = os.path.join(os.path.dirname(__file__), "buyback_v3_dilution_forward_ledger.jsonl")
        with open(p, "a") as f:
            f.write(json.dumps({"in_sample": result["in_sample"], "forward": result["forward"]}, default=str) + "\n")
    return result


def main():
    import json
    print(json.dumps(generate(write=False), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
