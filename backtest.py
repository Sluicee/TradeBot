import os
import pandas as pd
from data_provider import DataProvider
from signal_generator import SignalGenerator
from paper_trader import get_position_size_percent, get_dynamic_stop_loss_percent, PaperTrader
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

# --- Симулятор умного докупания ---
def simulate_averaging(
	entry_price: float,
	entry_amount: float,
	entry_invest: float,
	signals: List[Dict],
	current_index: int,
	balance: float,
	enable_averaging: bool = True
) -> Tuple[float, float, int, float, List[Dict]]:
	"""
	Гибридный симулятор докупаний для бэктестов.
	Имитирует 1-2 докупания при падении цены на X%.
	
	Args:
		entry_price: Цена первого входа
		entry_amount: Количество монет при первом входе
		entry_invest: Инвестированная сумма при первом входе
		signals: Список всех сигналов
		current_index: Индекс текущего сигнала
		balance: Доступный баланс
	
	Returns:
		(average_price, total_amount, averaging_count, total_invested, averaging_log)
	"""
	if not enable_averaging or MAX_AVERAGING_ATTEMPTS == 0:
		return entry_price, entry_amount, 0, entry_invest, []
	
	avg_price = entry_price
	total_amount = entry_amount
	total_invested = entry_invest
	averaging_count = 0
	averaging_log = []
	
	# Проходим по свечам после входа
	for i in range(current_index + 1, len(signals)):
		if averaging_count >= MAX_AVERAGING_ATTEMPTS:
			break
		
		current_price = signals[i]["price"]
		
		# Проверяем условие докупания: цена упала на X% от средней
		price_drop = (avg_price - current_price) / avg_price
		
		if price_drop >= AVERAGING_PRICE_DROP_PERCENT:
			# Рассчитываем размер докупания (50% от первоначального)
			averaging_invest = entry_invest * AVERAGING_SIZE_PERCENT
			
			if averaging_invest < 1 or averaging_invest > balance:
				continue
			
			commission = averaging_invest * COMMISSION_RATE
			averaging_amount = (averaging_invest - commission) / current_price
			
			# Обновляем среднюю цену и количество
			old_total_cost = avg_price * total_amount
			new_invest_net = averaging_invest - commission
			total_invested += averaging_invest
			total_amount += averaging_amount
			avg_price = (old_total_cost + new_invest_net) / total_amount
			
			averaging_count += 1
			averaging_log.append({
				"index": i,
				"time": signals[i].get("time", "N/A"),
				"price": current_price,
				"amount": averaging_amount,
				"invest": averaging_invest,
				"drop_percent": price_drop * 100,
				"new_avg_price": avg_price
			})
			
			# Уменьшаем баланс после докупания
			balance -= averaging_invest
	
	return avg_price, total_amount, averaging_count, total_invested, averaging_log

# --- Бэктест стратегии ---
async def run_backtest(
	symbol: str, 
	interval: str = "15m", 
	period_hours: int = 24, 
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

		generator = SignalGenerator(df, use_statistical_models=use_statistical_models)
		generator.compute_indicators()
		signals = []
		min_window = 14  # минимальное количество строк для индикаторов

		for i in range(len(df)):
			sub_df = df.iloc[:i+1]
			if len(sub_df) < min_window:
				signals.append({
					"time": sub_df.index[-1],
					"price": sub_df["close"].iloc[-1],
					"signal": "HOLD",
					"reasons": ["Недостаточно данных для анализа"]
				})
				continue
			gen = SignalGenerator(sub_df, use_statistical_models=use_statistical_models)
			gen.compute_indicators()
			res = gen.generate_signal()
			signals.append({
				"time": sub_df.index[-1],
				"price": res["price"],
				"signal": res["signal"],
				"reasons": res["reasons"],
				"bullish_votes": res.get("bullish_votes", 0),
				"bearish_votes": res.get("bearish_votes", 0),
				"ATR": res.get("ATR", 0),
				"statistical_models": res.get("statistical_models", None)
			})

		# --- Бэктест: расчёт баланса за период с учетом комиссии ---
		balance = start_balance
		position = 0.0
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
		partial_closed = False  # Флаг частичного закрытия
		max_price = 0.0  # Максимальная цена для trailing stop
		
		# Kelly Criterion: создаём PaperTrader для расчёта Kelly
		kelly_tracker = PaperTrader(initial_balance=start_balance) if enable_kelly else None

		for sig_index, s in enumerate(signals):
			price = s["price"]
			sig = s["signal"]
			
			# Получаем силу сигнала напрямую из результата (исправлено!)
			bullish = s.get("bullish_votes", 0)
			bearish = s.get("bearish_votes", 0)
			signal_strength = abs(bullish - bearish)
			atr = s.get("ATR", 0.0)
			
			# Проверка стоп-лосса и тейк-профита
			if position > 0 and entry_price:
				price_change = (price - entry_price) / entry_price
				
				# Если позиция частично закрыта - проверяем trailing stop
				if partial_closed:
					# Обновляем максимальную цену
					if price > max_price:
						max_price = price
					
					# Проверяем trailing stop от максимальной цены
					trailing_drop = (max_price - price) / max_price
					if trailing_drop >= TRAILING_STOP_PERCENT:
						sell_value = position * price
						commission = sell_value * COMMISSION_RATE
						total_commission += commission
						balance += sell_value - commission
						profit_from_max = ((price - max_price) / max_price) * 100
						profit = (price - entry_price) / entry_price * 100
						trades.append(f"TRAILING-STOP {position:.6f} @ {price} (от макс: {profit_from_max:+.2f}%, комиссия: ${commission:.4f})")
						
						# Kelly: добавляем сделку в историю
						if kelly_tracker:
							kelly_tracker.trades_history.append({
								"type": "TRAILING-STOP",
								"profit": sell_value - commission - (entry_price * position),
								"profit_percent": profit
							})
						
						position = 0.0
						entry_price = None
						partial_closed = False
						max_price = 0.0
						trailing_stop_triggers += 1
						continue
				else:
					# Обычная логика до частичного закрытия
					
					# Стоп-лосс (ДИНАМИЧЕСКИЙ на основе ATR)
					if price_change <= -dynamic_sl_percent:
						sell_value = position * price
						commission = sell_value * COMMISSION_RATE
						total_commission += commission
						balance += sell_value - commission
						profit = (price - entry_price) / entry_price * 100
						trades.append(f"STOP-LOSS {position:.6f} @ {price} (потеря: {price_change*100:.2f}%, SL: {dynamic_sl_percent*100:.1f}%, комиссия: ${commission:.4f})")
						
						# Kelly: добавляем сделку в историю
						if kelly_tracker:
							kelly_tracker.trades_history.append({
								"type": "STOP-LOSS",
								"profit": sell_value - commission - (entry_price * position),
								"profit_percent": profit
							})
						
						position = 0.0
						entry_price = None
						entry_atr = 0.0
						stop_loss_triggers += 1
						continue
					
					# Тейк-профит - частичное закрытие (ДИНАМИЧЕСКИЙ на основе ATR)
					if price_change >= dynamic_tp_percent:
						close_amount = position * PARTIAL_CLOSE_PERCENT
						keep_amount = position - close_amount
						
						sell_value = close_amount * price
						commission = sell_value * COMMISSION_RATE
						total_commission += commission
						balance += sell_value - commission
						
						trades.append(f"PARTIAL-TP {close_amount:.6f} @ {price} (прибыль: {price_change*100:.2f}%, закрыто: {PARTIAL_CLOSE_PERCENT*100:.0f}%, комиссия: ${commission:.4f})")
						
						position = keep_amount
						partial_closed = True
						max_price = price
						partial_close_triggers += 1
						continue
			
			# Логика входа/выхода
			if sig == "BUY" and position == 0 and balance > 0:
				# Kelly Criterion: рассчитываем множитель
				kelly_multiplier = 1.0
				if kelly_tracker:
					atr_percent = (atr / price) * 100 if atr > 0 and price > 0 else 1.5
					kelly_multiplier = kelly_tracker.calculate_kelly_fraction(symbol, atr_percent)
				
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
				
				# Симулируем докупания (если включено)
				avg_entry, total_amount, avg_count, total_invested, avg_log = simulate_averaging(
					entry_price=entry_price,
					entry_amount=initial_amount,
					entry_invest=invest_amount,
					signals=signals,
					current_index=sig_index,
					balance=balance,
					enable_averaging=enable_averaging
				)
				
				# Применяем результаты averaging
				position = total_amount
				entry_price = avg_entry  # используем среднюю цену для SL/TP
				
				# Обновляем баланс и комиссии если были докупания
				if avg_count > 0:
					balance -= sum(log["invest"] for log in avg_log)
					total_commission += sum(log["invest"] * COMMISSION_RATE for log in avg_log)
				
				trades.append(f"BUY {initial_amount:.6f} @ {price} (сила: {signal_strength}, размер: {position_size_percent*100:.0f}%, SL: {dynamic_sl_percent*100:.1f}%, TP: {dynamic_tp_percent*100:.1f}%, комиссия: ${commission:.4f})")
				
				# Логируем докупания
				if avg_count > 0:
					trades.append(f"  >> AVERAGING: {avg_count} dokupaний, srednyaya tsena: ${avg_entry:.2f}, total coins: {position:.6f}")
				
			elif sig == "SELL" and position > 0 and not partial_closed:
				# Закрываем позицию только если она не была частично закрыта
				# (после частичного закрытия управляет trailing stop)
				sell_value = position * price
				commission = sell_value * COMMISSION_RATE
				total_commission += commission
				balance += sell_value - commission
				
				profit_on_trade = ((price - entry_price) / entry_price) * 100
				trades.append(f"SELL {position:.6f} @ {price} (прибыль: {profit_on_trade:+.2f}%, комиссия: ${commission:.4f})")
				
				# Kelly: добавляем сделку в историю
				if kelly_tracker:
					kelly_tracker.trades_history.append({
						"type": "SELL",
						"profit": sell_value - commission - (entry_price * position),
						"profit_percent": profit_on_trade
					})
				
				position = 0.0
				entry_price = None

		# Если позиция осталась открытой — закрываем по последней цене с учетом комиссии
		if position > 0:
			final_price = signals[-1]["price"]
			sell_value = position * final_price
			commission = sell_value * COMMISSION_RATE
			total_commission += commission
			balance += sell_value - commission
			profit_on_trade = ((final_price - entry_price) / entry_price) * 100
			close_type = "частичной" if partial_closed else "полной"
			trades.append(f"Закрытие {close_type} позиции: SELL {position:.6f} @ {final_price} (прибыль: {profit_on_trade:+.2f}%, комиссия: ${commission:.4f})")
			
			# Kelly: добавляем сделку в историю
			if kelly_tracker:
				kelly_tracker.trades_history.append({
					"type": "FINAL-CLOSE",
					"profit": sell_value - commission - (entry_price * position),
					"profit_percent": profit_on_trade
				})
			
			position = 0.0
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

		with open(output_file, "w", encoding="utf-8") as f:
			json.dump(signals, f, ensure_ascii=False, indent=2, default=str)

		print(f"Результаты сохранены в {output_file}")
		
		return {
			"symbol": symbol,
			"start_balance": start_balance,
			"final_balance": total_balance,
			"profit": profit,
			"profit_percent": profit_percent,
			"total_commission": total_commission,
			"trades_count": len(trades),
			"stop_loss_triggers": stop_loss_triggers,
			"partial_tp_triggers": partial_close_triggers,
			"trailing_stop_triggers": trailing_stop_triggers,
			"win_rate": win_rate if 'win_rate' in locals() else 0,
			"use_statistical_models": use_statistical_models
		}


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