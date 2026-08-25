"""일일 성과 요약 텔레그램 알림 — 오늘 체결 있는 에이전트만, launchd가 하루 1회 실행.

Usage: python -m api_server.daily_summary
"""
from __future__ import annotations

import datetime as dt

from api_server import agent_perf, agent_store
from api_server.lv6_notify import notify_daily_summary


def _today_cycles(agent_id: str, today: str) -> list[dict]:
    return [c for c in agent_store.read_cycles(agent_id, limit=100000)
            if str(c.get("ts", "")).startswith(today)]


def run(today: str | None = None) -> int:
    """오늘 체결 있는 에이전트만 알림 발송. 반환값 = 발송 건수."""
    today = today or dt.datetime.now(dt.UTC).date().isoformat()
    sent = 0
    for a in agent_store.list_agents():
        cycles = _today_cycles(a["id"], today)
        # ponytail: today-slice라 어제 이전 진입분과 매칭되는 청산은 realized_pnl 누락 가능
        # (FIFO lot이 슬라이스 밖). 정확한 누적 회계는 /agents/overview/all — 이 알림은
        # "오늘 체결 있었다" digest 목적이라 근사치로 충분.
        perf = agent_perf.compute_performance(cycles)
        if not perf.trades:
            continue
        closed = [t for t in perf.trades if t.get("realized_pnl") is not None]
        win_rate = (sum(1 for t in closed if t["realized_pnl"] > 0) / len(closed)) if closed else None
        notify_daily_summary(
            agent_id=a["id"], venue=a.get("market", "?"), n_trades=len(perf.trades),
            win_rate=win_rate, pnl_usd=perf.realized_pnl if closed else None,
            paper=bool(a.get("paper", True)),
        )
        sent += 1
    return sent


if __name__ == "__main__":
    n = run()
    print(f"daily_summary: {n}개 에이전트 알림 발송")
