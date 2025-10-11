import aiohttp
import pandas as pd
from typing import List
from logger import logger
from dataclasses import dataclass

@dataclass
class Kline:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int

class DataProvider:
    BINANCE_KLINES = "https://api.binance.com/api/v3/klines"

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_klines(self, symbol="BTCUSDT", interval="1m", limit=500) -> List[Kline]:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        async with self.session.get(self.BINANCE_KLINES, params=params, timeout=10) as resp:
            resp.raise_for_status()
            data = await resp.json()
        klines = [Kline(
            open_time=int(item[0]),
            open=float(item[1]),
            high=float(item[2]),
            low=float(item[3]),
            close=float(item[4]),
            volume=float(item[5]),
            close_time=int(item[6]),
        ) for item in data]
        logger.info("Получено %d свечей для %s %s", len(klines), symbol, interval)
        return klines

    @staticmethod
    def klines_to_dataframe(klines: List[Kline]) -> pd.DataFrame:
        if not klines:
            return pd.DataFrame()
        df = pd.DataFrame([{
            "open_time": pd.to_datetime(k.open_time, unit="ms"),
            "open": k.open,
            "high": k.high,
            "low": k.low,
            "close": k.close,
            "volume": k.volume,
        } for k in klines]).set_index("open_time")
        return df
