# place_test_order.py
import datetime as dt
import os

from dotenv import load_dotenv

from backends.kis.client import KISClient
from backends.kis.order_client import KISOrderClient

# KRX tick sizes (호가단위) by price range, ascending. A limit price must be
# a multiple of the tick size for its range, or KIS rejects the order
# (KIS error: "모의투자 주문처리가 안되었습니다(호가단위 오류)").
_KRX_TICK_SIZES = [
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
    (float("inf"), 1_000),
]


def _round_down_to_tick_size(price: int) -> int:
    for upper_bound, tick_size in _KRX_TICK_SIZES:
        if price < upper_bound:
            return (price // tick_size) * tick_size
    raise AssertionError("unreachable: last tick size range is unbounded")


def main() -> None:
    load_dotenv()

    code = "005930"
    quantity = 1
    app_key = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]
    # KIS issues a separate app key/secret specifically for mock trading
    # (모의투자) — the real-trading app key above is rejected by order
    # endpoints on the mock domain (KIS error EGW02007).
    mock_app_key = os.environ["KIS_MOCK_APP_KEY"]
    mock_app_secret = os.environ["KIS_MOCK_APP_SECRET"]
    # Mock trading also requires its own account number — KIS rejects the
    # real account's CANO on the mock domain (KIS error IGW00002).
    mock_cano = os.environ["KIS_MOCK_CANO"]
    acnt_prdt_cd = os.environ["KIS_ACNT_PRDT_CD"]

    # Quotation endpoints are the same on KIS's real domain regardless of
    # whether orders go to the mock-trading domain, so KISClient keeps its
    # default base_url here.
    price_client = KISClient(app_key=app_key, app_secret=app_secret)
    today = dt.date.today()
    start = (today - dt.timedelta(days=10)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    rows = price_client.get_daily_price(code, start, end)
    last_close = int(rows[-1]["stck_clpr"])
    limit_price = _round_down_to_tick_size(int(last_close * 0.9))
    print(f"last close: {last_close}, limit price (90%, tick-rounded): {limit_price}")

    order_client = KISOrderClient(
        app_key=mock_app_key, app_secret=mock_app_secret, cano=mock_cano, acnt_prdt_cd=acnt_prdt_cd
    )
    order_date = today.strftime("%Y%m%d")

    placed = order_client.place_order(
        code=code, side="BUY", quantity=quantity, order_division="LIMIT", price=limit_price
    )
    order_no = placed["order_id"]
    print("placed:", placed)

    # Known mock-trading limitation (confirmed live 2026-06-23): KIS's
    # inquire-daily-ccld endpoint returns no rows for this account regardless
    # of parameters tried, even though the order genuinely exists and cancels
    # successfully — so this is expected to print None both times below, not
    # a bug. Revisit when wiring up real execution, since real-account query
    # behavior is unverified and may differ.
    status = order_client.get_order_status(order_date=order_date, order_no=order_no)
    print("status after place:", status)

    cancelled = order_client.cancel_order(order_no=order_no, code=code, quantity=quantity)
    print("cancelled:", cancelled)

    status_after_cancel = order_client.get_order_status(order_date=order_date, order_no=order_no)
    print("status after cancel:", status_after_cancel)


if __name__ == "__main__":
    main()
