"""
🔍 ДИАГНОСТИКА СИГНАЛОВ v5.5

Утилиты для детального логирования и анализа генерации сигналов.
Помогает понять почему нет сигналов или почему их слишком много.
"""

from datetime import datetime
from typing import Dict, Any, List
from logger import logger
import config


class SignalDiagnostics:
	"""Класс для диагностики сигналов"""
	
	def __init__(self):
		self.signal_history = []
		self.last_buy_time = None
		self.buy_signals_count = 0
		self.hold_signals_count = 0
		self.sell_signals_count = 0
		self.blocked_reasons = {}
		
	def log_signal_generation(
		self,
		symbol: str,
		signal_result: Dict[str, Any],
		price: float,
		can_buy: bool = True,
		block_reason: str = None,
		compact: bool = True
	):
		"""
		Логирует детальную информацию о генерации сигнала.
		
		Args:
			symbol: Символ пары
			signal_result: Результат от generate_signal_hybrid()
			price: Текущая цена
			can_buy: Можно ли открыть позицию
			block_reason: Причина блокировки (если can_buy=False)
			compact: Компактный режим логирования
		"""
		timestamp = datetime.now().isoformat()
		signal = signal_result.get("signal", "UNKNOWN")
		active_mode = signal_result.get("active_mode", "UNKNOWN")
		bullish_votes = signal_result.get("bullish_votes", 0)
		bearish_votes = signal_result.get("bearish_votes", 0)
		votes_delta = bullish_votes - bearish_votes
		reasons = signal_result.get("reasons", [])
		position_size = signal_result.get("position_size_percent", 0)
		
		# Базовая статистика
		if signal == "BUY":
			self.buy_signals_count += 1
		elif signal == "SELL":
			self.sell_signals_count += 1
		else:
			self.hold_signals_count += 1
		
		# Подсчёт причин блокировки
		if signal == "BUY" and not can_buy and block_reason:
			self.blocked_reasons[block_reason] = self.blocked_reasons.get(block_reason, 0) + 1
		
		# Сохраняем в историю
		signal_record = {
			"timestamp": timestamp,
			"symbol": symbol,
			"signal": signal,
			"mode": active_mode,
			"price": price,
			"bullish_votes": bullish_votes,
			"bearish_votes": bearish_votes,
			"votes_delta": votes_delta,
			"position_size": position_size,
			"can_buy": can_buy,
			"block_reason": block_reason,
			"reasons": reasons[:3]  # Топ-3 причины
		}
		self.signal_history.append(signal_record)
		
		# Компактное или детальное логирование
		if compact:
			# Компактный режим - только важная информация
			if signal == "BUY":
				status = "BLOCKED" if not can_buy else "READY"
				block_info = f" ({block_reason})" if not can_buy else ""
				logger.info(f"📊 {symbol}: {signal} @ ${price:.4f} | {active_mode} | V:{votes_delta:+d} | {status}{block_info}")
				if not can_buy:
					logger.warning(f"❌ {symbol} BLOCKED: {block_reason}")
				else:
					self.last_buy_time = timestamp
			elif signal == "HOLD":
				logger.debug(f"⏸️ {symbol}: HOLD (V:{votes_delta:+d})")
			elif signal == "SELL":
				logger.debug(f"🔴 {symbol}: SELL (V:{votes_delta:+d})")
		else:
			# Детальный режим - полная информация
			logger.info(f"\n{'='*80}")
			logger.info(f"[SIGNAL_DIAG] 📊 {symbol} @ ${price:.4f} | {timestamp}")
			logger.info(f"[SIGNAL_DIAG] Сигнал: {signal} | Режим: {active_mode}")
			logger.info(f"[SIGNAL_DIAG] Голоса: Bullish={bullish_votes}, Bearish={bearish_votes}, Delta={votes_delta:+d}")
			
			if signal == "BUY":
				logger.info(f"[SIGNAL_DIAG] 🎯 BUY СИГНАЛ ОБНАРУЖЕН!")
				logger.info(f"[SIGNAL_DIAG] Position Size: {position_size*100:.1f}%")
				logger.info(f"[SIGNAL_DIAG] Топ-3 причины:")
				for i, reason in enumerate(reasons[:3], 1):
					logger.info(f"[SIGNAL_DIAG]   {i}. {reason}")
				
				if not can_buy:
					logger.warning(f"[SIGNAL_DIAG] ❌ СИГНАЛ ЗАБЛОКИРОВАН: {block_reason}")
				else:
					logger.info(f"[SIGNAL_DIAG] ✅ Сигнал может быть исполнен")
					self.last_buy_time = timestamp
			
			elif signal == "HOLD":
				logger.debug(f"[SIGNAL_DIAG] ⏸️ HOLD - недостаточно сильный сигнал (delta={votes_delta})")
				if reasons:
					logger.debug(f"[SIGNAL_DIAG] Причины: {', '.join(reasons[:2])}")
			
			elif signal == "SELL":
				logger.debug(f"[SIGNAL_DIAG] 🔴 SELL - медвежий настрой (delta={votes_delta})")
			
			# Статистика конфликтов индикаторов
			conflicts = [r for r in reasons if "КРИТИЧНО" in r or "⚠️" in r]
			if conflicts:
				logger.warning(f"[SIGNAL_DIAG] ⚠️ Обнаружены конфликты индикаторов:")
				for conflict in conflicts:
					logger.warning(f"[SIGNAL_DIAG]   - {conflict}")
			
			logger.info(f"{'='*80}\n")
	
	def log_position_check(
		self,
		symbol: str,
		current_price: float,
		position_data: Dict[str, Any],
		action: str = None
	):
		"""
		Логирует проверку существующей позиции.
		
		Args:
			symbol: Символ пары
			current_price: Текущая цена
			position_data: Данные позиции (entry_price, pnl, etc)
			action: Действие (SL, TP, TRAILING, etc) или None
		"""
		entry_price = position_data.get("entry_price", 0)
		pnl_percent = position_data.get("pnl_percent", 0)
		stop_loss = position_data.get("stop_loss", 0)
		take_profit = position_data.get("take_profit", 0)
		
		price_change = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
		
		logger.info(f"\n{'='*60}")
		logger.info(f"[POS_CHECK] 📈 {symbol} @ ${current_price:.4f}")
		logger.info(f"[POS_CHECK] Entry: ${entry_price:.4f} → Change: {price_change:+.2f}%")
		logger.info(f"[POS_CHECK] P&L: {pnl_percent:+.2f}%")
		logger.info(f"[POS_CHECK] SL: ${stop_loss:.4f} | TP: ${take_profit:.4f}")
		
		if action:
			logger.info(f"[POS_CHECK] 🎬 Действие: {action}")
		
		# Расстояния до уровней
		if stop_loss > 0:
			dist_to_sl = ((current_price - stop_loss) / stop_loss) * 100
			logger.debug(f"[POS_CHECK] Дистанция до SL: {dist_to_sl:+.2f}%")
		
		if take_profit > 0:
			dist_to_tp = ((take_profit - current_price) / current_price) * 100
			logger.debug(f"[POS_CHECK] Дистанция до TP: {dist_to_tp:+.2f}%")
		
		logger.info(f"{'='*60}\n")
	
	def print_summary(self):
		"""Выводит сводку по всем сигналам"""
		total = self.buy_signals_count + self.hold_signals_count + self.sell_signals_count
		
		if total == 0:
			logger.warning("[SIGNAL_SUMMARY] ⚠️ Нет данных для анализа")
			return
		
		logger.info(f"\n{'='*80}")
		logger.info("[SIGNAL_SUMMARY] 📊 СВОДКА ПО СИГНАЛАМ")
		logger.info(f"{'='*80}")
		logger.info(f"Всего сигналов: {total}")
		logger.info(f"  BUY:  {self.buy_signals_count} ({self.buy_signals_count/total*100:.1f}%)")
		logger.info(f"  HOLD: {self.hold_signals_count} ({self.hold_signals_count/total*100:.1f}%)")
		logger.info(f"  SELL: {self.sell_signals_count} ({self.sell_signals_count/total*100:.1f}%)")
		
		if self.last_buy_time:
			logger.info(f"\nПоследний BUY сигнал: {self.last_buy_time}")
		else:
			logger.warning("\n⚠️ Ни одного BUY сигнала не было сгенерировано!")
		
		if self.blocked_reasons:
			logger.info(f"\n🚫 Причины блокировки BUY сигналов:")
			for reason, count in sorted(self.blocked_reasons.items(), key=lambda x: x[1], reverse=True):
				logger.info(f"  {reason}: {count} раз")
		
		# Анализ последних сигналов
		if len(self.signal_history) > 0:
			recent = self.signal_history[-10:]
			logger.info(f"\n📋 Последние 10 сигналов:")
			for i, sig in enumerate(recent, 1):
				symbol = sig["symbol"]
				signal = sig["signal"]
				delta = sig["votes_delta"]
				mode = sig["mode"]
				can_buy = "✅" if sig["can_buy"] else "❌"
				logger.info(
					f"  {i}. {symbol}: {signal} (delta={delta:+d}, mode={mode}) {can_buy}"
				)
		
		logger.info(f"{'='*80}\n")
	
	def analyze_vote_distribution(self):
		"""Анализирует распределение голосов"""
		if not self.signal_history:
			return
		
		deltas = [s["votes_delta"] for s in self.signal_history]
		
		logger.info(f"\n{'='*80}")
		logger.info("[VOTE_ANALYSIS] 📊 АНАЛИЗ РАСПРЕДЕЛЕНИЯ ГОЛОСОВ")
		logger.info(f"{'='*80}")
		logger.info(f"Min delta: {min(deltas):+d}")
		logger.info(f"Max delta: {max(deltas):+d}")
		logger.info(f"Avg delta: {sum(deltas)/len(deltas):+.1f}")
		logger.info(f"Median delta: {sorted(deltas)[len(deltas)//2]:+d}")
		
		# Распределение по диапазонам
		# HYBRID v5.5 использует адаптивную логику, но примерный порог BUY ~5 голосов
		min_buy_threshold = 5
		ranges = [
			(float('-inf'), -5, "Сильно bearish (<-5)"),
			(-5, -3, "Средне bearish (-5 to -3)"),
			(-3, 0, "Слабо bearish (-3 to 0)"),
			(0, 3, "Слабо bullish (0 to 3)"),
			(3, min_buy_threshold, f"Средне bullish (3 to {min_buy_threshold-1})"),
			(min_buy_threshold, float('inf'), f"Сильно bullish (>={min_buy_threshold}) 🎯 BUY!")
		]
		
		logger.info(f"\nРаспределение:")
		for low, high, label in ranges:
			count = len([d for d in deltas if low <= d < high])
			pct = count / len(deltas) * 100
			logger.info(f"  {label}: {count} ({pct:.1f}%)")
		
		# Рекомендации
		max_delta = max(deltas)
		avg_delta = sum(deltas)/len(deltas)
		
		logger.info(f"\n💡 РЕКОМЕНДАЦИИ:")
		if max_delta < min_buy_threshold:
			logger.warning(
				f"  ⚠️ Максимальный delta ({max_delta:+d}) меньше примерного порога BUY (~{min_buy_threshold})"
			)
			logger.warning(f"  → Рынок слабый, рассмотреть смягчение фильтров")
		
		if avg_delta < 0:
			logger.warning(f"  ⚠️ Средний delta отрицательный ({avg_delta:+.1f})")
			logger.warning(f"  → Рынок в медвежьей фазе, стратегия корректно не генерирует BUY")
		
		buy_ready = len([d for d in deltas if d >= min_buy_threshold])
		if buy_ready == 0:
			logger.warning(f"  ⚠️ Ни один сигнал не достиг примерного порога BUY (~{min_buy_threshold})!")
			logger.warning(f"  → Проверить фильтры или дождаться более сильного рынка")
		else:
			logger.info(f"  ✅ {buy_ready} сигналов готовы к BUY ({buy_ready/len(deltas)*100:.1f}%)")
		
		logger.info(f"{'='*80}\n")


# Глобальный экземпляр для использования в боте
diagnostics = SignalDiagnostics()


