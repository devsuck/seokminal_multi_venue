# place_test_order.py
import datetime as dt
import os

from dotenv import load_dotenv

from backends.kis.client import KISClient
from backends.kis.order_client import KISOrderClient


def main() -> None:
    load_dotenv()

    code = "005930"
    quantity = 1
    app_key = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]
    cano = os.environ["KIS_CANO"]
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
    limit_price = int(last_close * 0.9)
    print(f"last close: {last_close}, limit price (90%): {limit_price}")

    order_client = KISOrderClient(
        app_key=app_key, app_secret=app_secret, cano=cano, acnt_prdt_cd=acnt_prdt_cd
    )
    order_date = today.strftime("%Y%m%d")

    placed = order_client.place_order(
        code=code, side="BUY", quantity=quantity, order_division="LIMIT", price=limit_price
    )
    order_no = placed["output"]["ODNO"]
    print("placed:", placed)

    status = order_client.get_order_status(order_date=order_date, order_no=order_no)
    print("status after place:", status)

    cancelled = order_client.cancel_order(
        order_date=order_date, order_no=order_no, code=code, quantity=quantity
    )
    print("cancelled:", cancelled)

    status_after_cancel = order_client.get_order_status(order_date=order_date, order_no=order_no)
    print("status after cancel:", status_after_cancel)


if __name__ == "__main__":
    main()
