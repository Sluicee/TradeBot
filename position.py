from datetime import datetime
from typing import Dict, List, Optional, Any
from config import (
	STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT, PARTIAL_CLOSE_PERCENT, 
	TRAILING_STOP_PERCENT, MAX_HOLDING_HOURS, MR_MAX_HOLDING_HOURS,
	DYNAMIC_SL_ATR_MULTIPLIER, DYNAMIC_SL_MIN, DYNAMIC_SL_MAX,
	USE_DYNAMIC_TP_FOR_TF, DYNAMIC_TP_ATR_MULTIPLIER, DYNAMIC_TP_MIN, DYNAMIC_TP_MAX,
	ENABLE_AVERAGING, MAX_AVERAGING_ATTEMPTS, AVERAGING_PRICE_DROP_PERCENT,
	AVERAGING_TIME_THRESHOLD_HOURS, ENABLE_PYRAMID_UP, PYRAMID_ADX_THRESHOLD,
	MAX_POSITION_DRAWDOWN_PERCENT, MAX_AVERAGING_DRAWDOWN_PERCENT,
	STRATEGY_TYPE_MR, STRATEGY_TYPE_TF, STRATEGY_TYPE_HYBRID
)


def get_dynamic_stop_loss_percent(atr: float, price: float) -> float:
	"""
	Рассчитывает динамический стоп-лосс на основе ATR.
	Минимум DYNAMIC_SL_MIN%, максимум DYNAMIC_SL_MAX%.
	"""
	if atr <= 0 or price <= 0:
		return STOP_LOSS_PERCENT  # по умолчанию
	
	# DYNAMIC_SL_ATR_MULTIPLIER * ATR как стоп-лосс
	atr_based_sl = (DYNAMIC_SL_ATR_MULTIPLIER * atr / price)
	
	# Ограничиваем диапазоном DYNAMIC_SL_MIN-DYNAMIC_SL_MAX%
	return max(DYNAMIC_SL_MIN, min(DYNAMIC_SL_MAX, atr_based_sl))


def get_dynamic_take_profit_percent(atr: float, price: float, stop_loss_percent: float = None) -> float:
	"""
	Рассчитывает динамический тейк-профит на основе ATR.
	Минимум DYNAMIC_TP_MIN%, максимум DYNAMIC_TP_MAX%.
	Если передан stop_loss_percent, обеспечивает минимальный R:R.
	"""
	if not USE_DYNAMIC_TP_FOR_TF:
		return TAKE_PROFIT_PERCENT  # Используем фиксированный TP если динамический отключен
	
	if atr <= 0 or price <= 0:
		return TAKE_PROFIT_PERCENT  # по умолчанию
	
	# DYNAMIC_TP_ATR_MULTIPLIER * ATR как тейк-профит
	atr_based_tp = (DYNAMIC_TP_ATR_MULTIPLIER * atr / price)
	
	# Ограничиваем диапазоном DYNAMIC_TP_MIN-DYNAMIC_TP_MAX%
	dynamic_tp = max(DYNAMIC_TP_MIN, min(DYNAMIC_TP_MAX, atr_based_tp))
	
	# Если передан SL, обеспечиваем минимальный R:R (минимум 1.5:1)
	if stop_loss_percent and stop_loss_percent > 0:
		from config import MIN_RR_RATIO, ENFORCE_MIN_RR
		if ENFORCE_MIN_RR:
			min_tp = stop_loss_percent * MIN_RR_RATIO
			if dynamic_tp < min_tp:
				# Увеличиваем TP до минимального R:R, но не больше максимума
				dynamic_tp = min(min_tp, DYNAMIC_TP_MAX)
	
	return dynamic_tp


class Position:
	"""Виртуальная позиция"""
	def __init__(
		self,
		symbol: str,
		entry_price: float,
		amount: float,
		entry_time: str,
		signal_strength: int,
		invest_amount: float,
		commission: float,
		atr: float = 0.0,
		rsi: float = 50.0,
		adx: float = 0.0,
		market_regime: str = "NEUTRAL",
		strategy_type: str = STRATEGY_TYPE_TF
	):
		self.symbol = symbol
		self.entry_price = entry_price
		self.amount = amount  # Количество монет
		self.entry_time = entry_time
		self.signal_strength = signal_strength
		self.invest_amount = invest_amount  # Сколько вложено (с комиссией)
		self.entry_commission = commission
		self.atr = atr
		
		# Индикаторы для статистических моделей
		self.rsi = rsi
		self.adx = adx
		self.market_regime = market_regime
		self.strategy_type = strategy_type
		
		# Stop-loss и Take-profit уровни (динамические на основе ATR)
		dynamic_sl = get_dynamic_stop_loss_percent(atr, entry_price)
		dynamic_tp = get_dynamic_take_profit_percent(atr, entry_price, dynamic_sl)
		
		# Для LONG: SL ниже входа, TP выше входа
		self.stop_loss_price = entry_price * (1 - dynamic_sl)  # Ниже входа
		self.stop_loss_percent = dynamic_sl
		self.take_profit_percent = dynamic_tp  # Сохраняем процент TP
		self.take_profit_price = entry_price * (1 + dynamic_tp)  # Выше входа
		
		# Флаги и состояние
		self.partial_closed = False
		self.max_price = entry_price  # Для trailing stop
		self.partial_close_profit = 0.0  # Прибыль с частичного закрытия
		self.original_amount = amount  # Исходное количество
		
		# Averaging / Pyramiding
		self.averaging_count = 0  # Количество докупаний
		self.averaging_entries: List[Dict[str, Any]] = []  # История докупаний
		self.average_entry_price = entry_price  # Средняя цена входа
		self.pyramid_mode = False  # Пирамидинг или усреднение
		self.total_invested = invest_amount  # Общая инвестиция с докупаниями
		
	def update_max_price(self, current_price: float):
		"""Обновляет максимальную цену для trailing stop"""
		# Для LONG: обновляем максимальную цену (самую высокую цену)
		if current_price > self.max_price:
			self.max_price = current_price
			
	def check_stop_loss(self, current_price: float) -> bool:
		"""Проверяет срабатывание стоп-лосса"""
		if not self.partial_closed:
			# Для LONG: срабатывает если цена упала ниже SL
			return current_price <= self.stop_loss_price
		return False
		
	def check_take_profit(self, current_price: float) -> bool:
		"""Проверяет срабатывание тейк-профита (для частичного закрытия)"""
		if not self.partial_closed:
			# Для LONG: срабатывает если цена поднялась выше TP
			return current_price >= self.take_profit_price
		return False
		
	def check_trailing_stop(self, current_price: float) -> bool:
		"""Проверяет срабатывание trailing stop"""
		if self.partial_closed:
			# Для LONG: trailing stop срабатывает при падении цены
			trailing_drop = (self.max_price - current_price) / self.max_price if self.max_price > 0 else 0
			return trailing_drop >= TRAILING_STOP_PERCENT
		return False
	
	def check_time_exit(self, max_hours: int = None, strategy_type: str = None) -> bool:
		"""
		Проверяет, не слишком ли долго удерживается позиция.
		Если позиция висит >max_hours без движения - выходим принудительно.
		"""
		if max_hours is None:
			# НОВОЕ: Выбираем max_hours на основе типа стратегии
			strategy = strategy_type or self.strategy_type
			if strategy == STRATEGY_TYPE_MR:
				max_hours = MR_MAX_HOLDING_HOURS  # 24 часа для MR
			else:
				max_hours = MAX_HOLDING_HOURS  # 72 часа для TF/HYBRID
		
		try:
			entry_dt = datetime.fromisoformat(self.entry_time)
			now_dt = datetime.now()
			holding_hours = (now_dt - entry_dt).total_seconds() / 3600
			
			# Отладочное логирование
			if holding_hours > max_hours * 0.8:  # Логируем когда близко к лимиту
				from logger import logger
				strategy = strategy_type or self.strategy_type
				logger.info(f"[TIME_EXIT_DEBUG] {self.symbol}: holding={holding_hours:.1f}h, max={max_hours}h, strategy={strategy}")
			
			return holding_hours > max_hours
		except Exception as e:
			from logger import logger
			logger.error(f"[TIME_EXIT_ERROR] {self.symbol}: ошибка проверки времени: {e}")
			return False
	
	def can_average_down(self, current_price: float, adx: float) -> tuple[bool, str]:
		"""
		Проверяет возможность докупания позиции.
		Возвращает (можно_ли, режим).
		"""
		if not ENABLE_AVERAGING:
			return False, "DISABLED"
		
		# Проверка лимита докупаний
		if self.averaging_count >= MAX_AVERAGING_ATTEMPTS:
			return False, "MAX_ATTEMPTS"
		
		# НОВОЕ: Проверка drawdown позиции
		pnl_info = self.get_pnl(current_price)
		current_drawdown = abs(pnl_info["pnl_percent"]) if pnl_info["pnl_percent"] < 0 else 0
		
		# Блокируем докупание при большом drawdown
		if current_drawdown > MAX_POSITION_DRAWDOWN_PERCENT * 100:  # Конвертируем в проценты
			return False, f"DRAWDOWN_TOO_HIGH_{current_drawdown:.1f}%"
		
		# Определяем режим на основе ADX
		if ENABLE_PYRAMID_UP and adx > PYRAMID_ADX_THRESHOLD:
			# Пирамидинг вверх - докупаем при росте цены
			mode = "PYRAMID_UP"
			price_condition = current_price > self.average_entry_price * 1.02  # +2%
		else:
			# Усреднение вниз - докупаем при падении
			mode = "AVERAGE_DOWN"
			price_condition = current_price <= self.average_entry_price * (1 - AVERAGING_PRICE_DROP_PERCENT)
		
		if not price_condition:
			return False, mode
		
		# Проверка временного условия для AVERAGE_DOWN
		if mode == "AVERAGE_DOWN":
			try:
				entry_dt = datetime.fromisoformat(self.entry_time)
				now_dt = datetime.now()
				holding_hours = (now_dt - entry_dt).total_seconds() / 3600
				if holding_hours < AVERAGING_TIME_THRESHOLD_HOURS:
					return False, f"{mode}_TIME"
			except:
				pass
		
		return True, mode
		
	def get_pnl(self, current_price: float) -> Dict[str, float]:
		"""Возвращает текущую прибыль/убыток"""
		from config import COMMISSION_RATE
		
		# Используем total_invested для усредненных позиций
		total_investment = self.total_invested if self.averaging_count > 0 else self.invest_amount
		
		# Если позиция частично закрыта, учитываем только оставшуюся часть инвестиции
		if self.partial_closed:
			remaining_invested = total_investment * (1 - PARTIAL_CLOSE_PERCENT)
		else:
			remaining_invested = total_investment
		
		# Для LONG: обычный расчет
		current_value = self.amount * current_price
		# Учитываем комиссию на выход
		exit_commission = current_value * COMMISSION_RATE
		net_value = current_value - exit_commission
		
		# PnL = текущая стоимость - вложенная сумма + прибыль с частичного закрытия
		pnl = net_value - remaining_invested + self.partial_close_profit
		
		pnl_percent = (pnl / total_investment) * 100 if total_investment > 0 else 0
		
		# Для LONG используем net_value
		current_value = net_value
		
		return {
			"pnl": pnl,
			"pnl_percent": pnl_percent,
			"current_value": current_value,
			"invested": self.invest_amount
		}
		
	def to_dict(self) -> Dict[str, Any]:
		"""Сериализация в dict"""
		return {
			"symbol": self.symbol,
			"entry_price": self.entry_price,
			"amount": self.amount,
			"entry_time": self.entry_time,
			"signal_strength": self.signal_strength,
			"invest_amount": self.invest_amount,
			"entry_commission": self.entry_commission,
			"atr": self.atr,
			"stop_loss_price": self.stop_loss_price,
			"stop_loss_percent": self.stop_loss_percent,
			"take_profit_price": self.take_profit_price,
			"take_profit_percent": getattr(self, 'take_profit_percent', TAKE_PROFIT_PERCENT),  # Для обратной совместимости
			"partial_closed": self.partial_closed,
			"max_price": self.max_price,
			"partial_close_profit": self.partial_close_profit,
			"original_amount": self.original_amount,
			"averaging_count": self.averaging_count,
			"averaging_entries": self.averaging_entries,
			"average_entry_price": self.average_entry_price,
			"pyramid_mode": self.pyramid_mode,
			"total_invested": self.total_invested
		}
		
	@staticmethod
	def from_dict(data: Dict[str, Any]) -> 'Position':
		"""Десериализация из dict"""
		pos = Position(
			symbol=data["symbol"],
			entry_price=data["entry_price"],
			amount=data["amount"],
			entry_time=data["entry_time"],
			signal_strength=data["signal_strength"],
			invest_amount=data["invest_amount"],
			commission=data.get("entry_commission", 0.0),  # Обратная совместимость
			atr=data.get("atr", 0.0)  # Обратная совместимость
		)
		pos.stop_loss_price = data.get("stop_loss_price", pos.stop_loss_price)
		pos.stop_loss_percent = data.get("stop_loss_percent", STOP_LOSS_PERCENT)
		pos.take_profit_price = data.get("take_profit_price", pos.take_profit_price)
		pos.take_profit_percent = data.get("take_profit_percent", TAKE_PROFIT_PERCENT)  # Для обратной совместимости
		pos.partial_closed = data.get("partial_closed", False)
		pos.max_price = data.get("max_price", pos.entry_price)
		pos.partial_close_profit = data.get("partial_close_profit", 0.0)
		pos.original_amount = data.get("original_amount", pos.amount)
		pos.averaging_count = data.get("averaging_count", 0)
		pos.averaging_entries = data.get("averaging_entries", [])
		pos.average_entry_price = data.get("average_entry_price", pos.entry_price)
		pos.pyramid_mode = data.get("pyramid_mode", False)
		pos.total_invested = data.get("total_invested", pos.invest_amount)
		return pos
