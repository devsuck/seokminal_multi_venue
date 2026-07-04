"""검증된 buyback 엣지 ↔ 봇 페이퍼 연결. v1 동결 config로 실행(실주문 없음).

봇이 buyback 공시 감지 → v1 규칙(익일시가 진입·20일 보유·40bps) → 페이퍼 포지션 추적.
KRX 데이터로 진입/청산가 확정. open(보유중)/closed(실현) 원장. Jarvis가 live 차단 = 페이퍼만.
검증된 엣지만 실행 = 노이즈 매매 아님. v2 레짐필터는 shadow(여기선 v1 전체).
"""
from __future__ import annotations

import bisect
import glob
import json
import os
import time
from datetime import datetime, timezone

from jarvis.config import state_path

_LEDGER = "buyback_bot_positions.jsonl"
_cache = {"ts": 0.0, "series": None}


def _series():
    if _cache["series"] is not None and time.time() - _cache["ts"] < 3600:
        return _cache["series"]
    from research.data.krx_api import build_series, market_dir
    s = build_series("KOSDAQ", min_bars=25)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=25))
    _cache.update(ts=time.time(), series=s)
    return s


def _positions() -> dict:
    """{(stock,disclosure): position}."""
    p = state_path(_LEDGER)
    out = {}
    if os.path.exists(p):
        for ln in open(p):
            if ln.strip():
                d = json.loads(ln)
                out[(d["stock_code"], d["disclosure_date"])] = d
    return out


def _save(pos: dict) -> None:
    os.makedirs(os.path.dirname(state_path(_LEDGER)), exist_ok=True)
    with open(state_path(_LEDGER), "w") as f:
        for d in pos.values():
            f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")


def sync() -> dict:
    """buyback 이벤트 → 페이퍼 포지션 생성/갱신(v1 동결 config). 반환=요약."""
    from research.data.kr_dart_events import load_events
    from research.paper import buyback_config as CFG

    ev = load_events("buyback")
    series = _series()
    pos = _positions()
    opened = closed = 0
    for e in ev:
        sc, dd = e["stock_code"], e["date"]
        key = (sc, dd)
        b = series.get(sc)
        if b is None:
            continue
        j = bisect.bisect_right(b["dates"], dd)   # 익일(진입)
        if j >= len(b["dates"]):
            continue   # 아직 진입일 데이터 없음(대기)
        rec = pos.get(key)
        if rec is None:
            entry_px = b["open"][j]
            if entry_px <= 0:
                continue
            rec = {"stock_code": sc, "corp_name": e.get("corp_name", ""), "disclosure_date": dd,
                   "entry_date": b["dates"][j], "entry_price": entry_px, "hold_days": CFG.HOLD_DAYS,
                   "cost_bps": CFG.COST_BASE_BPS, "version": CFG.VERSION, "status": "open",
                   "exit_date": None, "exit_price": None, "pnl_pct": None, "capital": "paper"}
            pos[key] = rec; opened += 1
        if rec["status"] == "open":
            xi = j + CFG.HOLD_DAYS
            if xi < len(b["dates"]):   # 20일 경과 = 청산
                exit_px = b["close"][xi]
                rec["exit_date"] = b["dates"][xi]
                rec["exit_price"] = exit_px
                rec["pnl_pct"] = round(exit_px / rec["entry_price"] - 1 - CFG.COST_BASE_BPS / 1e4, 6)
                rec["status"] = "closed"; closed += 1
    _save(pos)
    return summary(pos)


def summary(pos: dict | None = None) -> dict:
    import statistics as _st
    from research.paper import buyback_config as CFG
    pos = pos if pos is not None else _positions()
    rows = list(pos.values())
    closed = [r for r in rows if r["status"] == "closed"]
    open_ = [r for r in rows if r["status"] == "open"]
    pnls = [r["pnl_pct"] for r in closed if r["pnl_pct"] is not None]
    recent = sorted(closed, key=lambda r: r["exit_date"] or "", reverse=True)[:10]
    return {
        "version": CFG.VERSION, "config": {"entry": CFG.ENTRY, "hold_days": CFG.HOLD_DAYS, "cost_bps": CFG.COST_BASE_BPS},
        "total": len(rows), "open": len(open_), "closed": len(closed),
        "paper_pnl_mean": round(_st.mean(pnls), 6) if pnls else None,
        "paper_win_rate": round(sum(1 for x in pnls if x > 0) / len(pnls), 4) if pnls else None,
        "cum_paper_pnl": round(sum(pnls), 6) if pnls else None,
        "open_positions": [{"corp": r["corp_name"], "code": r["stock_code"], "entry_date": r["entry_date"],
                            "entry_price": r["entry_price"]} for r in open_[:10]],
        "recent_closed": [{"corp": r["corp_name"], "entry_date": r["entry_date"], "exit_date": r["exit_date"],
                           "pnl_pct": r["pnl_pct"]} for r in recent],
        "execution": "paper_only", "live": "blocked (Jarvis)",
        "note": "검증된 v1 엣지 페이퍼 실행. 실주문 없음. paper→live는 사람.",
    }


if __name__ == "__main__":
    print(json.dumps(sync(), ensure_ascii=False, indent=2))
