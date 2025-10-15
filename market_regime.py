import pandas as pd
import numpy as np
import ta
from typing import Dict, Any, Optional
from logger import logger
from config import (
	ADX_WINDOW, ADX_TRENDING, ADX_RANGING, ADX_STRONG, ADX_MODERATE,
	TRENDING_TREND_WEIGHT, TRENDING_OSCILLATOR_WEIGHT,
	RANGING_TREND_WEIGHT, RANGING_OSCILLATOR_WEIGHT,
	TRANSITIONING_TREND_WEIGHT, TRANSITIONING_OSCILLATOR_WEIGHT,
	VOTE_THRESHOLD_TRENDING, VOTE_THRESHOLD_RANGING, VOTE_THRESHOLD_TRANSITIONING,
	MIN_FILTERS, RSI_BUY_RANGE, RSI_SELL_RANGE, VOLUME_MODERATE_RATIO
)

class MarketRegimeDetector:
	"""
	🎯 ДЕТЕКТОР РЕЖИМА РЫНКА
	
	Определяет режим рынка (TRENDING/RANGING/TRANSITIONING) на основе:
	- ADX (сила тренда)
	- Линейной регрессии (направление тренда)
	- Анализа индикаторов
	"""
	
	def __init__(self, df: pd.DataFrame):
		self.df = df.copy()
		if "close" not in self.df.columns:
			raise ValueError("DataFrame must contain 'close' column")
		self.df.sort_index(inplace=True)
	
	def detect_market_regime(self, indicators_data: Dict[str, Any]) -> Dict[str, Any]:
		"""
		🎯 ОПРЕДЕЛЕНИЕ РЕЖИМА РЫНКА
		
		Анализирует ADX, линейную регрессию и индикаторы для определения режима.
		
		Параметры:
		- indicators_data: словарь с данными индикаторов
		
		Возвращает:
		- dict: режим рынка и детализация анализа
		"""
		adx = indicators_data.get("ADX", 0)
		price = indicators_data.get("price", 0)
		
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
			percent_change = (price_range / prices[0]) * 100 if prices[0] > 0 else 0
			
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
		
		# Адаптивный порог в зависимости от режима рынка
		if market_regime == "TRENDING":
			vote_threshold = VOTE_THRESHOLD_TRENDING  # В тренде легче входить
		elif market_regime == "RANGING":
			vote_threshold = VOTE_THRESHOLD_RANGING  # Во флэте осторожнее
		else:
			vote_threshold = VOTE_THRESHOLD_TRANSITIONING
		
		return {
			"market_regime": market_regime,
			"trend_strength": trend_strength,
			"trend_direction": trend_direction,
			"trend_weight": trend_weight,
			"oscillator_weight": oscillator_weight,
			"vote_threshold": vote_threshold,
			"adx": adx
		}
	
	def analyze_voting_system(self, indicators_data: Dict[str, Any], regime_data: Dict[str, Any]) -> Dict[str, Any]:
		"""
		🗳️ АНАЛИЗ СИСТЕМЫ ГОЛОСОВАНИЯ
		
		Анализирует индикаторы и возвращает голоса за BUY/SELL.
		"""
		# Извлекаем данные
		ema_s = indicators_data.get("EMA_short", 0)
		ema_l = indicators_data.get("EMA_long", 0)
		sma_20 = indicators_data.get("SMA_20", 0)
		sma_50 = indicators_data.get("SMA_50", 0)
		rsi = indicators_data.get("RSI", 50)
		macd = indicators_data.get("MACD", 0)
		macd_signal = indicators_data.get("MACD_signal", 0)
		macd_hist = indicators_data.get("MACD_hist", 0)
		stoch_k = indicators_data.get("Stoch_K", 50)
		stoch_d = indicators_data.get("Stoch_D", 50)
		volume_ratio = indicators_data.get("volume_ratio", 1.0)
		
		trend_weight = regime_data.get("trend_weight", 1.0)
		oscillator_weight = regime_data.get("oscillator_weight", 1.0)
		trend_direction = regime_data.get("trend_direction", 0)
		trend_strength = regime_data.get("trend_strength", 0)
		
		# Голосование индикаторов
		bullish = 0
		bearish = 0
		reasons = []
		
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
		
		# RSI: КЛЮЧЕВОЙ осциллятор
		if rsi < 30:  # RSI_OVERSOLD
			bullish += 2 * oscillator_weight
			reasons.append(f"RSI ({rsi:.2f}) < 30 — перепродан [+{2*oscillator_weight}]")
		elif rsi < 35:  # RSI_OVERSOLD_NEAR
			bullish += oscillator_weight
			reasons.append(f"RSI ({rsi:.2f}) < 35 — близко к перепроданности [+{oscillator_weight}]")
		elif rsi > 70:  # RSI_OVERBOUGHT
			bearish += 2 * oscillator_weight
			reasons.append(f"RSI ({rsi:.2f}) > 70 — перекуплен [+{2*oscillator_weight}]")
		elif rsi > 65:  # RSI_OVERBOUGHT_NEAR
			bearish += oscillator_weight
			reasons.append(f"RSI ({rsi:.2f}) > 65 — близко к перекупленности [+{oscillator_weight}]")
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
		if stoch_k < 20 and stoch_d < 20 and stoch_k > stoch_d:  # STOCH_OVERSOLD
			bullish += oscillator_weight
			reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}) < 20 и K>D — выход из перепроданности [+{oscillator_weight}]")
		elif stoch_k > 80 and stoch_d > 80 and stoch_k < stoch_d:  # STOCH_OVERBOUGHT
			bearish += oscillator_weight
			reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}) > 80 и K<D — выход из перекупленности [+{oscillator_weight}]")
		else:
			reasons.append(f"Stoch K/D ({stoch_k:.2f}/{stoch_d:.2f}): нейтрально")
		
		# ОБЪЁМ - КРИТИЧНО! Подтверждение движения
		if volume_ratio > 1.5:  # VOLUME_HIGH_RATIO
			# Высокий объём подтверждает направление
			if ema_s > ema_l:
				bullish += 2
				reasons.append(f"Объём {volume_ratio:.1f}x выше среднего — подтверждение роста [+2]")
			else:
				bearish += 2
				reasons.append(f"Объём {volume_ratio:.1f}x выше среднего — подтверждение падения [+2]")
		elif volume_ratio > 1.2:  # VOLUME_MODERATE_RATIO
			if ema_s > ema_l:
				bullish += 1
				reasons.append(f"Объём {volume_ratio:.1f}x выше среднего — умеренное подтверждение")
			else:
				bearish += 1
				reasons.append(f"Объём {volume_ratio:.1f}x выше среднего — умеренное подтверждение")
		elif volume_ratio < 0.8:  # VOLUME_LOW_RATIO
			reasons.append(f"Объём {volume_ratio:.1f}x ниже среднего — слабое движение")
		else:
			reasons.append(f"Объём нормальный ({volume_ratio:.1f}x)")
		
		return {
			"bullish_votes": bullish,
			"bearish_votes": bearish,
			"reasons": reasons
		}
	
	def check_filters(self, indicators_data: Dict[str, Any]) -> Dict[str, Any]:
		"""
		🔍 ПРОВЕРКА ФИЛЬТРОВ
		
		Проверяет фильтры для BUY/SELL сигналов.
		"""
		# Извлекаем данные
		ema_s = indicators_data.get("EMA_short", 0)
		ema_l = indicators_data.get("EMA_long", 0)
		sma_20 = indicators_data.get("SMA_20", 0)
		sma_50 = indicators_data.get("SMA_50", 0)
		rsi = indicators_data.get("RSI", 50)
		macd = indicators_data.get("MACD", 0)
		macd_signal = indicators_data.get("MACD_signal", 0)
		macd_hist = indicators_data.get("MACD_hist", 0)
		adx = indicators_data.get("ADX", 0)
		volume_ratio = indicators_data.get("volume_ratio", 1.0)
		
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
		high_volume = volume_ratio > VOLUME_MODERATE_RATIO
		if high_volume:
			buy_filters_passed += 1
			sell_filters_passed += 1
		
		return {
			"buy_filters_passed": buy_filters_passed,
			"sell_filters_passed": sell_filters_passed,
			"min_filters": MIN_FILTERS
		}
