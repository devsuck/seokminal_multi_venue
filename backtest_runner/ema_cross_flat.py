from decimal import Decimal

from nautilus_trader.examples.strategies.ema_cross import EMACross, EMACrossConfig
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId


class EMACrossFlat(EMACross):
    def __init__(self, **kwargs) -> None:
        config = EMACrossConfig(
            instrument_id=InstrumentId.from_str(kwargs["instrument_id"]),
            bar_type=BarType.from_str(kwargs["bar_type"]),
            trade_size=Decimal(str(kwargs["trade_size"])),
            fast_ema_period=kwargs.get("fast_ema_period", 10),
            slow_ema_period=kwargs.get("slow_ema_period", 20),
            request_bars=kwargs.get("request_bars", False),
            subscribe_trade_ticks=kwargs.get("subscribe_trade_ticks", False),
        )
        super().__init__(config)
