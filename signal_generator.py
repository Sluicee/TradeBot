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
		# ====================================================================
		# ДИНАМИЧЕСКАЯ АДАПТАЦИЯ ПАРАМЕТРОВ НА ОСНОВЕ ВОЛАТИЛЬНОСТИ
		# ====================================================================
		
		# Сначала вычисляем ATR для оценки волатильности
		close = self.df["close"].astype(float)
		high = self.df["high"].astype(float)
		low = self.df["low"].astype(float)
		
		# Временный ATR для адаптации параметров
		if len(self.df) >= ATR_WINDOW:
			temp_atr = ta.volatility.average_true_range(high, low, close, window=ATR_WINDOW).iloc[-1]
			current_price = close.iloc[-1]
			volatility_percent = (temp_atr / current_price) * 100 if current_price > 0 else 1.5
		else:
			volatility_percent = 1.5  # Средняя волатильность по умолчанию
		
		# Адаптируем параметры на основе волатильности
		# При высокой волатильности (>3%) → увеличиваем периоды (сглаживаем шум)
		# При низкой волатильности (<1%) → уменьшаем периоды (быстрее реагируем)
		
		volatility_factor = 1.0  # Базовый множитель
		if volatility_percent > 3.0:
			volatility_factor = 1.3  # Увеличиваем периоды на 30%
		elif volatility_percent > 2.0:
			volatility_factor = 1.15  # Увеличиваем на 15%
		elif volatility_percent < 0.8:
			volatility_factor = 0.85  # Уменьшаем на 15%
		elif volatility_percent < 1.2:
			volatility_factor = 0.95  # Уменьшаем на 5%
		
		# Используем значения из config с адаптацией, если не переданы явно
		if ema_short_window is None:
			ema_short_window = max(5, int(EMA_SHORT_WINDOW * volatility_factor))
		if ema_long_window is None:
			ema_long_window = max(10, int(EMA_LONG_WINDOW * volatility_factor))
		if rsi_window is None:
			rsi_window = max(7, int(RSI_WINDOW * volatility_factor))
		if macd_fast is None:
			macd_fast = max(8, int(MACD_FAST * volatility_factor))
		if macd_slow is None:
			macd_slow = max(16, int(MACD_SLOW * volatility_factor))
		if macd_signal is None:
			macd_signal = max(5, int(MACD_SIGNAL * volatility_factor))
		
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
		
		# ====================================================================
		# ДЕТЕКЦИЯ РЕЖИМА: ADX + Линейная регрессия
		# ====================================================================
		
		# 1. Базовая детекция через ADX
		market_regime = "NEUTRAL"
		if adx > ADX_TRENDING:
			market_regime = "TRENDING"
		elif adx < ADX_RANGING:
			market_regime = "RANGING"
		else:
			market_regime = "TRANSITIONING"
		
		# 2. Линейная регрессия для подтверждения тренда
		trend_strength = 0  # R² от 0 до 1
		trend_direction = 0  # -1 (down), 0 (neutral), +1 (up)
		
		if len(self.df) >= 20:
			# Последние 20 цен закрытия
			prices = self.df['close'].iloc[-20:].values
			x = np.arange(len(prices))
			
			# Линейная регрессия: y = slope * x + intercept
			slope, intercept = np.polyfit(x, prices, 1)
			
			# R² (коэффициент детерминации) - насколько хорошо линия описывает данные
			y_pred = slope * x + intercept
			ss_res = np.sum((prices - y_pred) ** 2)
			ss_tot = np.sum((prices - np.mean(prices)) ** 2)
			trend_strength = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
			trend_strength = max(0, min(1, trend_strength))  # Ограничиваем 0-1
			
			# Направление тренда (нормализуем к % изменения)
			price_range = prices[-1] - prices[0]
			percent_change = (price_range / prices[0]) * 100
			
			if abs(percent_change) > 1.0 and trend_strength > 0.5:  # Сильный тренд
				trend_direction = 1 if slope > 0 else -1
			elif abs(percent_change) > 0.5 and trend_strength > 0.3:  # Умеренный тренд
				trend_direction = 1 if slope > 0 else -1
			else:
				trend_direction = 0
		
		# 3. Корректируем режим на основе линейной регрессии
		if trend_strength > 0.6 and abs(trend_direction) == 1:
			# Сильный линейный тренд обнаружен - переводим в TRENDING
			if market_regime != "TRENDING":
				market_regime = "TRENDING"
		elif trend_strength < 0.3:
			# Слабая линейность - скорее всего флэт
			if market_regime == "TRENDING":
				market_regime = "TRANSITIONING"

		# Голосование индикаторов
		bullish = 0
		bearish = 0
		reasons = []
		
		# Информация об адаптированных параметрах (если они менялись)
		atr_percent = (atr / price) * 100 if atr > 0 and price > 0 else 0

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

		# ADX и режим рынка с линейной регрессией
		trend_info = f"↑" if trend_direction == 1 else "↓" if trend_direction == -1 else "→"
		reasons.append(f"📊 Режим: {market_regime} | ADX: {adx:.2f}")
		reasons.append(f"📈 Тренд ЛР: {trend_info} (R²={trend_strength:.2f})")
		
		# Бонус за подтверждение тренда линейной регрессией
		if trend_direction == 1 and trend_strength > 0.5:
			# Сильный восходящий тренд по ЛР
			bullish += 1
			reasons.append(f"✓ ЛР подтверждает восходящий тренд [+1]")
		elif trend_direction == -1 and trend_strength > 0.5:
			# Сильный нисходящий тренд по ЛР
			bearish += 1
			reasons.append(f"✓ ЛР подтверждает нисходящий тренд [+1]")
			
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
		# ПРОВЕРКА КОРРЕЛЯЦИИ ИНДИКАТОРОВ
		# ====================================================================
		
		# Игнорируем сигналы, когда индикаторы сильно расходятся
		indicator_conflicts = []
		conflict_detected = False
		
		# 1. RSI vs MACD - проверка согласованности осцилляторов
		rsi_bullish = rsi < RSI_OVERSOLD_NEAR  # RSI показывает бычий сигнал
		rsi_bearish = rsi > RSI_OVERBOUGHT_NEAR  # RSI показывает медвежий сигнал
		macd_bullish = macd > macd_signal and macd_hist > 0
		macd_bearish = macd < macd_signal and macd_hist < 0
		
		if rsi_bullish and macd_bearish:
			indicator_conflicts.append("⚠️ RSI бычий, но MACD медвежий")
			conflict_detected = True
		elif rsi_bearish and macd_bullish:
			indicator_conflicts.append("⚠️ RSI медвежий, но MACD бычий")
			conflict_detected = True
		
		# 2. EMA тренд vs MACD - тренд и моментум должны совпадать
		ema_trend_up = ema_s > ema_l
		ema_trend_down = ema_s < ema_l
		
		if ema_trend_up and macd_bearish:
			indicator_conflicts.append("⚠️ EMA показывает восходящий тренд, но MACD медвежий")
			conflict_detected = True
		elif ema_trend_down and macd_bullish:
			indicator_conflicts.append("⚠️ EMA показывает нисходящий тренд, но MACD бычий")
			conflict_detected = True
		
		# 3. Stochastic vs RSI - осцилляторы должны быть согласованы
		stoch_oversold = stoch_k < STOCH_OVERSOLD
		stoch_overbought = stoch_k > STOCH_OVERBOUGHT
		
		if stoch_oversold and rsi > 60:  # Stoch перепродан, но RSI высокий
			indicator_conflicts.append("⚠️ Stochastic перепродан, но RSI высокий")
			conflict_detected = True
		elif stoch_overbought and rsi < 40:  # Stoch перекуплен, но RSI низкий
			indicator_conflicts.append("⚠️ Stochastic перекуплен, но RSI низкий")
			conflict_detected = True
		
		# 4. Линейная регрессия vs индикаторы - тренд должен подтверждаться
		if trend_strength > 0.5:  # Сильный тренд по ЛР
			if trend_direction == 1 and macd_bearish and rsi_bearish:
				indicator_conflicts.append("⚠️ ЛР показывает восходящий тренд, но MACD и RSI медвежьи")
				conflict_detected = True
			elif trend_direction == -1 and macd_bullish and rsi_bullish:
				indicator_conflicts.append("⚠️ ЛР показывает нисходящий тренд, но MACD и RSI бычьи")
				conflict_detected = True
		
		# 5. Противоположные экстремумы - критический конфликт
		extreme_oversold = rsi < RSI_OVERSOLD and stoch_k < STOCH_OVERSOLD
		extreme_overbought = rsi > RSI_OVERBOUGHT and stoch_k > STOCH_OVERBOUGHT
		
		if extreme_oversold and ema_trend_down and macd_bearish:
			# Все показывают на продолжение падения, но осцилляторы в перепроданности
			# Возможен разворот, но это конфликт для SHORT
			pass  # Это нормальная ситуация для потенциального BUY
		elif extreme_overbought and ema_trend_up and macd_bullish:
			# Все показывают на продолжение роста, но осцилляторы в перекупленности
			# Возможен разворот, но это конфликт для LONG
			pass  # Это нормальная ситуация для потенциального SELL
		
		# Добавляем информацию о конфликтах в reasons
		if indicator_conflicts:
			for conflict in indicator_conflicts:
				reasons.append(conflict)
		
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
		
		# Решение: нужно >= MIN_FILTERS из 5 + перевес голосов + НЕТ конфликтов индикаторов
		
		if conflict_detected:
			# Критический конфликт - индикаторы расходятся, игнорируем сигнал
			signal = "HOLD"
			signal_emoji = "⚠️"
			reasons.append(f"🚫 HOLD: Обнаружен конфликт индикаторов! Голосов {bullish} vs {bearish}")
		elif bullish - bearish >= VOTE_THRESHOLD and buy_filters_passed >= MIN_FILTERS:
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
			"indicator_conflicts": indicator_conflicts,
			"conflict_detected": conflict_detected,
			"reasons": reasons,
		}
