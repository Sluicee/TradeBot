import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from logger import logger
from config import (
	# Индикаторы
	ADX_WINDOW, RSI_OVERSOLD, RSI_OVERSOLD_NEAR, RSI_OVERBOUGHT, RSI_OVERBOUGHT_NEAR,
	STOCH_OVERSOLD, STOCH_OVERBOUGHT, VOLUME_HIGH_RATIO, VOLUME_MODERATE_RATIO, VOLUME_LOW_RATIO,
	# SHORT v2.1 - Adaptive Fear SHORT
	USE_ADVANCED_SHORT, SHORT_VERSION, SHORT_MAX_VOTES, SHORT_V1_VOTES, SHORT_V1_MIN_CONDITIONS,
	SHORT_FEAR_MODERATE_THRESHOLD, SHORT_FEAR_EXTREME_THRESHOLD, SHORT_FEAR_HIGH_THRESHOLD,
	SHORT_FUNDING_RATE_THRESHOLD, SHORT_LIQUIDATION_RATIO_THRESHOLD, SHORT_EMA_SLOPE_THRESHOLD,
	SHORT_GREED_THRESHOLD, SHORT_BTC_DOMINANCE_THRESHOLD, SHORT_BTC_DOMINANCE_FEAR_THRESHOLD,
	SHORT_FEAR_INERTIA_THRESHOLD, SHORT_FEAR_INERTIA_CANDLES, SHORT_MIN_SCORE, SHORT_VOLATILITY_MULTIPLIER,
	SHORT_FEAR_WEIGHT, SHORT_FUNDING_WEIGHT, SHORT_LIQUIDATION_WEIGHT, SHORT_RSI_WEIGHT,
	SHORT_EMA_WEIGHT, SHORT_VOLATILITY_WEIGHT, SHORT_FEAR_INERTIA_BONUS, SHORT_BTC_DOMINANCE_BONUS,
	RSI_OVERBOUGHT, ADX_RANGING
)

# Импортируем модули
from indicators import IndicatorsCalculator
from market_regime import MarketRegimeDetector
from short_mechanics import ShortMechanics
from strategies import MeanReversionStrategy, HybridStrategy
from multi_timeframe import MultiTimeframeAnalyzer

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
		
		# Инициализируем модули
		self.indicators_calculator = IndicatorsCalculator(self.df)
		self.market_regime_detector = MarketRegimeDetector(self.df)
		self.short_mechanics = ShortMechanics()
		self.mean_reversion_strategy = MeanReversionStrategy(self.df)
		self.hybrid_strategy = HybridStrategy(self.df, self, self.mean_reversion_strategy)
		
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
		- "BEAR": медвежий рынок (EMA200 падает, ADX>20, страх<{SHORT_FEAR_MODERATE_THRESHOLD})
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
			if slope < -SHORT_EMA_SLOPE_THRESHOLD and fear_greed_index < SHORT_FEAR_MODERATE_THRESHOLD:  # Более мягкие условия
				return "BEAR"
			elif slope > SHORT_EMA_SLOPE_THRESHOLD and fear_greed_index > SHORT_GREED_THRESHOLD:
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
		# SHORT активируется в медвежьем режиме (BEAR) или при страхе в любом режиме
		return (regime == "BEAR" or fear_greed_index < SHORT_FEAR_MODERATE_THRESHOLD)

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
		fear_score = 1.0 if fear_greed_index < SHORT_FEAR_MODERATE_THRESHOLD else 0.0
		funding_score = 1.0 if funding_rate < SHORT_FUNDING_RATE_THRESHOLD else 0.0
		
		# Ликвидации: больше long ликвидаций = больше SHORT сигнала
		if short_liquidations > 0:
			liquidation_ratio = long_liquidations / short_liquidations
			liquidation_score = 1.0 if liquidation_ratio > SHORT_LIQUIDATION_RATIO_THRESHOLD else 0.0
		else:
			liquidation_score = 0.0
		
		rsi_score = 1.0 if rsi > RSI_OVERBOUGHT else 0.0
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
		fear_score = 1.0 if fear_greed_index < SHORT_FEAR_MODERATE_THRESHOLD else 0.0
		funding_score = 1.0 if funding_rate < SHORT_FUNDING_RATE_THRESHOLD else 0.0
		
		# Ликвидации: больше long ликвидаций = больше SHORT сигнала
		if short_liquidations > 0:
			liquidation_ratio = long_liquidations / short_liquidations
			liquidation_score = 1.0 if liquidation_ratio > SHORT_LIQUIDATION_RATIO_THRESHOLD else 0.0
		else:
			liquidation_score = 0.0
		
		rsi_score = 1.0 if rsi > RSI_OVERBOUGHT else 0.0
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
		"""
		📊 ВЫЧИСЛЕНИЕ ИНДИКАТОРОВ
		
		Делегирует вычисление индикаторов соответствующему модулю.
		"""
		self.df = self.indicators_calculator.compute_indicators(
			ema_short_window, ema_long_window, rsi_window,
			macd_fast, macd_slow, macd_signal
		)
		
		# Обновляем все модули с новым DataFrame
		self.market_regime_detector.df = self.df.copy()
		self.mean_reversion_strategy.df = self.df.copy()
		self.hybrid_strategy.df = self.df.copy()
		
		return self.df

	def generate_signal(self) -> Dict[str, Any]:
		"""
		🎯 ОСНОВНОЙ МЕТОД ГЕНЕРАЦИИ СИГНАЛОВ
		
		Использует модульную архитектуру для генерации сигналов.
		"""
		if self.df.empty:
			raise ValueError("DataFrame is empty")
		
		try:
			# Получаем данные индикаторов
			indicators_data = self.indicators_calculator.get_indicators_data()
		except ValueError as e:
			# Недостаточно данных для расчета индикаторов
			logger.warning(f"Недостаточно данных для расчёта индикаторов: {e}")
			return {
				"signal": "HOLD",
				"reasons": [f"⚠️ Недостаточно данных для расчёта индикаторов"],
				"price": float(self.df["close"].iloc[-1]),
				"market_regime": "NONE",
				"bullish_votes": 0,
				"bearish_votes": 0,
				"vote_delta": 0,
				"filters_passed": 0,
				"short_enabled": False,
				"short_conditions": [],
				"indicators": {
					"RSI": "н/д",
					"ADX": "н/д",
					"MACD": "н/д"
				}
			}
		
		# Определяем режим рынка
		regime_data = self.market_regime_detector.detect_market_regime(indicators_data)
		
		# Анализируем систему голосования
		voting_data = self.market_regime_detector.analyze_voting_system(indicators_data, regime_data)
		
		# Проверяем фильтры
		filters_data = self.market_regime_detector.check_filters(indicators_data)
		
		# Получаем индекс страха/жадности
		fear_greed_index = self.short_mechanics.get_fear_greed_index(self.df)
		
		# Анализируем SHORT условия
		short_data = self.short_mechanics.analyze_short_conditions(indicators_data, fear_greed_index)
		
		# ====================================================================
		# ПРИНЯТИЕ РЕШЕНИЯ
		# ====================================================================
		
		# Извлекаем данные для принятия решения
		bullish = voting_data.get("bullish_votes", 0)
		bearish = voting_data.get("bearish_votes", 0)
		reasons = voting_data.get("reasons", [])
		
		market_regime = regime_data.get("market_regime", "NEUTRAL")
		vote_threshold = regime_data.get("vote_threshold", 3)
		
		buy_filters_passed = filters_data.get("buy_filters_passed", 0)
		sell_filters_passed = filters_data.get("sell_filters_passed", 0)
		min_filters = filters_data.get("min_filters", 3)
		
		# SHORT данные
		short_enabled = short_data.get("short_enabled", False)
		short_conditions = short_data.get("short_conditions", [])
		
		# Принимаем решение
		signal = "HOLD"
		signal_emoji = "⚠️"
		
		if bullish - bearish >= vote_threshold and buy_filters_passed >= min_filters:
			signal = "BUY"
			signal_emoji = "🟢"
			reasons.append(f"✅ BUY: Голосов {bullish} vs {bearish}, фильтров {buy_filters_passed}/{min_filters}")
		elif bearish - bullish >= vote_threshold and sell_filters_passed >= min_filters:
			# Проверяем, это обычный SELL или SHORT
			if short_enabled and len(short_conditions) >= 2:
				signal = "SHORT"
				signal_emoji = "🔴📉"
				reasons.append(f"✅ SHORT: Медвежий рынок + страх, голосов {bearish} vs {bullish}, фильтров {sell_filters_passed}/{min_filters}")
			else:
				signal = "SELL"
				signal_emoji = "🔴"
				reasons.append(f"✅ SELL: Голосов {bearish} vs {bullish}, фильтров {sell_filters_passed}/{min_filters}")
		else:
			reasons.append(f"⏸ HOLD: Бычьи {bullish} vs Медвежьи {bearish}, фильтров BUY:{buy_filters_passed} SELL:{sell_filters_passed}, режим: {market_regime}")

		# Формируем результат
		base_result = {
			"signal": signal,
			"signal_emoji": signal_emoji,
			"price": indicators_data.get("price", 0),
			"EMA_short": indicators_data.get("EMA_short", 0),
			"EMA_long": indicators_data.get("EMA_long", 0),
			"RSI": indicators_data.get("RSI", 50),
			"MACD": indicators_data.get("MACD", 0),
			"MACD_signal": indicators_data.get("MACD_signal", 0),
			"MACD_hist": indicators_data.get("MACD_hist", 0),
			"ADX": indicators_data.get("ADX", 0),
			"ATR": indicators_data.get("ATR", 0),
			"volume_ratio": indicators_data.get("volume_ratio", 1.0),
			"market_regime": market_regime,
			"bullish_votes": bullish,
			"bearish_votes": bearish,
			"buy_filters_passed": buy_filters_passed,
			"sell_filters_passed": sell_filters_passed,
			"indicator_conflicts": [],
			"conflict_detected": False,
			# SHORT-механика
			"short_enabled": short_enabled,
			"short_conditions": short_conditions,
			"fear_greed_index": fear_greed_index,
			"short_score": short_data.get("short_score", 0.0),
			"short_position_size": short_data.get("short_position_size", 0.0),
			"short_breakdown": short_data.get("short_breakdown", {}),
			"funding_rate": short_data.get("funding_rate", 0.0),
			"long_liquidations": short_data.get("long_liquidations", 0.0),
			"short_liquidations": short_data.get("short_liquidations", 0.0),
			"liquidation_ratio": short_data.get("liquidation_ratio", 0.0),
			"btc_dominance_change": short_data.get("btc_dominance_change", 0.0),
			"volatility_ratio": short_data.get("volatility_ratio", 1.0),
			"short_version": short_data.get("short_version", "1.0"),
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
		
		Делегирует генерацию сигнала соответствующему модулю.
		"""
		return self.mean_reversion_strategy.generate_signal()
	
	def generate_signal_hybrid(self, last_mode: str = None, last_mode_time: float = 0) -> Dict[str, Any]:
		"""
		🔀 ГИБРИДНАЯ СТРАТЕГИЯ
		
		Делегирует генерацию сигнала соответствующему модулю.
		"""
		return self.hybrid_strategy.generate_signal(last_mode, last_mode_time)
	
	async def generate_signal_multi_timeframe(
		self,
		data_provider,
		symbol: str,
		strategy: str = "TREND_FOLLOWING"
	) -> Dict[str, Any]:
		"""
		🔀 MULTI-TIMEFRAME ANALYSIS
		
		Делегирует мультитаймфрейм анализ соответствующему модулю.
		"""
		mtf_analyzer = MultiTimeframeAnalyzer(lambda df=None: SignalGenerator(df or self.df, self.use_statistical_models))
		return await mtf_analyzer.generate_signal_multi_timeframe(data_provider, symbol, strategy)
