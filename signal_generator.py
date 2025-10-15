import pandas as pd
import numpy as np
import ta
import requests
import json
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
	USE_MULTI_TIMEFRAME, MTF_TIMEFRAMES, MTF_WEIGHTS, MTF_MIN_AGREEMENT, MTF_FULL_ALIGNMENT_BONUS,
	# SHORT v2.1 - Adaptive Fear SHORT
	USE_ADVANCED_SHORT, SHORT_VERSION, SHORT_POSITION_SIZE_EXTREME_FEAR, SHORT_POSITION_SIZE_HIGH_FEAR,
	SHORT_POSITION_SIZE_MODERATE_FEAR, SHORT_POSITION_SIZE_NEUTRAL,
	SHORT_FEAR_EXTREME_THRESHOLD, SHORT_FEAR_HIGH_THRESHOLD, SHORT_FEAR_MODERATE_THRESHOLD,
	SHORT_FEAR_INERTIA_THRESHOLD, SHORT_FEAR_INERTIA_CANDLES, SHORT_FEAR_INERTIA_BONUS,
	SHORT_FEAR_WEIGHT, SHORT_FUNDING_WEIGHT, SHORT_LIQUIDATION_WEIGHT, SHORT_RSI_WEIGHT, SHORT_EMA_WEIGHT, SHORT_VOLATILITY_WEIGHT,
	SHORT_MIN_SCORE, SHORT_API_TIMEOUT, SHORT_FUNDING_RATE_THRESHOLD, SHORT_LIQUIDATION_RATIO_THRESHOLD,
	SHORT_VOLATILITY_MULTIPLIER, SHORT_VOLATILITY_BONUS, SHORT_BTC_DOMINANCE_THRESHOLD,
	SHORT_BTC_DOMINANCE_FEAR_THRESHOLD, SHORT_BTC_DOMINANCE_BONUS,
	SHORT_FALLBACK_FUNDING_RATE, SHORT_FALLBACK_LONG_LIQUIDATIONS, SHORT_FALLBACK_SHORT_LIQUIDATIONS, SHORT_FALLBACK_BTC_DOMINANCE
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

	def get_market_regime(self, df: pd.DataFrame, fear_greed_index: int = 50) -> str:
		"""
		🎯 ОПРЕДЕЛЕНИЕ РЫНОЧНОГО РЕЖИМА
		
		Анализирует EMA200, ADX и индекс страха для определения режима рынка.
		
		Параметры:
		- df: DataFrame с данными
		- fear_greed_index: индекс страха/жадности (0-100)
		
		Возвращает:
		- "BEAR": медвежий рынок (EMA200 падает, ADX>20, страх<40)
		- "BULL": бычий рынок (EMA200 растёт, страх>60)
		- "NEUTRAL": нейтральный режим
		"""
		if len(df) < 200:
			return "NEUTRAL"
		
		try:
			# EMA200 и её наклон
			ema200 = ta.trend.ema_indicator(df['close'], window=200)
			if len(ema200) < 10 or ema200.isna().all():
				return "NEUTRAL"
			
			# Наклон EMA200 за последние 10 периодов
			slope = (ema200.iloc[-1] - ema200.iloc[-10]) / ema200.iloc[-10]
			
			# ADX для силы тренда
			adx = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
			if len(adx) == 0 or adx.isna().all():
				adx_value = 0
			else:
				adx_value = adx.iloc[-1]
			
			# Логика определения режима (упрощённая)
			if slope < -0.001 and fear_greed_index < 40:  # Более мягкие условия
				return "BEAR"
			elif slope > 0.001 and fear_greed_index > 60:
				return "BULL"
			else:
				return "NEUTRAL"
		except Exception:
			return "NEUTRAL"

	def should_short(self, df: pd.DataFrame, fear_greed_index: int = 50) -> bool:
		"""
		🔴 АКТИВАЦИЯ SHORT-МЕХАНИКИ
		
		Возвращает True, если рынок медвежий и присутствует страх.
		Безопасная активация только при сильном падающем тренде.
		
		Параметры:
		- df: DataFrame с данными
		- fear_greed_index: индекс страха/жадности (0-100)
		
		Возвращает:
		- True: можно открывать SHORT позиции
		- False: SHORT отключён
		"""
		regime = self.get_market_regime(df, fear_greed_index)
		return regime == "BEAR" and fear_greed_index < 40

	def get_fear_greed_index(self) -> int:
		"""
		📊 ПОЛУЧЕНИЕ ИНДЕКСА СТРАХА/ЖАДНОСТИ
		
		Пытается получить реальный индекс от CNN Fear & Greed Index API.
		Если не удаётся, рассчитывает собственный на основе волатильности.
		
		Возвращает:
		- int: индекс от 0 (максимальный страх) до 100 (максимальная жадность)
		"""
		try:
			# Попытка получить от CNN Fear & Greed Index
			response = requests.get("https://api.alternative.me/fng/", timeout=5)
			if response.status_code == 200:
				data = response.json()
				if 'data' in data and len(data['data']) > 0:
					fear_greed = int(data['data'][0]['value'])
					logger.info(f"Получен индекс страха от API: {fear_greed}")
					return fear_greed
		except Exception as e:
			logger.warning(f"Не удалось получить индекс страха от API: {e}")
		
		# Fallback: собственный расчёт на основе волатильности
		return self._calculate_custom_fear_greed_index()
	
	def _calculate_custom_fear_greed_index(self) -> int:
		"""
		🧮 СОБСТВЕННЫЙ РАСЧЁТ ИНДЕКСА СТРАХА/ЖАДНОСТИ
		
		Анализирует волатильность, объёмы и тренды для определения настроений рынка.
		
		Возвращает:
		- int: индекс от 0 (страх) до 100 (жадность)
		"""
		if len(self.df) < 50:
			return 50  # Нейтрально при недостатке данных
		
		try:
			# 1. Анализ волатильности (высокая волатильность = страх)
			atr = ta.volatility.average_true_range(
				self.df['high'], self.df['low'], self.df['close'], window=14
			)
			current_atr = atr.iloc[-1]
			avg_atr = atr.tail(20).mean()
			volatility_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0
			
			# 2. Анализ объёмов (высокие объёмы при падении = страх)
			volume = self.df['volume']
			current_volume = volume.iloc[-1]
			avg_volume = volume.tail(20).mean()
			volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
			
			# 3. Анализ тренда (падение = страх)
			price_change_1d = (self.df['close'].iloc[-1] - self.df['close'].iloc[-24]) / self.df['close'].iloc[-24] if len(self.df) >= 24 else 0
			price_change_7d = (self.df['close'].iloc[-1] - self.df['close'].iloc[-168]) / self.df['close'].iloc[-168] if len(self.df) >= 168 else 0
			
			# 4. RSI анализ (перепроданность = страх)
			rsi = ta.momentum.rsi(self.df['close'], window=14)
			current_rsi = rsi.iloc[-1]
			
			# Расчёт компонентов индекса
			volatility_score = max(0, min(100, 100 - (volatility_ratio - 1) * 50))  # Высокая волатильность = низкий индекс
			volume_score = max(0, min(100, 100 - (volume_ratio - 1) * 30))  # Высокие объёмы = низкий индекс
			trend_score = max(0, min(100, 50 + price_change_1d * 1000))  # Падение = низкий индекс
			rsi_score = current_rsi  # RSI напрямую влияет на индекс
			
			# Взвешенное среднее
			fear_greed_index = int(
				volatility_score * 0.3 +
				volume_score * 0.2 +
				trend_score * 0.3 +
				rsi_score * 0.2
			)
			
			# Ограничиваем диапазон
			fear_greed_index = max(0, min(100, fear_greed_index))
			
			logger.info(f"Собственный индекс страха: {fear_greed_index} (волатильность: {volatility_ratio:.2f}, объём: {volume_ratio:.2f}, тренд: {price_change_1d:.3f}, RSI: {current_rsi:.1f})")
			return fear_greed_index
			
		except Exception as e:
			logger.error(f"Ошибка расчёта собственного индекса страха: {e}")
			return 50  # Нейтрально при ошибке

	def get_funding_rate(self, symbol: str = "BTCUSDT") -> float:
		"""
		💰 ПОЛУЧЕНИЕ FUNDING RATE
		
		Получает текущий funding rate для фьючерсов.
		Отрицательный funding rate усиливает SHORT сигналы.
		
		Параметры:
		- symbol: торговая пара (по умолчанию BTCUSDT)
		
		Возвращает:
		- float: funding rate в процентах
		"""
		try:
			# Binance Futures API для funding rate
			url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
			response = requests.get(url, timeout=SHORT_API_TIMEOUT)
			
			if response.status_code == 200:
				data = response.json()
				funding_rate = float(data.get('lastFundingRate', 0)) * 100  # Конвертируем в проценты
				logger.info(f"Получен funding rate для {symbol}: {funding_rate:.4f}%")
				return funding_rate
			else:
				logger.warning(f"Ошибка API funding rate: {response.status_code}")
				return SHORT_FALLBACK_FUNDING_RATE
				
		except Exception as e:
			logger.warning(f"Не удалось получить funding rate: {e}")
			return SHORT_FALLBACK_FUNDING_RATE

	def get_liquidation_data(self, symbol: str = "BTCUSDT") -> tuple:
		"""
		💥 ПОЛУЧЕНИЕ ДАННЫХ О ЛИКВИДАЦИЯХ
		
		Получает данные о ликвидациях long/short позиций.
		Преобладание long ликвидаций усиливает SHORT сигналы.
		
		Параметры:
		- symbol: торговая пара (по умолчанию BTCUSDT)
		
		Возвращает:
		- tuple: (long_liquidations, short_liquidations) в USD
		"""
		try:
			# Coinglass API для данных о ликвидациях
			url = "https://open-api.coinglass.com/public/v2/liquidation/exchange"
			headers = {
				"coinglassSecret": "your_api_key_here",  # Нужен API ключ
				"Content-Type": "application/json"
			}
			
			# Пробуем без API ключа (ограниченный доступ)
			response = requests.get(url, timeout=SHORT_API_TIMEOUT)
			
			if response.status_code == 200:
				data = response.json()
				# Парсим данные о ликвидациях
				long_liquidations = 0.0
				short_liquidations = 0.0
				
				if 'data' in data and 'list' in data['data']:
					for exchange in data['data']['list']:
						if exchange.get('exchangeName') == 'Binance':
							long_liquidations += float(exchange.get('longLiquidation', 0))
							short_liquidations += float(exchange.get('shortLiquidation', 0))
				
				logger.info(f"Ликвидации Long: ${long_liquidations:.1f}M, Short: ${short_liquidations:.1f}M")
				return long_liquidations, short_liquidations
			else:
				logger.warning(f"Ошибка API ликвидаций: {response.status_code}")
				return SHORT_FALLBACK_LONG_LIQUIDATIONS, SHORT_FALLBACK_SHORT_LIQUIDATIONS
				
		except Exception as e:
			logger.warning(f"Не удалось получить данные о ликвидациях: {e}")
			return SHORT_FALLBACK_LONG_LIQUIDATIONS, SHORT_FALLBACK_SHORT_LIQUIDATIONS

	def calculate_adaptive_short_score(
		self, 
		fear_greed_index: int, 
		funding_rate: float, 
		long_liquidations: float, 
		short_liquidations: float,
		rsi: float,
		ema_short: float,
		ema_long: float
	) -> tuple:
		"""
		🧮 РАСЧЁТ АДАПТИВНОГО СКОРА SHORT
		
		Вычисляет составной скор на основе множественных факторов.
		
		Параметры:
		- fear_greed_index: индекс страха/жадности (0-100)
		- funding_rate: funding rate в процентах
		- long_liquidations: ликвидации long позиций (USD)
		- short_liquidations: ликвидации short позиций (USD)
		- rsi: RSI значение
		- ema_short: быстрая EMA
		- ema_long: медленная EMA
		
		Возвращает:
		- tuple: (score, breakdown) где score 0-1, breakdown - детализация
		"""
		# Компоненты скора
		fear_score = 1.0 if fear_greed_index < 40 else 0.0
		funding_score = 1.0 if funding_rate < SHORT_FUNDING_RATE_THRESHOLD else 0.0
		
		# Ликвидации: больше long ликвидаций = больше SHORT сигнала
		if short_liquidations > 0:
			liquidation_ratio = long_liquidations / short_liquidations
			liquidation_score = 1.0 if liquidation_ratio > SHORT_LIQUIDATION_RATIO_THRESHOLD else 0.0
		else:
			liquidation_score = 0.0
		
		rsi_score = 1.0 if rsi > 70 else 0.0
		ema_score = 1.0 if ema_short < ema_long else 0.0
		
		# Взвешенный скор
		score = (
			fear_score * SHORT_FEAR_WEIGHT +
			funding_score * SHORT_FUNDING_WEIGHT +
			liquidation_score * SHORT_LIQUIDATION_WEIGHT +
			rsi_score * SHORT_RSI_WEIGHT +
			ema_score * SHORT_EMA_WEIGHT
		)
		
		# Детализация для логирования
		breakdown = {
			"fear_score": fear_score,
			"funding_score": funding_score,
			"liquidation_score": liquidation_score,
			"rsi_score": rsi_score,
			"ema_score": ema_score,
			"weights": {
				"fear": SHORT_FEAR_WEIGHT,
				"funding": SHORT_FUNDING_WEIGHT,
				"liquidation": SHORT_LIQUIDATION_WEIGHT,
				"rsi": SHORT_RSI_WEIGHT,
				"ema": SHORT_EMA_WEIGHT
			}
		}
		
		return score, breakdown

	def get_adaptive_short_position_size(self, fear_greed_index: int) -> float:
		"""
		📊 АДАПТИВНЫЙ РАЗМЕР ПОЗИЦИИ SHORT
		
		Определяет размер позиции на основе уровня страха.
		
		Параметры:
		- fear_greed_index: индекс страха/жадности (0-100)
		
		Возвращает:
		- float: размер позиции от 0.0 до 1.0
		"""
		if fear_greed_index < SHORT_FEAR_EXTREME_THRESHOLD:
			return SHORT_POSITION_SIZE_EXTREME_FEAR
		elif fear_greed_index < SHORT_FEAR_HIGH_THRESHOLD:
			return SHORT_POSITION_SIZE_HIGH_FEAR
		elif fear_greed_index < SHORT_FEAR_MODERATE_THRESHOLD:
			return SHORT_POSITION_SIZE_MODERATE_FEAR
		else:
			return SHORT_POSITION_SIZE_NEUTRAL

	def get_btc_dominance(self) -> float:
		"""
		📊 ПОЛУЧЕНИЕ BTC DOMINANCE
		
		Получает данные о доминировании Bitcoin.
		Рост доминирования усиливает SHORT сигналы на альтах.
		
		Возвращает:
		- float: изменение доминирования BTC в процентах
		"""
		try:
			# CoinGecko API для BTC dominance
			url = "https://api.coingecko.com/api/v3/global"
			response = requests.get(url, timeout=SHORT_API_TIMEOUT)
			
			if response.status_code == 200:
				data = response.json()
				btc_dominance = float(data['data']['market_cap_percentage']['btc'])
				
				# Получаем исторические данные для сравнения
				historical_url = "https://api.coingecko.com/api/v3/global"
				historical_response = requests.get(historical_url, timeout=SHORT_API_TIMEOUT)
				
				if historical_response.status_code == 200:
					historical_data = historical_response.json()
					# Упрощённый расчёт изменения (в реальности нужна история)
					dominance_change = 0.0  # По умолчанию
				else:
					dominance_change = 0.0
				
				logger.info(f"BTC Dominance: {btc_dominance:.1f}% (изменение: {dominance_change:+.1f}%)")
				return dominance_change
			else:
				logger.warning(f"Ошибка API BTC dominance: {response.status_code}")
				return SHORT_FALLBACK_BTC_DOMINANCE
				
		except Exception as e:
			logger.warning(f"Не удалось получить BTC dominance: {e}")
			return SHORT_FALLBACK_BTC_DOMINANCE

	def check_fear_inertia(self, fear_history: list) -> bool:
		"""
		🔄 ПРОВЕРКА ИНЕРЦИИ СТРАХА
		
		Проверяет, был ли страх < 30 в течение последних N свечей.
		
		Параметры:
		- fear_history: список последних значений страха
		
		Возвращает:
		- bool: True если инерция страха активна
		"""
		if len(fear_history) < SHORT_FEAR_INERTIA_CANDLES:
			return False
		
		# Проверяем последние N свечей
		recent_fears = fear_history[-SHORT_FEAR_INERTIA_CANDLES:]
		return all(fear < SHORT_FEAR_INERTIA_THRESHOLD for fear in recent_fears)

	def calculate_volatility_score(self, atr: float, atr_mean: float) -> float:
		"""
		📈 РАСЧЁТ СКОРА ВОЛАТИЛЬНОСТИ
		
		Вычисляет скор на основе волатильности (ATR).
		
		Параметры:
		- atr: текущий ATR
		- atr_mean: средний ATR за период
		
		Возвращает:
		- float: скор волатильности (0.0-1.0)
		"""
		if atr_mean == 0:
			return 0.0
		
		volatility_ratio = atr / atr_mean
		if volatility_ratio > SHORT_VOLATILITY_MULTIPLIER:
			return 1.0  # Высокая волатильность
		else:
			return 0.0  # Нормальная волатильность

	def calculate_adaptive_short_score_v2_1(
		self, 
		fear_greed_index: int, 
		funding_rate: float, 
		long_liquidations: float, 
		short_liquidations: float,
		rsi: float,
		ema_short: float,
		ema_long: float,
		atr: float,
		atr_mean: float,
		btc_dominance_change: float,
		fear_history: list = None
	) -> tuple:
		"""
		🧮 РАСЧЁТ АДАПТИВНОГО СКОРА SHORT v2.1
		
		Улучшенная версия с волатильностью, BTC dominance и инерцией страха.
		
		Параметры:
		- fear_greed_index: индекс страха/жадности (0-100)
		- funding_rate: funding rate в процентах
		- long_liquidations: ликвидации long позиций (USD)
		- short_liquidations: ликвидации short позиций (USD)
		- rsi: RSI значение
		- ema_short: быстрая EMA
		- ema_long: медленная EMA
		- atr: текущий ATR
		- atr_mean: средний ATR
		- btc_dominance_change: изменение доминирования BTC
		- fear_history: история значений страха
		
		Возвращает:
		- tuple: (score, breakdown) где score 0-1, breakdown - детализация
		"""
		# Компоненты скора v2.1
		fear_score = 1.0 if fear_greed_index < 45 else 0.0  # Увеличен порог
		funding_score = 1.0 if funding_rate < SHORT_FUNDING_RATE_THRESHOLD else 0.0
		
		# Ликвидации: больше long ликвидаций = больше SHORT сигнала
		if short_liquidations > 0:
			liquidation_ratio = long_liquidations / short_liquidations
			liquidation_score = 1.0 if liquidation_ratio > SHORT_LIQUIDATION_RATIO_THRESHOLD else 0.0
		else:
			liquidation_score = 0.0
		
		rsi_score = 1.0 if rsi > 70 else 0.0
		ema_score = 1.0 if ema_short < ema_long else 0.0
		
		# Новые компоненты v2.1
		volatility_score = self.calculate_volatility_score(atr, atr_mean)
		
		# BTC Dominance бонус
		btc_dominance_bonus = 0.0
		if (btc_dominance_change > SHORT_BTC_DOMINANCE_THRESHOLD and 
			fear_greed_index < SHORT_BTC_DOMINANCE_FEAR_THRESHOLD):
			btc_dominance_bonus = SHORT_BTC_DOMINANCE_BONUS
		
		# Inertia бонус
		inertia_bonus = 0.0
		if fear_history and self.check_fear_inertia(fear_history):
			inertia_bonus = SHORT_FEAR_INERTIA_BONUS
		
		# Взвешенный скор v2.1
		base_score = (
			fear_score * SHORT_FEAR_WEIGHT +
			funding_score * SHORT_FUNDING_WEIGHT +
			liquidation_score * SHORT_LIQUIDATION_WEIGHT +
			rsi_score * SHORT_RSI_WEIGHT +
			ema_score * SHORT_EMA_WEIGHT +
			volatility_score * SHORT_VOLATILITY_WEIGHT
		)
		
		# Применяем бонусы
		final_score = base_score + btc_dominance_bonus + inertia_bonus
		final_score = min(1.0, final_score)  # Ограничиваем максимумом
		
		# Детализация для логирования
		breakdown = {
			"fear_score": fear_score,
			"funding_score": funding_score,
			"liquidation_score": liquidation_score,
			"rsi_score": rsi_score,
			"ema_score": ema_score,
			"volatility_score": volatility_score,
			"btc_dominance_bonus": btc_dominance_bonus,
			"inertia_bonus": inertia_bonus,
			"base_score": base_score,
			"final_score": final_score,
			"weights": {
				"fear": SHORT_FEAR_WEIGHT,
				"funding": SHORT_FUNDING_WEIGHT,
				"liquidation": SHORT_LIQUIDATION_WEIGHT,
				"rsi": SHORT_RSI_WEIGHT,
				"ema": SHORT_EMA_WEIGHT,
				"volatility": SHORT_VOLATILITY_WEIGHT
			}
		}
		
		return final_score, breakdown

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
		# УПРОЩЁННАЯ ПРОВЕРКА КРИТИЧЕСКИХ КОНФЛИКТОВ (v5.5)
		# ====================================================================
		
		# Теперь проверяем только КРИТИЧЕСКИЕ конфликты, которые действительно важны
		# Убираем мелкие конфликты, которые блокировали хорошие сигналы
		indicator_conflicts = []
		conflict_detected = False
		
		# КРИТИЧЕСКИЙ КОНФЛИКТ #1: Экстремальное расхождение осцилляторов
		# Блокируем только если RSI и Stoch показывают ПРОТИВОПОЛОЖНЫЕ экстремумы
		rsi_extreme_oversold = rsi < 25  # Очень перепродан
		rsi_extreme_overbought = rsi > 75  # Очень перекуплен
		stoch_extreme_oversold = stoch_k < 15  # Очень перепродан
		stoch_extreme_overbought = stoch_k > 85  # Очень перекуплен
		
		if rsi_extreme_oversold and stoch_extreme_overbought:
			indicator_conflicts.append("⚠️ КРИТИЧНО: RSI перепродан, но Stochastic перекуплен")
			conflict_detected = True
		elif rsi_extreme_overbought and stoch_extreme_oversold:
			indicator_conflicts.append("⚠️ КРИТИЧНО: RSI перекуплен, но Stochastic перепродан")
			conflict_detected = True
		
		# КРИТИЧЕСКИЙ КОНФЛИКТ #2: Сильный нисходящий тренд + попытка BUY
		# Блокируем BUY только если ВСЕ трендовые индикаторы медвежьи + сильный downtrend
		ema_strong_down = ema_s < ema_l and sma_20 < sma_50
		macd_strong_bearish = macd < macd_signal and macd_hist < -0.0005  # Сильный negative momentum
		lr_strong_down = trend_direction == -1 and trend_strength > 0.7
		
		if ema_strong_down and macd_strong_bearish and lr_strong_down:
			indicator_conflicts.append("⚠️ КРИТИЧНО: Все индикаторы показывают сильный downtrend")
			# Не блокируем полностью - просто предупреждение, т.к. может быть MR opportunity
		
		# Убраны:
		# - RSI vs MACD конфликт (часто ложный)
		# - EMA vs MACD конфликт (нормальная дивергенция)
		# - Stoch vs RSI мелкие конфликты (разные периоды)
		# - ЛР vs индикаторы (ЛР может отставать)
		
		# Добавляем информацию о конфликтах в reasons
		if indicator_conflicts:
			for conflict in indicator_conflicts:
				reasons.append(conflict)
		
		# ====================================================================
		# SHORT-МЕХАНИКА v2.0 - ПОВЕДЕНЧЕСКИЕ СИГНАЛЫ
		# ====================================================================
		
		# Инициализация SHORT v2.0 переменных
		short_enabled = False
		short_score = 0.0
		short_position_size = 0.0
		short_conditions = []
		short_breakdown = {}
		funding_rate = 0.0
		long_liquidations = 0.0
		short_liquidations = 0.0
		
		# Получаем реальный индекс страха/жадности
		fear_greed_index = self.get_fear_greed_index()
		
		if USE_ADVANCED_SHORT:
			# Получаем дополнительные данные для SHORT v2.1
			funding_rate = self.get_funding_rate("BTCUSDT")
			long_liquidations, short_liquidations = self.get_liquidation_data("BTCUSDT")
			btc_dominance_change = self.get_btc_dominance()
			
			# Рассчитываем ATR для волатильности
			if hasattr(atr, 'tail'):
				atr_mean = atr.tail(20).mean() if len(atr) >= 20 else atr.mean()
			else:
				# Если atr это скаляр, используем его как среднее
				atr_mean = atr
			
			# Получаем историю страха (упрощённо - последние 5 значений)
			fear_history = [fear_greed_index]  # В реальности нужно хранить историю
			
			# Рассчитываем адаптивный скор SHORT v2.1
			short_score, short_breakdown = self.calculate_adaptive_short_score_v2_1(
				fear_greed_index, funding_rate, long_liquidations, short_liquidations,
				rsi, ema_s, ema_l, atr, atr_mean, btc_dominance_change, fear_history
			)
			
			# Проверяем активацию SHORT
			short_enabled = short_score >= SHORT_MIN_SCORE
			
			if short_enabled:
				# Адаптивный размер позиции
				short_position_size = self.get_adaptive_short_position_size(fear_greed_index)
				
				# Формируем условия для логирования v2.1
				if short_breakdown["fear_score"] > 0:
					short_conditions.append(f"Страх: {fear_greed_index} < 45")
				if short_breakdown["funding_score"] > 0:
					short_conditions.append(f"Funding: {funding_rate:.4f}% < 0")
				if short_breakdown["liquidation_score"] > 0:
					short_conditions.append(f"Ликвидации Long: ${long_liquidations:.1f}M > Short: ${short_liquidations:.1f}M")
				if short_breakdown["rsi_score"] > 0:
					short_conditions.append(f"RSI: {rsi:.1f} > 70")
				if short_breakdown["ema_score"] > 0:
					short_conditions.append(f"EMA: {ema_s:.2f} < {ema_l:.2f}")
				if short_breakdown["volatility_score"] > 0:
					volatility_ratio = atr / atr_mean if atr_mean > 0 else 1.0
					short_conditions.append(f"Волатильность: {volatility_ratio:.2f}x > 1.2x")
				if short_breakdown["btc_dominance_bonus"] > 0:
					short_conditions.append(f"BTC.D: +{btc_dominance_change:.1f}% при страхе {fear_greed_index}")
				if short_breakdown["inertia_bonus"] > 0:
					short_conditions.append(f"Инерция страха: {SHORT_FEAR_INERTIA_CANDLES} свечей < 30")
				
				# Добавляем голоса за SHORT
				bearish += int(short_score * 5)  # До 5 голосов за сильный SHORT
				reasons.append(f"🔴 SHORT v{SHORT_VERSION} АКТИВЕН: скор {short_score:.2f}, размер {short_position_size:.1%} [+{int(short_score * 5)}]")
				reasons.append(f"   Условия: {', '.join(short_conditions)}")
				
				# Детальное логирование v2.1
				logger.info(f"[SHORT v{SHORT_VERSION} ACTIVATION] Fear: {fear_greed_index}, Funding: {funding_rate:.4f}%, "
						   f"Volatility: {atr/atr_mean:.2f}x, BTC.D: {btc_dominance_change:+.1f}%, "
						   f"Long liq: ${long_liquidations:.1f}M > Short: ${short_liquidations:.1f}M, "
						   f"Score: {short_score:.2f} → SHORT CONFIRMED")
			else:
				reasons.append(f"🔴 SHORT v2.0 отключён: скор {short_score:.2f} < {SHORT_MIN_SCORE}")
		else:
			# Fallback на старую логику SHORT v1.0
			# Сбрасываем v2.0 поля при fallback
			short_score = 0.0
			short_position_size = 0.0
			short_breakdown = {}
			funding_rate = 0.0
			long_liquidations = 0.0
			short_liquidations = 0.0
			
			short_enabled = self.should_short(self.df, fear_greed_index)
			
			if short_enabled:
				# RSI > 70 (перекупленность)
				if rsi > 70:
					short_conditions.append(f"RSI={rsi:.1f} > 70 (перекупленность)")
				
				# Быстрая EMA ниже медленной (медвежий тренд)
				if ema_s < ema_l:
					short_conditions.append(f"EMA_short ({ema_s:.2f}) < EMA_long ({ema_l:.2f})")
				
				# ADX > 20 (выраженный тренд)
				if adx > 20:
					short_conditions.append(f"ADX={adx:.1f} > 20 (сильный тренд)")
				
				# Если все условия выполнены, добавляем SHORT голоса
				if len(short_conditions) >= 2:  # Минимум 2 из 3 условий
					bearish += 3  # Дополнительные голоса за SHORT
					reasons.append(f"🔴 SHORT v1.0 АКТИВЕН: {', '.join(short_conditions)} [+3]")
				else:
					reasons.append(f"🔴 SHORT v1.0 отключён: недостаточно условий ({len(short_conditions)}/3)")
			else:
				reasons.append(f"🔴 SHORT v1.0 отключён: режим не BEAR или страх < 40")

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
		# ВАЖНО: в TRENDING режиме конфликты осцилляторов - норма, не блокируем сигнал
		
		if conflict_detected and market_regime != "TRENDING":
			# Критический конфликт - индикаторы расходятся, игнорируем сигнал (ТОЛЬКО во флэте!)
			signal = "HOLD"
			signal_emoji = "⚠️"
			reasons.append(f"🚫 HOLD: Обнаружен конфликт индикаторов! Голосов {bullish} vs {bearish}")
		elif bullish - bearish >= VOTE_THRESHOLD and buy_filters_passed >= MIN_FILTERS:
			signal = "BUY"
			signal_emoji = "🟢"
			reasons.append(f"✅ BUY: Голосов {bullish} vs {bearish}, фильтров {buy_filters_passed}/5, ADX={adx:.1f}")
		elif bearish - bullish >= VOTE_THRESHOLD and sell_filters_passed >= MIN_FILTERS:
			# Проверяем, это обычный SELL или SHORT
			if short_enabled and len(short_conditions) >= 2:
				signal = "SHORT"
				signal_emoji = "🔴📉"
				reasons.append(f"✅ SHORT: Медвежий рынок + страх, голосов {bearish} vs {bullish}, фильтров {sell_filters_passed}/5")
			else:
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
			# SHORT-механика v1.0
			"short_enabled": short_enabled,
			"short_conditions": short_conditions,
			"fear_greed_index": fear_greed_index,
		# SHORT-механика v2.1 - Adaptive Fear SHORT
		"short_score": short_score,
		"short_position_size": short_position_size,
		"short_breakdown": short_breakdown,
		"funding_rate": funding_rate,
		"long_liquidations": long_liquidations,
		"short_liquidations": short_liquidations,
		"liquidation_ratio": long_liquidations / short_liquidations if short_liquidations > 0 else 0.0,
		"btc_dominance_change": btc_dominance_change if USE_ADVANCED_SHORT else 0.0,
		"volatility_ratio": atr / atr_mean if atr_mean > 0 and USE_ADVANCED_SHORT else 1.0,
		"short_version": SHORT_VERSION if USE_ADVANCED_SHORT else "1.0",
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
	
	def calculate_adaptive_position_size(
		self,
		bullish_votes: int,
		bearish_votes: int,
		adx: float,
		regime: str
	) -> float:
		"""
		🎯 АДАПТИВНЫЙ РАЗМЕР ПОЗИЦИИ v5.4
		
		Расчёт на основе:
		1. Силы сигнала (votes delta)
		2. Силы тренда/боковика (ADX)
		3. Текущего режима (MR/TF)
		
		Returns: position_size от 0.2 до 0.7
		"""
		votes_delta = bullish_votes - bearish_votes
		
		# Базовый размер по силе сигнала
		if votes_delta >= 7:
			base_size = 0.7  # Очень уверенный сигнал
		elif votes_delta >= 5:
			base_size = 0.5  # Уверенный сигнал
		elif votes_delta >= 3:
			base_size = 0.35  # Средний сигнал
		else:
			base_size = 0.25  # Слабый сигнал
		
		# Корректировка по ADX и режиму
		if regime == "TREND_FOLLOWING":
			# В тренде: чем сильнее ADX, тем больше позиция
			if adx > 35:
				multiplier = 1.3  # Сильный тренд +30%
			elif adx > 30:
				multiplier = 1.2  # Средний тренд +20%
			elif adx > 26:
				multiplier = 1.1  # Слабый тренд +10%
			else:
				multiplier = 1.0  # Нейтрально
		
		elif regime == "MEAN_REVERSION":
			# В боковике: чем слабее ADX, тем больше позиция
			if adx < 15:
				multiplier = 1.3  # Чёткий боковик +30%
			elif adx < 18:
				multiplier = 1.2  # Средний боковик +20%
			elif adx < 20:
				multiplier = 1.1  # Слабый боковик +10%
			else:
				multiplier = 1.0  # Нейтрально
		else:
			multiplier = 1.0
		
		# Применяем множитель
		final_size = base_size * multiplier
		
		# Ограничиваем диапазон 0.2-0.7
		final_size = max(0.2, min(0.7, final_size))
		
		return final_size
	
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
			price_vs_24h_low = (price - low_24h) / low_24h if low_24h > 0 else 0
			
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
				candle_change = (close_price - open_price) / open_price if open_price > 0 else 0
				
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
				candle_change = (close_price - open_price) / open_price if open_price > 0 else 0
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
				current_mode = "TRANSITION"  # Исправлено: должно быть TRANSITION, не HOLD
				reasons.append(f"⏸ ADX={adx:.1f} в переходной зоне [{HYBRID_ADX_MR_THRESHOLD}, {HYBRID_ADX_TF_THRESHOLD}] → TRANSITION")
			else:  # LAST
				current_mode = last_mode if last_mode else "TRANSITION"  # Исправлено: TRANSITION по умолчанию
				reasons.append(f"🔄 ADX={adx:.1f} в переходной зоне → используем последний режим ({current_mode})")
		
		# Проверяем минимальное время в режиме (защита от частого переключения)
		if last_mode is not None and last_mode != current_mode and last_mode_time < HYBRID_MIN_TIME_IN_MODE:
			current_mode = last_mode
			reasons.append(f"⏱ Остаёмся в режиме {last_mode} (прошло {last_mode_time:.1f}h < {HYBRID_MIN_TIME_IN_MODE}h)")
		
		# Генерируем сигнал в зависимости от режима
		if current_mode == "MR":
			signal_result = self.generate_signal_mean_reversion()
			signal_result["active_mode"] = "MEAN_REVERSION"
			signal_result["strategy"] = "HYBRID"
			# Добавляем reasons о режиме в начало
			signal_result["reasons"] = reasons + signal_result.get("reasons", [])
			
			# v5.4: Адаптивный размер позиции
			if signal_result["signal"] == "BUY":
				bullish_votes = signal_result.get("bullish_votes", 0)
				bearish_votes = signal_result.get("bearish_votes", 0)
				adaptive_size = self.calculate_adaptive_position_size(
					bullish_votes, bearish_votes, adx, "MEAN_REVERSION"
				)
				signal_result["position_size_percent"] = adaptive_size
				signal_result["reasons"].append(
					f"📊 Adaptive Size: {adaptive_size*100:.0f}% (votes={bullish_votes-bearish_votes}, ADX={adx:.1f})"
				)
		
		elif current_mode == "TF":
			signal_result = self.generate_signal()
			signal_result["active_mode"] = "TREND_FOLLOWING"
			signal_result["strategy"] = "HYBRID"
			# Добавляем reasons о режиме в начало
			signal_result["reasons"] = reasons + signal_result.get("reasons", [])
			
			# v5.4: Адаптивный размер позиции
			if signal_result["signal"] == "BUY":
				bullish_votes = signal_result.get("bullish_votes", 0)
				bearish_votes = signal_result.get("bearish_votes", 0)
				adaptive_size = self.calculate_adaptive_position_size(
					bullish_votes, bearish_votes, adx, "TREND_FOLLOWING"
				)
				signal_result["position_size_percent"] = adaptive_size
				signal_result["reasons"].append(
					f"📊 Adaptive Size: {adaptive_size*100:.0f}% (votes={bullish_votes-bearish_votes}, ADX={adx:.1f})"
				)
		
		else:  # HOLD или TRANSITION
			# Если переходная зона, всё равно генерируем полный сигнал для аналитики
			# но переопределяем его на HOLD
			signal_result = self.generate_signal()
			signal_result["signal"] = "HOLD"  # Принудительно HOLD в переходной зоне
			signal_result["signal_emoji"] = "⚠️"
			signal_result["active_mode"] = "TRANSITION"
			signal_result["strategy"] = "HYBRID"
			# Добавляем reason о переходной зоне в начало
			signal_result["reasons"] = reasons + signal_result.get("reasons", [])
		
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
		logger.info(f"MTF: загрузка данных для {symbol} на таймфреймах {MTF_TIMEFRAMES}")
		try:
			# Если уже в async контексте, используем gather, иначе создаём event loop
			try:
				loop = asyncio.get_running_loop()
				# Мы уже в async контексте - просто await
				tf_data = await fetch_all_timeframes()
				logger.info(f"MTF: данные загружены, получено {len(tf_data)} результатов")
			except RuntimeError:
				# Нет running loop - создаём новый
				tf_data = asyncio.run(fetch_all_timeframes())
				logger.info(f"MTF: данные загружены (new loop), получено {len(tf_data)} результатов")
		except Exception as e:
			logger.error(f"Ошибка загрузки MTF данных: {e}", exc_info=True)
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
			logger.debug(f"MTF: обработка {tf} (index={i})")
			if isinstance(tf_data[i], Exception):
				logger.warning(f"MTF: ошибка данных для {tf}: {tf_data[i]}")
				timeframe_signals[tf] = {
					"signal": "HOLD",
					"price": 0,
					"RSI": 0,
					"ADX": 0,
					"MACD_hist": 0,
					"market_regime": "NEUTRAL",
					"bullish_votes": 0,
					"bearish_votes": 0,
					"weight": MTF_WEIGHTS.get(tf, 0),
					"confidence": 0,
					"error": str(tf_data[i])
				}
				continue
			
			df = tf_data[i]
			logger.debug(f"MTF: DataFrame для {tf}: {len(df) if not df.empty else 0} строк")
			if df.empty:
				logger.warning(f"MTF: пустой DataFrame для {tf}")
				timeframe_signals[tf] = {
					"signal": "HOLD",
					"price": 0,
					"RSI": 0,
					"ADX": 0,
					"MACD_hist": 0,
					"market_regime": "NEUTRAL",
					"bullish_votes": 0,
					"bearish_votes": 0,
					"weight": MTF_WEIGHTS.get(tf, 0),
					"confidence": 0,
					"error": "Empty dataframe"
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
				signal = signal_result.get("signal", "HOLD")
				price = signal_result.get("price", 0)
				rsi = signal_result.get("RSI", 0)
				adx = signal_result.get("ADX", 0)
				
				logger.info(f"MTF: {tf} → {signal} (цена={price:.2f}, RSI={rsi:.1f}, ADX={adx:.1f})")
				
				timeframe_signals[tf] = {
					"signal": signal,
					"price": price,
					"RSI": rsi,
					"ADX": adx,
					"MACD_hist": signal_result.get("MACD_hist", 0),
					"market_regime": signal_result.get("market_regime", "NEUTRAL"),
					"bullish_votes": signal_result.get("bullish_votes", 0),
					"bearish_votes": signal_result.get("bearish_votes", 0),
					"weight": MTF_WEIGHTS.get(tf, 0),
					"confidence": signal_result.get("confidence", 0)
				}
				
			except Exception as e:
				logger.error(f"Ошибка генерации сигнала для {tf}: {e}", exc_info=True)
				timeframe_signals[tf] = {
					"signal": "HOLD",
					"price": 0,
					"RSI": 0,
					"ADX": 0,
					"MACD_hist": 0,
					"market_regime": "NEUTRAL",
					"bullish_votes": 0,
					"bearish_votes": 0,
					"weight": MTF_WEIGHTS.get(tf, 0),
					"confidence": 0,
					"error": str(e)
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
