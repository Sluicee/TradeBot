import pandas as pd
import numpy as np
import ta
from typing import Dict, Any
from logger import logger
from config import (
	# Индикаторы
	SMA_PERIODS, EMA_PERIODS, EMA_SHORT_WINDOW, EMA_LONG_WINDOW,
	RSI_WINDOW, RSI_OVERSOLD, RSI_OVERSOLD_NEAR, RSI_OVERBOUGHT, RSI_OVERBOUGHT_NEAR,
	RSI_BUY_RANGE, RSI_SELL_RANGE,
	MACD_FAST, MACD_SLOW, MACD_SIGNAL,
	ADX_WINDOW, ADX_TRENDING, ADX_RANGING, ADX_STRONG, ADX_MODERATE,
	STOCH_WINDOW, STOCH_SMOOTH_WINDOW, STOCH_OVERSOLD, STOCH_OVERBOUGHT,
	ATR_WINDOW, VOLUME_MA_WINDOW, VOLUME_HIGH_RATIO, VOLUME_MODERATE_RATIO, VOLUME_LOW_RATIO,
	# Веса и пороги
	TRENDING_TREND_WEIGHT, TRENDING_OSCILLATOR_WEIGHT,
	RANGING_TREND_WEIGHT, RANGING_OSCILLATOR_WEIGHT,
	TRANSITIONING_TREND_WEIGHT, TRANSITIONING_OSCILLATOR_WEIGHT,
	VOTE_THRESHOLD_TRENDING, VOTE_THRESHOLD_RANGING, VOTE_THRESHOLD_TRANSITIONING,
	MIN_FILTERS
)

class SignalGenerator:
	def __init__(self, df: pd.DataFrame):
		self.df = df.copy()
		if "close" not in self.df.columns:
			raise ValueError("DataFrame must contain 'close' column")
		self.df.sort_index(inplace=True)

	def compute_indicators(
		self, ema_short_window=None, ema_long_window=None, rsi_window=None,
		macd_fast=None, macd_slow=None, macd_signal=None
	) -> pd.DataFrame:
		# Используем значения из config, если не переданы явно
		ema_short_window = ema_short_window or EMA_SHORT_WINDOW
		ema_long_window = ema_long_window or EMA_LONG_WINDOW
		rsi_window = rsi_window or RSI_WINDOW
		macd_fast = macd_fast or MACD_FAST
		macd_slow = macd_slow or MACD_SLOW
		macd_signal = macd_signal or MACD_SIGNAL
		
		close = self.df["close"].astype(float)
		high = self.df["high"].astype(float)
		low = self.df["low"].astype(float)
		volume = self.df["volume"].astype(float)

		# Скользящие средние - из config
		for w in SMA_PERIODS:
			if len(self.df) >= w:
				self.df[f"SMA_{w}"] = ta.trend.sma_indicator(close, window=w)
			else:
				self.df[f"SMA_{w}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
		
		for w in EMA_PERIODS:
			if len(self.df) >= w:
				self.df[f"EMA_{w}"] = ta.trend.ema_indicator(close, window=w)
			else:
				self.df[f"EMA_{w}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
		
		# ATR для волатильности (КРИТИЧНО для динамического SL)
		if len(self.df) >= ATR_WINDOW:
			self.df[f"ATR_{ATR_WINDOW}"] = ta.volatility.average_true_range(high, low, close, window=ATR_WINDOW)
		else:
			self.df[f"ATR_{ATR_WINDOW}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
		
		# Объём
		if len(self.df) >= VOLUME_MA_WINDOW:
			self.df[f"Volume_MA_{VOLUME_MA_WINDOW}"] = volume.rolling(window=VOLUME_MA_WINDOW).mean()
		else:
			self.df[f"Volume_MA_{VOLUME_MA_WINDOW}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)

		# Осцилляторы - только самые важные
		self.df[f"RSI_{RSI_WINDOW}"] = ta.momentum.rsi(close, window=RSI_WINDOW) if len(self.df) >= RSI_WINDOW else pd.Series([np.nan]*len(self.df), index=self.df.index)
		
		# ADX - сила тренда (критично!)
		if (
			len(self.df) >= ADX_WINDOW
			and len(self.df.tail(ADX_WINDOW)) == ADX_WINDOW
			and self.df[["high", "low", "close"]].tail(ADX_WINDOW).isna().sum().sum() == 0
		):
			try:
				self.df[f"ADX_{ADX_WINDOW}"] = ta.trend.adx(high, low, close, window=ADX_WINDOW)
			except Exception:
				self.df[f"ADX_{ADX_WINDOW}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
		else:
			self.df[f"ADX_{ADX_WINDOW}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
		
		# Stochastic - для перекупленности/перепроданности
		self.df["Stoch_K"] = ta.momentum.stoch(high, low, close, window=STOCH_WINDOW, smooth_window=STOCH_SMOOTH_WINDOW) if len(self.df) >= STOCH_WINDOW else pd.Series([np.nan]*len(self.df), index=self.df.index)
		self.df["Stoch_D"] = ta.momentum.stoch_signal(high, low, close, window=STOCH_WINDOW, smooth_window=STOCH_SMOOTH_WINDOW) if len(self.df) >= STOCH_WINDOW else pd.Series([np.nan]*len(self.df), index=self.df.index)

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
		adx = float(last.get(f"ADX_{ADX_WINDOW}", 0))
		stoch_k = float(last.get("Stoch_K", 0))
		stoch_d = float(last.get("Stoch_D", 0))
		atr = float(last.get(f"ATR_{ATR_WINDOW}", 0))
		
		# Объём
		volume = float(last["volume"])
		volume_ma = float(last.get(f"Volume_MA_{VOLUME_MA_WINDOW}", volume))
		
		# Детекция рыночного режима
		market_regime = "NEUTRAL"
		if adx > ADX_TRENDING:
			market_regime = "TRENDING"
		elif adx < ADX_RANGING:
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
			trend_weight = TRENDING_TREND_WEIGHT
			oscillator_weight = TRENDING_OSCILLATOR_WEIGHT
		elif market_regime == "RANGING":
			trend_weight = RANGING_TREND_WEIGHT
			oscillator_weight = RANGING_OSCILLATOR_WEIGHT
		else:
			trend_weight = TRANSITIONING_TREND_WEIGHT
			oscillator_weight = TRANSITIONING_OSCILLATOR_WEIGHT

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
		if rsi < RSI_OVERSOLD:
			bullish += 2 * oscillator_weight
			reasons.append(f"RSI ({rsi:.2f}) < {RSI_OVERSOLD} — перепродан [+{2*oscillator_weight}]")
		elif rsi < RSI_OVERSOLD_NEAR:
			bullish += oscillator_weight
			reasons.append(f"RSI ({rsi:.2f}) < {RSI_OVERSOLD_NEAR} — близко к перепроданности [+{oscillator_weight}]")
		elif rsi > RSI_OVERBOUGHT:
			bearish += 2 * oscillator_weight
			reasons.append(f"RSI ({rsi:.2f}) > {RSI_OVERBOUGHT} — перекуплен [+{2*oscillator_weight}]")
		elif rsi > RSI_OVERBOUGHT_NEAR:
			bearish += oscillator_weight
			reasons.append(f"RSI ({rsi:.2f}) > {RSI_OVERBOUGHT_NEAR} — близко к перекупленности [+{oscillator_weight}]")
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
		if stoch_k < STOCH_OVERSOLD and stoch_d < STOCH_OVERSOLD and stoch_k > stoch_d:
			bullish += oscillator_weight
			reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}) < {STOCH_OVERSOLD} и K>D — выход из перепроданности [+{oscillator_weight}]")
		elif stoch_k > STOCH_OVERBOUGHT and stoch_d > STOCH_OVERBOUGHT and stoch_k < stoch_d:
			bearish += oscillator_weight
			reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}) > {STOCH_OVERBOUGHT} и K<D — выход из перекупленности [+{oscillator_weight}]")
		else:
			reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}): нейтрально")
		
		# ОБЪЁМ - КРИТИЧНО! Подтверждение движения
		if volume_ma > 0:
			volume_ratio = volume / volume_ma
			if volume_ratio > VOLUME_HIGH_RATIO:
				# Высокий объём подтверждает направление
				if ema_s > ema_l:
					bullish += 2
					reasons.append(f"Объём {volume_ratio:.1f}x выше среднего — подтверждение роста [+2]")
				else:
					bearish += 2
					reasons.append(f"Объём {volume_ratio:.1f}x выше среднего — подтверждение падения [+2]")
			elif volume_ratio > VOLUME_MODERATE_RATIO:
				if ema_s > ema_l:
					bullish += 1
					reasons.append(f"Объём {volume_ratio:.1f}x выше среднего — умеренное подтверждение")
				else:
					bearish += 1
					reasons.append(f"Объём {volume_ratio:.1f}x выше среднего — умеренное подтверждение")
			elif volume_ratio < VOLUME_LOW_RATIO:
				reasons.append(f"Объём {volume_ratio:.1f}x ниже среднего — слабое движение")
			else:
				reasons.append(f"Объём нормальный ({volume_ratio:.1f}x)")
		
		# ====================================================================
		# Итоговое голосование с ГИБКИМИ фильтрами (3 из 5)
		# ====================================================================
		
		# Адаптивный порог в зависимости от режима рынка
		if market_regime == "TRENDING":
			VOTE_THRESHOLD = VOTE_THRESHOLD_TRENDING  # В тренде легче входить
		elif market_regime == "RANGING":
			VOTE_THRESHOLD = VOTE_THRESHOLD_RANGING  # Во флэте осторожнее
		else:
			VOTE_THRESHOLD = VOTE_THRESHOLD_TRANSITIONING
		
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
		moderate_trend = adx > ADX_MODERATE
		strong_trend = adx > ADX_STRONG
		if strong_trend:
			buy_filters_passed += 1
			sell_filters_passed += 1
		elif moderate_trend:
			# Половинка балла за умеренный тренд
			pass
		
		# 3. RSI
		buy_rsi_ok = RSI_BUY_RANGE[0] < rsi < RSI_BUY_RANGE[1]  # Расширенный диапазон
		sell_rsi_ok = RSI_SELL_RANGE[0] < rsi < RSI_SELL_RANGE[1]
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
		high_volume = volume / volume_ma > VOLUME_MODERATE_RATIO if volume_ma > 0 else False
		if high_volume:
			buy_filters_passed += 1
			sell_filters_passed += 1
		
		# Решение: нужно >= MIN_FILTERS из 5 + перевес голосов
		
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
