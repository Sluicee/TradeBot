import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
import json
import os
from datetime import datetime, timedelta
from logger import logger

# ====================================================================
# BAYESIAN DECISION LAYER
# ====================================================================

class BayesianDecisionLayer:
	"""
	Храним статистику каждого типа сигнала и вычисляем вероятность успеха.
	P(profit | signal) = успешные сигналы / общее количество
	"""
	
	def __init__(self, stats_file: str = "signal_statistics.json"):
		self.stats_file = stats_file
		self.stats = self._load_stats()
	
	def _load_stats(self) -> Dict:
		"""Загружаем статистику из файла"""
		if os.path.exists(self.stats_file):
			try:
				with open(self.stats_file, 'r', encoding='utf-8') as f:
					return json.load(f)
			except Exception as e:
				logger.warning(f"Не удалось загрузить статистику: {e}")
		return {"signals": {}, "last_updated": None}
	
	def _save_stats(self):
		"""Сохраняем статистику в файл"""
		try:
			self.stats["last_updated"] = datetime.now().isoformat()
			with open(self.stats_file, 'w', encoding='utf-8') as f:
				json.dump(self.stats, f, ensure_ascii=False, indent=2)
		except Exception as e:
			logger.error(f"Ошибка сохранения статистики: {e}")
	
	def get_signal_signature(self, signal_data: Dict) -> str:
		"""
		Создаём уникальную сигнатуру сигнала на основе условий.
		Например: "RSI<30_EMA_CROSS_UP_ADX>25_TRENDING"
		"""
		components = []
		
		# RSI
		rsi = signal_data.get("RSI", 50)
		if rsi < 30:
			components.append("RSI<30")
		elif rsi < 40:
			components.append("RSI<40")
		elif rsi > 70:
			components.append("RSI>70")
		elif rsi > 60:
			components.append("RSI>60")
		else:
			components.append("RSI_NEUTRAL")
		
		# EMA Crossover
		ema_short = signal_data.get("EMA_short", 0)
		ema_long = signal_data.get("EMA_long", 0)
		if ema_short > ema_long:
			components.append("EMA_CROSS_UP")
		else:
			components.append("EMA_CROSS_DOWN")
		
		# ADX
		adx = signal_data.get("ADX", 0)
		if adx > 30:
			components.append("ADX>30")
		elif adx > 25:
			components.append("ADX>25")
		elif adx < 20:
			components.append("ADX<20")
		else:
			components.append("ADX_MODERATE")
		
		# Market Regime
		regime = signal_data.get("market_regime", "NEUTRAL")
		components.append(regime)
		
		# MACD
		macd_hist = signal_data.get("MACD_hist", 0)
		if macd_hist > 0:
			components.append("MACD_POS")
		else:
			components.append("MACD_NEG")
		
		return "_".join(components)
	
	def record_signal(self, signal_signature: str, signal_type: str, entry_price: float):
		"""Записываем новый сигнал"""
		if signal_signature not in self.stats["signals"]:
			self.stats["signals"][signal_signature] = {
				"total": 0,
				"profitable": 0,
				"losing": 0,
				"total_profit": 0.0,
				"total_loss": 0.0,
				"avg_profit": 0.0,
				"avg_loss": 0.0,
				"pending": []
			}
		
		# Добавляем в pending
		self.stats["signals"][signal_signature]["pending"].append({
			"signal_type": signal_type,
			"entry_price": entry_price,
			"timestamp": datetime.now().isoformat()
		})
		
		self._save_stats()
	
	def complete_signal(self, signal_signature: str, exit_price: float, entry_price: float):
		"""Завершаем сигнал и обновляем статистику"""
		if signal_signature not in self.stats["signals"]:
			return
		
		sig_stats = self.stats["signals"][signal_signature]
		profit_percent = ((exit_price - entry_price) / entry_price) * 100
		
		sig_stats["total"] += 1
		
		if profit_percent > 0:
			sig_stats["profitable"] += 1
			sig_stats["total_profit"] += profit_percent
			sig_stats["avg_profit"] = sig_stats["total_profit"] / sig_stats["profitable"]
		else:
			sig_stats["losing"] += 1
			sig_stats["total_loss"] += abs(profit_percent)
			sig_stats["avg_loss"] = sig_stats["total_loss"] / sig_stats["losing"] if sig_stats["losing"] > 0 else 0
		
		# Убираем из pending
		sig_stats["pending"] = [p for p in sig_stats["pending"] if abs(p["entry_price"] - entry_price) > 0.0001]
		
		self._save_stats()
	
	def get_success_probability(self, signal_signature: str, min_samples: int = 10) -> float:
		"""
		Вычисляем P(profit | signal) с учётом сглаживания (Bayesian smoothing).
		Используем Beta prior для сглаживания малых выборок.
		"""
		if signal_signature not in self.stats["signals"]:
			return 0.5  # Нет данных - нейтральная вероятность
		
		sig_stats = self.stats["signals"][signal_signature]
		total = sig_stats["total"]
		
		if total < min_samples:
			# Недостаточно данных - используем Bayesian prior
			# Prior: Beta(alpha=5, beta=5) = равномерное с небольшим смещением к 0.5
			alpha_prior = 5
			beta_prior = 5
			
			# Posterior: Beta(alpha + successes, beta + failures)
			alpha_post = alpha_prior + sig_stats["profitable"]
			beta_post = beta_prior + sig_stats["losing"]
			
			# Ожидаемое значение Beta распределения
			probability = alpha_post / (alpha_post + beta_post)
		else:
			# Достаточно данных - используем эмпирическую вероятность
			probability = sig_stats["profitable"] / total if total > 0 else 0.5
		
		return probability
	
	def should_take_signal(
		self, signal_signature: str, 
		min_probability: float = 0.55,
		min_samples: int = 10
	) -> Tuple[bool, float, str]:
		"""
		Решение: входить в сделку или нет.
		
		Returns:
			(should_take, probability, reason)
		"""
		prob = self.get_success_probability(signal_signature, min_samples)
		
		if signal_signature not in self.stats["signals"]:
			reason = f"Нет истории (P={prob:.2%}, используем prior)"
			return prob >= min_probability, prob, reason
		
		sig_stats = self.stats["signals"][signal_signature]
		total = sig_stats["total"]
		
		if total < min_samples:
			reason = f"Мало данных ({total} сигналов, P={prob:.2%} с prior)"
		else:
			profitable = sig_stats["profitable"]
			reason = f"История: {profitable}/{total} успешных (P={prob:.2%})"
		
		should_take = prob >= min_probability
		
		if should_take:
			avg_profit = sig_stats.get("avg_profit", 0)
			avg_loss = sig_stats.get("avg_loss", 0)
			if avg_profit > 0 and avg_loss > 0:
				risk_reward = avg_profit / avg_loss
				reason += f", R:R={risk_reward:.2f}"
		
		return should_take, prob, reason
	
	def get_stats_summary(self) -> str:
		"""Получить сводку по всей статистике"""
		if not self.stats["signals"]:
			return "Статистика пуста"
		
		lines = ["СТАТИСТИКА СИГНАЛОВ:\n"]
		
		# Сортируем по количеству сигналов
		sorted_sigs = sorted(
			self.stats["signals"].items(),
			key=lambda x: x[1]["total"],
			reverse=True
		)
		
		for sig_name, sig_stats in sorted_sigs[:10]:  # Топ-10
			total = sig_stats["total"]
			if total == 0:
				continue
			
			prof = sig_stats["profitable"]
			loss = sig_stats["losing"]
			prob = prof / total if total > 0 else 0
			
			avg_p = sig_stats.get("avg_profit", 0)
			avg_l = sig_stats.get("avg_loss", 0)
			
			lines.append(f"\n{sig_name[:60]}...")
			lines.append(f"  Всего: {total}, Win: {prof}, Loss: {loss}, P={prob:.1%}")
			lines.append(f"  Avg Profit: {avg_p:.2f}%, Avg Loss: {avg_l:.2f}%")
		
		return "\n".join(lines)


# ====================================================================
# Z-SCORE MEAN REVERSION ANALYZER
# ====================================================================

class ZScoreAnalyzer:
	"""
	Z-score анализ для выявления mean reversion сигналов.
	z = (price - SMA) / std(price - SMA)
	"""
	
	def __init__(self, window: int = 50, buy_threshold: float = -2.0, sell_threshold: float = 2.0):
		self.window = window
		self.buy_threshold = buy_threshold
		self.sell_threshold = sell_threshold
	
	def calculate_zscore(self, df: pd.DataFrame, column: str = "close") -> pd.Series:
		"""Вычисляем z-score для цены относительно SMA"""
		if len(df) < self.window:
			return pd.Series([0] * len(df), index=df.index)
		
		close = df[column].astype(float)
		sma = close.rolling(window=self.window).mean()
		
		# Отклонение от SMA
		deviation = close - sma
		
		# Стандартное отклонение отклонений
		std = deviation.rolling(window=self.window).std()
		
		# Z-score
		zscore = deviation / std
		zscore = zscore.fillna(0)
		
		return zscore
	
	def generate_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
		"""
		Генерируем сигнал mean reversion на основе z-score.
		
		Returns:
			{
				"signal": "BUY" | "SELL" | "HOLD",
				"zscore": float,
				"confidence": float,
				"reason": str
			}
		"""
		if df.empty or len(df) < self.window:
			return {
				"signal": "HOLD",
				"zscore": 0,
				"confidence": 0,
				"reason": "Недостаточно данных для z-score"
			}
		
		zscore_series = self.calculate_zscore(df)
		current_zscore = zscore_series.iloc[-1]
		
		signal = "HOLD"
		confidence = 0
		reason = ""
		
		if current_zscore <= self.buy_threshold:
			# Цена сильно ниже среднего - возможен отскок вверх
			signal = "BUY"
			confidence = min(1.0, abs(current_zscore) / abs(self.buy_threshold))
			reason = f"Z-score={current_zscore:.2f} < {self.buy_threshold} - цена перепродана (mean reversion)"
		elif current_zscore >= self.sell_threshold:
			# Цена сильно выше среднего - возможен откат вниз
			signal = "SELL"
			confidence = min(1.0, abs(current_zscore) / abs(self.sell_threshold))
			reason = f"Z-score={current_zscore:.2f} > {self.sell_threshold} - цена перекуплена (mean reversion)"
		else:
			reason = f"Z-score={current_zscore:.2f} - цена в норме"
		
		return {
			"signal": signal,
			"zscore": current_zscore,
			"confidence": confidence,
			"reason": reason
		}


# ====================================================================
# MARKOV REGIME SWITCHING MODEL
# ====================================================================

class MarkovRegimeSwitcher:
	"""
	Упрощённая Markov Switching Model для детекции режимов рынка.
	
	Режимы:
	- BULL: Бычий рынок (восходящий тренд, низкая волатильность)
	- BEAR: Медвежий рынок (нисходящий тренд, низкая волатильность)
	- HIGH_VOL: Высокая волатильность (любое направление)
	- SIDEWAYS: Боковик (флэт)
	"""
	
	def __init__(
		self,
		window: int = 50,
		vol_threshold_high: float = 0.03,  # 3% волатильность
		vol_threshold_low: float = 0.01,   # 1% волатильность
		trend_threshold: float = 0.02      # 2% тренд за период
	):
		self.window = window
		self.vol_threshold_high = vol_threshold_high
		self.vol_threshold_low = vol_threshold_low
		self.trend_threshold = trend_threshold
		
		# Transition matrix (примерная, можно обучать на истории)
		# P[from_state][to_state]
		self.transition_matrix = {
			"BULL": {"BULL": 0.85, "BEAR": 0.05, "HIGH_VOL": 0.05, "SIDEWAYS": 0.05},
			"BEAR": {"BULL": 0.05, "BEAR": 0.85, "HIGH_VOL": 0.05, "SIDEWAYS": 0.05},
			"HIGH_VOL": {"BULL": 0.25, "BEAR": 0.25, "HIGH_VOL": 0.30, "SIDEWAYS": 0.20},
			"SIDEWAYS": {"BULL": 0.20, "BEAR": 0.20, "HIGH_VOL": 0.10, "SIDEWAYS": 0.50}
		}
		
		self.current_regime = "SIDEWAYS"
		self.regime_history = []
	
	def calculate_returns(self, df: pd.DataFrame, window: int = None) -> float:
		"""Вычисляем доходность за окно"""
		if window is None:
			window = self.window
		
		if len(df) < window:
			return 0.0
		
		prices = df["close"].iloc[-window:]
		returns = (prices.iloc[-1] - prices.iloc[0]) / prices.iloc[0]
		
		return returns
	
	def calculate_volatility(self, df: pd.DataFrame, window: int = None) -> float:
		"""Вычисляем волатильность (стандартное отклонение логарифмических доходностей)"""
		if window is None:
			window = self.window
		
		if len(df) < window:
			return 0.0
		
		prices = df["close"].iloc[-window:]
		log_returns = np.log(prices / prices.shift(1)).dropna()
		
		volatility = log_returns.std()
		
		return volatility
	
	def detect_regime(self, df: pd.DataFrame) -> Dict[str, Any]:
		"""
		Определяем текущий режим рынка.
		
		Returns:
			{
				"regime": str,
				"confidence": float,
				"returns": float,
				"volatility": float,
				"reason": str
			}
		"""
		if len(df) < self.window:
			return {
				"regime": "SIDEWAYS",
				"confidence": 0.5,
				"returns": 0,
				"volatility": 0,
				"reason": "Недостаточно данных"
			}
		
		returns = self.calculate_returns(df)
		volatility = self.calculate_volatility(df)
		
		# Определяем режим по волатильности и доходности
		regime = "SIDEWAYS"
		confidence = 0.5
		reason = ""
		
		if volatility > self.vol_threshold_high:
			regime = "HIGH_VOL"
			confidence = min(1.0, volatility / self.vol_threshold_high)
			reason = f"Высокая волатильность {volatility:.2%}"
		elif abs(returns) < self.trend_threshold and volatility < self.vol_threshold_low:
			regime = "SIDEWAYS"
			confidence = 1.0 - (abs(returns) / self.trend_threshold)
			reason = f"Боковик: доходность {returns:.2%}, волатильность {volatility:.2%}"
		elif returns > self.trend_threshold:
			regime = "BULL"
			confidence = min(1.0, returns / (self.trend_threshold * 2))
			reason = f"Бычий рынок: доходность {returns:.2%}"
		elif returns < -self.trend_threshold:
			regime = "BEAR"
			confidence = min(1.0, abs(returns) / (self.trend_threshold * 2))
			reason = f"Медвежий рынок: доходность {returns:.2%}"
		
		# Обновляем текущий режим с учётом transition matrix (сглаживание)
		if self.current_regime:
			transition_prob = self.transition_matrix[self.current_regime].get(regime, 0.1)
			# Если вероятность перехода низкая - снижаем confidence
			confidence *= transition_prob * 2  # Boost для правдоподобных переходов
			confidence = min(1.0, confidence)
		
		self.current_regime = regime
		self.regime_history.append({
			"regime": regime,
			"timestamp": datetime.now().isoformat(),
			"returns": returns,
			"volatility": volatility
		})
		
		# Храним только последние 100 записей
		if len(self.regime_history) > 100:
			self.regime_history = self.regime_history[-100:]
		
		return {
			"regime": regime,
			"confidence": confidence,
			"returns": returns,
			"volatility": volatility,
			"reason": reason
		}
	
	def get_regime_stats(self) -> str:
		"""Статистика по режимам"""
		if not self.regime_history:
			return "Нет истории режимов"
		
		regimes = [r["regime"] for r in self.regime_history]
		from collections import Counter
		counts = Counter(regimes)
		
		lines = ["📈 СТАТИСТИКА РЕЖИМОВ:\n"]
		for regime, count in counts.most_common():
			percent = (count / len(regimes)) * 100
			lines.append(f"{regime}: {count} ({percent:.1f}%)")
		
		return "\n".join(lines)
	
	def should_trade_in_regime(self, regime: str, signal_type: str) -> Tuple[bool, str]:
		"""
		Определяем, стоит ли торговать в текущем режиме.
		
		Returns:
			(should_trade, reason)
		"""
		if regime == "HIGH_VOL":
			# В высокой волатильности торговать рискованно
			return False, "Высокая волатильность - риск слишком велик"
		
		elif regime == "BULL" and signal_type == "BUY":
			# В бычьем рынке покупаем на откатах
			return True, "Бычий рынок - BUY сигнал подходит"
		
		elif regime == "BEAR" and signal_type == "SELL":
			# В медвежьем рынке продаём на отскоках
			return True, "Медвежий рынок - SELL сигнал подходит"
		
		elif regime == "SIDEWAYS":
			# В боковике торгуем mean reversion
			return True, "Боковик - можно торговать mean reversion"
		
		else:
			# Несоответствие режима и сигнала
			return False, f"Режим {regime} не подходит для {signal_type}"


# ====================================================================
# ENSEMBLE DECISION MAKER
# ====================================================================

class EnsembleDecisionMaker:
	"""
	Объединяет все статистические модели для принятия финального решения.
	"""
	
	def __init__(
		self,
		bayesian_layer: BayesianDecisionLayer,
		zscore_analyzer: ZScoreAnalyzer,
		regime_switcher: MarkovRegimeSwitcher,
		bayesian_weight: float = 0.4,
		zscore_weight: float = 0.3,
		regime_weight: float = 0.3
	):
		self.bayesian = bayesian_layer
		self.zscore = zscore_analyzer
		self.regime = regime_switcher
		
		# Веса для weighted voting
		self.bayesian_weight = bayesian_weight
		self.zscore_weight = zscore_weight
		self.regime_weight = regime_weight
	
	def make_decision(
		self, 
		df: pd.DataFrame,
		original_signal: Dict[str, Any],
		min_probability: float = 0.55,
		min_samples: int = 10
	) -> Dict[str, Any]:
		"""
		Принимаем финальное решение с учётом всех моделей.
		
		Returns:
			{
				"final_signal": "BUY" | "SELL" | "HOLD",
				"confidence": float,
				"reasons": List[str],
				"models": {
					"bayesian": {...},
					"zscore": {...},
					"regime": {...}
				}
			}
		"""
		reasons = []
		
		# 1. Bayesian Decision
		signal_signature = self.bayesian.get_signal_signature(original_signal)
		should_take_bayesian, bayesian_prob, bayesian_reason = self.bayesian.should_take_signal(
			signal_signature, min_probability, min_samples
		)
		reasons.append(f"Bayesian: {bayesian_reason}")
		
		# 2. Z-Score Analysis
		zscore_result = self.zscore.generate_signal(df)
		reasons.append(f"Z-Score: {zscore_result['reason']}")
		
		# 3. Regime Detection
		regime_result = self.regime.detect_regime(df)
		reasons.append(f"Regime: {regime_result['reason']}")
		
		# 4. Проверяем, подходит ли режим для сигнала
		original_signal_type = original_signal.get("signal", "HOLD")
		should_trade_regime, regime_trade_reason = self.regime.should_trade_in_regime(
			regime_result["regime"], original_signal_type
		)
		reasons.append(f"Режим: {regime_trade_reason}")
		
		# 5. Weighted Voting
		buy_score = 0
		sell_score = 0
		hold_score = 0
		
		# Bayesian
		if should_take_bayesian:
			if original_signal_type == "BUY":
				buy_score += self.bayesian_weight * bayesian_prob
			elif original_signal_type == "SELL":
				sell_score += self.bayesian_weight * bayesian_prob
		else:
			hold_score += self.bayesian_weight
		
		# Z-Score
		if zscore_result["signal"] == "BUY":
			buy_score += self.zscore_weight * zscore_result["confidence"]
		elif zscore_result["signal"] == "SELL":
			sell_score += self.zscore_weight * zscore_result["confidence"]
		else:
			hold_score += self.zscore_weight * 0.5
		
		# Regime
		if should_trade_regime:
			if original_signal_type == "BUY":
				buy_score += self.regime_weight * regime_result["confidence"]
			elif original_signal_type == "SELL":
				sell_score += self.regime_weight * regime_result["confidence"]
		else:
			hold_score += self.regime_weight
		
		# 6. Финальное решение
		max_score = max(buy_score, sell_score, hold_score)
		
		if max_score == buy_score and buy_score > 0.5:
			final_signal = "BUY"
			confidence = buy_score
		elif max_score == sell_score and sell_score > 0.5:
			final_signal = "SELL"
			confidence = sell_score
		else:
			final_signal = "HOLD"
			confidence = hold_score
		
		reasons.append(f"\nФинальные оценки: BUY={buy_score:.2f}, SELL={sell_score:.2f}, HOLD={hold_score:.2f}")
		reasons.append(f"Решение: {final_signal} (confidence={confidence:.2%})")
		
		return {
			"final_signal": final_signal,
			"confidence": confidence,
			"reasons": reasons,
			"models": {
				"bayesian": {
					"should_take": should_take_bayesian,
					"probability": bayesian_prob,
					"signature": signal_signature
				},
				"zscore": zscore_result,
				"regime": regime_result
			}
		}

