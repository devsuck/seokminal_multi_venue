"""TSMOM 어댑터 — 전략 자신의 point-in-time 신호함수를 호출해 번역.

전략 로직 무수정: `research.hypotheses.tsmom.tsmom_weights(panels, date, params)`를
그대로 호출한다. 그 함수는 `_asset_ctx`에서 date 이하 데이터만 쓰고 date 정확일치를
요구하므로 **구조적으로 no-lookahead**. 어댑터는 as_of를 date로 넘기고 부호/크기를
StrategySignal로 번역만 한다(재구현 아님).

weight_fn/panel_loader 주입 가능(테스트/의존성 분리). 데이터 없으면 빈 신호(정직).
"""
from __future__ import annotations

from typing import Callable

from jarvis.fusion.adapters.base import as_date
from jarvis.fusion.types import StrategySignal

_CAP_DEFAULT = 3.0


class TsmomAdapter:
    def __init__(self, strategy_id: str, symbols: list[str] | None = None,
                 params: dict | None = None,
                 panel_loader: Callable[[str], dict] | None = None,
                 weights_fn: Callable | None = None) -> None:
        self.strategy_id = strategy_id
        self._symbols = symbols
        self.params = params or {}
        self._loader = panel_loader
        self._weights_fn = weights_fn

    def _resolve_symbols(self) -> list[str]:
        if self._symbols is not None:
            return self._symbols
        try:  # 실환경: 선물 유니버스. 데이터 없으면 아래 loader가 빈 패널.
            from research.data.futures_loader import ASSET_CLASS
            return sorted(ASSET_CLASS.keys())
        except Exception:  # noqa: BLE001
            return []

    def _load_panels(self, symbols: list[str]) -> dict:
        loader = self._loader
        if loader is None:
            from research.hypotheses.tsmom import build_panel as loader  # lazy
        panels = {}
        for s in symbols:
            try:
                pn = loader(s)
            except Exception:  # noqa: BLE001
                continue
            if pn and pn.get("dates"):
                panels[s] = pn
        return panels

    def signals(self, as_of: str = "") -> list[StrategySignal]:
        d = as_date(as_of)
        if d is None:
            return []
        panels = self._load_panels(self._resolve_symbols())
        if not panels:
            return []  # 데이터 미배선 = 정직한 빈 신호(블로커)
        wf = self._weights_fn
        if wf is None:
            from research.hypotheses.tsmom import tsmom_weights as wf  # lazy
        weights = wf(panels, d, self.params)
        cap = float(self.params.get("cap", _CAP_DEFAULT))
        out = []
        for a, w in sorted(weights.items()):
            if w == 0:
                continue
            out.append(StrategySignal(
                strategy_id=self.strategy_id, instrument=a,
                direction=1 if w > 0 else -1, strength=min(1.0, abs(w) / cap),
                as_of=as_of, source="tsmom_weights", meta={"weight": round(w, 6)}))
        return out
