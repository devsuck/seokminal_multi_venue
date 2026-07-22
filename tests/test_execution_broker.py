"""페이퍼 브로커 + 포지션 회계 + live 안전장치 유닛테스트."""
import pytest

from execution.broker import (
    Order, PaperBroker, Position, make_broker, register_live_adapter,
)


def _o(sym, side, qty, price, ts=1.0):
    return Order(venue="paper", symbol=sym, side=side, qty=qty, price=price, ts=ts)


# ── 포지션 회계 ──────────────────────────────────────────────────
def test_position_open_and_average():
    p = Position("X")
    assert p.apply(10, 100) == 0.0        # 신규 롱 10@100
    assert p.apply(10, 120) == 0.0        # 추가 10@120 → avg 110
    assert p.qty == 20 and p.avg_price == 110


def test_position_partial_close_realizes():
    p = Position("X")
    p.apply(10, 100)
    r = p.apply(-4, 130)                   # 4 청산 @130 → (130-100)*4=120
    assert r == 120 and p.qty == 6 and p.avg_price == 100


def test_position_full_close():
    p = Position("X")
    p.apply(10, 100)
    r = p.apply(-10, 90)                   # 전량 청산 → (90-100)*10=-100
    assert r == -100 and p.qty == 0 and p.avg_price == 0.0


def test_position_flip_through_zero():
    p = Position("X")
    p.apply(10, 100)
    r = p.apply(-15, 110)                  # 10청산(+100) + 5숏 신규@110
    assert r == 100 and p.qty == -5 and p.avg_price == 110


def test_position_short_side_realized_sign():
    p = Position("X")
    p.apply(-10, 100)                      # 숏 10@100
    r = p.apply(5, 90)                     # 5 커버 @90 → 숏이익 (100-90)*5=50
    assert r == 50 and p.qty == -5


# ── 페이퍼 브로커 ─────────────────────────────────────────────────
def test_paper_broker_fills_and_tracks(tmp_path):
    b = PaperBroker(journal_dir=tmp_path)
    res = b.place(_o("BTC", "buy", 2, 50000))
    assert res.accepted and res.status == "filled" and res.fill_price == 50000
    b.place(_o("BTC", "sell", 1, 55000))
    assert b.realized_pnl == 5000          # (55000-50000)*1
    assert b.positions()["BTC"].qty == 1


def test_paper_broker_rejects_bad_order(tmp_path):
    b = PaperBroker(journal_dir=tmp_path, persist=False)
    assert not b.place(_o("X", "buy", 0, 100)).accepted
    assert not b.place(_o("X", "hodl", 1, 100)).accepted


def test_paper_broker_writes_journal(tmp_path):
    b = PaperBroker(journal_dir=tmp_path)
    b.place(_o("ETH", "buy", 1, 3000))
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1 and "ETH" in files[0].read_text()


# ── live 안전장치 ─────────────────────────────────────────────────
def test_make_broker_paper_default():
    assert isinstance(make_broker(), PaperBroker)
    assert isinstance(make_broker("hl", "paper"), PaperBroker)


def test_make_broker_live_without_adapter_raises():
    with pytest.raises(NotImplementedError):
        make_broker("hl", "live")          # 어댑터 미등록 → 실주문 경로 없음


def test_make_broker_live_with_registered_adapter():
    register_live_adapter("dummy", lambda: PaperBroker(persist=False))
    assert isinstance(make_broker("dummy", "live"), PaperBroker)


def test_make_broker_unknown_mode():
    with pytest.raises(ValueError):
        make_broker("paper", "bogus")
