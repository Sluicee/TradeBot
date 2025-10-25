"""
Бэктест реальной торговой стратегии на основе real_trader.py
Анализирует 10 торговых пар за 1000 свечей (1h) с стартовым капиталом 100 USDT
"""

import os
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

# Импорты из проекта
from data_provider import DataProvider
from signal_generator import SignalGenerator
from position_sizing import get_position_size_percent, calculate_kelly_fraction, calculate_position_size_for_small_balance
from position import get_dynamic_stop_loss_percent
from correlation import check_correlation_risk
from config import (
	COMMISSION_RATE, MAX_POSITIONS, STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT,
	PARTIAL_CLOSE_PERCENT, TRAILING_STOP_PERCENT, INITIAL_BALANCE,
	DYNAMIC_SL_ATR_MULTIPLIER, USE_KELLY_CRITERION, ENABLE_AVERAGING,
	MAX_AVERAGING_ATTEMPTS, AVERAGING_PRICE_DROP_PERCENT, AVERAGING_SIZE_PERCENT,
	MAX_HOLDING_HOURS, get_dynamic_max_positions, REAL_MIN_ORDER_VALUE,
	SMALL_BALANCE_THRESHOLD, SIGNAL_STRENGTH_STRONG, SIGNAL_STRENGTH_MEDIUM,
	POSITION_SIZE_STRONG, POSITION_SIZE_MEDIUM, POSITION_SIZE_WEAK,
	REAL_MAX_POSITION_SIZE
)

# Торговые пары для бэктеста
TRADING_PAIRS = [
	"SUIUSDT", "SOLUSDT", "XRPUSDT", "HYPEUSDT", "TRXUSDT",
	"SEIUSDT", "BTCUSDT", "ADAUSDT", "PUMPUSDT", "BNBUSDT"
]

@dataclass
class Position:
	"""Класс позиции для бэктеста"""
	symbol: str
	entry_price: float
	amount: float
	entry_time: str
	signal_strength: int
	invest_amount: float
	commission: float
	atr: float
	stop_loss_price: float
	take_profit_price: float
	partial_closed: bool = False
	max_price: float = 0.0
	partial_close_profit: float = 0.0
	averaging_count: int = 0
	average_entry_price: float = 0.0
	total_invested: float = 0.0
	averaging_entries: List[Dict] = field(default_factory=list)
	
	def __post_init__(self):
		if self.average_entry_price == 0.0:
			self.average_entry_price = self.entry_price
		if self.total_invested == 0.0:
			self.total_invested = self.invest_amount
	
	def get_pnl(self, current_price: float) -> Dict[str, float]:
		"""Рассчитывает P&L позиции"""
		current_value = self.amount * current_price
		total_invested = self.total_invested if self.averaging_count > 0 else self.invest_amount
		pnl = current_value - total_invested + self.partial_close_profit
		pnl_percent = (pnl / total_invested) * 100 if total_invested > 0 else 0
		return {"pnl": pnl, "pnl_percent": pnl_percent}
	
	def update_max_price(self, price: float):
		"""Обновляет максимальную цену"""
		if price > self.max_price:
			self.max_price = price
	
	def check_stop_loss(self, current_price: float) -> bool:
		"""Проверяет срабатывание стоп-лосса"""
		# Используем среднюю цену входа для averaging позиций
		entry_price = self.average_entry_price if self.averaging_count > 0 else self.entry_price
		# Используем динамический SL на основе ATR
		stop_loss_percent = get_dynamic_stop_loss_percent(self.atr, entry_price)
		stop_loss_price = entry_price * (1 - stop_loss_percent)
		return current_price <= stop_loss_price
	
	def check_take_profit(self, current_price: float) -> bool:
		"""Проверяет срабатывание тейк-профита"""
		# Используем среднюю цену входа для averaging позиций
		entry_price = self.average_entry_price if self.averaging_count > 0 else self.entry_price
		take_profit_price = entry_price * (1 + TAKE_PROFIT_PERCENT)
		return current_price >= take_profit_price
	
	def check_trailing_stop(self, current_price: float) -> bool:
		"""Проверяет срабатывание трейлинг-стопа"""
		if not self.partial_closed or self.max_price == 0:
			return False
		trailing_drop = (self.max_price - current_price) / self.max_price
		return trailing_drop >= TRAILING_STOP_PERCENT
	
	def check_time_exit(self, current_time: str = None) -> bool:
		"""Проверяет выход по времени"""
		entry_dt = datetime.fromisoformat(self.entry_time)
		# В бэктесте используем переданное время или текущее
		if current_time:
			now_dt = datetime.fromisoformat(current_time)
		else:
			now_dt = datetime.now()
		hours_held = (now_dt - entry_dt).total_seconds() / 3600
		return hours_held >= MAX_HOLDING_HOURS
	
	def can_average_down(self, current_price: float, adx: float) -> Tuple[bool, str]:
		"""Проверяет возможность докупания"""
		if self.averaging_count >= MAX_AVERAGING_ATTEMPTS:
			return False, "MAX_ATTEMPTS"
		
		# Проверяем падение цены
		price_drop = (self.average_entry_price - current_price) / self.average_entry_price
		if price_drop < AVERAGING_PRICE_DROP_PERCENT:
			return False, "PRICE_DROP"
		
		# Проверяем общий риск
		potential_invest = self.invest_amount * AVERAGING_SIZE_PERCENT
		total_after = self.total_invested + potential_invest
		if total_after > self.invest_amount * 1.5:  # MAX_TOTAL_RISK_MULTIPLIER
			return False, "RISK_LIMIT"
		
		# Определяем режим докупания
		if adx >= 25:  # Сильный тренд - пирамидинг вверх
			return True, "PYRAMID_UP"
		else:
			return True, "AVERAGING_DOWN"

class RealTraderBacktest:
	"""Бэктест реальной торговой стратегии"""
	
	def __init__(self, initial_balance: float = 100.0):
		self.initial_balance = initial_balance
		self.balance = initial_balance
		self.positions: Dict[str, Position] = {}
		self.trades_history: List[Dict[str, Any]] = []
		self.stats = {
			"total_trades": 0,
			"winning_trades": 0,
			"losing_trades": 0,
			"total_commission": 0.0,
			"stop_loss_triggers": 0,
			"take_profit_triggers": 0,
			"trailing_stop_triggers": 0,
			"averaging_triggers": 0
		}
		self.max_drawdown = 0.0
		self.peak_balance = initial_balance
	
	def can_open_position(self, symbol: str) -> bool:
		"""Проверяет возможность открытия позиции"""
		# Проверяем, нет ли уже позиции по этому символу
		if symbol in self.positions:
			return False
		
		# Проверяем динамический лимит позиций
		total_balance = self.balance + sum(pos.get_pnl(0.0)["pnl"] for pos in self.positions.values())
		dynamic_max_positions = get_dynamic_max_positions(total_balance)
		
		if len(self.positions) >= dynamic_max_positions:
			return False
		
		# Проверяем корреляцию
		return check_correlation_risk(symbol, self.positions)
	
	def open_position(
		self,
		symbol: str,
		price: float,
		signal_strength: int,
		atr: float = 0.0,
		reasons: List[str] = None,
		bullish_votes: int = 0,
		bearish_votes: int = 0,
		rsi: float = 50.0,
		adx: float = 0.0
	) -> Optional[Dict[str, Any]]:
		"""Открывает позицию"""
		if not self.can_open_position(symbol):
			return None
		
		# Рассчитываем Kelly multiplier (как в реальном трейдере)
		atr_percent = (atr / price) * 100 if atr > 0 and price > 0 else 1.5
		kelly_multiplier = calculate_kelly_fraction(self.trades_history, atr_percent, self.balance)
		
		# Используем ту же логику расчета размера позиции, что и в реальном трейдере
		position_size_percent = get_position_size_percent(
			signal_strength, atr, price, kelly_multiplier, self.balance, symbol
		)
		
		# Ограничиваем размер позиции лимитами безопасности (как в реальном трейдере)
		invest_amount = min(self.balance * position_size_percent, REAL_MAX_POSITION_SIZE)
		
		# Адаптивный расчет для малых балансов (как в реальном трейдере)
		if self.balance < SMALL_BALANCE_THRESHOLD:
			# Для малых балансов используем специальную логику
			position_size_percent = calculate_position_size_for_small_balance(
				self.balance, signal_strength, atr, price, symbol
			)
			invest_amount = self.balance * position_size_percent
		
		# Проверяем минимальную сумму (как в реальном трейдере)
		if invest_amount < REAL_MIN_ORDER_VALUE:
			return None
		
		# Рассчитываем количество
		commission = invest_amount * COMMISSION_RATE
		amount = (invest_amount - commission) / price
		
		# Рассчитываем стоп-лосс и тейк-профит
		stop_loss_percent = get_dynamic_stop_loss_percent(atr, price)
		stop_loss_price = price * (1 - stop_loss_percent)
		take_profit_price = price * (1 + TAKE_PROFIT_PERCENT)
		
		# Создаем позицию
		position = Position(
			symbol=symbol,
			entry_price=price,
			amount=amount,
			entry_time=datetime.now().isoformat(),
			signal_strength=signal_strength,
			invest_amount=invest_amount,
			commission=commission,
			atr=atr,
			stop_loss_price=stop_loss_price,
			take_profit_price=take_profit_price
		)
		
		self.positions[symbol] = position
		self.balance -= invest_amount
		self.stats["total_commission"] += commission
		self.stats["total_trades"] += 1
		
		# Записываем сделку
		trade_info = {
			"type": "BUY",
			"symbol": symbol,
			"price": price,
			"amount": amount,
			"invest_amount": invest_amount,
			"commission": commission,
			"signal_strength": signal_strength,
			"time": position.entry_time,
			"bullish_votes": bullish_votes,
			"bearish_votes": bearish_votes,
			"votes_delta": bullish_votes - bearish_votes,
			"position_size_percent": position_size_percent,
			"reasons": reasons[:3] if reasons else []
		}
		self.trades_history.append(trade_info)
		
		return trade_info
	
	def close_position(self, symbol: str, price: float, reason: str = "SELL") -> Optional[Dict[str, Any]]:
		"""Закрывает позицию"""
		if symbol not in self.positions:
			return None
		
		position = self.positions[symbol]
		
		# Рассчитываем прибыль
		total_investment = position.total_invested if position.averaging_count > 0 else position.invest_amount
		sell_value = position.amount * price
		commission = sell_value * COMMISSION_RATE
		profit = sell_value - total_investment + position.partial_close_profit - commission
		profit_percent = (profit / total_investment) * 100
		
		# Обновляем статистику
		self.balance += sell_value - commission
		self.stats["total_commission"] += commission
		
		if profit > 0:
			self.stats["winning_trades"] += 1
		else:
			self.stats["losing_trades"] += 1
		
		if reason == "STOP-LOSS":
			self.stats["stop_loss_triggers"] += 1
		elif reason == "TRAILING-STOP":
			self.stats["trailing_stop_triggers"] += 1
		
		# Записываем сделку
		trade_info = {
			"type": reason,
			"symbol": symbol,
			"price": price,
			"amount": position.amount,
			"sell_value": sell_value,
			"commission": commission,
			"profit": profit,
			"profit_percent": profit_percent,
			"time": datetime.now().isoformat()
		}
		self.trades_history.append(trade_info)
		
		# Удаляем позицию
		del self.positions[symbol]
		
		return trade_info
	
	def partial_close_position(self, symbol: str, price: float) -> Optional[Dict[str, Any]]:
		"""Частично закрывает позицию"""
		if symbol not in self.positions:
			return None
		
		position = self.positions[symbol]
		
		if position.partial_closed:
			return None
		
		# Закрываем часть
		close_amount = position.amount * PARTIAL_CLOSE_PERCENT
		keep_amount = position.amount - close_amount
		
		# Рассчитываем прибыль для проданной части
		total_investment = position.total_invested if position.averaging_count > 0 else position.invest_amount
		partial_invested = total_investment * PARTIAL_CLOSE_PERCENT
		
		sell_value = close_amount * price
		commission = sell_value * COMMISSION_RATE
		net_value = sell_value - commission
		profit = net_value - partial_invested
		profit_percent = ((price - position.average_entry_price) / position.average_entry_price) * 100
		
		# Обновляем позицию
		position.amount = keep_amount
		position.partial_closed = True
		position.max_price = price
		position.partial_close_profit = profit
		
		# Обновляем баланс
		self.balance += net_value
		self.stats["total_commission"] += commission
		self.stats["take_profit_triggers"] += 1
		
		# Записываем сделку
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
			"time": datetime.now().isoformat()
		}
		self.trades_history.append(trade_info)
		
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
		"""Докупает позицию (как в реальном трейдере)"""
		if not ENABLE_AVERAGING or symbol not in self.positions:
			return None
		
		position = self.positions[symbol]
		
		# Проверяем возможность докупания
		can_average, mode = position.can_average_down(price, adx)
		if not can_average:
			return None
		
		# Рассчитываем Kelly multiplier для докупания (как в реальном трейдере)
		atr_percent = (atr / price) * 100 if atr > 0 and price > 0 else 1.5
		kelly_multiplier = calculate_kelly_fraction(self.trades_history, atr_percent, self.balance)
		
		# Определяем размер докупания на основе силы сигнала и Kelly
		if mode == "PYRAMID_UP":
			# Пирамидинг вверх - используем полную логику расчета позиции
			position_size_percent = get_position_size_percent(
				signal_strength, atr, price, kelly_multiplier, self.balance, symbol
			)
			# Для пирамидинга берем меньший процент от рассчитанного размера
			size_percent = position_size_percent * 0.6
		else:
			# Обычное докупание - используем стандартный размер
			size_percent = AVERAGING_SIZE_PERCENT
		
		# Рассчитываем сумму докупания
		original_invest = position.invest_amount
		new_invest = original_invest * size_percent
		
		# Проверяем лимиты безопасности (как в реальном трейдере)
		if new_invest > self.balance:
			return None
		
		# Проверяем минимальную сумму для докупания
		if new_invest < REAL_MIN_ORDER_VALUE:
			return None
		
		# Рассчитываем количество
		commission = new_invest * COMMISSION_RATE
		new_amount = (new_invest - commission) / price
		
		# Обновляем позицию
		old_total_invested = position.total_invested
		old_amount = position.amount
		old_avg_price = position.average_entry_price
		
		position.total_invested += new_invest
		position.amount += new_amount
		position.averaging_count += 1
		position.average_entry_price = (old_avg_price * old_amount + price * new_amount) / position.amount
		position.take_profit_price = position.average_entry_price * (1 + TAKE_PROFIT_PERCENT)
		
		# Добавляем запись о докупании
		averaging_entry = {
			"time": datetime.now().isoformat(),
			"price": price,
			"amount": new_amount,
			"invest": new_invest,
			"commission": commission,
			"mode": mode,
			"signal_strength": signal_strength,
			"adx": adx,
			"reason": reason
		}
		position.averaging_entries.append(averaging_entry)
		
		# Обновляем баланс и статистику
		self.balance -= new_invest
		self.stats["total_commission"] += commission
		self.stats["averaging_triggers"] += 1
		
		# Записываем сделку
		trade_info = {
			"type": "AVERAGING",
			"symbol": symbol,
			"price": price,
			"amount": new_amount,
			"invest": new_invest,
			"commission": commission,
			"mode": mode,
			"averaging_count": position.averaging_count,
			"new_avg_price": position.average_entry_price,
			"time": datetime.now().isoformat()
		}
		self.trades_history.append(trade_info)
		
		return trade_info
	
	def check_positions(self, prices: Dict[str, float], current_time: str = None) -> List[Dict[str, Any]]:
		"""Проверяет все позиции на триггеры"""
		actions = []
		
		for symbol, position in list(self.positions.items()):
			if symbol not in prices:
				continue
			
			current_price = prices[symbol]
			position.update_max_price(current_price)
			
			# 1. Проверяем время удержания (ПЕРВЫЙ приоритет)
			if position.check_time_exit(current_time):
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
	
	def update_drawdown(self):
		"""Обновляет максимальный drawdown"""
		current_balance = self.balance + sum(pos.get_pnl(0.0)["pnl"] for pos in self.positions.values())
		
		if current_balance > self.peak_balance:
			self.peak_balance = current_balance
		
		drawdown = (self.peak_balance - current_balance) / self.peak_balance
		if drawdown > self.max_drawdown:
			self.max_drawdown = drawdown
	
	def get_final_balance(self) -> float:
		"""Возвращает финальный баланс"""
		# Все позиции должны быть закрыты к этому моменту
		return self.balance

async def run_real_trader_backtest():
	"""Запускает бэктест реальной торговой стратегии"""
	print("🚀 Запуск бэктеста реальной торговой стратегии")
	print(f"📊 Пары: {', '.join(TRADING_PAIRS)}")
	print(f"💰 Стартовый баланс: $100.00")
	print(f"📈 Свечей: 1000 (1h)")
	print("=" * 80)
	
	# Создаем папку для результатов
	os.makedirs("backtests", exist_ok=True)
	timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
	
	results = []
	
	async with aiohttp.ClientSession() as session:
		provider = DataProvider(session)
		
		for symbol in TRADING_PAIRS:
			print(f"\n📊 Анализ {symbol}...")
			
			try:
				# Получаем данные
				df = await provider.fetch_klines(symbol=symbol, interval="1h", limit=1000)
				if df is None or df.empty:
					print(f"❌ Нет данных для {symbol}")
					continue
				
				# Создаем бэктестер для символа
				backtester = RealTraderBacktest(initial_balance=100.0)
				
				# Генерируем сигналы
				generator = SignalGenerator(df)
				generator.compute_indicators()
				
				# Обрабатываем каждую свечу
				for i in range(len(df)):
					sub_df = df.iloc[:i+1]
					if len(sub_df) < 14:  # Минимум для индикаторов
						continue
					
					# Генерируем сигнал
					gen = SignalGenerator(sub_df)
					gen.compute_indicators()
					signal_result = gen.generate_signal()
					
					price = signal_result["price"]
					signal = signal_result["signal"]
					current_time = sub_df.index[-1].isoformat() if hasattr(sub_df.index[-1], 'isoformat') else str(sub_df.index[-1])
					
					# СНАЧАЛА проверяем позиции (критично!)
					actions = backtester.check_positions({symbol: price}, current_time)
					
					# Обрабатываем сигнал только если нет активных позиций
					if signal == "BUY" and symbol not in backtester.positions:
						backtester.open_position(
							symbol=symbol,
							price=price,
							signal_strength=signal_result.get("signal_strength", 0),
							atr=signal_result.get("ATR", 0.0),
							reasons=signal_result.get("reasons", []),
							bullish_votes=signal_result.get("bullish_votes", 0),
							bearish_votes=signal_result.get("bearish_votes", 0),
							rsi=signal_result.get("RSI", 50.0),
							adx=signal_result.get("ADX", 0.0)
						)
					
					# Проверяем возможность докупания для существующих позиций
					if symbol in backtester.positions and signal == "BUY":
						backtester.average_position(
							symbol=symbol,
							price=price,
							signal_strength=signal_result.get("signal_strength", 0),
							adx=signal_result.get("ADX", 0.0),
							atr=signal_result.get("ATR", 0.0),
							reason="SIGNAL_AVERAGING"
						)
					
					# Обновляем drawdown
					backtester.update_drawdown()
				
				# Закрываем оставшиеся позиции
				for symbol_pos in list(backtester.positions.keys()):
					final_price = df["close"].iloc[-1]
					backtester.close_position(symbol_pos, final_price, "FINAL-CLOSE")
				
				# Рассчитываем финальные результаты
				final_balance = backtester.get_final_balance()
				profit = final_balance - 100.0
				profit_percent = (profit / 100.0) * 100
				
				# Статистика
				total_closed = backtester.stats["winning_trades"] + backtester.stats["losing_trades"]
				win_rate = (backtester.stats["winning_trades"] / total_closed * 100) if total_closed > 0 else 0
				
				# Результат для символа
				result = {
					"symbol": symbol,
					"start_balance": 100.0,
					"end_balance": final_balance,
					"profit": profit,
					"profit_percent": profit_percent,
					"total_commission": backtester.stats["total_commission"],
					"trades_count": backtester.stats["total_trades"],
					"winning_trades": backtester.stats["winning_trades"],
					"losing_trades": backtester.stats["losing_trades"],
					"win_rate": win_rate,
					"stop_loss_triggers": backtester.stats["stop_loss_triggers"],
					"take_profit_triggers": backtester.stats["take_profit_triggers"],
					"trailing_stop_triggers": backtester.stats["trailing_stop_triggers"],
					"max_drawdown": backtester.max_drawdown,
					"trades": backtester.trades_history
				}
				
				results.append(result)
				
				print(f"✅ {symbol}: ${final_balance:.2f} ({profit_percent:+.2f}%) | WR: {win_rate:.1f}% | Trades: {backtester.stats['total_trades']}")
				
			except Exception as e:
				print(f"❌ Ошибка при анализе {symbol}: {e}")
				continue
	
	# Генерируем отчеты
	generate_reports(results, timestamp)
	
	print(f"\n🎉 Бэктест завершен! Результаты сохранены в папке backtests/")

def generate_reports(results: List[Dict], timestamp: str):
	"""Генерирует CSV и JSON отчеты"""
	
	# CSV отчет
	csv_file = f"backtests/real_trader_report_{timestamp}.csv"
	with open(csv_file, "w", encoding="utf-8") as f:
		f.write("Symbol,Trades,Win%,ROI%,P&L,Avg Trade,Max DD,SL Triggers,TP Triggers,TSL Triggers\n")
		
		for result in results:
			avg_trade = result["profit"] / result["trades_count"] if result["trades_count"] > 0 else 0
			f.write(f"{result['symbol']},{result['trades_count']},{result['win_rate']:.1f},{result['profit_percent']:.2f},{result['profit']:.2f},{avg_trade:.2f},{result['max_drawdown']:.2f},{result['stop_loss_triggers']},{result['take_profit_triggers']},{result['trailing_stop_triggers']}\n")
	
	# JSON отчет
	json_file = f"backtests/real_trader_details_{timestamp}.json"
	with open(json_file, "w", encoding="utf-8") as f:
		json.dump(results, f, ensure_ascii=False, indent=2, default=str)
	
	print(f"📄 CSV отчет: {csv_file}")
	print(f"📄 JSON отчет: {json_file}")

if __name__ == "__main__":
	asyncio.run(run_real_trader_backtest())