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
    venues: list[str] = []
    # 거래소별 원장(풀링 전) — 프론트 3분할 래더(BIN/OKX/HL 개별 컬럼)용. 위 bids/asks는 여전히
    # tick_size로 반올림해 합산한 풀 뷰(기존 클라 호환), 이건 그 옆에 병행 제공하는 raw 뷰.
    by_venue: dict[str, dict[str, list[OrderBookLevel]]] = {}


class TradeEvent(BaseModel):
    symbol: str
    ts: float
    price: float
    size: float
    side: Literal["buy", "sell"]


class LiquidationEvent(BaseModel):
    """실제 강제청산 체결 이벤트 — OI/funding 기반 estimateLiquidationLevels(추정)와 다른 개념.
    현재 유일한 소스는 Binance 선물 forceOrder 퍼블릭 스트림(HL은 청산 이벤트 퍼블릭 피드 없음).
    타 거래소 데이터라 참고용이며 HL 자체 청산이 아님 — 프론트에서 반드시 출처 라벨과 함께 노출."""

    symbol: str
    ts: float
    price: float
    size: float
    side: Literal["long", "short"]  # 청산된 포지션 방향(강제매도=롱 청산, 강제매수=숏 청산)


class FootprintCell(BaseModel):
    bucket_ts: float
    price: float
    buy_vol: float
    sell_vol: float


class HeatmapCell(BaseModel):
    ts: float
    price: float
    size: float
