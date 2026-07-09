"""오더플로우(풋프린트)/유동성 히트맵 파이프라인 공용 데이터 모델.
매매 실행 로직(live_engine 등)과 이 모듈 사이에 임포트 의존을 만들지 않는다."""
from typing import Literal

from pydantic import BaseModel


class OrderBookLevel(BaseModel):
    price: float
    size: float


class OrderBookSnapshot(BaseModel):
    symbol: str
    ts: float
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]


class TradeEvent(BaseModel):
    symbol: str
    ts: float
    price: float
    size: float
    side: Literal["buy", "sell"]


class FootprintCell(BaseModel):
    bucket_ts: float
    price: float
    buy_vol: float
    sell_vol: float


class HeatmapCell(BaseModel):
    ts: float
    price: float
    size: float
