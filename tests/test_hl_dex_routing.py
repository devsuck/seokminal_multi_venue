"""Builder-DEX name parsing for HL multi-asset routing."""
from hyperliquid.trader import _dex_of, _perp_dexs


def test_dex_of_builder():
    assert _dex_of("xyz:TSLA") == "xyz"
    assert _dex_of("xyz:GOLD") == "xyz"


def test_dex_of_standard_crypto():
    assert _dex_of("BTC") == ""
    assert _dex_of("ETH") == ""


def test_perp_dexs_builder_vs_standard():
    assert _perp_dexs("xyz:TSLA") == ["xyz"]
    assert _perp_dexs("BTC") is None
