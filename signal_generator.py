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

        # Скользящие средние - только основные
        for w in [20, 50, 200]:
            if len(self.df) >= w:
                self.df[f"SMA_{w}"] = ta.trend.sma_indicator(close, window=w)
                self.df[f"EMA_{w}"] = ta.trend.ema_indicator(close, window=w)
            else:
                self.df[f"SMA_{w}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
                self.df[f"EMA_{w}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
        
        # ATR для волатильности (КРИТИЧНО для динамического SL)
        if len(self.df) >= 14:
            self.df["ATR_14"] = ta.volatility.average_true_range(high, low, close, window=14)
        else:
            self.df["ATR_14"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
        
        # Объём
        if len(self.df) >= 20:
            self.df["Volume_MA_20"] = volume.rolling(window=20).mean()
        else:
            self.df["Volume_MA_20"] = pd.Series([np.nan]*len(self.df), index=self.df.index)

        # Осцилляторы - только самые важные
        self.df["RSI_14"] = ta.momentum.rsi(close, window=14) if len(self.df) >= 14 else pd.Series([np.nan]*len(self.df), index=self.df.index)
        
        # ADX - сила тренда (критично!)
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
        
        # Stochastic - для перекупленности/перепроданности
        self.df["Stoch_K"] = ta.momentum.stoch(high, low, close, window=14, smooth_window=3) if len(self.df) >= 14 else pd.Series([np.nan]*len(self.df), index=self.df.index)
        self.df["Stoch_D"] = ta.momentum.stoch_signal(high, low, close, window=14, smooth_window=3) if len(self.df) >= 14 else pd.Series([np.nan]*len(self.df), index=self.df.index)

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

    def generate_signal(self) -> Dict[str, Any]:
        if self.df.empty:
            raise ValueError("DataFrame is empty")
        last = self.df.iloc[-1]
        price = float(last["close"])

        # Индикаторы
        ema_s = float(last["EMA_short"])
        ema_l = float(last["EMA_long"])
        ema_20 = float(last.get("EMA_20", 0))
        ema_50 = float(last.get("EMA_50", 0))
        ema_200 = float(last.get("EMA_200", 0))
        sma_20 = float(last.get("SMA_20", 0))
        sma_50 = float(last.get("SMA_50", 0))
        rsi = float(last["RSI"])
        macd_hist = float(last["MACD_hist"])
        macd = float(last["MACD"])
        macd_signal = float(last["MACD_signal"])
        adx = float(last.get("ADX_14", 0))
        stoch_k = float(last.get("Stoch_K", 0))
        stoch_d = float(last.get("Stoch_D", 0))
        atr = float(last.get("ATR_14", 0))
        
        # Объём
        volume = float(last["volume"])
        volume_ma = float(last.get("Volume_MA_20", volume))
        
        # Детекция рыночного режима
        market_regime = "NEUTRAL"
        if adx > 30:
            market_regime = "TRENDING"
        elif adx < 20:
            market_regime = "RANGING"
        else:
            market_regime = "TRANSITIONING"

        # Голосование индикаторов
        bullish = 0
        bearish = 0
        reasons = []

        # ====================================================================
        ## Калибровка индикаторов (оптимизировано)
        # ====================================================================
        
        # Адаптивные веса в зависимости от режима рынка
        if market_regime == "TRENDING":
            trend_weight = 3
            oscillator_weight = 1
        elif market_regime == "RANGING":
            trend_weight = 1
            oscillator_weight = 2
        else:
            trend_weight = 2
            oscillator_weight = 2

        # EMA: Основной тренд. КЛЮЧЕВОЙ индикатор.
        if ema_s > ema_l:
            bullish += trend_weight
            reasons.append(f"EMA_short ({ema_s:.2f}) > EMA_long ({ema_l:.2f}) — бычий тренд [+{trend_weight}]")
        else:
            bearish += trend_weight
            reasons.append(f"EMA_short ({ema_s:.2f}) < EMA_long ({ema_l:.2f}) — медвежий тренд [+{trend_weight}]")
        
        # SMA: Среднесрочный тренд
        if sma_20 > sma_50:
            bullish += 1
            reasons.append(f"SMA_20 > SMA_50 — краткосрочный тренд вверх")
        elif sma_20 < sma_50:
            bearish += 1
            reasons.append(f"SMA_20 < SMA_50 — краткосрочный тренд вниз")
        
        # EMA 200 - долгосрочный тренд (фильтр)
        if ema_200 > 0:
            if price > ema_200:
                reasons.append(f"Цена выше EMA200 ({ema_200:.2f}) — долгосрочный бычий тренд")
            else:
                reasons.append(f"Цена ниже EMA200 ({ema_200:.2f}) — долгосрочный медвежий тренд")

        # RSI: КЛЮЧЕВОЙ осциллятор
        if rsi < 30:
            bullish += 2 * oscillator_weight
            reasons.append(f"RSI ({rsi:.2f}) < 30 — перепродан [+{2*oscillator_weight}]")
        elif rsi < 40:
            bullish += oscillator_weight
            reasons.append(f"RSI ({rsi:.2f}) < 40 — близко к перепроданности [+{oscillator_weight}]")
        elif rsi > 70:
            bearish += 2 * oscillator_weight
            reasons.append(f"RSI ({rsi:.2f}) > 70 — перекуплен [+{2*oscillator_weight}]")
        elif rsi > 60:
            bearish += oscillator_weight
            reasons.append(f"RSI ({rsi:.2f}) > 60 — близко к перекупленности [+{oscillator_weight}]")
        else:
            reasons.append(f"RSI = {rsi:.2f} — нейтрально")

        # MACD: КЛЮЧЕВОЙ индикатор тренда и моментума
        if macd > macd_signal:
            bullish += 2
            reasons.append(f"MACD ({macd:.4f}) > MACD_signal ({macd_signal:.4f}) — бычье пересечение [+2]")
        else:
            bearish += 2
            reasons.append(f"MACD ({macd:.4f}) < MACD_signal ({macd_signal:.4f}) — медвежье пересечение [+2]")
            
        if macd_hist > 0:
            bullish += 1
            reasons.append(f"MACD_hist ({macd_hist:.4f}) > 0 — положительный моментум [+1]")
        else:
            bearish += 1
            reasons.append(f"MACD_hist ({macd_hist:.4f}) < 0 — отрицательный моментум [+1]")

        # ADX: Режим рынка
        reasons.append(f"ADX ({adx:.2f}) — режим: {market_regime}")
            
        # Stochastic: для экстремумов
        if stoch_k < 20 and stoch_d < 20 and stoch_k > stoch_d:
            bullish += oscillator_weight
            reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}) < 20 и K>D — выход из перепроданности [+{oscillator_weight}]")
        elif stoch_k > 80 and stoch_d > 80 and stoch_k < stoch_d:
            bearish += oscillator_weight
            reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}) > 80 и K<D — выход из перекупленности [+{oscillator_weight}]")
        else:
            reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}): нейтрально")
        
        # ОБЪЁМ - КРИТИЧНО! Подтверждение движения
        if volume_ma > 0:
            volume_ratio = volume / volume_ma
            if volume_ratio > 1.5:
                # Высокий объём подтверждает направление
                if ema_s > ema_l:
                    bullish += 2
                    reasons.append(f"Объём {volume_ratio:.1f}x выше среднего — подтверждение роста [+2]")
                else:
                    bearish += 2
                    reasons.append(f"Объём {volume_ratio:.1f}x выше среднего — подтверждение падения [+2]")
            elif volume_ratio > 1.2:
                if ema_s > ema_l:
                    bullish += 1
                    reasons.append(f"Объём {volume_ratio:.1f}x выше среднего — умеренное подтверждение")
                else:
                    bearish += 1
                    reasons.append(f"Объём {volume_ratio:.1f}x выше среднего — умеренное подтверждение")
            elif volume_ratio < 0.7:
                reasons.append(f"Объём {volume_ratio:.1f}x ниже среднего — слабое движение")
            else:
                reasons.append(f"Объём нормальный ({volume_ratio:.1f}x)")
        
        # ====================================================================
        # Итоговое голосование с ГИБКИМИ фильтрами (3 из 5)
        # ====================================================================
        
        # Адаптивный порог в зависимости от режима рынка
        if market_regime == "TRENDING":
            VOTE_THRESHOLD = 2  # В тренде легче входить
        elif market_regime == "RANGING":
            VOTE_THRESHOLD = 4  # Во флэте осторожнее
        else:
            VOTE_THRESHOLD = 3
        
        # Фильтры (считаем сколько пройдено)
        buy_filters_passed = 0
        sell_filters_passed = 0
        
        # 1. Тренд
        buy_trend_ok = ema_s > ema_l and sma_20 > sma_50
        sell_trend_ok = ema_s < ema_l and sma_20 < sma_50
        if buy_trend_ok:
            buy_filters_passed += 1
        if sell_trend_ok:
            sell_filters_passed += 1
        
        # 2. ADX (опционально в зависимости от режима)
        moderate_trend = adx > 20
        strong_trend = adx > 25
        if strong_trend:
            buy_filters_passed += 1
            sell_filters_passed += 1
        elif moderate_trend:
            # Половинка балла за умеренный тренд
            pass
        
        # 3. RSI
        buy_rsi_ok = 30 < rsi < 70  # Расширенный диапазон
        sell_rsi_ok = 30 < rsi < 70
        if buy_rsi_ok:
            buy_filters_passed += 1
        if sell_rsi_ok:
            sell_filters_passed += 1
        
        # 4. MACD
        macd_buy_ok = macd > macd_signal
        macd_sell_ok = macd < macd_signal
        if macd_buy_ok and macd_hist > 0:
            buy_filters_passed += 1
        if macd_sell_ok and macd_hist < 0:
            sell_filters_passed += 1
        
        # 5. Объём (опционально)
        high_volume = volume / volume_ma > 1.2 if volume_ma > 0 else False
        if high_volume:
            buy_filters_passed += 1
            sell_filters_passed += 1
        
        # Решение: нужно >= 3 фильтра из 5 + перевес голосов
        MIN_FILTERS = 3
        
        if bullish - bearish >= VOTE_THRESHOLD and buy_filters_passed >= MIN_FILTERS:
            signal = "BUY"
            signal_emoji = "🟢"
            reasons.append(f"✅ BUY: Голосов {bullish} vs {bearish}, фильтров {buy_filters_passed}/5, ADX={adx:.1f}")
        elif bearish - bullish >= VOTE_THRESHOLD and sell_filters_passed >= MIN_FILTERS:
            signal = "SELL"
            signal_emoji = "🔴"
            reasons.append(f"✅ SELL: Голосов {bearish} vs {bullish}, фильтров {sell_filters_passed}/5, ADX={adx:.1f}")
        else:
            signal = "HOLD"
            signal_emoji = "⚠️"
            reasons.append(f"⏸ HOLD: Бычьи {bullish} vs Медвежьи {bearish}, фильтров BUY:{buy_filters_passed} SELL:{sell_filters_passed}, режим: {market_regime}")

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
            "ADX": adx,
            "ATR": atr,
            "volume_ratio": volume / volume_ma if volume_ma > 0 else 1.0,
            "market_regime": market_regime,
            "bullish_votes": bullish,
            "bearish_votes": bearish,
            "buy_filters_passed": buy_filters_passed,
            "sell_filters_passed": sell_filters_passed,
            "reasons": reasons,
        }
