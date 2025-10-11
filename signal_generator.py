import pandas as pd
import numpy as np
import ta
from typing import Dict, Any
from logger import logger

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
