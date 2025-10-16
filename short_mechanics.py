import requests
import json
import ta
from typing import Dict, Any, Optional, Tuple
from logger import logger
from config import (
	# SHORT v2.1 - Adaptive Fear SHORT
	USE_ADVANCED_SHORT, SHORT_VERSION, SHORT_POSITION_SIZE_EXTREME_FEAR, SHORT_POSITION_SIZE_HIGH_FEAR,
	SHORT_POSITION_SIZE_MODERATE_FEAR, SHORT_POSITION_SIZE_NEUTRAL,
	SHORT_FEAR_EXTREME_THRESHOLD, SHORT_FEAR_HIGH_THRESHOLD, SHORT_FEAR_MODERATE_THRESHOLD, SHORT_GREED_THRESHOLD, SHORT_EMA_SLOPE_THRESHOLD, SHORT_MAX_VOTES, SHORT_V1_VOTES, SHORT_V1_MIN_CONDITIONS,
	SHORT_FEAR_INERTIA_THRESHOLD, SHORT_FEAR_INERTIA_CANDLES, SHORT_FEAR_INERTIA_BONUS,
	SHORT_FEAR_WEIGHT, SHORT_FUNDING_WEIGHT, SHORT_LIQUIDATION_WEIGHT, SHORT_RSI_WEIGHT, SHORT_EMA_WEIGHT, SHORT_VOLATILITY_WEIGHT,
	SHORT_MIN_SCORE, SHORT_API_TIMEOUT, SHORT_FUNDING_RATE_THRESHOLD, SHORT_LIQUIDATION_RATIO_THRESHOLD,
	SHORT_VOLATILITY_MULTIPLIER, SHORT_VOLATILITY_BONUS, SHORT_BTC_DOMINANCE_THRESHOLD,
	SHORT_BTC_DOMINANCE_FEAR_THRESHOLD, SHORT_BTC_DOMINANCE_BONUS,
	SHORT_FALLBACK_FUNDING_RATE, SHORT_FALLBACK_LONG_LIQUIDATIONS, SHORT_FALLBACK_SHORT_LIQUIDATIONS, SHORT_FALLBACK_BTC_DOMINANCE,
	RSI_OVERBOUGHT, ADX_RANGING
)

class ShortMechanics:
	"""
	🔴 SHORT-МЕХАНИКА v2.1 - ADAPTIVE FEAR SHORT
	
	Отвечает за:
	- Получение индекса страха/жадности
	- Анализ funding rate и ликвидаций
	- Расчёт адаптивного скора SHORT
	- Определение размера позиции
	"""
	
	def __init__(self):
		pass
	
	def get_market_regime(self, df, fear_greed_index: int = 50) -> str:
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
			if slope < -SHORT_EMA_SLOPE_THRESHOLD and fear_greed_index < SHORT_FEAR_MODERATE_THRESHOLD:  # Более мягкие условия
				return "BEAR"
			elif slope > SHORT_EMA_SLOPE_THRESHOLD and fear_greed_index > SHORT_GREED_THRESHOLD:
				return "BULL"
			else:
				return "NEUTRAL"
		except Exception:
			return "NEUTRAL"

	def should_short(self, df, fear_greed_index: int = 50) -> bool:
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

	def get_fear_greed_index(self, df) -> int:
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
		return self._calculate_custom_fear_greed_index(df)
	
	def _calculate_custom_fear_greed_index(self, df) -> int:
		"""
		🧮 СОБСТВЕННЫЙ РАСЧЁТ ИНДЕКСА СТРАХА/ЖАДНОСТИ
		
		Анализирует волатильность, объёмы и тренды для определения настроений рынка.
		
		Возвращает:
		- int: индекс от 0 (страх) до 100 (жадность)
		"""
		if len(df) < 50:
			return 50  # Нейтрально при недостатке данных
		
		try:
			import ta
			# 1. Анализ волатильности (высокая волатильность = страх)
			atr = ta.volatility.average_true_range(
				df['high'], df['low'], df['close'], window=14
			)
			current_atr = atr.iloc[-1]
			avg_atr = atr.tail(20).mean()
			volatility_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0
			
			# 2. Анализ объёмов (высокие объёмы при падении = страх)
			volume = df['volume']
			current_volume = volume.iloc[-1]
			avg_volume = volume.tail(20).mean()
			volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
			
			# 3. Анализ тренда (падение = страх)
			price_change_1d = (df['close'].iloc[-1] - df['close'].iloc[-24]) / df['close'].iloc[-24] if len(df) >= 24 else 0
			price_change_7d = (df['close'].iloc[-1] - df['close'].iloc[-168]) / df['close'].iloc[-168] if len(df) >= 168 else 0
			
			# 4. RSI анализ (перепроданность = страх)
			rsi = ta.momentum.rsi(df['close'], window=14)
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

	def analyze_short_conditions(self, indicators_data: Dict[str, Any], fear_greed_index: int) -> Dict[str, Any]:
		"""
		🔴 АНАЛИЗ SHORT УСЛОВИЙ
		
		Анализирует все условия для SHORT сигналов и возвращает результат.
		"""
		# Инициализация SHORT v2.0 переменных
		short_enabled = False
		short_score = 0.0
		short_position_size = 0.0
		short_conditions = []
		short_breakdown = {}
		funding_rate = 0.0
		long_liquidations = 0.0
		short_liquidations = 0.0
		
		# Получаем данные индикаторов
		rsi = indicators_data.get("RSI", 50)
		ema_s = indicators_data.get("EMA_short", 0)
		ema_l = indicators_data.get("EMA_long", 0)
		adx = indicators_data.get("ADX", 0)
		atr = indicators_data.get("ATR", 0)
		
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
					short_conditions.append(f"Страх: {fear_greed_index} < {SHORT_FEAR_MODERATE_THRESHOLD}")
				if short_breakdown["funding_score"] > 0:
					short_conditions.append(f"Funding: {funding_rate:.4f}% < 0")
				if short_breakdown["liquidation_score"] > 0:
					short_conditions.append(f"Ликвидации Long: ${long_liquidations:.1f}M > Short: ${short_liquidations:.1f}M")
				if short_breakdown["rsi_score"] > 0:
					short_conditions.append(f"RSI: {rsi:.1f} > {RSI_OVERBOUGHT}")
				if short_breakdown["ema_score"] > 0:
					short_conditions.append(f"EMA: {ema_s:.2f} < {ema_l:.2f}")
				if short_breakdown["volatility_score"] > 0:
					volatility_ratio = atr / atr_mean if atr_mean > 0 else 1.0
					short_conditions.append(f"Волатильность: {volatility_ratio:.2f}x > {SHORT_VOLATILITY_MULTIPLIER}x")
				if short_breakdown["btc_dominance_bonus"] > 0:
					short_conditions.append(f"BTC.D: +{btc_dominance_change:.1f}% при страхе {fear_greed_index}")
				if short_breakdown["inertia_bonus"] > 0:
					short_conditions.append(f"Инерция страха: {SHORT_FEAR_INERTIA_CANDLES} свечей < {SHORT_FEAR_INERTIA_THRESHOLD}")
		else:
			# Fallback на старую логику SHORT v1.0
			short_enabled = self.should_short(self.df, fear_greed_index)
			
			if short_enabled:
				# RSI > 70 (перекупленность)
				if rsi > RSI_OVERBOUGHT:
					short_conditions.append(f"RSI={rsi:.1f} > {RSI_OVERBOUGHT} (перекупленность)")
				
				# Быстрая EMA ниже медленной (медвежий тренд)
				if ema_s < ema_l:
					short_conditions.append(f"EMA_short ({ema_s:.2f}) < EMA_long ({ema_l:.2f})")
				
				# ADX > 20 (выраженный тренд)
				if adx > ADX_RANGING:
					short_conditions.append(f"ADX={adx:.1f} > {ADX_RANGING} (сильный тренд)")
		
		return {
			"short_enabled": short_enabled,
			"short_score": short_score,
			"short_position_size": short_position_size,
			"short_conditions": short_conditions,
			"short_breakdown": short_breakdown,
			"funding_rate": funding_rate,
			"long_liquidations": long_liquidations,
			"short_liquidations": short_liquidations,
			"liquidation_ratio": long_liquidations / short_liquidations if short_liquidations > 0 else 0.0,
			"btc_dominance_change": btc_dominance_change if USE_ADVANCED_SHORT else 0.0,
			"volatility_ratio": atr / atr_mean if atr_mean > 0 and USE_ADVANCED_SHORT else 1.0,
			"short_version": SHORT_VERSION if USE_ADVANCED_SHORT else "1.0"
		}
