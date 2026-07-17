from api_server import fee_model


def test_fee_bps_defaults_to_zero_when_unset(monkeypatch):
    monkeypatch.delenv("PNL_FEE_BPS_KR", raising=False)
    assert fee_model.fee_bps("KR") == 0.0


def test_fee_bps_reads_venue_env_var(monkeypatch):
    monkeypatch.setenv("PNL_FEE_BPS_US", "3.5")
    assert fee_model.fee_bps("US") == 3.5


def test_fee_bps_unknown_venue_is_zero():
    assert fee_model.fee_bps("HL") == 0.0


def test_fee_bps_invalid_value_falls_back_to_zero(monkeypatch):
    monkeypatch.setenv("PNL_FEE_BPS_US_OPTIONS", "not-a-number")
    assert fee_model.fee_bps("US_OPTIONS") == 0.0
