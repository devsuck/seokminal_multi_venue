# place_test_order_ib.py
import asyncio

from backends.ib.order_client import IBOrderClient

SYMBOL = "AAPL"
QUANTITY = 1
LIMIT_PRICE = 50.0  # well below any plausible AAPL price, won't fill immediately


async def run() -> None:
    client = IBOrderClient()

    placed = await client.place_order(
        symbol=SYMBOL, side="BUY", quantity=QUANTITY, order_type="LIMIT", limit_price=LIMIT_PRICE
    )
    print("placed:", placed)
    order_id = placed["order_id"]

    await asyncio.sleep(1)
    status = await client.get_order_status(order_id)
    print("status after place:", status)

    cancelled = await client.cancel_order(order_id)
    print("cancelled:", cancelled)

    await asyncio.sleep(1)
    status_after_cancel = await client.get_order_status(order_id)
    print("status after cancel:", status_after_cancel)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
