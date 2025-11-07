import os
import pandas as pd
from data_provider import DataProvider
from signal_generator import SignalGenerator
from paper_trader import PaperTrader
from position_sizing import get_position_size_percent, calculate_kelly_fraction
from position import get_dynamic_stop_loss_percent
import aiohttp
import asyncio
import json
from datetime import datetime
from typing import Tuple, List, Dict
from config import (
	COMMISSION_RATE, MAX_POSITIONS, STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT,
	PARTIAL_CLOSE_PERCENT, TRAILING_STOP_PERCENT, INITIAL_BALANCE,
	DYNAMIC_SL_ATR_MULTIPLIER, USE_KELLY_CRITERION, ENABLE_AVERAGING,
	MAX_AVERAGING_ATTEMPTS, AVERAGING_PRICE_DROP_PERCENT, AVERAGING_SIZE_PERCENT,
	get_dynamic_max_positions
)

# --- Класс позиции для бэктеста (как в real_trader) ---
class BacktestPosition:
	"""Позиция для бэктеста"""
	def __init__(self, entry_price: float, amount: float, invest_amount: float, atr: float):
		self.entry_price = entry_price
		self.amount = amount
		self.invest_amount = invest_amount
		self.atr = atr
		self.averaging_count = 0
		self.average_entry_price = entry_price
		self.total_invested = invest_amount
		self.averaging_entries = []
	
	def can_average_down(self, current_price: float, balance: float) -> bool:
		"""Проверяет возможность докупания"""
		if self.averaging_count >= MAX_AVERAGING_ATTEMPTS:
			return False
		
		# Проверяем падение цены от средней
		price_drop = (self.average_entry_price - current_price) / self.average_entry_price
		if price_drop < AVERAGING_PRICE_DROP_PERCENT:
			return False
		
		# Проверяем баланс
		averaging_invest = self.invest_amount * AVERAGING_SIZE_PERCENT
		if averaging_invest < 1 or averaging_invest > balance:
			return False
		
		return True
	
	def average_down(self, current_price: float, balance: float) -> Tuple[float, float]:
		"""Выполняет докупание, возвращает (new_invest, commission)"""
		averaging_invest = self.invest_amount * AVERAGING_SIZE_PERCENT
		commission = averaging_invest * COMMISSION_RATE
		averaging_amount = (averaging_invest - commission) / current_price
		
		# Обновляем позицию (ПРАВИЛЬНАЯ формула как в real_trader)
		old_avg_price = self.average_entry_price
		old_amount = self.amount
		
		self.total_invested += averaging_invest
		self.amount += averaging_amount
		self.averaging_count += 1
		self.average_entry_price = (old_avg_price * old_amount + current_price * averaging_amount) / self.amount
		
		self.averaging_entries.append({
			"price": current_price,
			"amount": averaging_amount,
			"invest": averaging_invest,
			"new_avg_price": self.average_entry_price
		})
		
		return averaging_invest, commission

# --- Бэктест стратегии ---
async def run_backtest(
	symbol: str, 
	interval: str = "15m", 
	period_hours: int = 90, 
	start_balance: float = None,
	use_statistical_models: bool = False,
	enable_kelly: bool = None,
	enable_averaging: bool = None
):
	if start_balance is None:
		start_balance = INITIAL_BALANCE
	if enable_kelly is None:
		enable_kelly = USE_KELLY_CRITERION
	if enable_averaging is None:
		enable_averaging = ENABLE_AVERAGING
	
	candles_per_hour = int(60 / int(interval.replace('m',''))) if 'm' in interval else 1
	limit = period_hours * candles_per_hour

	async with aiohttp.ClientSession() as session:
		provider = DataProvider(session)
		df = await provider.fetch_klines(symbol=symbol, interval=interval, limit=limit)

		if df is None or df.empty:
			print(f"Нет данных для бэктеста {symbol}.")
			return None

		# --- Бэктест: расчёт баланса за период с учетом комиссии ---
		balance = start_balance
		position_obj = None  # Объект позиции (BacktestPosition или None)
		entry_price = None
		entry_strength = 0
		entry_atr = 0.0  # ATR при входе (для динамического SL/TP)
		dynamic_sl_percent = STOP_LOSS_PERCENT  # Динамический SL
		dynamic_tp_percent = TAKE_PROFIT_PERCENT  # Динамический TP
		trades = []
		total_commission = 0.0
		stop_loss_triggers = 0
		take_profit_triggers = 0
		partial_close_triggers = 0
		trailing_stop_triggers = 0
		averaging_triggers = 0
		partial_closed = False  # Флаг частичного закрытия
		max_price = 0.0  # Максимальная цена для trailing stop
		
		# Kelly Criterion: создаём PaperTrader для расчёта Kelly
		kelly_tracker = PaperTrader(initial_balance=start_balance) if enable_kelly else None
		
		min_window = 14  # минимальное количество строк для индикаторов

		# ИСПРАВЛЕНО: Проходим по каждой свече и проверяем позиции
		for i in range(len(df)):
			sub_df = df.iloc[:i+1]
			if len(sub_df) < min_window:
				continue
			
			# Генерируем сигнал для текущей свечи
			gen = SignalGenerator(sub_df, use_statistical_models=use_statistical_models)
			gen.compute_indicators()
			signal_result = gen.generate_signal()
			
			price = signal_result["price"]
			sig = signal_result["signal"]
			
			# Получаем силу сигнала напрямую из результата
			bullish = signal_result.get("bullish_votes", 0)
			bearish = signal_result.get("bearish_votes", 0)
			signal_strength = abs(bullish - bearish)
			atr = signal_result.get("ATR", 0.0)
			
			# Проверка стоп-лосса и тейк-профита
			if position_obj and entry_price:
				# ИСПРАВЛЕНО: используем среднюю цену входа для расчета изменения
				avg_entry = position_obj.average_entry_price
				
				# КРИТИЧНО: Пересчитываем SL/TP на каждой свече (как в real_trader!)
				current_sl_percent = get_dynamic_stop_loss_percent(position_obj.atr, avg_entry)
				current_tp_percent = max(0.04, current_sl_percent * 2.0)
				current_tp_percent = min(current_tp_percent, 0.12)
				
				stop_loss_price = avg_entry * (1 - current_sl_percent)
				take_profit_price = avg_entry * (1 + current_tp_percent)
				
				# Если позиция частично закрыта - проверяем trailing stop
				if partial_closed:
					# Обновляем максимальную цену
					if price > max_price:
						max_price = price
					
					# Проверяем trailing stop от максимальной цены
					trailing_drop = (max_price - price) / max_price
					if trailing_drop >= TRAILING_STOP_PERCENT:
						sell_value = position_obj.amount * price
						commission = sell_value * COMMISSION_RATE
						total_commission += commission
						balance += sell_value - commission
						profit_from_max = ((price - max_price) / max_price) * 100
						profit = (price - avg_entry) / avg_entry * 100
						trades.append(f"TRAILING-STOP {position_obj.amount:.6f} @ {price} (от макс: {profit_from_max:+.2f}%, комиссия: ${commission:.4f})")
						
						# Kelly: добавляем сделку в историю
						if kelly_tracker:
							kelly_tracker.trades_history.append({
								"type": "TRAILING-STOP",
								"profit": sell_value - commission - (avg_entry * position_obj.amount),
								"profit_percent": profit
							})
						
						position_obj = None
						entry_price = None
						partial_closed = False
						max_price = 0.0
						trailing_stop_triggers += 1
						continue
				else:
					# Обычная логика до частичного закрытия
					
					# Стоп-лосс (ДИНАМИЧЕСКИЙ на основе ATR)
					if price <= stop_loss_price:
						sell_value = position_obj.amount * price
						commission = sell_value * COMMISSION_RATE
						total_commission += commission
						balance += sell_value - commission
						profit = (price - avg_entry) / avg_entry * 100
						price_change_percent = ((price - avg_entry) / avg_entry) * 100
						trades.append(f"STOP-LOSS {position_obj.amount:.6f} @ {price} (потеря: {price_change_percent:.2f}%, SL: ${stop_loss_price:.2f}, комиссия: ${commission:.4f})")
						
						# Kelly: добавляем сделку в историю
						if kelly_tracker:
							kelly_tracker.trades_history.append({
								"type": "STOP-LOSS",
								"profit": sell_value - commission - (avg_entry * position_obj.amount),
								"profit_percent": profit
							})
						
						position_obj = None
						entry_price = None
						entry_atr = 0.0
						stop_loss_triggers += 1
						continue
					
					# Тейк-профит - частичное закрытие (ДИНАМИЧЕСКИЙ на основе ATR)
					if price >= take_profit_price:
						close_amount = position_obj.amount * PARTIAL_CLOSE_PERCENT
						keep_amount = position_obj.amount - close_amount
						
						sell_value = close_amount * price
						commission = sell_value * COMMISSION_RATE
						total_commission += commission
						balance += sell_value - commission
						
						price_change_percent = ((price - avg_entry) / avg_entry) * 100
						trades.append(f"PARTIAL-TP {close_amount:.6f} @ {price} (прибыль: {price_change_percent:.2f}%, TP: ${take_profit_price:.2f}, закрыто: {PARTIAL_CLOSE_PERCENT*100:.0f}%, комиссия: ${commission:.4f})")
						
						position_obj.amount = keep_amount
						partial_closed = True
						max_price = price
						partial_close_triggers += 1
						continue
			
			# НОВОЕ: Проверка докупания (ПЕРЕД новыми входами)
			if position_obj and sig == "BUY" and enable_averaging:
				# Проверяем возможность докупания
				if position_obj.can_average_down(price, balance):
					# Выполняем докупание
					averaging_invest, avg_commission = position_obj.average_down(price, balance)
					
					# Обновляем баланс и статистику
					balance -= averaging_invest
					total_commission += avg_commission
					averaging_triggers += 1
					
					# КРИТИЧНО: Обновляем TP на основе НОВОЙ средней цены
					dynamic_tp_percent = max(0.04, dynamic_sl_percent * 2.0)
					dynamic_tp_percent = min(dynamic_tp_percent, 0.12)
					
					trades.append(f"  >> AVERAGING: докупание #{position_obj.averaging_count}, цена: ${price:.2f}, средняя: ${position_obj.average_entry_price:.2f}, монет: {position_obj.amount:.6f}")
			
			# Логика входа/выхода
			if sig == "BUY" and not position_obj and balance > 0:
				# Kelly Criterion: рассчитываем множитель
				kelly_multiplier = 1.0
				if kelly_tracker:
					atr_percent = (atr / price) * 100 if atr > 0 and price > 0 else 1.5
					kelly_multiplier = calculate_kelly_fraction(kelly_tracker.trades_history, atr_percent)
				
				# Динамический размер позиции с учётом волатильности и Kelly
				position_size_percent = get_position_size_percent(signal_strength, atr, price, kelly_multiplier)
				invest_amount = balance * position_size_percent
				
				# Рассчитываем ДИНАМИЧЕСКИЙ Stop-Loss на основе ATR
				dynamic_sl_percent = get_dynamic_stop_loss_percent(atr, price)
				
				# Рассчитываем ДИНАМИЧЕСКИЙ Take-Profit
				# Используем R:R = 2:1 но с минимумом 4% (чтобы не быть слишком консервативными)
				dynamic_tp_percent = max(0.04, dynamic_sl_percent * 2.0)
				dynamic_tp_percent = min(dynamic_tp_percent, 0.12)  # Максимум 12%
				
				commission = invest_amount * COMMISSION_RATE
				total_commission += commission
				initial_amount = (invest_amount - commission) / price
				entry_price = price
				entry_strength = signal_strength
				entry_atr = atr
				balance -= invest_amount
				
				# ИСПРАВЛЕНО: Создаем объект позиции (БЕЗ предсказания будущего)
				position_obj = BacktestPosition(
					entry_price=entry_price,
					amount=initial_amount,
					invest_amount=invest_amount,
					atr=atr
				)
				
				trades.append(f"BUY {initial_amount:.6f} @ {price} (сила: {signal_strength}, размер: {position_size_percent*100:.0f}%, SL: {dynamic_sl_percent*100:.1f}%, TP: {dynamic_tp_percent*100:.1f}%, комиссия: ${commission:.4f})")
				
			elif sig == "SELL" and position_obj:
				# ИСПРАВЛЕНО: Убрали условие "not partial_closed" - закрываем по сигналу SELL всегда
				# В реальном трейдере SELL сигнал тоже закрывает позицию
				avg_entry = position_obj.average_entry_price
				sell_value = position_obj.amount * price
				commission = sell_value * COMMISSION_RATE
				total_commission += commission
				balance += sell_value - commission
				
				profit_on_trade = ((price - avg_entry) / avg_entry) * 100
				trades.append(f"SELL {position_obj.amount:.6f} @ {price} (прибыль: {profit_on_trade:+.2f}%, комиссия: ${commission:.4f})")
				
				# Kelly: добавляем сделку в историю
				if kelly_tracker:
					kelly_tracker.trades_history.append({
						"type": "SELL",
						"profit": sell_value - commission - (avg_entry * position_obj.amount),
						"profit_percent": profit_on_trade
					})
				
				position_obj = None
				entry_price = None
				partial_closed = False

		# Если позиция осталась открытой — закрываем по последней цене с учетом комиссии
		if position_obj:
			final_price = df["close"].iloc[-1]
			avg_entry = position_obj.average_entry_price
			sell_value = position_obj.amount * final_price
			commission = sell_value * COMMISSION_RATE
			total_commission += commission
			balance += sell_value - commission
			profit_on_trade = ((final_price - avg_entry) / avg_entry) * 100
			close_type = "частичной" if partial_closed else "полной"
			trades.append(f"Закрытие {close_type} позиции: SELL {position_obj.amount:.6f} @ {final_price} (прибыль: {profit_on_trade:+.2f}%, комиссия: ${commission:.4f})")
			
			# Kelly: добавляем сделку в историю
			if kelly_tracker:
				kelly_tracker.trades_history.append({
					"type": "FINAL-CLOSE",
					"profit": sell_value - commission - (avg_entry * position_obj.amount),
					"profit_percent": profit_on_trade
				})
			
			position_obj = None
			partial_closed = False

		# Финальный баланс = свободные деньги
		total_balance = balance
		
		profit = total_balance - start_balance
		profit_percent = (profit / start_balance) * 100
		
		models_label = "со СТАТИСТИЧЕСКИМИ МОДЕЛЯМИ" if use_statistical_models else "БАЗОВАЯ стратегия"
		
		print(f"\n=== {symbol} ({models_label}) ===")
		print(f"Бэктест за {period_hours} часов")
		print(f"Начальный баланс: ${start_balance:.2f}")
		print(f"Итоговый баланс: ${total_balance:.2f}")
		print(f"Доходность: {profit:.2f} USD ({profit_percent:+.2f}%)")
		print(f"Общая комиссия: ${total_commission:.4f}")
		print(f"Количество сделок: {len(trades)}")
		print(f"Stop-loss срабатываний: {stop_loss_triggers}")
		print(f"Partial Take-profit: {partial_close_triggers}")
		print(f"Trailing-stop: {trailing_stop_triggers}")
		print(f"Докупаний: {averaging_triggers}")
		if len(trades) > 0:
			win_trades = sum(1 for t in trades if "прибыль: +" in t or "PARTIAL-TP" in t)
			loss_trades = sum(1 for t in trades if "прибыль: -" in t or "STOP-LOSS" in t or "TRAILING-STOP" in t)
			if win_trades + loss_trades > 0:
				win_rate = (win_trades / (win_trades + loss_trades)) * 100
				print(f"Винрейт: {win_rate:.1f}% ({win_trades}W / {loss_trades}L)")
		print("Торговые действия:")
		for t in trades:
			print(t)

		# --- Сохраняем результат ---
		output_dir = "backtests"
		os.makedirs(output_dir, exist_ok=True)
		# Добавляем timestamp к имени файла
		timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
		output_file = os.path.join(output_dir, f"backtest_{symbol}_{interval}_{timestamp}.json")

		# Создаем объект с результатами бэктеста
		backtest_result = {
			"symbol": symbol,
			"start_balance": start_balance,
			"end_balance": total_balance,
			"profit": profit,
			"profit_percent": profit_percent,
			"total_commission": total_commission,
			"trades_count": len(trades),
			"stop_loss_triggers": stop_loss_triggers,
			"partial_tp_triggers": partial_close_triggers,
			"trailing_stop_triggers": trailing_stop_triggers,
			"averaging_triggers": averaging_triggers,
			"win_rate": win_rate if 'win_rate' in locals() else 0,
			"use_statistical_models": use_statistical_models,
			"enable_averaging": enable_averaging,
			"trades": trades
		}

		with open(output_file, "w", encoding="utf-8") as f:
			json.dump(backtest_result, f, ensure_ascii=False, indent=2, default=str)

		print(f"Результаты сохранены в {output_file}")
		
		return backtest_result


async def run_backtest_multiple(symbols: list, interval: str = "15m", period_hours: int = 24, start_balance: float = None, use_statistical_models: bool = False):
	"""Запускает бэктест для нескольких символов"""
	if start_balance is None:
		start_balance = INITIAL_BALANCE
	results = []
	
	for symbol in symbols:
		result = await run_backtest(symbol, interval, period_hours, start_balance, use_statistical_models)
		if result:
			results.append(result)
	
	# Выводим сводную таблицу
	if results:
		models_label = "со СТАТИСТИЧЕСКИМИ МОДЕЛЯМИ" if use_statistical_models else "БАЗОВАЯ стратегия"
		print("\n" + "="*110)
		print(f"СВОДНАЯ ТАБЛИЦА РЕЗУЛЬТАТОВ ({models_label})")
		print("="*110)
		print(f"{'Символ':<10} {'Баланс':<10} {'Прибыль':<10} {'%':<8} {'Комиссия':<10} {'Сделок':<8} {'SL':<5} {'PTP':<5} {'TSL':<5} {'WinRate':<10}")
		print("-"*110)
		
		total_profit = 0
		total_commission = 0
		total_sl = 0
		total_ptp = 0
		total_tsl = 0
		
		for r in results:
			wr = f"{r['win_rate']:.1f}%" if r['win_rate'] > 0 else "N/A"
			print(f"{r['symbol']:<10} ${r['final_balance']:<9.2f} ${r['profit']:<9.2f} {r['profit_percent']:>+6.2f}% ${r['total_commission']:<9.4f} {r['trades_count']:<8} {r['stop_loss_triggers']:<5} {r['partial_tp_triggers']:<5} {r['trailing_stop_triggers']:<5} {wr:<10}")
			total_profit += r['profit']
			total_commission += r['total_commission']
			total_sl += r['stop_loss_triggers']
			total_ptp += r['partial_tp_triggers']
			total_tsl += r['trailing_stop_triggers']
		
		print("-"*110)
		avg_profit_percent = (total_profit / (start_balance * len(results))) * 100
		print(f"{'ИТОГО:':<10} {'':10} ${total_profit:<9.2f} {avg_profit_percent:>+6.2f}% ${total_commission:<9.4f} {'':8} {total_sl:<5} {total_ptp:<5} {total_tsl:<5}")
		print("="*110)
		print("\nЛегенда: SL=Stop-Loss, PTP=Partial Take-Profit, TSL=Trailing-Stop")


if __name__ == "__main__":
	import sys
	
	# Проверяем, хочет ли пользователь протестировать tracked_symbols
	if len(sys.argv) > 1 and sys.argv[1] == "--tracked":
		# Читаем tracked_symbols.json
		try:
			with open("tracked_symbols.json", "r", encoding="utf-8") as f:
				data = json.load(f)
				symbols = data.get("symbols", [])
			
			interval = sys.argv[2] if len(sys.argv) > 2 else "15m"
			period_hours = int(sys.argv[3]) if len(sys.argv) > 3 else 24
			start_balance = float(sys.argv[4]) if len(sys.argv) > 4 else INITIAL_BALANCE
			
			print(f"Запуск бэктеста для {len(symbols)} символов: {', '.join(symbols)}")
			asyncio.run(run_backtest_multiple(symbols, interval, period_hours, start_balance))
		except FileNotFoundError:
			print("Файл tracked_symbols.json не найден!")
		except Exception as e:
			print(f"Ошибка при чтении tracked_symbols.json: {e}")
	else:
		# Обычный режим - одна пара
		symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
		interval = sys.argv[2] if len(sys.argv) > 2 else "15m"
		period_hours = int(sys.argv[3]) if len(sys.argv) > 3 else 24
		start_balance = float(sys.argv[4]) if len(sys.argv) > 4 else INITIAL_BALANCE
		asyncio.run(run_backtest(symbol, interval, period_hours, start_balance))
	
	# Примеры запуска:
	# python backtest.py BTCUSDT 15m 24 100  -- одна пара
	# python backtest.py --tracked 15m 24 100  -- все пары из tracked_symbols.json