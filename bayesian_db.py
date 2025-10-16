"""
Bayesian Decision Layer с поддержкой базы данных
Заменяет JSON файлы на SQLite/PostgreSQL
"""

from typing import Dict, Any, List, Tuple
from datetime import datetime
from logger import logger
from database import db


class BayesianDecisionLayerDB:
	"""
	Bayesian Decision Layer с сохранением в базу данных.
	Заменяет файловое хранение на БД для надежности.
	"""
	
	def __init__(self):
		"""Инициализация с подключением к БД"""
		self.db = db
		logger.info("Bayesian Decision Layer инициализирован с поддержкой БД")
	
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
		"""Записываем новый сигнал в БД"""
		try:
			# Добавляем в pending таблицу
			self.db.add_pending_signal(signal_signature, signal_type, entry_price)
			logger.debug(f"Записан pending сигнал: {signal_signature[:50]}...")
		except Exception as e:
			logger.error(f"Ошибка записи pending сигнала: {e}")
	
	def complete_signal(self, signal_signature: str, exit_price: float, entry_price: float):
		"""Завершаем сигнал и обновляем статистику в БД"""
		try:
			# Удаляем из pending
			self.db.remove_pending_signal(signal_signature, entry_price)
			
			# Вычисляем результат
			profit_percent = ((exit_price - entry_price) / entry_price) * 100
			
			# Получаем текущую статистику
			current_stats = self.db.get_bayesian_stats(signal_signature)
			
			if current_stats:
				# Обновляем существующую статистику
				total = current_stats["total"] + 1
				profitable = current_stats["profitable"]
				losing = current_stats["losing"]
				total_profit = current_stats["total_profit"]
				total_loss = current_stats["total_loss"]
				
				if profit_percent > 0:
					profitable += 1
					total_profit += profit_percent
					avg_profit = total_profit / profitable
					avg_loss = total_loss / losing if losing > 0 else 0
				else:
					losing += 1
					total_loss += abs(profit_percent)
					avg_profit = total_profit / profitable if profitable > 0 else 0
					avg_loss = total_loss / losing
				
				# Обновляем в БД
				self.db.update_bayesian_stats(signal_signature, {
					"total_signals": total,
					"profitable_signals": profitable,
					"losing_signals": losing,
					"total_profit": total_profit,
					"total_loss": total_loss,
					"avg_profit": avg_profit,
					"avg_loss": avg_loss
				})
			else:
				# Создаем новую запись
				stats_data = {
					"total_signals": 1,
					"profitable_signals": 1 if profit_percent > 0 else 0,
					"losing_signals": 0 if profit_percent > 0 else 1,
					"total_profit": profit_percent if profit_percent > 0 else 0,
					"total_loss": abs(profit_percent) if profit_percent <= 0 else 0,
					"avg_profit": profit_percent if profit_percent > 0 else 0,
					"avg_loss": abs(profit_percent) if profit_percent <= 0 else 0
				}
				self.db.update_bayesian_stats(signal_signature, stats_data)
			
			logger.debug(f"Завершен сигнал: {signal_signature[:50]}... (P&L: {profit_percent:+.1f}%)")
			
		except Exception as e:
			logger.error(f"Ошибка завершения сигнала: {e}")
	
	def get_success_probability(self, signal_signature: str, min_samples: int = 10) -> float:
		"""
		Вычисляем P(profit | signal) с учётом сглаживания (Bayesian smoothing).
		Используем Beta prior для сглаживания малых выборок.
		"""
		try:
			stats = self.db.get_bayesian_stats(signal_signature)
			
			if not stats:
				return 0.5  # Нет данных - нейтральная вероятность
			
			total = stats["total"]
			
			if total < min_samples:
				# Недостаточно данных - используем Bayesian prior
				# Prior: Beta(alpha=5, beta=5) = равномерное с небольшим смещением к 0.5
				alpha_prior = 5
				beta_prior = 5
				
				# Posterior: Beta(alpha + successes, beta + failures)
				alpha_post = alpha_prior + stats["profitable"]
				beta_post = beta_prior + stats["losing"]
				
				# Ожидаемое значение Beta распределения
				probability = alpha_post / (alpha_post + beta_post)
			else:
				# Достаточно данных - используем эмпирическую вероятность
				probability = stats["profitable"] / total if total > 0 else 0.5
			
			return probability
			
		except Exception as e:
			logger.error(f"Ошибка вычисления вероятности: {e}")
			return 0.5
	
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
		try:
			prob = self.get_success_probability(signal_signature, min_samples)
			stats = self.db.get_bayesian_stats(signal_signature)
			
			if not stats:
				reason = f"Нет истории (P={prob:.2%}, используем prior)"
				return prob >= min_probability, prob, reason
			
			total = stats["total"]
			
			if total < min_samples:
				reason = f"Мало данных ({total} сигналов, P={prob:.2%} с prior)"
			else:
				profitable = stats["profitable"]
				reason = f"История: {profitable}/{total} успешных (P={prob:.2%})"
			
			should_take = prob >= min_probability
			
			if should_take:
				avg_profit = stats.get("avg_profit", 0)
				avg_loss = stats.get("avg_loss", 0)
				if avg_profit > 0 and avg_loss > 0:
					risk_reward = avg_profit / avg_loss
					reason += f", R:R={risk_reward:.2f}"
			
			return should_take, prob, reason
			
		except Exception as e:
			logger.error(f"Ошибка принятия решения: {e}")
			return False, 0.5, f"Ошибка: {e}"
	
	def get_stats_summary(self) -> str:
		"""Получить сводку по всей статистике из БД"""
		try:
			all_stats = self.db.get_all_bayesian_stats()
			
			if not all_stats:
				return "Статистика пуста"
			
			lines = ["СТАТИСТИКА СИГНАЛОВ:\n"]
			
			# Сортируем по количеству сигналов
			sorted_stats = sorted(all_stats, key=lambda x: x["total"], reverse=True)
			
			for stats in sorted_stats[:10]:  # Топ-10
				total = stats["total"]
				if total == 0:
					continue
				
				prof = stats["profitable"]
				loss = stats["losing"]
				prob = prof / total if total > 0 else 0
				
				avg_p = stats.get("avg_profit", 0)
				avg_l = stats.get("avg_loss", 0)
				
				lines.append(f"\n{stats['signal_signature'][:60]}...")
				lines.append(f"  Всего: {total}, Win: {prof}, Loss: {loss}, P={prob:.1%}")
				lines.append(f"  Avg Profit: {avg_p:.2f}%, Avg Loss: {avg_l:.2f}%")
			
			return "\n".join(lines)
			
		except Exception as e:
			logger.error(f"Ошибка получения статистики: {e}")
			return f"Ошибка загрузки статистики: {e}"
	
	def migrate_from_json(self, json_file: str = "signal_statistics.json"):
		"""Миграция данных из JSON файла в БД"""
		import json
		import os
		
		if not os.path.exists(json_file):
			logger.info("JSON файл не найден, миграция не требуется")
			return
		
		try:
			with open(json_file, 'r', encoding='utf-8') as f:
				json_data = json.load(f)
			
			signals = json_data.get("signals", {})
			migrated = 0
			
			for signature, stats in signals.items():
				# Мигрируем статистику
				self.db.update_bayesian_stats(signature, {
					"total_signals": stats.get("total", 0),
					"profitable_signals": stats.get("profitable", 0),
					"losing_signals": stats.get("losing", 0),
					"total_profit": stats.get("total_profit", 0.0),
					"total_loss": stats.get("total_loss", 0.0),
					"avg_profit": stats.get("avg_profit", 0.0),
					"avg_loss": stats.get("avg_loss", 0.0)
				})
				migrated += 1
			
			logger.info(f"Мигрировано {migrated} сигналов из JSON в БД")
			
			# Переименовываем JSON файл как резервную копию
			backup_file = f"{json_file}.backup"
			os.rename(json_file, backup_file)
			logger.info(f"JSON файл переименован в {backup_file}")
			
		except Exception as e:
			logger.error(f"Ошибка миграции из JSON: {e}")
