"""
Модуль для контроля лимитов безопасности в реальном трейдинге
Предотвращает превышение рисков и защищает капитал
"""

from datetime import datetime, timedelta
from typing import Dict, List
from logger import logger
from config import (
	REAL_MAX_DAILY_LOSS, REAL_MAX_POSITION_SIZE, REAL_MAX_POSITIONS
)
from database import db


class SafetyLimits:
	"""Класс для контроля лимитов безопасности"""
	
	def __init__(self):
		self.daily_loss = 0.0
		self.last_reset_date = datetime.now().date()
	
	def check_daily_loss_limit(self) -> bool:
		"""Проверяет, не превышен ли дневной лимит убытков"""
		# Сбрасываем счетчик если новый день
		today = datetime.now().date()
		if today > self.last_reset_date:
			self.daily_loss = 0.0
			self.last_reset_date = today
			logger.info("Дневной лимит убытков сброшен")
		
		# Получаем актуальный дневной убыток из БД
		self.daily_loss = self.get_daily_loss()
		
		if self.daily_loss >= REAL_MAX_DAILY_LOSS:
			logger.warning(f"Достигнут дневной лимит убытков: ${self.daily_loss:.2f} >= ${REAL_MAX_DAILY_LOSS}")
			return False
		
		# Проверяем приближение к лимиту (80%)
		warning_threshold = REAL_MAX_DAILY_LOSS * 0.8
		if self.daily_loss >= warning_threshold:
			logger.warning(f"Приближение к дневному лимиту убытков: ${self.daily_loss:.2f} (лимит: ${REAL_MAX_DAILY_LOSS})")
		
		return True
	
	def check_position_limits(self, symbol: str, positions: Dict) -> bool:
		"""Проверяет лимиты для новой позиции"""
		# Проверяем лимит количества позиций
		if len(positions) >= REAL_MAX_POSITIONS:
			logger.warning(f"Достигнут лимит позиций: {len(positions)}/{REAL_MAX_POSITIONS}")
			return False
		
		# Проверяем, нет ли уже позиции по этому символу
		if symbol in positions:
			logger.warning(f"Позиция по {symbol} уже открыта")
			return False
		
		# Проверяем дневной лимит убытков
		if not self.check_daily_loss_limit():
			return False
		
		return True
	
	def get_daily_loss(self) -> float:
		"""Получает дневной убыток из БД"""
		try:
			# Получаем убытки за сегодня
			today = datetime.now().date()
			start_time = datetime.combine(today, datetime.min.time())
			end_time = datetime.combine(today, datetime.max.time())
			
			# Получаем сделки за сегодня
			trades = db.get_real_trades_by_date_range(start_time, end_time)
			
			daily_loss = 0.0
			for trade in trades:
				if trade.get("profit", 0) < 0:  # Только убыточные сделки
					daily_loss += abs(trade["profit"])
			
			return daily_loss
			
		except Exception as e:
			logger.error(f"Ошибка получения дневного убытка: {e}")
			return 0.0
	
	def check_position_size(self, invest_amount: float) -> bool:
		"""Проверяет размер позиции"""
		if invest_amount > REAL_MAX_POSITION_SIZE:
			logger.warning(f"Размер позиции превышает лимит: ${invest_amount:.2f} > ${REAL_MAX_POSITION_SIZE}")
			return False
		
		return True
	
	def get_remaining_daily_loss(self) -> float:
		"""Возвращает оставшийся дневной лимит убытков"""
		return max(0, REAL_MAX_DAILY_LOSS - self.get_daily_loss())
	
	def get_status(self) -> Dict:
		"""Возвращает статус лимитов"""
		return {
			"daily_loss": self.get_daily_loss(),
			"daily_loss_limit": REAL_MAX_DAILY_LOSS,
			"remaining_daily_loss": self.get_remaining_daily_loss(),
			"max_position_size": REAL_MAX_POSITION_SIZE,
			"max_positions": REAL_MAX_POSITIONS,
			"is_daily_limit_reached": self.get_daily_loss() >= REAL_MAX_DAILY_LOSS
		}
	
	def reset_daily_loss(self):
		"""Принудительно сбрасывает дневной убыток (для тестирования)"""
		self.daily_loss = 0.0
		self.last_reset_date = datetime.now().date()
		logger.info("Дневной убыток принудительно сброшен")
	
	def update_daily_loss(self, profit: float):
		"""Обновляет дневной убыток при закрытии позиции"""
		if profit < 0:  # Только убытки
			self.daily_loss += abs(profit)
			logger.info(f"Дневной убыток обновлен: ${self.daily_loss:.2f}")
			
			# Проверяем лимит
			if self.daily_loss >= REAL_MAX_DAILY_LOSS:
				logger.warning("Достигнут дневной лимит убытков! Торговля заблокирована.")
