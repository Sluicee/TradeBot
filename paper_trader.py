from datetime import datetime
from typing import Dict, List, Optional, Any
from logger import logger
from database import db
from config import (
	COMMISSION_RATE, MAX_POSITIONS, STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT,
	PARTIAL_CLOSE_PERCENT, TRAILING_STOP_PERCENT,
	POSITION_SIZE_STRONG, POSITION_SIZE_MEDIUM, POSITION_SIZE_WEAK,
	SIGNAL_STRENGTH_STRONG, SIGNAL_STRENGTH_MEDIUM,
	DYNAMIC_SL_ATR_MULTIPLIER, DYNAMIC_SL_MIN, DYNAMIC_SL_MAX,
	VOLATILITY_HIGH_THRESHOLD, VOLATILITY_LOW_THRESHOLD, VOLATILITY_ADJUSTMENT_MAX,
	MAX_HOLDING_HOURS,
	# Kelly Criterion
	USE_KELLY_CRITERION, KELLY_FRACTION, MIN_TRADES_FOR_KELLY, KELLY_LOOKBACK_WINDOW,
	# Averaging
	ENABLE_AVERAGING, MAX_AVERAGING_ATTEMPTS, AVERAGING_PRICE_DROP_PERCENT,
	AVERAGING_TIME_THRESHOLD_HOURS, MAX_TOTAL_RISK_MULTIPLIER,
	ENABLE_PYRAMID_UP, PYRAMID_ADX_THRESHOLD, AVERAGING_SIZE_PERCENT,
	# Dynamic Positions
	get_dynamic_max_positions
)

# Группы коррелированных активов (упрощенно)
CORRELATION_GROUPS = {
	"BTC": ["BTCUSDT", "BTCUSD", "BTCBUSD"],
	"ETH": ["ETHUSDT", "ETHUSD", "ETHBUSD", "ETHBTC"],
	"BNB": ["BNBUSDT", "BNBUSD", "BNBBUSD"],
	"SOL": ["SOLUSDT", "SOLUSD", "SOLBUSD"],
	"XRP": ["XRPUSDT", "XRPUSD", "XRPBUSD"],
	"ADA": ["ADAUSDT", "ADAUSD", "ADABUSD"],
	# L1 блокчейны часто коррелируют
	"L1": ["AVAXUSDT", "ATOMUSDT", "DOTUSDT", "NEARUSDT", "APTUSDT"],
	# DeFi токены
	"DEFI": ["UNIUSDT", "AAVEUSDT", "LINKUSDT", "MKRUSDT"],
	# Мемы
	"MEME": ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT"]
}


def check_correlation_risk(new_symbol: str, existing_positions: Dict[str, Any]) -> bool:
	"""
	Проверяет риск корреляции.
	Возвращает True если можно открывать позицию, False если риск высокий.
	"""
	if not existing_positions:
		return True
	
	# Находим группу нового символа
	new_group = None
	for group_name, symbols in CORRELATION_GROUPS.items():
		if new_symbol in symbols:
			new_group = group_name
			break
	
	# Если символ не в известных группах, разрешаем (неизвестная корреляция)
	if new_group is None:
		return True
	
	# Проверяем открытые позиции
	for pos_symbol in existing_positions.keys():
		for group_name, symbols in CORRELATION_GROUPS.items():
			if pos_symbol in symbols:
				# Нашли группу существующей позиции
				if group_name == new_group:
					# Уже есть позиция из той же группы - запрещаем
					logger.warning(f"[CORRELATION] ❌ {new_symbol}: конфликт с {pos_symbol} (группа '{new_group}')")
					return False
	return True


def get_position_size_percent(
	signal_strength: int,
	atr: float = 0,
	price: float = 0,
	kelly_multiplier: float = 1.0
) -> float:
	"""
	Возвращает процент от баланса для входа в позицию.
	Учитывает силу сигнала, волатильность (ATR) и Kelly Criterion.
	"""
	# Базовый размер по силе сигнала
	if signal_strength >= SIGNAL_STRENGTH_STRONG:
		base_size = POSITION_SIZE_STRONG
		strength_level = "STRONG"
	elif signal_strength >= SIGNAL_STRENGTH_MEDIUM:
		base_size = POSITION_SIZE_MEDIUM
		strength_level = "MEDIUM"
	else:
		base_size = POSITION_SIZE_WEAK
		strength_level = "WEAK"
	
	# Корректировка на волатильность (если есть ATR)
	if atr > 0 and price > 0:
		atr_percent = (atr / price) * 100
		
		# Если волатильность высокая (>VOLATILITY_HIGH_THRESHOLD%), уменьшаем размер позиции
		if atr_percent > VOLATILITY_HIGH_THRESHOLD:
			volatility_factor = VOLATILITY_HIGH_THRESHOLD / atr_percent  # Обратная пропорция
			base_size *= volatility_factor
		# Если волатильность низкая (<VOLATILITY_LOW_THRESHOLD%), можно чуть увеличить
		elif atr_percent < VOLATILITY_LOW_THRESHOLD:
			volatility_adjustment = min(VOLATILITY_ADJUSTMENT_MAX, VOLATILITY_LOW_THRESHOLD / atr_percent)
			base_size *= volatility_adjustment
	
	# Применяем Kelly multiplier (0.5-1.5)
	base_size *= kelly_multiplier
	
	final_size = min(base_size, POSITION_SIZE_STRONG * 1.2)  # Максимум 120% от STRONG
	
	return final_size


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
		atr: float = 0.0
	):
		self.symbol = symbol
		self.entry_price = entry_price
		self.amount = amount  # Количество монет
		self.entry_time = entry_time
		self.signal_strength = signal_strength
		self.invest_amount = invest_amount  # Сколько вложено (с комиссией)
		self.entry_commission = commission
		self.atr = atr
		
		# Stop-loss и Take-profit уровни (динамические на основе ATR)
		dynamic_sl = get_dynamic_stop_loss_percent(atr, entry_price)
		self.stop_loss_price = entry_price * (1 - dynamic_sl)
		self.stop_loss_percent = dynamic_sl
		self.take_profit_price = entry_price * (1 + TAKE_PROFIT_PERCENT)
		
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
		if current_price > self.max_price:
			self.max_price = current_price
			
	def check_stop_loss(self, current_price: float) -> bool:
		"""Проверяет срабатывание стоп-лосса"""
		if not self.partial_closed:
			return current_price <= self.stop_loss_price
		return False
		
	def check_take_profit(self, current_price: float) -> bool:
		"""Проверяет срабатывание тейк-профита (для частичного закрытия)"""
		if not self.partial_closed:
			return current_price >= self.take_profit_price
		return False
		
	def check_trailing_stop(self, current_price: float) -> bool:
		"""Проверяет срабатывание trailing stop"""
		if self.partial_closed:
			trailing_drop = (self.max_price - current_price) / self.max_price if self.max_price > 0 else 0
			return trailing_drop >= TRAILING_STOP_PERCENT
		return False
	
	def check_time_exit(self, max_hours: int = None) -> bool:
		"""
		Проверяет, не слишком ли долго удерживается позиция.
		Если позиция висит >max_hours без движения - выходим принудительно.
		"""
		if max_hours is None:
			max_hours = MAX_HOLDING_HOURS
		try:
			entry_dt = datetime.fromisoformat(self.entry_time)
			now_dt = datetime.now()
			holding_hours = (now_dt - entry_dt).total_seconds() / 3600
			return holding_hours > max_hours
		except:
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
		current_value = self.amount * current_price
		# Учитываем комиссию на выход
		exit_commission = current_value * COMMISSION_RATE
		net_value = current_value - exit_commission
		
		# Используем total_invested для усредненных позиций
		total_investment = self.total_invested if self.averaging_count > 0 else self.invest_amount
		
		# Если позиция частично закрыта, учитываем только оставшуюся часть инвестиции
		if self.partial_closed:
			remaining_invested = total_investment * (1 - PARTIAL_CLOSE_PERCENT)
		else:
			remaining_invested = total_investment
		
		# PnL = текущая стоимость - вложенная сумма + прибыль с частичного закрытия
		pnl = net_value - remaining_invested + self.partial_close_profit
		pnl_percent = (pnl / total_investment) * 100 if total_investment > 0 else 0
		
		return {
			"pnl": pnl,
			"pnl_percent": pnl_percent,
			"current_value": net_value,
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


class PaperTrader:
	"""Система виртуальной торговли"""
	
	def __init__(self, initial_balance: float = None):
		if initial_balance is None:
			from config import INITIAL_BALANCE
			initial_balance = INITIAL_BALANCE
		self.initial_balance = initial_balance
		self.balance = initial_balance
		self.positions: Dict[str, Position] = {}  # symbol -> Position
		self.trades_history: List[Dict[str, Any]] = []
		self.stats = {
			"total_trades": 0,
			"winning_trades": 0,
			"losing_trades": 0,
			"total_commission": 0.0,
			"stop_loss_triggers": 0,
			"take_profit_triggers": 0,
			"trailing_stop_triggers": 0
		}
		self.is_running = False
		self.start_time = None
		
	def start(self):
		"""Запускает paper trading"""
		self.is_running = True
		self.start_time = datetime.now().isoformat()
		logger.info(f"Paper Trading запущен: ${self.balance:.2f}")
		
	def stop(self):
		"""Останавливает paper trading"""
		self.is_running = False
		logger.info("Paper Trading остановлен")
		
	def reset(self):
		"""Сбрасывает состояние к начальному"""
		self.balance = self.initial_balance
		self.positions.clear()
		self.trades_history.clear()
		self.stats = {
			"total_trades": 0,
			"winning_trades": 0,
			"losing_trades": 0,
			"total_commission": 0.0,
			"stop_loss_triggers": 0,
			"take_profit_triggers": 0,
			"trailing_stop_triggers": 0
		}
		self.start_time = datetime.now().isoformat()
		
	def can_open_position(self, symbol: str) -> bool:
		"""Проверяет, можно ли открыть позицию"""
		# Рассчитываем динамический лимит позиций на основе общего баланса
		total_invested = sum(pos.total_invested for pos in self.positions.values())
		total_balance = self.balance + total_invested
		dynamic_max_positions = get_dynamic_max_positions(total_balance)
		
		# Проверяем лимит позиций
		if len(self.positions) >= dynamic_max_positions:
			logger.warning(f"[CAN_OPEN] ❌ {symbol}: достигнут лимит позиций {len(self.positions)}/{dynamic_max_positions}")
			return False
		
		# Проверяем, нет ли уже позиции по этому символу
		if symbol in self.positions:
			return False
		
		# Проверяем баланс
		if self.balance <= 0:
			logger.warning(f"[CAN_OPEN] ❌ {symbol}: недостаточно баланса (${self.balance:.2f})")
			return False
		return True
		
	def open_position(
		self,
		symbol: str,
		price: float,
		signal_strength: int,
		atr: float = 0.0,
		position_size_percent: float = None,
		reasons: List[str] = None,
		active_mode: str = "UNKNOWN",
		bullish_votes: int = 0,
		bearish_votes: int = 0
	) -> Optional[Dict[str, Any]]:
		"""Открывает позицию"""
		logger.info(f"\n{'='*60}")
		logger.info(f"[OPEN_POSITION] 📊 Попытка открыть позицию {symbol}")
		logger.info(f"[OPEN_POSITION] Режим: {active_mode} | Цена: ${price:.4f}")
		logger.info(f"[OPEN_POSITION] Голоса: +{bullish_votes}/-{bearish_votes} (delta={bullish_votes-bearish_votes})")
		logger.info(f"[OPEN_POSITION] Сила сигнала: {signal_strength}, ATR: {atr:.4f}")
		if reasons:
			logger.info(f"[OPEN_POSITION] 📋 Причины: {reasons[:3]}")
		
		if not self.can_open_position(symbol):
			logger.warning(f"[OPEN_POSITION] ❌ {symbol}: не пройдены базовые проверки")
			return None
		
		# Проверка корреляции - не открываем коррелированные позиции
		if not check_correlation_risk(symbol, self.positions):
			logger.warning(f"[OPEN_POSITION] ❌ {symbol}: конфликт корреляции с открытыми позициями")
			return None
		
		# Рассчитываем Kelly multiplier
		atr_percent = (atr / price) * 100 if atr > 0 and price > 0 else 1.5
		kelly_multiplier = self.calculate_kelly_fraction(symbol, atr_percent)
			
		# Используем переданный position_size_percent (из v5.5 adaptive sizing) или рассчитываем
		if position_size_percent is None:
			position_size_percent = get_position_size_percent(signal_strength, atr, price, kelly_multiplier)
		
		invest_amount = self.balance * position_size_percent
		
		if invest_amount <= 0:
			logger.error(f"[OPEN_POSITION] ❌ {symbol}: invest_amount <= 0")
			return None
			
		# Комиссия на вход
		commission = invest_amount * COMMISSION_RATE
		self.stats["total_commission"] += commission
		
		# Покупаем монеты
		amount = (invest_amount - commission) / price
		
		# Создаем позицию с ATR для динамического SL
		position = Position(
			symbol=symbol,
			entry_price=price,
			amount=amount,
			entry_time=datetime.now().isoformat(),
			signal_strength=signal_strength,
			invest_amount=invest_amount,
			commission=commission,
			atr=atr
		)
		
		# Обновляем баланс
		self.balance -= invest_amount
		
		# Сохраняем позицию
		self.positions[symbol] = position
		
		# Добавляем в историю
		trade_info = {
			"type": "BUY",
			"symbol": symbol,
			"price": price,
			"amount": amount,
			"invest_amount": invest_amount,
			"commission": commission,
			"signal_strength": signal_strength,
			"time": position.entry_time,
			"balance_after": self.balance,
			# v5.5 метаданные
			"active_mode": active_mode,
			"bullish_votes": bullish_votes,
			"bearish_votes": bearish_votes,
			"votes_delta": bullish_votes - bearish_votes,
			"position_size_percent": position_size_percent,
			"reasons": reasons[:3] if reasons else []
		}
		self.trades_history.append(trade_info)
		self.stats["total_trades"] += 1
		
		# Сохраняем в БД
		try:
			db.add_trade(trade_info)
		except Exception as e:
			logger.error(f"[OPEN_POSITION] ❌ Ошибка сохранения сделки в БД: {e}")
		
		logger.info(f"[OPEN_POSITION] ✅ {symbol}: ${invest_amount:.2f} ({position_size_percent*100:.1f}%) | SL: {position.stop_loss_percent*100:.1f}% | TP: {TAKE_PROFIT_PERCENT*100:.1f}%")
		
		return trade_info
		
	def close_position(
		self,
		symbol: str,
		price: float,
		reason: str = "SELL"
	) -> Optional[Dict[str, Any]]:
		"""Закрывает позицию полностью"""
		logger.info(f"\n{'='*60}")
		logger.info(f"[CLOSE_POSITION] 🔴 Закрытие позиции {symbol}")
		logger.info(f"[CLOSE_POSITION] Причина: {reason}, Цена: ${price:.4f}")
		
		if symbol not in self.positions:
			logger.warning(f"[CLOSE_POSITION] ❌ Позиция {symbol} не найдена")
			return None
			
		position = self.positions[symbol]
		
		logger.info(f"[CLOSE_POSITION] 📊 Вход: ${position.entry_price:.4f}, Количество: {position.amount:.6f}")
		
		# Продаем все монеты
		sell_value = position.amount * price
		commission = sell_value * COMMISSION_RATE
		self.stats["total_commission"] += commission
		net_value = sell_value - commission
		
		# Обновляем баланс
		self.balance += net_value
		
		# Рассчитываем прибыль
		# Используем total_invested для усредненных позиций
		total_investment = position.total_invested if position.averaging_count > 0 else position.invest_amount
		
		# Если позиция частично закрыта, учитываем только оставшуюся часть инвестиции
		if position.partial_closed:
			remaining_invested = total_investment * (1 - PARTIAL_CLOSE_PERCENT)
		else:
			remaining_invested = total_investment
		
		profit = net_value - remaining_invested + position.partial_close_profit
		profit_percent = (profit / total_investment) * 100
		
		# Обновляем статистику
		if profit > 0:
			self.stats["winning_trades"] += 1
		else:
			self.stats["losing_trades"] += 1
			
		if reason == "STOP-LOSS":
			self.stats["stop_loss_triggers"] += 1
		elif reason == "TRAILING-STOP":
			self.stats["trailing_stop_triggers"] += 1
			
		holding_time = self._calculate_holding_time(position.entry_time)
		
		# Добавляем в историю
		trade_info = {
			"type": reason,
			"symbol": symbol,
			"price": price,
			"amount": position.amount,
			"sell_value": net_value,
			"commission": commission,
			"profit": profit,
			"profit_percent": profit_percent,
			"time": datetime.now().isoformat(),
			"balance_after": self.balance,
			"holding_time": holding_time
		}
		self.trades_history.append(trade_info)
		
		# Сохраняем в БД
		try:
			db.add_trade(trade_info)
		except Exception as e:
			logger.error(f"[CLOSE_POSITION] ❌ Ошибка сохранения сделки в БД: {e}")
		
		# Win Rate
		total_closed = self.stats["winning_trades"] + self.stats["losing_trades"]
		win_rate = (self.stats["winning_trades"] / total_closed * 100) if total_closed > 0 else 0
		
		# Удаляем позицию
		del self.positions[symbol]
		
		# Краткий лог результата
		emoji = "💚" if profit > 0 else "💔"
		logger.info(f"[CLOSE_POSITION] {emoji} {symbol}: {profit:+.2f} ({profit_percent:+.1f}%) | {holding_time} | WR: {win_rate:.1f}%")
		
		return trade_info
		
	def partial_close_position(
		self,
		symbol: str,
		price: float
	) -> Optional[Dict[str, Any]]:
		"""Частично закрывает позицию (тейк-профит)"""
		if symbol not in self.positions:
			return None
			
		position = self.positions[symbol]
		
		if position.partial_closed:
			return None
			
		# Закрываем часть
		close_amount = position.amount * PARTIAL_CLOSE_PERCENT
		keep_amount = position.amount - close_amount
		
		# Продаем
		sell_value = close_amount * price
		commission = sell_value * COMMISSION_RATE
		self.stats["total_commission"] += commission
		net_value = sell_value - commission
		
		# Обновляем баланс
		self.balance += net_value
		
		# Рассчитываем прибыль с этой части
		# Используем total_invested для усредненных позиций
		total_investment = position.total_invested if position.averaging_count > 0 else position.invest_amount
		partial_invested = total_investment * PARTIAL_CLOSE_PERCENT
		profit = net_value - partial_invested
		profit_percent = ((price - position.average_entry_price) / position.average_entry_price) * 100 if position.average_entry_price > 0 else 0
		
		# Обновляем позицию
		position.amount = keep_amount
		position.partial_closed = True
		position.max_price = price
		position.partial_close_profit = profit
		
		# Обновляем статистику
		self.stats["take_profit_triggers"] += 1
		
		# Добавляем в историю
		trade_info = {
			"type": "PARTIAL-TP",
			"symbol": symbol,
			"price": price,
			"amount": close_amount,
			"sell_value": net_value,
			"commission": commission,
			"profit": profit,
			"profit_percent": profit_percent,
			"closed_percent": PARTIAL_CLOSE_PERCENT * 100,
			"time": datetime.now().isoformat(),
			"balance_after": self.balance
		}
		self.trades_history.append(trade_info)
		
		# Сохраняем в БД
		try:
			db.add_trade(trade_info)
		except Exception as e:
			logger.error(f"Ошибка сохранения сделки в БД: {e}")
		
		logger.info(f"[PARTIAL-TP] 💎 {symbol}: {profit:+.2f} ({profit_percent:+.1f}%) | 50% закрыто")
	
		return trade_info

	def average_position(
		self,
		symbol: str,
		price: float,
		signal_strength: int,
		adx: float,
		atr: float,
		reason: str
	) -> Optional[Dict[str, Any]]:
		"""
		Докупает существующую позицию (averaging down/pyramid up).
		"""
		if not ENABLE_AVERAGING:
			return None
		
		if symbol not in self.positions:
			return None
		
		position = self.positions[symbol]
		
		# Проверка возможности докупания
		can_average, mode = position.can_average_down(price, adx)
		if not can_average:
			return None
		
		# Определение размера докупания
		if mode == "PYRAMID_UP":
			# Пирамидинг вверх - размер зависит от силы сигнала
			size_multiplier = (signal_strength / SIGNAL_STRENGTH_STRONG) if signal_strength > 0 and SIGNAL_STRENGTH_STRONG > 0 else 0.3
			size_percent = AVERAGING_SIZE_PERCENT * size_multiplier * 0.6  # ~30% от исходного
			position.pyramid_mode = True
		else:
			# Усреднение вниз - фиксированный размер
			size_percent = AVERAGING_SIZE_PERCENT  # 50% от исходного
			position.pyramid_mode = False
		
		# Рассчитываем сумму докупания
		original_invest = position.invest_amount  # Исходная инвестиция (без докупаний)
		new_invest = original_invest * size_percent
		
		# Проверка общего риска
		total_invested_after = position.total_invested + new_invest
		if total_invested_after > position.invest_amount * MAX_TOTAL_RISK_MULTIPLIER:
			return None
		
		# Проверка баланса
		if new_invest > self.balance:
			return None
		
		# Комиссия на докупание
		commission = new_invest * COMMISSION_RATE
		self.stats["total_commission"] += commission
		
		# Покупаем дополнительные монеты
		new_amount = (new_invest - commission) / price
		
		# Обновляем позицию
		old_amount = position.amount
		old_cost = position.average_entry_price * old_amount
		new_cost = price * new_amount
		
		position.amount += new_amount
		position.averaging_count += 1
		position.total_invested += new_invest
		
		# Пересчёт средней цены
		position.average_entry_price = (old_cost + new_cost) / (old_amount + new_amount)
		
		# Умное обновление SL/TP от новой средней цены
		dynamic_sl = get_dynamic_stop_loss_percent(atr, position.average_entry_price)
		new_stop_loss = position.average_entry_price * (1 - dynamic_sl)
		
		# Не сужаем SL при усреднении (берём max)
		position.stop_loss_price = max(new_stop_loss, position.stop_loss_price)
		position.stop_loss_percent = dynamic_sl
		position.take_profit_price = position.average_entry_price * (1 + TAKE_PROFIT_PERCENT)
		
		# Сохраняем историю докупания
		averaging_entry = {
			"price": price,
			"amount": new_amount,
			"invest_amount": new_invest,
			"commission": commission,
			"mode": mode,
			"reason": reason,
			"time": datetime.now().isoformat()
		}
		position.averaging_entries.append(averaging_entry)
		
		# Обновляем баланс
		self.balance -= new_invest
		
		# Добавляем в историю
		trade_info = {
			"type": f"AVERAGE-{mode}",
			"symbol": symbol,
			"price": price,
			"amount": new_amount,
			"invest_amount": new_invest,
			"commission": commission,
			"signal_strength": signal_strength,
			"reason": reason,
			"averaging_count": position.averaging_count,
			"average_entry_price": position.average_entry_price,
			"time": averaging_entry["time"],
			"balance_after": self.balance
		}
		self.trades_history.append(trade_info)
		
		# Сохраняем в БД
		try:
			db.add_trade(trade_info)
		except Exception as e:
			logger.error(f"Ошибка сохранения сделки в БД: {e}")
		
		logger.info(f"[AVERAGE-{mode}] 📈 {symbol}: #{position.averaging_count} | avg=${position.average_entry_price:.2f}")
		
		return trade_info
		
	def check_positions(self, prices: Dict[str, float]) -> List[Dict[str, Any]]:
		"""Проверяет все позиции на стоп-лоссы, тейк-профиты и время удержания"""
		actions = []
		
		if not self.positions:
			return actions
		
		for symbol, position in list(self.positions.items()):
			if symbol not in prices:
				continue
				
			current_price = prices[symbol]
			
			# Обновляем максимальную цену
			position.update_max_price(current_price)
			
			# 1. Проверяем время удержания
			if position.check_time_exit():
				trade_info = self.close_position(symbol, current_price, "TIME-EXIT")
				if trade_info:
					actions.append(trade_info)
				continue
			
			# 2. Проверяем trailing stop (если позиция частично закрыта)
			if position.check_trailing_stop(current_price):
				trade_info = self.close_position(symbol, current_price, "TRAILING-STOP")
				if trade_info:
					actions.append(trade_info)
				continue
				
			# 3. Проверяем стоп-лосс
			if position.check_stop_loss(current_price):
				trade_info = self.close_position(symbol, current_price, "STOP-LOSS")
				if trade_info:
					actions.append(trade_info)
				continue
				
			# 4. Проверяем тейк-профит (частичное закрытие)
			if position.check_take_profit(current_price):
				trade_info = self.partial_close_position(symbol, current_price)
				if trade_info:
					actions.append(trade_info)
				continue
		
		return actions
		
	def get_status(self) -> Dict[str, Any]:
		"""Возвращает текущий статус"""
		total_invested = sum(pos.invest_amount for pos in self.positions.values())
		total_pnl = 0.0
		
		positions_info = []
		for symbol, pos in self.positions.items():
			# Нужна текущая цена для расчета PnL, пока что используем entry_price
			pnl_info = pos.get_pnl(pos.entry_price)
			total_pnl += pnl_info["pnl"]
			
			positions_info.append({
				"symbol": symbol,
				"entry_price": pos.entry_price,
				"amount": pos.amount,
				"entry_time": pos.entry_time,
				"stop_loss": pos.stop_loss_price,
				"take_profit": pos.take_profit_price,
				"partial_closed": pos.partial_closed,
				"pnl": pnl_info["pnl"],
				"pnl_percent": pnl_info["pnl_percent"]
			})
			
		total_balance = self.balance + total_invested + total_pnl
		total_profit = total_balance - self.initial_balance
		total_profit_percent = (total_profit / self.initial_balance) * 100 if self.initial_balance > 0 else 0
		
		# Рассчитываем динамический лимит позиций
		dynamic_max_positions = get_dynamic_max_positions(total_balance)
		
		win_rate = 0.0
		if self.stats["winning_trades"] + self.stats["losing_trades"] > 0:
			win_rate = (self.stats["winning_trades"] / (self.stats["winning_trades"] + self.stats["losing_trades"])) * 100
			
		return {
			"is_running": self.is_running,
			"initial_balance": self.initial_balance,
			"current_balance": self.balance,
			"total_balance": total_balance,
			"total_profit": total_profit,
			"total_profit_percent": total_profit_percent,
			"positions_count": len(self.positions),
			"max_positions": dynamic_max_positions,  # Динамический лимит позиций
			"positions": positions_info,
			"stats": {
				**self.stats,
				"win_rate": win_rate
			},
			"start_time": self.start_time
		}
		
	def _calculate_holding_time(self, entry_time: str) -> str:
		"""Рассчитывает время удержания позиции"""
		try:
			entry_dt = datetime.fromisoformat(entry_time)
			now_dt = datetime.now()
			delta = now_dt - entry_dt
			
			hours = delta.seconds // 3600
			minutes = (delta.seconds % 3600) // 60
			
			if delta.days > 0:
				return f"{delta.days}д {hours}ч"
			elif hours > 0:
				return f"{hours}ч {minutes}м"
			else:
				return f"{minutes}м"
		except:
			return "N/A"
	
	def calculate_kelly_fraction(self, symbol: str, atr_percent: float) -> float:
		"""
		Рассчитывает Kelly fraction для оптимального размера позиции.
		Использует скользящее окно последних сделок.
		Нормализуется по волатильности актива.
		"""
		if not USE_KELLY_CRITERION:
			return 1.0  # Нейтральный множитель
		
		# Берём только закрытые сделки (BUY и соответствующие closes)
		closed_trades = [
			t for t in self.trades_history 
			if t.get("type") in ["SELL", "STOP-LOSS", "TRAILING-STOP", "TIME-EXIT"]
			and t.get("profit") is not None
		]
		
		# Недостаточно данных для расчёта Kelly
		if len(closed_trades) < MIN_TRADES_FOR_KELLY:
			return 1.0
		
		# Используем скользящее окно последних N сделок
		recent_trades = closed_trades[-KELLY_LOOKBACK_WINDOW:]
		
		# Рассчитываем win rate и средние значения
		winning_trades = [t for t in recent_trades if t.get("profit", 0) > 0]
		losing_trades = [t for t in recent_trades if t.get("profit", 0) <= 0]
		
		total_trades = len(recent_trades)
		win_count = len(winning_trades)
		
		if total_trades == 0:
			return 1.0
		
		win_rate = win_count / total_trades
		
		# Средний выигрыш и проигрыш (в процентах)
		if winning_trades:
			avg_win = sum(t.get("profit_percent", 0) for t in winning_trades) / len(winning_trades)
		else:
			avg_win = 0.0
		
		if losing_trades:
			avg_loss = abs(sum(t.get("profit_percent", 0) for t in losing_trades) / len(losing_trades))
		else:
			avg_loss = 1.0  # Избегаем деления на 0
		
		# Kelly formula: (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
		if avg_win <= 0 or avg_loss <= 0:
			return 1.0
		
		kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
		
		# Применяем консервативную дробь Kelly (например, 25%)
		kelly *= KELLY_FRACTION
		
		# Нормализация по волатильности: уменьшаем размер при высокой волатильности
		volatility_adjustment = 1 / (1 + atr_percent / 2)
		kelly *= volatility_adjustment
		
		# Ограничиваем диапазон 0.5-1.5 (не более 50% уменьшение и 50% увеличение)
		kelly_multiplier = max(0.5, min(1.5, kelly))
		
		return kelly_multiplier
			
	def save_state(self):
		"""Сохраняет состояние в БД"""
		try:
			# Сохраняем основное состояние
			start_time = datetime.fromisoformat(self.start_time) if isinstance(self.start_time, str) and self.start_time else datetime.now()
			db.save_paper_state(
				initial_balance=self.initial_balance,
				balance=self.balance,
				is_running=self.is_running,
				start_time=start_time,
				stats=self.stats
			)
			
			# Сохраняем позиции
			for symbol, pos in self.positions.items():
				pos_data = pos.to_dict()
				# Преобразуем entry_time в datetime
				if isinstance(pos_data.get("entry_time"), str):
					pos_data["entry_time"] = datetime.fromisoformat(pos_data["entry_time"])
				
				# Сохраняем позицию
				averaging_entries = pos_data.pop("averaging_entries", [])
				db_position = db.save_position(pos_data)
				
				# Сохраняем докупания (если есть новые)
				existing_entries = db.get_averaging_entries(db_position.id)
				if len(averaging_entries) > len(existing_entries):
					for entry in averaging_entries[len(existing_entries):]:
						entry_time = datetime.fromisoformat(entry["time"]) if isinstance(entry.get("time"), str) else datetime.now()
						db.add_averaging_entry(
							position_id=db_position.id,
							price=entry.get("price", 0),
							amount=entry.get("amount", 0),
							invest_amount=entry.get("invest_amount", 0),
							commission=entry.get("commission", 0),
							mode=entry.get("mode", ""),
							reason=entry.get("reason", ""),
							time=entry_time
						)
			
			# Удаляем закрытые позиции из БД
			db_positions = db.get_all_positions()
			for db_pos in db_positions:
				if db_pos.symbol not in self.positions:
					db.delete_position(db_pos.symbol)
			
		except Exception as e:
			logger.error(f"Ошибка сохранения состояния в БД: {e}")
			raise
			
	def load_state(self) -> bool:
		"""Загружает состояние из БД"""
		try:
			# Загружаем основное состояние
			db_state = db.get_paper_state()
			if not db_state:
				logger.info("Paper Trading: состояние не найдено, используем начальные значения")
				return False
			
			self.initial_balance = db_state.initial_balance
			self.balance = db_state.balance
			self.is_running = db_state.is_running
			self.start_time = db_state.start_time.isoformat() if db_state.start_time else None
			
			self.stats = {
				"total_trades": db_state.total_trades,
				"winning_trades": db_state.winning_trades,
				"losing_trades": db_state.losing_trades,
				"total_commission": db_state.total_commission,
				"stop_loss_triggers": db_state.stop_loss_triggers,
				"take_profit_triggers": db_state.take_profit_triggers,
				"trailing_stop_triggers": db_state.trailing_stop_triggers
			}
			
			# Загружаем позиции
			db_positions = db.get_all_positions()
			self.positions = {}
			
			for db_pos in db_positions:
				# Преобразуем DB модель в Position объект
				pos_data = {
					"symbol": db_pos.symbol,
					"entry_price": db_pos.entry_price,
					"amount": db_pos.amount,
					"entry_time": db_pos.entry_time.isoformat() if db_pos.entry_time else datetime.now().isoformat(),
					"signal_strength": db_pos.signal_strength,
					"invest_amount": db_pos.invest_amount,
					"commission": db_pos.entry_commission,
					"atr": db_pos.atr,
					"stop_loss_price": db_pos.stop_loss_price,
					"stop_loss_percent": db_pos.stop_loss_percent,
					"take_profit_price": db_pos.take_profit_price,
					"partial_closed": db_pos.partial_closed,
					"max_price": db_pos.max_price,
					"partial_close_profit": db_pos.partial_close_profit,
					"original_amount": db_pos.original_amount,
					"averaging_count": db_pos.averaging_count,
					"average_entry_price": db_pos.average_entry_price,
					"pyramid_mode": db_pos.pyramid_mode,
					"total_invested": db_pos.total_invested,
					"averaging_entries": db.get_averaging_entries(db_pos.id)
				}
				
				self.positions[db_pos.symbol] = Position.from_dict(pos_data)
			
			# Загружаем историю сделок (последние 1000)
			db_trades = db.get_trades_history(limit=1000)
			self.trades_history = db_trades
			
			logger.info(f"Paper Trading загружен из БД: ${self.balance:.2f}, {len(self.positions)} позиций, {len(self.trades_history)} сделок")
			return True
			
		except Exception as e:
			logger.error(f"Ошибка загрузки состояния из БД: {e}")
			raise

