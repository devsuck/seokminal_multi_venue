"""HL OI(Open Interest) 스냅샷 수집기 — 주기 실행 전제(cron/launchd, 여기선 미등록).

HL은 OI 히스토리 백필 API가 없다(funding과 다름) — 이 스크립트를 주기적으로 돌려야만
`research/data/oi_store.py`에 시계열이 쌓인다. 1회 실행 = 현재 시점 스냅샷 1행/코인.

CLI: PYTHONPATH=. python3 research/run_oi_collect.py [--coins BTC ETH ...]
"""
from __future__ import annotations

import argparse
import time

from hyperliquid.client import get_meta_and_ctxs
from research.data.hl_funding_loader import LIQUID_PERPS
from research.data.oi_store import save_oi


def collect(coins: list[str] | None, now: int | None = None) -> dict:
    now = now if now is not None else int(time.time())
    universe, ctxs = get_meta_and_ctxs()
    names = [u["name"] for u in universe]
    wanted = set(coins) if coins else set(LIQUID_PERPS)
    saved: dict[str, int] = {}
    for name, ctx in zip(names, ctxs):
        if name not in wanted:
            continue
        row = {"ts": now, "open_interest": float(ctx["openInterest"]), "mark_px": float(ctx["markPx"])}
        saved[name] = save_oi(name, [row])
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coins", nargs="*")
    args = ap.parse_args()
    saved = collect(args.coins)
    for coin, total in saved.items():
        print(f"[{coin}] total={total}")


if __name__ == "__main__":
    main()
