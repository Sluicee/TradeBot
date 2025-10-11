import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from logger import logger

# Параметры стратегии (из backtest.py)
COMMISSION_RATE = 0.0018  # 0.18%
MAX_POSITIONS = 3
STOP_LOSS_PERCENT = 0.05
TAKE_PROFIT_PERCENT = 0.10
PARTIAL_CLOSE_PERCENT = 0.50
TRAILING_STOP_PERCENT = 0.02

STATE_FILE = "paper_trading_state.json"


def get_position_size_percent(signal_strength: int) -> float:
	"""Возвращает процент от баланса для входа в позицию"""
	if signal_strength >= 9:
		return 0.70  # Сильный сигнал - 70%
	elif signal_strength >= 6:
		return 0.50  # Средний сигнал - 50%
	else:
		return 0.30  # Слабый сигнал - 30%


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
		commission: float
	):
		self.symbol = symbol
		self.entry_price = entry_price
		self.amount = amount  # Количество монет
		self.entry_time = entry_time
		self.signal_strength = signal_strength
		self.invest_amount = invest_amount  # Сколько вложено (с комиссией)
		self.entry_commission = commission
		
		# Stop-loss и Take-profit уровни
		self.stop_loss_price = entry_price * (1 - STOP_LOSS_PERCENT)
		self.take_profit_price = entry_price * (1 + TAKE_PROFIT_PERCENT)
		
		# Флаги и состояние
		self.partial_closed = False
		self.max_price = entry_price  # Для trailing stop
		self.partial_close_profit = 0.0  # Прибыль с частичного закрытия
		self.original_amount = amount  # Исходное количество
		
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
			trailing_drop = (self.max_price - current_price) / self.max_price
			return trailing_drop >= TRAILING_STOP_PERCENT
		return False
		
	def get_pnl(self, current_price: float) -> Dict[str, float]:
		"""Возвращает текущую прибыль/убыток"""
		current_value = self.amount * current_price
		# Учитываем комиссию на выход
		exit_commission = current_value * COMMISSION_RATE
		net_value = current_value - exit_commission
		
		# PnL = текущая стоимость - вложенная сумма + прибыль с частичного закрытия
		pnl = net_value - (self.invest_amount - self.entry_commission) + self.partial_close_profit
		pnl_percent = (pnl / self.invest_amount) * 100
		
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
			"stop_loss_price": self.stop_loss_price,
			"take_profit_price": self.take_profit_price,
			"partial_closed": self.partial_closed,
			"max_price": self.max_price,
			"partial_close_profit": self.partial_close_profit,
			"original_amount": self.original_amount
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
			commission=data["entry_commission"]
		)
		pos.stop_loss_price = data["stop_loss_price"]
		pos.take_profit_price = data["take_profit_price"]
		pos.partial_closed = data["partial_closed"]
		pos.max_price = data["max_price"]
		pos.partial_close_profit = data["partial_close_profit"]
		pos.original_amount = data["original_amount"]
		return pos


class PaperTrader:
	"""Система виртуальной торговли"""
	
	def __init__(self, initial_balance: float = 100.0):
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
		logger.info(f"Paper Trading запущен с балансом ${self.balance:.2f}")
		
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
		logger.info("Paper Trading сброшен")
		
	def can_open_position(self, symbol: str) -> bool:
		"""Проверяет, можно ли открыть позицию"""
		# Проверяем лимит позиций
		if len(self.positions) >= MAX_POSITIONS:
			return False
		# Проверяем, нет ли уже позиции по этому символу
		if symbol in self.positions:
			return False
		# Проверяем баланс
		if self.balance <= 0:
			return False
		return True
		
	def open_position(
		self,
		symbol: str,
		price: float,
		signal_strength: int
	) -> Optional[Dict[str, Any]]:
		"""Открывает позицию"""
		if not self.can_open_position(symbol):
			return None
			
		# Рассчитываем размер позиции
		position_size_percent = get_position_size_percent(signal_strength)
		invest_amount = self.balance * position_size_percent
		
		if invest_amount <= 0:
			return None
			
		# Комиссия на вход
		commission = invest_amount * COMMISSION_RATE
		self.stats["total_commission"] += commission
		
		# Покупаем монеты
		amount = (invest_amount - commission) / price
		
		# Создаем позицию
		position = Position(
			symbol=symbol,
			entry_price=price,
			amount=amount,
			entry_time=datetime.now().isoformat(),
			signal_strength=signal_strength,
			invest_amount=invest_amount,
			commission=commission
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
			"balance_after": self.balance
		}
		self.trades_history.append(trade_info)
		self.stats["total_trades"] += 1
		
		logger.info(f"[PAPER] BUY {amount:.6f} {symbol} @ ${price:.2f} (сила: {signal_strength}, размер: {position_size_percent*100:.0f}%, комиссия: ${commission:.4f})")
		
		return trade_info
		
	def close_position(
		self,
		symbol: str,
		price: float,
		reason: str = "SELL"
	) -> Optional[Dict[str, Any]]:
		"""Закрывает позицию полностью"""
		if symbol not in self.positions:
			return None
			
		position = self.positions[symbol]
		
		# Продаем все монеты
		sell_value = position.amount * price
		commission = sell_value * COMMISSION_RATE
		self.stats["total_commission"] += commission
		net_value = sell_value - commission
		
		# Обновляем баланс
		self.balance += net_value
		
		# Рассчитываем прибыль
		profit = net_value - (position.invest_amount - position.entry_commission) + position.partial_close_profit
		profit_percent = (profit / position.invest_amount) * 100
		
		# Обновляем статистику
		if profit > 0:
			self.stats["winning_trades"] += 1
		else:
			self.stats["losing_trades"] += 1
			
		if reason == "STOP-LOSS":
			self.stats["stop_loss_triggers"] += 1
		elif reason == "TRAILING-STOP":
			self.stats["trailing_stop_triggers"] += 1
			
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
			"holding_time": self._calculate_holding_time(position.entry_time)
		}
		self.trades_history.append(trade_info)
		
		logger.info(f"[PAPER] {reason} {position.amount:.6f} {symbol} @ ${price:.2f} (прибыль: {profit:+.2f} USD / {profit_percent:+.2f}%, комиссия: ${commission:.4f})")
		
		# Удаляем позицию
		del self.positions[symbol]
		
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
		partial_invested = position.invest_amount * PARTIAL_CLOSE_PERCENT
		profit = net_value - partial_invested
		profit_percent = ((price - position.entry_price) / position.entry_price) * 100
		
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
		
		logger.info(f"[PAPER] PARTIAL-TP {close_amount:.6f} {symbol} @ ${price:.2f} (прибыль: {profit:+.2f} USD / {profit_percent:+.2f}%, закрыто: {PARTIAL_CLOSE_PERCENT*100:.0f}%)")
		
		return trade_info
		
	def check_positions(self, prices: Dict[str, float]) -> List[Dict[str, Any]]:
		"""Проверяет все позиции на стоп-лоссы и тейк-профиты"""
		actions = []
		
		for symbol, position in list(self.positions.items()):
			if symbol not in prices:
				continue
				
			current_price = prices[symbol]
			
			# Обновляем максимальную цену
			position.update_max_price(current_price)
			
			# Проверяем trailing stop (если позиция частично закрыта)
			if position.check_trailing_stop(current_price):
				trade_info = self.close_position(symbol, current_price, "TRAILING-STOP")
				if trade_info:
					actions.append(trade_info)
				continue
				
			# Проверяем стоп-лосс
			if position.check_stop_loss(current_price):
				trade_info = self.close_position(symbol, current_price, "STOP-LOSS")
				if trade_info:
					actions.append(trade_info)
				continue
				
			# Проверяем тейк-профит (частичное закрытие)
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
		total_profit_percent = (total_profit / self.initial_balance) * 100
		
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
			
	def save_state(self):
		"""Сохраняет состояние в файл"""
		state = {
			"initial_balance": self.initial_balance,
			"balance": self.balance,
			"positions": {symbol: pos.to_dict() for symbol, pos in self.positions.items()},
			"trades_history": self.trades_history,
			"stats": self.stats,
			"is_running": self.is_running,
			"start_time": self.start_time
		}
		
		try:
			with open(STATE_FILE, "w", encoding="utf-8") as f:
				json.dump(state, f, ensure_ascii=False, indent=2)
			logger.info(f"Состояние Paper Trading сохранено в {STATE_FILE}")
		except Exception as e:
			logger.error(f"Ошибка сохранения состояния: {e}")
			
	def load_state(self) -> bool:
		"""Загружает состояние из файла"""
		if not os.path.exists(STATE_FILE):
			logger.info(f"Файл состояния {STATE_FILE} не найден, начинаем с чистого листа")
			return False
			
		try:
			with open(STATE_FILE, "r", encoding="utf-8") as f:
				state = json.load(f)
				
			self.initial_balance = state.get("initial_balance", 100.0)
			self.balance = state.get("balance", self.initial_balance)
			self.trades_history = state.get("trades_history", [])
			self.stats = state.get("stats", {
				"total_trades": 0,
				"winning_trades": 0,
				"losing_trades": 0,
				"total_commission": 0.0,
				"stop_loss_triggers": 0,
				"take_profit_triggers": 0,
				"trailing_stop_triggers": 0
			})
			self.is_running = state.get("is_running", False)
			self.start_time = state.get("start_time")
			
			# Восстанавливаем позиции
			positions_data = state.get("positions", {})
			self.positions = {
				symbol: Position.from_dict(pos_data)
				for symbol, pos_data in positions_data.items()
			}
			
			logger.info(f"Состояние Paper Trading загружено из {STATE_FILE}")
			logger.info(f"Баланс: ${self.balance:.2f}, Позиций: {len(self.positions)}, Сделок: {len(self.trades_history)}")
			return True
			
		except Exception as e:
			logger.error(f"Ошибка загрузки состояния: {e}")
			return False

