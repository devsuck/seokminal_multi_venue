"""Per-venue fee/slippage assumption for realized-PnL display.

No broker in this codebase reports live commission (KIS/IB/Alpaca order
responses carry no fee field) — so this is not a broker-verified number, it's
an operator-supplied bps estimate applied symmetrically to both legs of a
matched trade. Defaults to 0 (no adjustment) unless configured. Callers must
label figures using this as "추정" (estimated), never as confirmed cost.
"""
from __future__ import annotations

import os

_ENV_KEY = {"KR": "PNL_FEE_BPS_KR", "US": "PNL_FEE_BPS_US", "US_OPTIONS": "PNL_FEE_BPS_US_OPTIONS"}


def fee_bps(venue: str) -> float:
    env_key = _ENV_KEY.get(venue)
    if env_key is None:
        return 0.0
    raw = os.environ.get(env_key)
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0
