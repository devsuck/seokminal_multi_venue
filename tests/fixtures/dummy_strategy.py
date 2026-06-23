from nautilus_trader.trading.strategy import Strategy


class DummyStrategy(Strategy):
    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.kwargs = kwargs


class NotAStrategy:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
