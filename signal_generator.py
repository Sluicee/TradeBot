import pandas as pd
import numpy as np
import ta
from typing import Dict, Any, Optional
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
	MIN_FILTERS,
	# Mean Reversion
	MR_RSI_OVERSOLD, MR_RSI_EXIT, MR_ZSCORE_BUY_THRESHOLD, MR_ZSCORE_SELL_THRESHOLD,
	MR_ZSCORE_STRONG_BUY, MR_ADX_MAX, MR_EMA_DIVERGENCE_MAX, MR_ZSCORE_WINDOW,
	MR_POSITION_SIZE_STRONG, MR_POSITION_SIZE_MEDIUM, MR_POSITION_SIZE_WEAK,
	# Фильтры "падающего ножа" v5
	NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT, NO_BUY_IF_EMA200_SLOPE_NEG, EMA200_NEG_SLOPE_THRESHOLD,
	USE_RED_CANDLES_FILTER, USE_VOLUME_FILTER, VOLUME_SPIKE_THRESHOLD,
	# Динамический SL/TP v5
	USE_DYNAMIC_SL_FOR_MR, MR_ATR_SL_MULTIPLIER, MR_ATR_SL_MIN, MR_ATR_SL_MAX,
	ADAPTIVE_SL_ON_RISK, ADAPTIVE_SL_MULTIPLIER,
	USE_DYNAMIC_TP_FOR_MR, MR_ATR_TP_MULTIPLIER, MR_ATR_TP_MIN, MR_ATR_TP_MAX,
	# Гибридная стратегия
	STRATEGY_HYBRID_MODE, HYBRID_ADX_MR_THRESHOLD, HYBRID_ADX_TF_THRESHOLD,
	HYBRID_TRANSITION_MODE, HYBRID_MIN_TIME_IN_MODE,
	# Multi-timeframe анализ
	USE_MULTI_TIMEFRAME, MTF_TIMEFRAMES, MTF_WEIGHTS, MTF_MIN_AGREEMENT, MTF_FULL_ALIGNMENT_BONUS
)

try:
	from statistical_models import (
		BayesianDecisionLayer,
		ZScoreAnalyzer,
		MarkovRegimeSwitcher,
		EnsembleDecisionMaker
	)
	STATISTICAL_MODELS_AVAILABLE = True
except ImportError:
	STATISTICAL_MODELS_AVAILABLE = False
	logger.warning("Статистические модели не доступны")

class SignalGenerator:
	def __init__(self, df: pd.DataFrame, use_statistical_models: bool = False):
		self.df = df.copy()
		if "close" not in self.df.columns:
			raise ValueError("DataFrame must contain 'close' column")
		self.df.sort_index(inplace=True)
		
		# Статистические модели (опционально)
		self.use_statistical_models = use_statistical_models and STATISTICAL_MODELS_AVAILABLE
		if self.use_statistical_models:
			self.bayesian = BayesianDecisionLayer()
			self.zscore = ZScoreAnalyzer(window=50, buy_threshold=-2.0, sell_threshold=2.0)
			self.regime = MarkovRegimeSwitcher(window=50)
			self.ensemble = EnsembleDecisionMaker(
				self.bayesian, self.zscore, self.regime,
				bayesian_weight=0.4, zscore_weight=0.3, regime_weight=0.3
			)

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

		base_result = {
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
		
		# ====================================================================
		# СТАТИСТИЧЕСКИЕ МОДЕЛИ (если включены)
		# ====================================================================
		
		if self.use_statistical_models and signal != "HOLD":
			try:
				ensemble_decision = self.ensemble.make_decision(
					self.df,
					base_result,
					min_probability=0.55
				)
				
				# Обновляем сигнал на основе ensemble решения
				base_result["original_signal"] = signal
				base_result["signal"] = ensemble_decision["final_signal"]
				base_result["statistical_confidence"] = ensemble_decision["confidence"]
				base_result["statistical_models"] = ensemble_decision["models"]
				
				# Добавляем новые reasons
				base_result["reasons"].append("\n🤖 === СТАТИСТИЧЕСКИЕ МОДЕЛИ ===")
				base_result["reasons"].extend(ensemble_decision["reasons"])
				
				# Обновляем emoji
				if base_result["signal"] == "BUY":
					base_result["signal_emoji"] = "🟢🤖"
				elif base_result["signal"] == "SELL":
					base_result["signal_emoji"] = "🔴🤖"
				else:
					base_result["signal_emoji"] = "⚠️🤖"
				
			except Exception as e:
				logger.error(f"Ошибка в статистических моделях: {e}")
				base_result["statistical_error"] = str(e)
		
		return base_result
	
	def generate_signal_mean_reversion(self) -> Dict[str, Any]:
		"""
		🔄 MEAN REVERSION STRATEGY
		
		Логика: покупка на сильной перепроданности, быстрый выход на возврате к среднему.
		Цель: короткие сделки 1-4% в боковом/падающем рынке.
		
		Условия входа (BUY):
		1. RSI < MR_RSI_OVERSOLD (30)
		2. Z-score < MR_ZSCORE_BUY_THRESHOLD (-2.5)
		3. ADX < MR_ADX_MAX (25) - нет сильного тренда
		4. EMA12 ≈ EMA26 (разница < 1%) - боковик
		
		Условия выхода (SELL):
		1. RSI > MR_RSI_EXIT (45)
		2. Z-score > MR_ZSCORE_SELL_THRESHOLD (0.5)
		
		Адаптивный размер позиции:
		- RSI < 20 и Z < -2.5 → 70% (сильная перепроданность)
		- RSI < 25 и Z < -2.0 → 50% (умеренная)
		- Иначе → 30%
		"""
		if self.df.empty:
			raise ValueError("DataFrame is empty")
		
		last = self.df.iloc[-1]
		price = float(last["close"])
		
		# Индикаторы
		ema_12 = float(last.get("EMA_12", 0))
		ema_26 = float(last.get("EMA_26", 0))
		rsi = float(last["RSI"])
		adx = float(last.get(f"ADX_{ADX_WINDOW}", 0))
		atr = float(last.get(f"ATR_{ATR_WINDOW}", 0))
		stoch_k = float(last.get("Stoch_K", 0))
		
		# ====================================================================
		# РАСЧЁТ Z-SCORE
		# ====================================================================
		
		if len(self.df) >= MR_ZSCORE_WINDOW:
			close_prices = self.df["close"].iloc[-MR_ZSCORE_WINDOW:].astype(float)
			sma = close_prices.mean()
			std = close_prices.std()
			zscore = (price - sma) / std if std > 0 else 0
		else:
			zscore = 0
		
		# ====================================================================
		# ПРОВЕРКА РЕЖИМА РЫНКА
		# ====================================================================
		
		# 1. ADX - не должен быть высоким (исключаем трендовый рынок)
		is_not_trending = adx < MR_ADX_MAX
		
		# 2. EMA дивергенция - EMA12 и EMA26 должны быть близки (флэт)
		if ema_12 > 0 and ema_26 > 0:
			ema_divergence = abs(ema_12 - ema_26) / ema_26
			is_sideways = ema_divergence < MR_EMA_DIVERGENCE_MAX
		else:
			is_sideways = False
		
		# ====================================================================
		# ФИЛЬТРЫ "ПАДАЮЩЕГО НОЖА" (КРИТИЧНО!)
		# ====================================================================
		
		reasons = []  # Инициализируем список причин
		falling_knife_detected = False
		
		# 1. Проверка: цена ниже минимума последних 24 часов на X%
		if len(self.df) >= 24:
			low_24h = self.df["low"].iloc[-24:].min()
			price_vs_24h_low = (price - low_24h) / low_24h
			
			if price_vs_24h_low < -NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT:
				falling_knife_detected = True
				reasons.append(f"🚫 ПАДАЮЩИЙ НОЖ: цена ${price:.2f} ниже min(24h)=${low_24h:.2f} на {abs(price_vs_24h_low)*100:.1f}% (>{NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT*100}%)")
		
		# 2. Проверка: отрицательный наклон EMA200
		if NO_BUY_IF_EMA200_SLOPE_NEG and len(self.df) >= 200 + 24:
			ema_200 = float(last.get("EMA_200", 0))
			if ema_200 > 0:
				# Берём EMA200 24 свечи назад
				ema_200_24h_ago = float(self.df["EMA_200"].iloc[-24])
				if ema_200_24h_ago > 0:
					ema200_slope = (ema_200 - ema_200_24h_ago) / ema_200_24h_ago
					
					if ema200_slope < EMA200_NEG_SLOPE_THRESHOLD:
						falling_knife_detected = True
						reasons.append(f"🚫 EMA200 ПАДАЕТ: slope={ema200_slope*100:.2f}% за 24h (< {EMA200_NEG_SLOPE_THRESHOLD*100:.1f}%)")
		
		# 3. Проверка: последовательность красных свечей (v5: ВКЛЮЧЕН ОБРАТНО)
		if USE_RED_CANDLES_FILTER and len(self.df) >= 5:
			# Берём последние 5 свечей
			recent_candles = self.df.tail(5)
			red_candles = 0
			total_drop = 0.0
			
			for idx in range(len(recent_candles)):
				candle = recent_candles.iloc[idx]
				open_price = float(candle["open"])
				close_price = float(candle["close"])
				candle_change = (close_price - open_price) / open_price
				
				if candle_change < 0:  # Красная свеча
					red_candles += 1
					total_drop += abs(candle_change)
			
			# Если 4+ красных свечей подряд и общее падение > 3%
			if red_candles >= 4 and total_drop > 0.03:
				falling_knife_detected = True
				reasons.append(f"🚫 СЕРИЯ КРАСНЫХ СВЕЧЕЙ: {red_candles}/5 свечей, падение {total_drop*100:.1f}% (>3%)")
			
			# Или если последние 3 свечи все красные и падение > 2%
			last_3_candles = self.df.tail(3)
			last_3_red = 0
			last_3_drop = 0.0
			for idx in range(len(last_3_candles)):
				candle = last_3_candles.iloc[idx]
				open_price = float(candle["open"])
				close_price = float(candle["close"])
				candle_change = (close_price - open_price) / open_price
				if candle_change < 0:
					last_3_red += 1
					last_3_drop += abs(candle_change)
			
			if last_3_red == 3 and last_3_drop > 0.02:
				falling_knife_detected = True
				reasons.append(f"🚫 3 КРАСНЫЕ СВЕЧИ ПОДРЯД: падение {last_3_drop*100:.1f}% (>2%)")
		
		# 4. v5: Проверка всплеска объёма (НОВОЕ)
		if USE_VOLUME_FILTER and "volume" in self.df.columns and len(self.df) >= 24:
			current_volume = float(self.df["volume"].iloc[-1])
			avg_volume_24h = float(self.df["volume"].iloc[-24:].mean())
			
			if avg_volume_24h > 0:
				volume_ratio = current_volume / avg_volume_24h
				if volume_ratio > VOLUME_SPIKE_THRESHOLD:
					falling_knife_detected = True
					reasons.append(f"🚫 ВСПЛЕСК ОБЪЁМА: {volume_ratio:.2f}x средний за 24h (> {VOLUME_SPIKE_THRESHOLD}x)")
		
		# ====================================================================
		# ЛОГИКА СИГНАЛОВ
		# ====================================================================
		
		signal = "HOLD"
		signal_emoji = "⚠️"
		position_size_percent = 0
		confidence = 0
		dynamic_sl = None  # Динамический SL на основе ATR
		dynamic_tp = None  # Динамический TP на основе ATR (v4)
		
		# --- УСЛОВИЯ ПОКУПКИ ---
		is_rsi_oversold = rsi < MR_RSI_OVERSOLD
		is_zscore_low = zscore < MR_ZSCORE_BUY_THRESHOLD
		is_strong_oversold = rsi < 20 and zscore < MR_ZSCORE_STRONG_BUY
		
		# v5: БЛОКИРУЕМ ВХОД ПРИ FALLING KNIFE (если адаптивный SL отключен)
		if is_rsi_oversold and is_zscore_low and not falling_knife_detected:
			# Вход разрешён - нет падающего ножа
			# Дополнительная фильтрация: желательно боковик или слабый тренд
			if is_not_trending or is_sideways:
				signal = "BUY"
				signal_emoji = "🟢"
				
				# Адаптивный размер позиции
				if is_strong_oversold:
					position_size_percent = MR_POSITION_SIZE_STRONG
					reasons.append(f"✅ STRONG BUY: RSI={rsi:.1f} (<20), Z-score={zscore:.2f} (<-2.5) → позиция 70%")
				elif rsi < 25 and zscore < -2.0:
					position_size_percent = MR_POSITION_SIZE_MEDIUM
					reasons.append(f"✅ MEDIUM BUY: RSI={rsi:.1f} (<25), Z-score={zscore:.2f} (<-2.0) → позиция 50%")
				else:
					position_size_percent = MR_POSITION_SIZE_WEAK
					reasons.append(f"✅ WEAK BUY: RSI={rsi:.1f}, Z-score={zscore:.2f} → позиция 30%")
				
				confidence = min(1.0, (abs(zscore) / abs(MR_ZSCORE_BUY_THRESHOLD)) * 0.5 + ((MR_RSI_OVERSOLD - rsi) / MR_RSI_OVERSOLD) * 0.5)
				
				reasons.append(f"📊 RSI={rsi:.1f} < {MR_RSI_OVERSOLD} (перепродан)")
				reasons.append(f"📉 Z-score={zscore:.2f} < {MR_ZSCORE_BUY_THRESHOLD} (сильно ниже среднего)")
				reasons.append(f"🎯 ADX={adx:.1f} {'<' if is_not_trending else '≥'} {MR_ADX_MAX} ({'нет сильного тренда' if is_not_trending else 'тренд есть!'})")
				
				if is_sideways:
					reasons.append(f"📈 EMA12≈EMA26 (дивергенция {ema_divergence*100:.2f}% < 1%) - боковик ✓")
				
				if stoch_k < STOCH_OVERSOLD:
					reasons.append(f"📉 Stoch={stoch_k:.1f} < {STOCH_OVERSOLD} - дополнительное подтверждение перепроданности")
				
				# Рассчитываем динамический SL на основе ATR
				if USE_DYNAMIC_SL_FOR_MR and atr > 0:
					atr_percent = (atr / price) * 100
					dynamic_sl = (atr / price) * MR_ATR_SL_MULTIPLIER
					dynamic_sl = max(MR_ATR_SL_MIN, min(dynamic_sl, MR_ATR_SL_MAX))
					
					# v4: АДАПТИВНЫЙ SL при риске падающего ножа
					if falling_knife_detected and ADAPTIVE_SL_ON_RISK:
						dynamic_sl *= ADAPTIVE_SL_MULTIPLIER  # Увеличиваем на 50%
						reasons.append(f"🛡️ Адаптивный SL: {dynamic_sl*100:.2f}% (риск падающего ножа, увеличен на {(ADAPTIVE_SL_MULTIPLIER-1)*100:.0f}%)")
					else:
						reasons.append(f"🛡️ Динамический SL: {dynamic_sl*100:.2f}% (ATR={atr_percent:.2f}% × {MR_ATR_SL_MULTIPLIER})")
				
				# v4: Рассчитываем динамический TP на основе ATR
				if USE_DYNAMIC_TP_FOR_MR and atr > 0:
					atr_percent = (atr / price) * 100
					dynamic_tp = (atr / price) * MR_ATR_TP_MULTIPLIER
					dynamic_tp = max(MR_ATR_TP_MIN, min(dynamic_tp, MR_ATR_TP_MAX))
					reasons.append(f"🎯 Динамический TP: {dynamic_tp*100:.2f}% (ATR × {MR_ATR_TP_MULTIPLIER}, R:R={MR_ATR_TP_MULTIPLIER/MR_ATR_SL_MULTIPLIER:.1f})")
			else:
				signal = "HOLD"
				reasons.append(f"⏸ HOLD: RSI и Z-score перепроданы, но ADX={adx:.1f} > {MR_ADX_MAX} (сильный тренд) → пропускаем")
		
		elif is_rsi_oversold and is_zscore_low and falling_knife_detected:
			# v5: Падающий нож обнаружен
			if ADAPTIVE_SL_ON_RISK:
				# v4 режим: разрешаем вход с увеличенным SL
				# (этот код не выполнится в v5, т.к. ADAPTIVE_SL_ON_RISK=False)
				pass  # логика выше уже обработана
			else:
				# v5 режим: блокируем вход
				signal = "HOLD"
				# reasons уже содержит причины блокировки от фильтров
		
		# --- УСЛОВИЯ ПРОДАЖИ (выход из позиции) ---
		is_rsi_normal = rsi > MR_RSI_EXIT
		is_zscore_normalized = zscore > MR_ZSCORE_SELL_THRESHOLD
		
		if is_rsi_normal or is_zscore_normalized:
			signal = "SELL"
			signal_emoji = "🔴"
			confidence = min(1.0, (rsi - MR_RSI_EXIT) / (70 - MR_RSI_EXIT) * 0.5 + (zscore / 2.0) * 0.5)
			
			reasons.append(f"✅ EXIT: Возврат к среднему")
			if is_rsi_normal:
				reasons.append(f"📊 RSI={rsi:.1f} > {MR_RSI_EXIT} (вернулся к норме)")
			if is_zscore_normalized:
				reasons.append(f"📈 Z-score={zscore:.2f} > {MR_ZSCORE_SELL_THRESHOLD} (цена вернулась к среднему)")
		
		# Если не BUY и не SELL - HOLD
		if signal == "HOLD" and not reasons:
			reasons.append(f"⏸ HOLD: RSI={rsi:.1f}, Z-score={zscore:.2f}")
			reasons.append(f"📊 ADX={adx:.1f}, EMA дивергенция={(abs(ema_12-ema_26)/ema_26*100 if ema_26 > 0 else 0):.2f}%")
			reasons.append("🔍 Ожидаем перепроданности (RSI<30, Z<-2.5)")
		
		return {
			"signal": signal,
			"signal_emoji": signal_emoji,
			"price": price,
			"RSI": rsi,
			"zscore": zscore,
			"ADX": adx,
			"ATR": atr,
			"EMA_12": ema_12,
			"EMA_26": ema_26,
			"ema_divergence": abs(ema_12 - ema_26) / ema_26 if ema_26 > 0 else 0,
			"stoch_k": stoch_k,
			"is_not_trending": is_not_trending,
			"is_sideways": is_sideways,
			"position_size_percent": position_size_percent,
			"confidence": confidence,
			"falling_knife_detected": falling_knife_detected,
			"dynamic_sl": dynamic_sl,  # Динамический SL для бэктеста
			"dynamic_tp": dynamic_tp,  # Динамический TP для бэктеста (v4)
			"reasons": reasons,
			"strategy": "MEAN_REVERSION",
			"bullish_votes": 0,  # Mean reversion не использует систему голосования
			"bearish_votes": 0
		}
	
	def generate_signal_hybrid(self, last_mode: str = None, last_mode_time: float = 0) -> Dict[str, Any]:
		"""
		🔀 ГИБРИДНАЯ СТРАТЕГИЯ (MR + TF с переключением по ADX)
		
		Логика:
		- ADX < 20 → Mean Reversion (боковой рынок)
		- ADX > 25 → Trend Following (трендовый рынок)
		- 20 <= ADX <= 25 → переходная зона (HOLD или последний режим)
		
		Параметры:
		- last_mode: последний активный режим ("MR" или "TF")
		- last_mode_time: время в последнем режиме (часы)
		
		Возвращает сигнал с указанием активного режима.
		"""
		if self.df.empty:
			return {
				"signal": "HOLD",
				"signal_emoji": "⚠️",
				"price": 0,
				"ADX": 0,
				"active_mode": "NONE",
				"reasons": ["⚠️ DataFrame пустой"],
				"strategy": "HYBRID",
				"bullish_votes": 0,
				"bearish_votes": 0
			}
		
		reasons = []
		
		# Получаем ADX и цену из последней строки DataFrame
		last = self.df.iloc[-1]
		price = float(last["close"])
		adx = float(last.get(f"ADX_{ADX_WINDOW}", 0))
		
		if adx == 0 or price == 0:
			return {
				"signal": "HOLD",
				"signal_emoji": "⚠️",
				"price": price,
				"ADX": adx,
				"active_mode": "NONE",
				"reasons": ["⚠️ Недостаточно данных для расчёта индикаторов"],
				"strategy": "HYBRID",
				"bullish_votes": 0,
				"bearish_votes": 0
			}
		
		# Определяем текущий режим на основе ADX
		if adx < HYBRID_ADX_MR_THRESHOLD:
			current_mode = "MR"
			reasons.append(f"📊 ADX={adx:.1f} < {HYBRID_ADX_MR_THRESHOLD} → MEAN REVERSION режим")
		elif adx > HYBRID_ADX_TF_THRESHOLD:
			current_mode = "TF"
			reasons.append(f"📊 ADX={adx:.1f} > {HYBRID_ADX_TF_THRESHOLD} → TREND FOLLOWING режим")
		else:
			# Переходная зона
			if HYBRID_TRANSITION_MODE == "HOLD":
				current_mode = "HOLD"
				reasons.append(f"⏸ ADX={adx:.1f} в переходной зоне [{HYBRID_ADX_MR_THRESHOLD}, {HYBRID_ADX_TF_THRESHOLD}] → HOLD")
			else:  # LAST
				current_mode = last_mode if last_mode else "HOLD"
				reasons.append(f"🔄 ADX={adx:.1f} в переходной зоне → используем последний режим ({current_mode})")
		
		# Проверяем минимальное время в режиме (защита от частого переключения)
		if last_mode and last_mode != current_mode and last_mode_time < HYBRID_MIN_TIME_IN_MODE:
			current_mode = last_mode
			reasons.append(f"⏱ Остаёмся в режиме {last_mode} (прошло {last_mode_time:.1f}h < {HYBRID_MIN_TIME_IN_MODE}h)")
		
		# Генерируем сигнал в зависимости от режима
		if current_mode == "MR":
			signal_result = self.generate_signal_mean_reversion()
			signal_result["active_mode"] = "MEAN_REVERSION"
			signal_result["strategy"] = "HYBRID"
			signal_result["reasons"] = reasons + signal_result.get("reasons", [])
		
		elif current_mode == "TF":
			signal_result = self.generate_signal()
			signal_result["active_mode"] = "TREND_FOLLOWING"
			signal_result["strategy"] = "HYBRID"
			signal_result["reasons"] = reasons + signal_result.get("reasons", [])
		
		else:  # HOLD
			signal_result = {
				"signal": "HOLD",
				"signal_emoji": "⚠️",
				"price": price,
				"ADX": adx,
				"active_mode": "TRANSITION",
				"reasons": reasons,
				"strategy": "HYBRID",
				"bullish_votes": 0,
				"bearish_votes": 0
			}
		
		return signal_result
	
	async def generate_signal_multi_timeframe(
		self,
		data_provider,
		symbol: str,
		strategy: str = "TREND_FOLLOWING"
	) -> Dict[str, Any]:
		"""
		🔀 MULTI-TIMEFRAME ANALYSIS
		
		Анализирует сигналы на нескольких таймфреймах (15m, 1h, 4h) и
		объединяет их через weighted voting для повышения точности.
		
		Параметры:
		- data_provider: объект DataProvider для загрузки данных
		- symbol: торговая пара (например, "BTCUSDT")
		- strategy: "TREND_FOLLOWING", "MEAN_REVERSION", или "HYBRID"
		
		Возвращает:
		- Объединённый сигнал с информацией по каждому таймфрейму
		"""
		import asyncio
		
		if not USE_MULTI_TIMEFRAME:
			# Fallback: используем текущий DataFrame если MTF отключен
			if strategy == "MEAN_REVERSION":
				return self.generate_signal_mean_reversion()
			elif strategy == "HYBRID":
				return self.generate_signal_hybrid()
			else:
				return self.generate_signal()
		
		reasons = []
		timeframe_signals = {}
		
		# ====================================================================
		# 1. ЗАГРУЗКА ДАННЫХ ДЛЯ КАЖДОГО ТАЙМФРЕЙМА
		# ====================================================================
		
		async def fetch_all_timeframes():
			"""Параллельная загрузка всех таймфреймов"""
			tasks = []
			for tf in MTF_TIMEFRAMES:
				tasks.append(data_provider.fetch_klines(symbol, tf, limit=200))
			return await asyncio.gather(*tasks, return_exceptions=True)
		
		# Запускаем загрузку
		try:
			# Если уже в async контексте, используем gather, иначе создаём event loop
			try:
				loop = asyncio.get_running_loop()
				# Мы уже в async контексте - просто await
				tf_data = await fetch_all_timeframes()
			except RuntimeError:
				# Нет running loop - создаём новый
				tf_data = asyncio.run(fetch_all_timeframes())
		except Exception as e:
			logger.error(f"Ошибка загрузки MTF данных: {e}")
			# Fallback на single TF
			if strategy == "MEAN_REVERSION":
				return self.generate_signal_mean_reversion()
			elif strategy == "HYBRID":
				return self.generate_signal_hybrid()
			else:
				return self.generate_signal()
		
		# ====================================================================
		# 2. ГЕНЕРАЦИЯ СИГНАЛОВ ДЛЯ КАЖДОГО ТАЙМФРЕЙМА
		# ====================================================================
		
		for i, tf in enumerate(MTF_TIMEFRAMES):
			if isinstance(tf_data[i], Exception):
				logger.warning(f"Ошибка данных для {tf}: {tf_data[i]}")
				timeframe_signals[tf] = {
					"signal": "HOLD",
					"error": str(tf_data[i]),
					"weight": MTF_WEIGHTS.get(tf, 0)
				}
				continue
			
			df = tf_data[i]
			if df.empty:
				timeframe_signals[tf] = {
					"signal": "HOLD",
					"error": "Empty dataframe",
					"weight": MTF_WEIGHTS.get(tf, 0)
				}
				continue
			
			# Создаём отдельный генератор для этого таймфрейма
			try:
				sg = SignalGenerator(df, use_statistical_models=self.use_statistical_models)
				sg.compute_indicators()
				
				# Генерируем сигнал в зависимости от стратегии
				if strategy == "MEAN_REVERSION":
					signal_result = sg.generate_signal_mean_reversion()
				elif strategy == "HYBRID":
					signal_result = sg.generate_signal_hybrid()
				else:
					signal_result = sg.generate_signal()
				
				# Сохраняем результат
				timeframe_signals[tf] = {
					"signal": signal_result.get("signal", "HOLD"),
					"price": signal_result.get("price", 0),
					"RSI": signal_result.get("RSI", 0),
					"ADX": signal_result.get("ADX", 0),
					"MACD_hist": signal_result.get("MACD_hist", 0),
					"market_regime": signal_result.get("market_regime", "NEUTRAL"),
					"bullish_votes": signal_result.get("bullish_votes", 0),
					"bearish_votes": signal_result.get("bearish_votes", 0),
					"weight": MTF_WEIGHTS.get(tf, 0),
					"confidence": signal_result.get("confidence", 0)
				}
				
			except Exception as e:
				logger.error(f"Ошибка генерации сигнала для {tf}: {e}")
				timeframe_signals[tf] = {
					"signal": "HOLD",
					"error": str(e),
					"weight": MTF_WEIGHTS.get(tf, 0)
				}
		
		# ====================================================================
		# 3. WEIGHTED VOTING
		# ====================================================================
		
		buy_score = 0.0
		sell_score = 0.0
		hold_score = 0.0
		
		buy_count = 0
		sell_count = 0
		hold_count = 0
		
		for tf, sig_data in timeframe_signals.items():
			signal = sig_data.get("signal", "HOLD")
			weight = sig_data.get("weight", 0)
			confidence = sig_data.get("confidence", 0.5)
			
			# Взвешиваем по весу таймфрейма и уверенности сигнала
			weighted_score = weight * (1 + confidence)
			
			if signal == "BUY":
				buy_score += weighted_score
				buy_count += 1
				reasons.append(f"📊 {tf}: BUY (вес={weight:.2f}, conf={confidence:.2f})")
			elif signal == "SELL":
				sell_score += weighted_score
				sell_count += 1
				reasons.append(f"📊 {tf}: SELL (вес={weight:.2f}, conf={confidence:.2f})")
			else:
				hold_score += weighted_score
				hold_count += 1
				reasons.append(f"📊 {tf}: HOLD (вес={weight:.2f})")
		
		# ====================================================================
		# 4. ПРОВЕРКА СОГЛАСОВАННОСТИ (ALIGNMENT)
		# ====================================================================
		
		total_tf = len(MTF_TIMEFRAMES)
		alignment_strength = 0
		final_signal = "HOLD"
		signal_emoji = "⚠️"
		
		# Проверяем полное согласие (все 3 TF показывают одинаково)
		if buy_count == total_tf:
			alignment_strength = 1.0
			final_signal = "BUY"
			signal_emoji = "🟢🔥"
			buy_score *= MTF_FULL_ALIGNMENT_BONUS
			reasons.append(f"✅ ПОЛНОЕ СОГЛАСИЕ: все {total_tf} таймфрейма показывают BUY! (бонус {MTF_FULL_ALIGNMENT_BONUS}x)")
		elif sell_count == total_tf:
			alignment_strength = 1.0
			final_signal = "SELL"
			signal_emoji = "🔴🔥"
			sell_score *= MTF_FULL_ALIGNMENT_BONUS
			reasons.append(f"✅ ПОЛНОЕ СОГЛАСИЕ: все {total_tf} таймфрейма показывают SELL! (бонус {MTF_FULL_ALIGNMENT_BONUS}x)")
		
		# Проверяем частичное согласие (минимум MTF_MIN_AGREEMENT)
		elif buy_count >= MTF_MIN_AGREEMENT and buy_score > sell_score:
			alignment_strength = buy_count / total_tf
			final_signal = "BUY"
			signal_emoji = "🟢"
			reasons.append(f"✓ Частичное согласие: {buy_count}/{total_tf} таймфреймов показывают BUY")
		elif sell_count >= MTF_MIN_AGREEMENT and sell_score > buy_score:
			alignment_strength = sell_count / total_tf
			final_signal = "SELL"
			signal_emoji = "🔴"
			reasons.append(f"✓ Частичное согласие: {sell_count}/{total_tf} таймфреймов показывают SELL")
		
		# Конфликт таймфреймов - остаёмся в HOLD
		else:
			final_signal = "HOLD"
			signal_emoji = "⚠️"
			reasons.append(f"⚠️ КОНФЛИКТ ТАЙМФРЕЙМОВ: BUY={buy_count}, SELL={sell_count}, HOLD={hold_count}")
			reasons.append(f"   Weighted scores: BUY={buy_score:.2f}, SELL={sell_score:.2f}, HOLD={hold_score:.2f}")
		
		# ====================================================================
		# 5. ФИНАЛЬНЫЙ РЕЗУЛЬТАТ
		# ====================================================================
		
		# Берём данные из основного таймфрейма (обычно 1h)
		main_tf = '1h' if '1h' in timeframe_signals else MTF_TIMEFRAMES[0]
		main_data = timeframe_signals.get(main_tf, {})
		
		# Расчёт итоговой силы сигнала (для адаптивного размера позиции)
		signal_strength = 0
		if final_signal == "BUY":
			signal_strength = int(buy_score * 3)  # Нормализуем к scale ~3-15
		elif final_signal == "SELL":
			signal_strength = int(sell_score * 3)
		
		result = {
			"signal": final_signal,
			"signal_emoji": signal_emoji,
			"price": main_data.get("price", 0),
			"strategy": f"{strategy}_MTF",
			
			# Multi-timeframe данные
			"mtf_enabled": True,
			"timeframe_signals": timeframe_signals,
			"alignment_strength": alignment_strength,
			"buy_score": buy_score,
			"sell_score": sell_score,
			"hold_score": hold_score,
			"buy_count": buy_count,
			"sell_count": sell_count,
			"hold_count": hold_count,
			
			# Данные из основного таймфрейма
			"RSI": main_data.get("RSI", 0),
			"ADX": main_data.get("ADX", 0),
			"MACD_hist": main_data.get("MACD_hist", 0),
			"market_regime": main_data.get("market_regime", "NEUTRAL"),
			
			# Голоса (для совместимости)
			"bullish_votes": signal_strength if final_signal == "BUY" else 0,
			"bearish_votes": signal_strength if final_signal == "SELL" else 0,
			
			# Причины
			"reasons": reasons
		}
		
		return result
