import aiohttp
import pandas as pd
from typing import List
from logger import logger
from dataclasses import dataclass
import time

# Таймаут для API запросов (30 секунд)
API_TIMEOUT = aiohttp.ClientTimeout(total=30)

@dataclass
class Kline:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int  # Bybit не возвращает напрямую, можно вычислить при необходимости


class DataProvider:
    BYBIT_KLINES = "https://api.bybit.com/v5/market/kline"

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_klines(self, symbol="BTCUSDT", interval="1m", limit=200, category=None):
        """
        Получение исторических свечей с Bybit API.
        Если категория не указана, автоматически пробует spot и linear.
        """

        interval_map = {
            "1m": "1", "3m": "3", "5m": "5", "15m": "15",
            "30m": "30", "1h": "60", "2h": "120", "4h": "240",
            "6h": "360", "12h": "720", "1d": "D", "1w": "W", "1M": "M"
        }

        interval = interval_map.get(interval, interval)
        categories = [category] if category else ["spot", "linear"]
        last_error = None

        # временные рамки (Bybit требует start/end для корректного возврата)
        now = int(time.time() * 1000)
        try:
            interval_minutes = int(interval)
        except ValueError:
            # Для дневных/недельных/месячных интервалов
            if interval == 'D':
                interval_minutes = 1440  # 24 часа
            elif interval == 'W':
                interval_minutes = 10080  # 7 дней
            elif interval == 'M':
                interval_minutes = 43200  # ~30 дней
            else:
                interval_minutes = 15  # fallback
        start_time = now - limit * interval_minutes * 60 * 1000

        for cat in categories:
            params = {
                "category": cat,
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "start": start_time,
                "end": now
            }

            async with self.session.get(self.BYBIT_KLINES, params=params, timeout=API_TIMEOUT) as resp:
                data = await resp.json()

            if data.get("retCode") != 0:
                last_error = data.get("retMsg", "Unknown error")
                logger.warning(f"Bybit API error for {symbol} ({cat}): {last_error}")
                continue

            result = data.get("result", {})
            if not result.get("list"):
                last_error = f"No 'list' in response for {symbol} ({cat})"
                logger.warning(last_error)
                continue

            klines = result["list"]
            df = pd.DataFrame(klines, columns=["open_time", "open", "high", "low", "close", "volume", "turnover"])
            
            # Валидация данных
            if df.empty:
                last_error = f"Empty dataframe for {symbol} ({cat})"
                logger.warning(last_error)
                continue
            
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            
            # Проверка на NaN после конвертации
            if df[["open", "high", "low", "close", "volume"]].isna().any().any():
                logger.warning(f"NaN values in {symbol} ({cat}), filling...")
                df.ffill(inplace=True)
                df.bfill(inplace=True)
            
            # Проверка на отрицательные значения
            if (df[["open", "high", "low", "close", "volume"]] < 0).any().any():
                last_error = f"Invalid negative values in data for {symbol} ({cat})"
                logger.warning(last_error)
                continue
            
            df["open_time"] = pd.to_datetime(pd.to_numeric(df["open_time"]), unit="ms")
            df = df.sort_values("open_time").reset_index(drop=True)
            df.set_index("open_time", inplace=True)
            df = df.astype(float)
            return df

        raise ValueError(f"Не удалось получить данные для {symbol}: {last_error}")

    @staticmethod
    def klines_to_dataframe(klines) -> pd.DataFrame:
        # Если уже DataFrame, просто возвращаем
        if isinstance(klines, pd.DataFrame):
            return klines

        # Если список Kline
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
