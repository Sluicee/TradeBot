#!/usr/bin/env python3
# bot.py — асинхронный Telegram-бот для анализа криптовалют с командами управления отслеживаемыми парами.

import os
import time
import asyncio
import logging
from dataclasses import dataclass
from typing import List, Dict, Any

import json

import aiohttp
import pandas as pd
import numpy as np
import dotenv
import ta

from telegram import Update, __version__ as tg_version
from telegram.ext import Application, CommandHandler, ContextTypes

# -----------------------------
# Настройки и логирование
# -----------------------------
dotenv.load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "BTCUSDT")
DEFAULT_INTERVAL = os.getenv("DEFAULT_INTERVAL", "1m")


# --- Логирование в файл и консоль ---
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
def get_log_filename():
    return os.path.join(LOG_DIR, time.strftime("log_%Y%m%d_%H%M%S.txt"))


class TimedFileHandler(logging.FileHandler):
    def __init__(self, interval=8*60*60, *args, **kwargs):
        self.interval = interval
        self.start_time = time.time()
        self.baseFilename = get_log_filename()
        super().__init__(self.baseFilename, encoding="utf-8", *args, **kwargs)

    def emit(self, record):
        if time.time() - self.start_time > self.interval:
            self.start_time = time.time()
            self.baseFilename = get_log_filename()
            self.stream.close()
            self.stream = self._open()
        super().emit(record)

logger = logging.getLogger("crypto_signal_bot")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s — %(name)s — %(levelname)s — %(message)s")

# Консоль
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Файл с ротацией
file_handler = TimedFileHandler()
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# -----------------------------
# Модель свечи
# -----------------------------
@dataclass
class Kline:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int

# -----------------------------
# DataProvider
# -----------------------------
class DataProvider:
    BINANCE_KLINES = "https://api.binance.com/api/v3/klines"

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_klines(
        self, symbol: str = "BTCUSDT", interval: str = "1m", limit: int = 500
    ) -> List[Kline]:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        async with self.session.get(self.BINANCE_KLINES, params=params, timeout=10) as resp:
            resp.raise_for_status()
            data = await resp.json()
        klines = [
            Kline(
                open_time=int(item[0]),
                open=float(item[1]),
                high=float(item[2]),
                low=float(item[3]),
                close=float(item[4]),
                volume=float(item[5]),
                close_time=int(item[6]),
            )
            for item in data
        ]
        logger.info("Получено %d свечей для %s %s", len(klines), symbol, interval)
        return klines

    @staticmethod
    def klines_to_dataframe(klines: List[Kline]) -> pd.DataFrame:
        if not klines:
            return pd.DataFrame()
        df = pd.DataFrame(
            [
                {
                    "open_time": pd.to_datetime(k.open_time, unit="ms"),
                    "open": k.open,
                    "high": k.high,
                    "low": k.low,
                    "close": k.close,
                    "volume": k.volume,
                }
                for k in klines
            ]
        ).set_index("open_time")
        return df

# -----------------------------
# SignalGenerator
# -----------------------------
class SignalGenerator:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        if "close" not in self.df.columns:
            raise ValueError("DataFrame must contain 'close' column")
        self.df.sort_index(inplace=True)

    def compute_indicators(
        self, ema_short_window=12, ema_long_window=26, rsi_window=14,
        macd_fast=12, macd_slow=26, macd_signal=9
    ) -> pd.DataFrame:
        close = self.df["close"].astype(float)
        high = self.df["high"].astype(float)
        low = self.df["low"].astype(float)
        volume = self.df["volume"].astype(float)

        # Скользящие средние
        for w in [10, 20, 30, 50, 100, 200]:
            if len(self.df) >= w:
                self.df[f"SMA_{w}"] = ta.trend.sma_indicator(close, window=w)
                self.df[f"EMA_{w}"] = ta.trend.ema_indicator(close, window=w)
            else:
                self.df[f"SMA_{w}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
                self.df[f"EMA_{w}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)

        def hull_moving_average(series, window):
            if len(series) < window:
                return pd.Series([np.nan]*len(series), index=series.index)
            half_length = int(window / 2)
            sqrt_length = int(window ** 0.5)
            wma_half = series.rolling(half_length).mean()
            wma_full = series.rolling(window).mean()
            diff = 2 * wma_half - wma_full
            hma = diff.rolling(sqrt_length).mean()
            return hma
        self.df["HMA_9"] = hull_moving_average(close, 9)
        self.df["VWMA_20"] = ta.volume.volume_weighted_average_price(high, low, close, volume, window=20) if len(self.df) >= 20 else pd.Series([np.nan]*len(self.df), index=self.df.index)

        # Ишимоку
        if len(self.df) >= 52:
            ichimoku = ta.trend.IchimokuIndicator(high, low, window1=9, window2=26, window3=52, visual=False)
            self.df["Ichimoku_a"] = ichimoku.ichimoku_a()
            self.df["Ichimoku_b"] = ichimoku.ichimoku_b()
        else:
            self.df["Ichimoku_a"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
            self.df["Ichimoku_b"] = pd.Series([np.nan]*len(self.df), index=self.df.index)

        # Осцилляторы
            self.df["RSI_14"] = ta.momentum.rsi(close, window=14) if len(self.df) >= 14 else pd.Series([np.nan]*len(self.df), index=self.df.index)
            self.df["Stoch_K"] = ta.momentum.stoch(high, low, close, window=14, smooth_window=3) if len(self.df) >= 14 else pd.Series([np.nan]*len(self.df), index=self.df.index)
            self.df["Stoch_D"] = ta.momentum.stoch_signal(high, low, close, window=14, smooth_window=3) if len(self.df) >= 14 else pd.Series([np.nan]*len(self.df), index=self.df.index)
            self.df["CCI_20"] = ta.trend.cci(high, low, close, window=20) if len(self.df) >= 20 else pd.Series([np.nan]*len(self.df), index=self.df.index)
            # ADX с обработкой ошибок
            if (
                len(self.df) >= 14
                and len(self.df.tail(14)) == 14
                and self.df[["high", "low", "close"]].tail(14).isna().sum().sum() == 0
            ):
                try:
                    self.df["ADX_14"] = ta.trend.adx(high, low, close, window=14)
                except Exception:
                    self.df["ADX_14"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
            else:
                self.df["ADX_14"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
        self.df["Awesome"] = ta.momentum.awesome_oscillator(high, low, window1=5, window2=34) if len(self.df) >= 34 else pd.Series([np.nan]*len(self.df), index=self.df.index)
        self.df["Momentum_10"] = ta.momentum.roc(close, window=10) if len(self.df) >= 10 else pd.Series([np.nan]*len(self.df), index=self.df.index)
        self.df["MACD_level"] = ta.trend.macd(close, window_slow=26, window_fast=12) if len(self.df) >= 26 else pd.Series([np.nan]*len(self.df), index=self.df.index)
        self.df["Stoch_RSI"] = ta.momentum.stochrsi(close, window=14, smooth1=3, smooth2=3) if len(self.df) >= 14 else pd.Series([np.nan]*len(self.df), index=self.df.index)
        self.df["WilliamsR_14"] = ta.momentum.williams_r(high, low, close, lbp=14) if len(self.df) >= 14 else pd.Series([np.nan]*len(self.df), index=self.df.index)
        self.df["BullPower"] = high - ta.trend.sma_indicator(close, window=13) if len(self.df) >= 13 else pd.Series([np.nan]*len(self.df), index=self.df.index)
        self.df["BearPower"] = low - ta.trend.sma_indicator(close, window=13) if len(self.df) >= 13 else pd.Series([np.nan]*len(self.df), index=self.df.index)
        self.df["UltimateOsc"] = ta.momentum.ultimate_oscillator(high, low, close, window1=7, window2=14, window3=28) if len(self.df) >= 28 else pd.Series([np.nan]*len(self.df), index=self.df.index)

        # Базовые индикаторы
        self.df["EMA_short"] = ta.trend.ema_indicator(close, window=ema_short_window) if len(self.df) >= ema_short_window else pd.Series([np.nan]*len(self.df), index=self.df.index)
        self.df["EMA_long"] = ta.trend.ema_indicator(close, window=ema_long_window) if len(self.df) >= ema_long_window else pd.Series([np.nan]*len(self.df), index=self.df.index)
        self.df["RSI"] = ta.momentum.rsi(close, window=rsi_window) if len(self.df) >= rsi_window else pd.Series([np.nan]*len(self.df), index=self.df.index)
        if len(self.df) >= max(macd_slow, macd_fast, macd_signal):
            macd = ta.trend.MACD(close, window_slow=macd_slow, window_fast=macd_fast, window_sign=macd_signal)
            self.df["MACD"] = macd.macd()
            self.df["MACD_signal"] = macd.macd_signal()
            self.df["MACD_hist"] = macd.macd_diff()
        else:
            self.df["MACD"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
            self.df["MACD_signal"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
            self.df["MACD_hist"] = pd.Series([np.nan]*len(self.df), index=self.df.index)

        self.df.ffill(inplace=True)
        self.df.bfill(inplace=True)
        return self.df
        self.df.bfill(inplace=True)
        return self.df

    def generate_signal(self) -> Dict[str, Any]:
        if self.df.empty:
            raise ValueError("DataFrame is empty")
        last = self.df.iloc[-1]
        price = float(last["close"])

        # Индикаторы
        ema_s = float(last["EMA_short"])
        ema_l = float(last["EMA_long"])
        sma_20 = float(last.get("SMA_20", 0))
        sma_50 = float(last.get("SMA_50", 0))
        rsi = float(last["RSI"])
        macd_hist = float(last["MACD_hist"])
        macd = float(last["MACD"])
        macd_signal = float(last["MACD_signal"])
        adx = float(last.get("ADX_14", 0))
        stoch_k = float(last.get("Stoch_K", 0))
        stoch_d = float(last.get("Stoch_D", 0))
        momentum = float(last.get("Momentum_10", 0))
        cci = float(last.get("CCI_20", 0))
        willr = float(last.get("WilliamsR_14", 0))
        bull = float(last.get("BullPower", 0))
        bear = float(last.get("BearPower", 0))

        # Голосование индикаторов
        bullish = 0
        bearish = 0
        reasons = []

        # ====================================================================
        ## Калибровка индикаторов
        # ====================================================================

        # EMA: Основной тренд. Увеличиваем вес.
        if ema_s > ema_l:
            bullish += 2  # Увеличенный вес
            reasons.append(f"EMA_short ({ema_s:.2f}) > EMA_long ({ema_l:.2f}) — сильный бычий тренд")
        else:
            bearish += 2  # Увеличенный вес
            reasons.append(f"EMA_short ({ema_s:.2f}) < EMA_long ({ema_l:.2f}) — сильный медвежий тренд")
        
        # SMA: Среднесрочный тренд. Добавляем проверку на близость.
        if sma_20 > sma_50:
            bullish += 1
            reasons.append(f"SMA_20 > SMA_50 — краткосрочный тренд вверх")
        elif sma_20 < sma_50:
            bearish += 1
            reasons.append(f"SMA_20 < SMA_50 — краткосрочный тренд вниз")
        else:
            reasons.append(f"SMA_20 ≈ SMA_50 — тренды сближаются (нейтрально)")

        # RSI: Осциллятор (уточнение порогов). Используем 40/60 как сигналы зарождающегося тренда.
        if rsi < 30:
            bullish += 2 # Сильный сигнал
            reasons.append(f"RSI ({rsi:.2f}) < 30 — перепродан (сильный бычий)")
        elif rsi < 40:
            bullish += 1
            reasons.append(f"RSI ({rsi:.2f}) < 40 — близко к перепроданности (бычий)")
        elif rsi > 70:
            bearish += 2 # Сильный сигнал
            reasons.append(f"RSI ({rsi:.2f}) > 70 — перекуплен (сильный медвежий)")
        elif rsi > 60:
            bearish += 1
            reasons.append(f"RSI ({rsi:.2f}) > 60 — близко к перекупленности (медвежий)")
        else:
            reasons.append(f"RSI = {rsi:.2f} — нейтрально (40-60)")

        # MACD: Учет гистограммы (моментум) и пересечения (сигнал).
        if macd > macd_signal: # Бычье пересечение
            bullish += 1
            reasons.append(f"MACD ({macd:.4f}) > MACD_signal ({macd_signal:.4f}) — бычье пересечение")
        else: # Медвежье пересечение
            bearish += 1
            reasons.append(f"MACD ({macd:.4f}) < MACD_signal ({macd_signal:.4f}) — медвежье пересечение")
            
        if macd_hist > 0:
            bullish += 1
            reasons.append(f"MACD_hist ({macd_hist:.4f}) > 0 — положительный моментум")
        else:
            bearish += 1
            reasons.append(f"MACD_hist ({macd_hist:.4f}) < 0 — отрицательный моментум")

        # ADX: Только сила тренда. Не голосует за направление.
        if adx > 25:
            reasons.append(f"ADX ({adx:.2f}) > 25 — сильный тренд")
        else:
            reasons.append(f"ADX ({adx:.2f}) <= 25 — слабый тренд/флэт")
            
        # Stochastic: Строгое использование зон перекупленности/перепроданности И пересечений.
        if stoch_k < 20 and stoch_d < 20 and stoch_k > stoch_d: # Перепроданность и восходящее пересечение
            bullish += 2 # Сильный сигнал
            reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}) < 20 и K>D — выход из перепроданности (сильный бычий)")
        elif stoch_k > 80 and stoch_d > 80 and stoch_k < stoch_d: # Перекупленность и нисходящее пересечение
            bearish += 2 # Сильный сигнал
            reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}) > 80 и K<D — выход из перекупленности (сильный медвежий)")
        elif stoch_k > stoch_d and stoch_k < 80 and stoch_k > 20: # Бычий моментум в нейтральной зоне
            bullish += 1
            reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}): K>D — бычий моментум")
        elif stoch_k < stoch_d and stoch_k > 20 and stoch_k < 80: # Медвежий моментум в нейтральной зоне
            bearish += 1
            reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}): K<D — медвежий моментум")
        else:
            reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}): нейтрально/флэт")

        # Momentum: Голосуем только при сильном движении (выше/ниже определенного порога)
        # Предполагаем, что Momentum_10 - это разница цены Close(N) - Close(N-10).
        MOMENTUM_THRESHOLD = 0.005 * price # 0.5% изменения за 10 периодов (пример калибровки, зависит от актива)
        if momentum > MOMENTUM_THRESHOLD:
            bullish += 1
            reasons.append(f"Momentum ({momentum:.4f}) > {MOMENTUM_THRESHOLD:.4f} — сильное ускорение вверх")
        elif momentum < -MOMENTUM_THRESHOLD:
            bearish += 1
            reasons.append(f"Momentum ({momentum:.4f}) < {-MOMENTUM_THRESHOLD:.4f} — сильное ускорение вниз")
        else:
            reasons.append(f"Momentum ({momentum:.4f}) — слабый моментум")

        # CCI: Используем стандартные зоны 100/-100.
        if cci > 100:
            bullish += 1
            reasons.append(f"CCI ({cci:.2f}) > 100 — бычий сигнал (перекупленность, но сигнал продолжения тренда)")
        elif cci < -100:
            bearish += 1
            reasons.append(f"CCI ({cci:.2f}) < -100 — медвежий сигнал (перепроданность, но сигнал продолжения тренда)")
        else:
            reasons.append(f"CCI ({cci:.2f}) — нейтрально (-100 до 100)")

        # Williams %R: Аналогично RSI, с поправкой на -80/-20.
        if willr < -80:
            bullish += 2 # Сильный сигнал
            reasons.append(f"Williams %R ({willr:.2f}) < -80 — перепродан (сильный бычий)")
        elif willr > -20:
            bearish += 2 # Сильный сигнал
            reasons.append(f"Williams %R ({willr:.2f}) > -20 — перекуплен (сильный медвежий)")
        else:
            reasons.append(f"Williams %R ({willr:.2f}) — нейтрально")

        # Bull/Bear Power: Использование нуля как разделителя силы быков/медведей.
        if bull > 0:
            bullish += 1
            reasons.append(f"Bull Power ({bull:.4f}) > 0 — быки контролируют рынок")
        else: # Если Bull Power <= 0, это медвежий сигнал
            bearish += 1
            reasons.append(f"Bull Power ({bull:.4f}) <= 0 — медведи сильнее")

        if bear < 0:
            bearish += 1
            reasons.append(f"Bear Power ({bear:.4f}) < 0 — медведи контролируют рынок")
        else: # Если Bear Power >= 0, это бычий сигнал
            bullish += 1
            reasons.append(f"Bear Power ({bear:.4f}) >= 0 — медвежья сила иссякла")
        
        # ====================================================================
        # Итоговое голосование
        # ====================================================================
        
        # Используем порог для "HOLD"
        VOTE_THRESHOLD = 3 # Минимальная разница для уверенного сигнала (калибруется)

        if bullish - bearish >= VOTE_THRESHOLD:
            signal = "BUY"
            signal_emoji = "🚀"
            reasons.append(f"Итого: Бычьи ({bullish}) > Медвежьи ({bearish}). Сильный сигнал на покупку.")
        elif bearish - bullish >= VOTE_THRESHOLD:
            signal = "SELL"
            signal_emoji = "🔻"
            reasons.append(f"Итого: Медвежьи ({bearish}) > Бычьи ({bullish}). Сильный сигнал на продажу.")
        else:
            signal = "HOLD"
            signal_emoji = "⏸️"
            reasons.append(f"Итого: Бычьи ({bullish}) против Медвежьих ({bearish}). Слабый сигнал — удержание позиции.")

        return {
            "signal": signal,
            "signal_emoji": signal_emoji,
            "price": price,
            "EMA_short": ema_s,
            "EMA_long": ema_l,
            "RSI": rsi,
            "MACD": macd,
            "MACD_signal": macd_signal,
            "MACD_hist": macd_hist,
            "bullish_votes": bullish,
            "bearish_votes": bearish,
            "reasons": reasons,
        }

# -----------------------------
# TelegramBot
# -----------------------------
class TelegramBot:
    def __init__(self, token: str, default_symbol: str = "BTCUSDT", default_interval: str = "1m"):
        if token is None:
            raise RuntimeError("TELEGRAM_TOKEN not set")
        self.token = token
        self.default_symbol = default_symbol
        self.default_interval = default_interval
        self.tracked_symbols: set[str] = set()  # <-- новое хранилище
        self.json_file = "tracked_symbols.json"  # путь к файлу
        self._load_tracked_symbols()
        self.application = Application.builder().token(self.token).build()
        self._register_handlers()
        self.poll_interval = 60  # интервал фонового анализа в секундах
        self.last_signals: dict[str, str] = {}  # хранит последний сигнал для каждой пары
        self.chat_id: int | None = None  # куда слать авто-сигналы
        self.volatility_window = 10  # сколько свечей анализировать
        self.volatility_threshold = 0.02  # порог изменения цены (2% = 0.02)
        self.last_volatility_alert: dict[str, float] = {}  # хранит последнюю цену, чтобы не спамить

    def _register_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("status", self.status))
        self.application.add_handler(CommandHandler("analyze", self.analyze))
        self.application.add_handler(CommandHandler("add", self.add_symbol))
        self.application.add_handler(CommandHandler("remove", self.remove_symbol))
        self.application.add_handler(CommandHandler("list", self.list_symbols))
        self.application.add_handler(CommandHandler("settings", self.settings))

    # -----------------------------
    # Работа с JSON
    # -----------------------------
    def _load_tracked_symbols(self):
        """Загрузить пары, chat_id и настройки из JSON"""
        try:
            with open(self.json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.tracked_symbols = set(s.upper() for s in data.get("symbols", []))
                self.chat_id = data.get("chat_id")
                settings = data.get("settings", {})
                self.poll_interval = settings.get("poll_interval", 60)
                self.volatility_window = settings.get("volatility_window", 10)
                self.volatility_threshold = settings.get("volatility_threshold", 0.02)
                logger.info("Загружено %d пар, chat_id=%s, настройки=%s",
                            len(self.tracked_symbols), self.chat_id, settings)
        except FileNotFoundError:
            logger.info("JSON-файл %s не найден, создаём новый", self.json_file)
            self.tracked_symbols = set()
            self.chat_id = None
            self.poll_interval = 60
            self.volatility_window = 10
            self.volatility_threshold = 0.02
        except Exception as e:
            logger.error("Ошибка загрузки %s: %s", self.json_file, e)
            self.tracked_symbols = set()
            self.chat_id = None
            self.poll_interval = 60
            self.volatility_window = 10
            self.volatility_threshold = 0.02

    def _save_tracked_symbols(self):
        """Сохраняем пары, chat_id и настройки в JSON"""
        try:
            with open(self.json_file, "w", encoding="utf-8") as f:
                json.dump({
                    "chat_id": self.chat_id,
                    "symbols": sorted(self.tracked_symbols),
                    "settings": {
                        "poll_interval": self.poll_interval,
                        "volatility_window": self.volatility_window,
                        "volatility_threshold": self.volatility_threshold
                    }
                }, f, indent=2)
            logger.info("Сохранено %d пар и chat_id=%s, настройки=%s",
                        len(self.tracked_symbols), self.chat_id,
                        {"poll_interval": self.poll_interval,
                        "volatility_window": self.volatility_window,
                        "volatility_threshold": self.volatility_threshold})
        except Exception as e:
            logger.error("Ошибка сохранения %s: %s", self.json_file, e)


    # -------------------------
    # Основные команды
    # -------------------------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Привет! Я — бот для анализа криптовалют.\n"
            "Команды:\n"
            "/start, /help, /status, /analyze [SYMBOL] [INTERVAL]\n"
            "/add SYMBOL — добавить пару\n"
            "/remove SYMBOL — удалить пару\n"
            "/list — показать все отслеживаемые пары"
        )
        if self.chat_id is None:
            self.chat_id = update.effective_chat.id
            self._save_tracked_symbols()

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Помощь:\n"
            "/analyze SYMBOL INTERVAL — анализ пары\n"
            "/add SYMBOL — добавить пару в отслеживаемые\n"
            "/remove SYMBOL — удалить пару\n"
            "/list — показать все пары\n"
            "Если SYMBOL и INTERVAL не указаны, используются значения по умолчанию."
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            f"Bot version: python-telegram-bot {tg_version}\n"
            f"Default symbol: {self.default_symbol}\n"
            f"Default interval: {self.default_interval}\n"
            f"Отслеживаемые пары: {', '.join(self.tracked_symbols) if self.tracked_symbols else 'нет'}\n"
            "Status: OK"
        )
        await update.message.reply_text(text)
        if self.chat_id is None:
            self.chat_id = update.effective_chat.id
            self._save_tracked_symbols()

    # -------------------------
    # Управление парами
    # -------------------------
    async def add_symbol(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Использование: /add SYMBOL")
            return
        symbol = context.args[0].upper()
        if symbol in self.tracked_symbols:
            await update.message.reply_text(f"{symbol} уже в списке отслеживаемых.")
        else:
            self.tracked_symbols.add(symbol)
            self._save_tracked_symbols()
            logger.info("Добавлена пара: %s", symbol)
            await update.message.reply_text(f"{symbol} добавлен в список отслеживаемых.")

    async def remove_symbol(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Использование: /remove SYMBOL")
            return
        symbol = context.args[0].upper()
        if symbol in self.tracked_symbols:
            self.tracked_symbols.remove(symbol)
            self._save_tracked_symbols()
            logger.info("Удалена пара: %s", symbol)
            await update.message.reply_text(f"{symbol} удалён из списка отслеживаемых.")
        else:
            await update.message.reply_text(f"{symbol} нет в списке отслеживаемых.")

    async def list_symbols(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.tracked_symbols:
            text = "Отслеживаемые пары:\n" + "\n".join(self.tracked_symbols)
        else:
            text = "Список отслеживаемых пар пуст."
        await update.message.reply_text(text)

    # -------------------------
    # Анализ пары
    # -------------------------
    async def analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args or []
        symbol = args[0].upper() if len(args) >= 1 else self.default_symbol
        interval = args[1] if len(args) >= 2 else self.default_interval

        msg = await update.message.reply_text(f"Запрашиваю данные для {symbol} {interval}...")

        try:
            async with aiohttp.ClientSession() as session:
                provider = DataProvider(session)
                klines = await provider.fetch_klines(symbol=symbol, interval=interval, limit=500)
                df = provider.klines_to_dataframe(klines)

            if df.empty:
                await msg.edit_text("Не удалось получить данные от Binance.")
                return

            generator = SignalGenerator(df)
            generator.compute_indicators()
            result = generator.generate_signal()

            # Форматированный вывод для Telegram MarkdownV2
            # Форматирование через HTML
            import math
            def html_escape(s):
                s = str(s)
                s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                return s
            def fmt(val):
                if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
                    return 'нет данных'
                return f'{val:.5f}' if isinstance(val, float) else str(val)

            reasons_text = '\n'.join([f"• {html_escape(r)}" for r in result["reasons"]])
            # Расширенный вывод индикаторов
            ind = result
            indicators_text = (
                f"EMA_short: {fmt(ind['EMA_short'])}\n"
                f"EMA_long: {fmt(ind['EMA_long'])}\n"
                f"RSI: {fmt(ind['RSI'])}\n"
                f"MACD: {fmt(ind['MACD'])}\n"
                f"MACD_signal: {fmt(ind['MACD_signal'])}\n"
                f"MACD_hist: {fmt(ind['MACD_hist'])}\n"
            )
            text = (
                f"<b>📊 Авто-анализ {html_escape(symbol)} ({html_escape(interval)})</b>\n"
                f"Цена: <b>{fmt(result['price'])}</b>\n"
                f"Сигнал: <b>{html_escape(result['signal'])}</b> {result['signal_emoji']}\n\n"
                f"<b>Обоснование:</b>\n{reasons_text}\n"
                f"<b>Индикаторы:</b>\n{indicators_text}\n"
                f"<i>Простой индикаторный сигнал — не торговая рекомендация.</i>"
            )
            await msg.edit_text(text, parse_mode="HTML")
        except Exception as e:
            logger.exception("Ошибка в /analyze")
            await msg.edit_text(f"Ошибка при анализе: {e}")

    async def _background_task(self):
        """Фоновая задача, периодически анализирует все отслеживаемые пары"""
        while True:
            if not self.tracked_symbols or self.chat_id is None:
                await asyncio.sleep(self.poll_interval)
                continue

            async with aiohttp.ClientSession() as session:
                provider = DataProvider(session)
                for symbol in self.tracked_symbols:
                    try:
                        klines = await provider.fetch_klines(symbol=symbol, interval=self.default_interval, limit=500)
                        df = provider.klines_to_dataframe(klines)
                        if df.empty:
                            continue

                        generator = SignalGenerator(df)
                        generator.compute_indicators()
                        result = generator.generate_signal()
                        signal = result["signal"]

                        last = self.last_signals.get(symbol)
                        if last != signal:
                            # сигнал изменился → отправляем сообщение
                            # Форматирование через HTML
                            import math
                            def html_escape(s):
                                s = str(s)
                                s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                                return s
                            def fmt(val):
                                if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
                                    return 'нет данных'
                                return f'{val:.2f}' if isinstance(val, float) else str(val)

                            reasons_text = '\n'.join([f"• {html_escape(r)}" for r in result["reasons"]])
                            ind = result
                            indicators_text = (
                                f"EMA_short: {fmt(ind['EMA_short'])}\n"
                                f"EMA_long: {fmt(ind['EMA_long'])}\n"
                                f"RSI: {fmt(ind['RSI'])}\n"
                                f"MACD: {fmt(ind['MACD'])}\n"
                                f"MACD_signal: {fmt(ind['MACD_signal'])}\n"
                                f"MACD_hist: {fmt(ind['MACD_hist'])}\n"
                            )
                            text = (
                                f"<b>📊 Авто-анализ {html_escape(symbol)} ({html_escape(self.default_interval)})</b>\n"
                                f"Цена: <b>{fmt(result['price'])}</b>\n"
                                f"Сигнал: <b>{html_escape(signal)}</b> {result['signal_emoji']}\n\n"
                                f"<b>Обоснование:</b>\n{reasons_text}\n"
                                f"<b>Индикаторы:</b>\n{indicators_text}\n"
                                f"<i>Простой индикаторный сигнал — не торговая рекомендация.</i>"
                            )
                            await self.application.bot.send_message(chat_id=self.chat_id, text=text, parse_mode="HTML")
                            self.last_signals[symbol] = signal
                        # -------------------
                        # Волатильность
                        # -------------------
                        if len(df) >= self.volatility_window:
                            recent_df = df.iloc[-self.volatility_window:]
                            open_price = recent_df["open"].iloc[0]
                            close_price = recent_df["close"].iloc[-1]
                            change = (close_price - open_price) / open_price  # относительное изменение

                            last_alert_price = self.last_volatility_alert.get(symbol)
                            # Отправляем уведомление, если превышен порог и это новая цена
                            if abs(change) >= self.volatility_threshold and last_alert_price != close_price:
                                direction = "↑" if change > 0 else "↓"
                                impact = "Резкое движение цены, возможна волатильность в ближайшие минуты"
                                # Форматирование через HTML
                                text = (
                                    f"<b>⚠️ Волатильность {symbol} ({self.default_interval})</b>\n"
                                    f"За последние {self.volatility_window} свечей: {change*100:.2f}% {direction}\n"
                                    f"Текущая цена: <b>{close_price:.8f}</b>\n"
                                    f"<i>{impact}</i>"
                                )
                                await self.application.bot.send_message(chat_id=self.chat_id, text=text, parse_mode="HTML")
                                self.last_volatility_alert[symbol] = close_price

                    except Exception as e:
                        logger.error("Ошибка фонового анализа %s: %s", symbol, e)
            await asyncio.sleep(self.poll_interval)

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /settings [poll_interval] [volatility_window] [volatility_threshold]
        Пример: /settings 60 10 0.02
        Если аргументы не указаны — покажет текущие настройки.
        """
        args = context.args
        if not args:
            text = (
                f"Текущие настройки:\n"
                f"Фоновый интервал (poll_interval): {self.poll_interval} сек\n"
                f"Окно волатильности (volatility_window): {self.volatility_window} свечей\n"
                f"Порог волатильности (volatility_threshold): {self.volatility_threshold*100:.2f}%"
            )
            await update.message.reply_text(text)
            return

        # Пытаемся обновить настройки по аргументам
        try:
            if len(args) >= 1:
                self.poll_interval = int(args[0])
            if len(args) >= 2:
                self.volatility_window = int(args[1])
            if len(args) >= 3:
                self.volatility_threshold = float(args[2])
            self._save_tracked_symbols()
            await update.message.reply_text(
                f"Настройки обновлены:\n"
                f"poll_interval = {self.poll_interval} сек\n"
                f"volatility_window = {self.volatility_window} свечей\n"
                f"volatility_threshold = {self.volatility_threshold*100:.2f}%"
            )
        except Exception as e:
            await update.message.reply_text(f"Ошибка при обновлении настроек: {e}")


    def run(self):
        logger.info("Запуск бота...")
        async def start_background(application):
            asyncio.create_task(self._background_task())

        # Запуск background task и polling
        self.application.post_init = start_background
        self.application.run_polling(stop_signals=None)

# -----------------------------
# Точка входа
# -----------------------------
if __name__ == "__main__":
    try:
        bot = TelegramBot(token=TELEGRAM_TOKEN, default_symbol=DEFAULT_SYMBOL, default_interval=DEFAULT_INTERVAL)
        bot.run()
    except Exception as exc:
        logger.exception("Не удалось запустить бота: %s", exc)
        raise
