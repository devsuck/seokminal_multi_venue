"""알파 검증 리포트 생성 — markdown + json."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

REPORT_DIR = os.path.join(os.path.dirname(__file__), "alpha")

# 하네스 드라이런 배너 — 일봉 결과를 알파 주장으로 오독 방지
HARNESS_BANNER = (
    "> ⚠️ **HARNESS VALIDATION, NOT ALPHA.** 이 결과는 검증 엔진 동작 확인용 "
    "드라이런입니다. 일봉 표본이며 인트라데이 알파 주장이 아닙니다."
)


def _verdict(strategy_pnl: float, pval: dict, wf: dict, underpowered: bool) -> str:
    p = pval.get("percentile")
    if underpowered:
        return "UNDERPOWERED — 거래 수 부족, 판정 보류"
    if p is None:
        return "NO DATA"
    # 2026-07-17 버그 수정: percentile만 보고 EDGE CANDIDATE 판정하면 순손실
    # 전략도(랜덤보다만 덜 나쁘면) 통과해버림 — net PnL 부호를 반드시 같이 봄.
    if p >= 95:
        if strategy_pnl is not None and strategy_pnl <= 0:
            return "SIGNAL-BUT-SUBCOST — 방향예측력 유의하나 net PnL<=0(비용이 갉아먹음), 거래대상 아님"
        return "EDGE CANDIDATE — 랜덤 95퍼센타일 초과 · net PnL>0"
    if p >= 70:
        return "WEAK — 랜덤 상위권이나 유의 미달"
    if p >= 50:
        return "INDISTINGUISHABLE — 랜덤과 구분 불가"
    return "REJECT — 랜덤 이하"


def build_report(
    name: str,
    hypothesis: str,
    universe: list[str],
    timeframe: str,
    cost: dict,
    strategy: dict,
    random_pval: dict,
    naive: dict,
    walk_forward_result: dict,
    is_harness_dryrun: bool = True,
    extra: dict | None = None,
) -> dict:
    """리포트 dict 조립 + markdown/json 파일 기록. 반환: {json_path, md_path, verdict}."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    underpowered = bool(strategy.get("underpowered"))
    verdict = _verdict(strategy.get("total_pnl", 0.0), random_pval, walk_forward_result, underpowered)

    payload = {
        "name": name,
        "hypothesis": hypothesis,
        "universe": universe,
        "timeframe": timeframe,
        "generated_at": ts,
        "is_harness_dryrun": is_harness_dryrun,
        "cost": cost,
        "strategy": strategy,
        "baseline_random": random_pval,
        "baseline_naive": naive,
        "walk_forward": walk_forward_result.get("summary"),
        "verdict": verdict,
    }
    if extra:
        payload["extra"] = extra

    os.makedirs(REPORT_DIR, exist_ok=True)
    safe = name.replace(" ", "_").replace("/", "_")
    json_path = os.path.join(REPORT_DIR, f"{safe}.json")
    md_path = os.path.join(REPORT_DIR, f"{safe}.md")

    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    md = _to_markdown(payload)
    with open(md_path, "w") as f:
        f.write(md)

    return {"json_path": json_path, "md_path": md_path, "verdict": verdict}


def _to_markdown(p: dict) -> str:
    s = p["strategy"]
    r = p["baseline_random"]
    wf = p["walk_forward"] or {}
    lines = [
        f"# Alpha Report — {p['name']}",
        "",
    ]
    if p.get("is_harness_dryrun"):
        lines += [HARNESS_BANNER, ""]
    lines += [
        f"**가설:** {p['hypothesis']}",
        f"**유니버스:** {', '.join(p['universe'])}  |  **타임프레임:** {p['timeframe']}",
        f"**생성:** {p['generated_at']}",
        "",
        f"## 판정: {p['verdict']}",
        "",
        "## 전략 성과 (비용 후)",
        f"- 거래수: {s['num_trades']}  {'⚠️ UNDERPOWERED' if s.get('underpowered') else ''}",
        f"- total PnL: {s['total_pnl']}  |  expectancy: {s['expectancy']}",
        f"- win rate: {s['win_rate']}  |  profit factor: {s.get('profit_factor')}",
        f"- per-trade Sharpe: {s.get('per_trade_sharpe')}  |  MDD: {s.get('max_drawdown')}",
        "",
        "## vs Random (same-frequency 분포)",
        f"- random runs: {r.get('n_random')}",
        f"- **percentile: {r.get('percentile')}**  |  empirical p-value: {r.get('p_value')}",
        f"- random median PnL: {r.get('random_median')}  |  이긴 랜덤 수: {r.get('random_beating')}",
        "",
        "## vs Naive (buy & hold)",
        f"- naive total PnL: {p['baseline_naive'].get('total_pnl')}",
        "",
        "## Walk-Forward",
        f"- windows: {wf.get('n_windows')}  |  consistency(양수 윈도우 비율): {wf.get('consistency')}",
        f"- avg total PnL: {wf.get('avg_total_pnl')}  |  avg expectancy: {wf.get('avg_expectancy')}",
        "",
        "## 비용 가정",
        f"- cost_bps: {p['cost'].get('cost_bps')} | slippage_bps: {p['cost'].get('slippage_bps')} | "
        f"spread_bps: {p['cost'].get('spread_bps')} | effective/체결: {p['cost'].get('effective_bps')}",
        "",
    ]
    return "\n".join(lines)
