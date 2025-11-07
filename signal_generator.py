import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from logger import logger
from config import (
	# Индикаторы
	ADX_WINDOW, RSI_OVERSOLD, RSI_OVERSOLD_NEAR, RSI_OVERBOUGHT, RSI_OVERBOUGHT_NEAR,
	STOCH_OVERSOLD, STOCH_OVERBOUGHT, VOLUME_HIGH_RATIO, VOLUME_MODERATE_RATIO, VOLUME_LOW_RATIO,
	RSI_OVERBOUGHT, ADX_RANGING, MIN_FILTERS, MIN_FILTERS_SELL
)

# Импортируем модули
from indicators import IndicatorsCalculator
from market_regime import MarketRegimeDetector
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

	def get_market_regime(self, df: pd.DataFrame) -> str:
		"""
		🎯 ОПРЕДЕЛЕНИЕ РЫНОЧНОГО РЕЖИМА
		
		Анализирует EMA200 и ADX для определения режима рынка.
		
		Параметры:
		- df: DataFrame с данными
		
		Возвращает:
		- "BEAR": медвежий рынок (EMA200 падает)
		- "BULL": бычий рынок (EMA200 растёт)
		- "NEUTRAL": нейтральный режим
		"""
		if len(df) < 200:
			return "NEUTRAL"
		
		try:
			# EMA200 и её наклон
			import ta
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
			if slope < -0.001:  # EMA200 падает
				return "BEAR"
			elif slope > 0.001:  # EMA200 растёт
				return "BULL"
			else:
				return "NEUTRAL"
		except Exception:
			return "NEUTRAL"


	

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
		
		
		# Принимаем решение
		signal = "HOLD"
		signal_emoji = "⚠️"
		
		if bullish - bearish >= vote_threshold and buy_filters_passed >= min_filters:
			signal = "BUY"
			signal_emoji = "🟢"
			reasons.append(f"✅ BUY: Голосов {bullish} vs {bearish}, фильтров {buy_filters_passed}/{min_filters}")
		elif bearish - bullish >= vote_threshold and sell_filters_passed >= MIN_FILTERS_SELL:
				signal = "SELL"
				signal_emoji = "🔴"
				reasons.append(f"✅ SELL: Голосов {bearish} vs {bullish}, фильтров {sell_filters_passed}/{MIN_FILTERS_SELL}")
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
		mtf_analyzer = MultiTimeframeAnalyzer(lambda df=None: SignalGenerator(df if df is not None else self.df, self.use_statistical_models))
		return await mtf_analyzer.generate_signal_multi_timeframe(data_provider, symbol, strategy)
