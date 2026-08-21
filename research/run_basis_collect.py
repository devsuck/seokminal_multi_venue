"""Basis(현물-무기한선물 스프레드) 스냅샷 수집기 — 주기 실행 전제(cron/launchd, 여기선 미등록).

perp_px = HL markPx(metaAndAssetCtxs). spot_px = Binance spot REST ticker.
코인 범위 = `orderflow/binance_adapter.py`의 BINANCE_SYMBOL_MAP(현재 BTC/ETH/SOL만 —
바이낸스 spot 매핑이 그만큼만 있음, HL 전체 유니버스로 확장하려면 그 맵부터 늘려야함).

CLI: PYTHONPATH=. python3 research/run_basis_collect.py [--coins BTC ETH]
"""
from __future__ import annotations

import argparse
import time

import requests

from hyperliquid.client import get_meta_and_ctxs
from orderflow.binance_adapter import BINANCE_SYMBOL_MAP
from research.data.basis_store import save_basis

BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"


def _spot_px(coin: str) -> float:
    pair = BINANCE_SYMBOL_MAP[coin].upper()
    resp = requests.get(BINANCE_TICKER_URL, params={"symbol": pair}, timeout=10)
    resp.raise_for_status()
    return float(resp.json()["price"])


def collect(coins: list[str] | None, now: int | None = None) -> dict:
    now = now if now is not None else int(time.time())
    wanted = coins or list(BINANCE_SYMBOL_MAP)
    universe, ctxs = get_meta_and_ctxs()
    perp_px = {u["name"]: float(c["markPx"]) for u, c in zip(universe, ctxs)}

    saved: dict[str, int] = {}
    for coin in wanted:
        if coin not in BINANCE_SYMBOL_MAP or coin not in perp_px:
            continue
        spot = _spot_px(coin)
        perp = perp_px[coin]
        row = {"ts": now, "spot_px": spot, "perp_px": perp, "basis_bps": (perp - spot) / spot * 10000}
        saved[coin] = save_basis(coin, [row])
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
