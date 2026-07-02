"""순수 워크포워드 러너. bars를 N 윈도우로 나눠 각 윈도우에서 signal_fn 실행 →
윈도우별 거래기반 지표. train/test 분리는 signal_fn 내부 책임(예: xgb train_ratio),
룰 전략은 윈도우 자체가 독립 OOS 조각."""
from __future__ import annotations

import statistics as _st
from typing import Callable

from research.validation.engine import simulate_long_short
from research.validation.metrics import trade_metrics


def walk_forward(
    closes: list[float],
    signal_fn: Callable[[list[float]], list[str]],
    n_windows: int = 5,
    trade_size: float = 10.0,
    cost_bps: float = 0.0,
) -> dict:
    """반환: {"windows": [지표...], "summary": {avg_expectancy, avg_pnl, consistency}}.
    consistency = 총 PnL 양수인 윈도우 비율."""
    n = len(closes)
    if n < n_windows * 5:
        raise ValueError(f"need >= {n_windows * 5} bars, got {n}")

    wsize = n // n_windows
    windows: list[dict] = []
    for i in range(n_windows):
        s = i * wsize
        e = s + wsize if i < n_windows - 1 else n
        seg = closes[s:e]
        if len(seg) < 5:
            continue
        sigs = signal_fn(seg)
        trades = simulate_long_short(seg, sigs, trade_size, cost_bps)
        m = trade_metrics(trades)
        m["window"] = i
        windows.append(m)

    pnls = [w["total_pnl"] for w in windows]
    exps = [w["expectancy"] for w in windows]
    positive = sum(1 for p in pnls if p > 0)
    summary = {
        "n_windows": len(windows),
        "avg_total_pnl": round(_st.mean(pnls), 6) if pnls else None,
        "avg_expectancy": round(_st.mean(exps), 6) if exps else None,
        "consistency": round(positive / len(windows), 4) if windows else None,
        "positive_windows": positive,
    }
    return {"windows": windows, "summary": summary}
