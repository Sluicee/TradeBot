"""
Скрипт для сравнения бэктестов с и без статистических моделей.

Использование:
	python backtest_compare.py BTCUSDT 1h 168 100  # 1 неделя
	python backtest_compare.py --tracked 1h 168 100  # все отслеживаемые пары
"""

import asyncio
import json
from backtest import run_backtest, run_backtest_multiple
from config import INITIAL_BALANCE

async def compare_strategies(symbol: str, interval: str = "1h", period_hours: int = 168, start_balance: float = None):
	"""
	Сравниваем две стратегии:
	1. Базовая (без статистических моделей)
	2. Со статистическими моделями
	"""
	if start_balance is None:
		start_balance = INITIAL_BALANCE
	
	print("\n" + "="*120)
	print(f"СРАВНЕНИЕ СТРАТЕГИЙ: {symbol} | {interval} | {period_hours}h")
	print("="*120)
	
	# Базовая стратегия
	print("\n[BASE] ЗАПУСК БАЗОВОЙ СТРАТЕГИИ...")
	result_base = await run_backtest(symbol, interval, period_hours, start_balance, use_statistical_models=False)
	
	# Со статистическими моделями
	print("\n[STAT] ЗАПУСК СО СТАТИСТИЧЕСКИМИ МОДЕЛЯМИ...")
	result_stat = await run_backtest(symbol, interval, period_hours, start_balance, use_statistical_models=True)
	
	# Сравниваем результаты
	if result_base and result_stat:
		print("\n" + "="*120)
		print("СРАВНИТЕЛЬНАЯ ТАБЛИЦА")
		print("="*120)
		print(f"{'Метрика':<30} {'Базовая':<25} {'Статистическая':<25} {'Разница':<25}")
		print("-"*120)
		
		# Прибыль
		profit_diff = result_stat['profit'] - result_base['profit']
		profit_percent_diff = result_stat['profit_percent'] - result_base['profit_percent']
		print(f"{'Прибыль':<30} ${result_base['profit']:<24.2f} ${result_stat['profit']:<24.2f} ${profit_diff:<24.2f}")
		print(f"{'Прибыль %':<30} {result_base['profit_percent']:<24.2f}% {result_stat['profit_percent']:<24.2f}% {profit_percent_diff:+.2f}%")
		
		# Сделки
		trades_diff = result_stat['trades_count'] - result_base['trades_count']
		print(f"{'Количество сделок':<30} {result_base['trades_count']:<25} {result_stat['trades_count']:<25} {trades_diff:+d}")
		
		# Винрейт
		wr_diff = result_stat['win_rate'] - result_base['win_rate']
		print(f"{'Винрейт':<30} {result_base['win_rate']:<24.1f}% {result_stat['win_rate']:<24.1f}% {wr_diff:+.1f}%")
		
		# Комиссия
		comm_diff = result_stat['total_commission'] - result_base['total_commission']
		print(f"{'Комиссия':<30} ${result_base['total_commission']:<24.4f} ${result_stat['total_commission']:<24.4f} ${comm_diff:+.4f}")
		
		# Stop-loss
		sl_diff = result_stat['stop_loss_triggers'] - result_base['stop_loss_triggers']
		print(f"{'Stop-Loss срабатываний':<30} {result_base['stop_loss_triggers']:<25} {result_stat['stop_loss_triggers']:<25} {sl_diff:+d}")
		
		# Partial TP
		ptp_diff = result_stat['partial_tp_triggers'] - result_base['partial_tp_triggers']
		print(f"{'Partial Take-Profit':<30} {result_base['partial_tp_triggers']:<25} {result_stat['partial_tp_triggers']:<25} {ptp_diff:+d}")
		
		# Trailing Stop
		tsl_diff = result_stat['trailing_stop_triggers'] - result_base['trailing_stop_triggers']
		print(f"{'Trailing Stop':<30} {result_base['trailing_stop_triggers']:<25} {result_stat['trailing_stop_triggers']:<25} {tsl_diff:+d}")
		
		print("="*120)
		
		# Вывод
		if profit_percent_diff > 0:
			print(f"\n[+] СТАТИСТИЧЕСКИЕ МОДЕЛИ ЛУЧШЕ на {profit_percent_diff:+.2f}% ({profit_diff:+.2f} USD)")
		elif profit_percent_diff < 0:
			print(f"\n[-] БАЗОВАЯ СТРАТЕГИЯ ЛУЧШЕ на {abs(profit_percent_diff):.2f}% ({abs(profit_diff):.2f} USD)")
		else:
			print(f"\n[=] РЕЗУЛЬТАТЫ ОДИНАКОВЫЕ")
		
		# Дополнительный анализ
		if trades_diff != 0:
			trades_change = (trades_diff / result_base['trades_count'] * 100) if result_base['trades_count'] > 0 else 0
			print(f"   Изменение количества сделок: {trades_diff:+d} ({trades_change:+.1f}%)")
		
		if wr_diff > 0:
			print(f"   Винрейт улучшился на {wr_diff:+.1f}%")
		elif wr_diff < 0:
			print(f"   Винрейт ухудшился на {wr_diff:.1f}%")
		
		print()
		
		return {
			"symbol": symbol,
			"base": result_base,
			"statistical": result_stat,
			"profit_improvement": profit_percent_diff,
			"trades_diff": trades_diff,
			"win_rate_diff": wr_diff
		}
	
	return None


async def compare_multiple(symbols: list, interval: str = "1h", period_hours: int = 168, start_balance: float = None):
	"""Сравниваем стратегии на нескольких парах"""
	if start_balance is None:
		start_balance = INITIAL_BALANCE
	
	comparisons = []
	
	for symbol in symbols:
		result = await compare_strategies(symbol, interval, period_hours, start_balance)
		if result:
			comparisons.append(result)
	
	# Общая сводка
	if comparisons:
		print("\n" + "="*120)
		print("ОБЩАЯ СВОДКА ПО ВСЕМ ПАРАМ")
		print("="*120)
		print(f"{'Символ':<15} {'База: Прибыль%':<20} {'Стат: Прибыль%':<20} {'Разница':<15} {'Сделки (diff)':<20} {'WR (diff)':<15}")
		print("-"*120)
		
		total_base_profit = 0
		total_stat_profit = 0
		better_count = 0
		worse_count = 0
		same_count = 0
		
		for comp in comparisons:
			base_pct = comp['base']['profit_percent']
			stat_pct = comp['statistical']['profit_percent']
			diff = comp['profit_improvement']
			
			trades_base = comp['base']['trades_count']
			trades_stat = comp['statistical']['trades_count']
			trades_diff = comp['trades_diff']
			
			wr_diff = comp['win_rate_diff']
			
			indicator = "[+]" if diff > 0 else "[-]" if diff < 0 else "[=]"
			
			print(f"{comp['symbol']:<15} {base_pct:<19.2f}% {stat_pct:<19.2f}% {indicator} {diff:>+6.2f}%     {trades_base}->{trades_stat} ({trades_diff:+d})      {wr_diff:>+6.1f}%")
			
			total_base_profit += base_pct
			total_stat_profit += stat_pct
			
			if diff > 0:
				better_count += 1
			elif diff < 0:
				worse_count += 1
			else:
				same_count += 1
		
		print("-"*120)
		avg_base = total_base_profit / len(comparisons)
		avg_stat = total_stat_profit / len(comparisons)
		avg_diff = avg_stat - avg_base
		
		print(f"{'СРЕДНЯЯ':<15} {avg_base:<19.2f}% {avg_stat:<19.2f}% {'':3} {avg_diff:>+6.2f}%")
		print("="*120)
		
		print(f"\nСтатистика: Лучше={better_count}, Хуже={worse_count}, Одинаково={same_count}")
		
		if better_count > worse_count:
			win_ratio = (better_count / len(comparisons)) * 100
			print(f"[+] СТАТИСТИЧЕСКИЕ МОДЕЛИ ЛУЧШЕ в {better_count}/{len(comparisons)} случаях ({win_ratio:.1f}%)")
		elif worse_count > better_count:
			print(f"[-] БАЗОВАЯ СТРАТЕГИЯ ЛУЧШЕ в {worse_count}/{len(comparisons)} случаях")
		else:
			print(f"[=] РЕЗУЛЬТАТЫ СМЕШАННЫЕ")
		
		print(f"\nСредняя разница в доходности: {avg_diff:+.2f}%")
		print()


if __name__ == "__main__":
	import sys
	
	if len(sys.argv) > 1 and sys.argv[1] == "--tracked":
		# Сравниваем все tracked symbols
		try:
			with open("tracked_symbols.json", "r", encoding="utf-8") as f:
				data = json.load(f)
				symbols = data.get("symbols", [])
			
			interval = sys.argv[2] if len(sys.argv) > 2 else "1h"
			period_hours = int(sys.argv[3]) if len(sys.argv) > 3 else 168
			start_balance = float(sys.argv[4]) if len(sys.argv) > 4 else INITIAL_BALANCE
			
			asyncio.run(compare_multiple(symbols, interval, period_hours, start_balance))
		except FileNotFoundError:
			print("Файл tracked_symbols.json не найден!")
		except Exception as e:
			print(f"Ошибка: {e}")
	else:
		# Сравниваем одну пару
		symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
		interval = sys.argv[2] if len(sys.argv) > 2 else "1h"
		period_hours = int(sys.argv[3]) if len(sys.argv) > 3 else 168
		start_balance = float(sys.argv[4]) if len(sys.argv) > 4 else INITIAL_BALANCE
		
		asyncio.run(compare_strategies(symbol, interval, period_hours, start_balance))
	
	# Примеры:
	# python backtest_compare.py BTCUSDT 1h 168 100  -- одна пара (1 неделя)
	# python backtest_compare.py --tracked 1h 168 100  -- все пары
	# python backtest_compare.py ETHUSDT 15m 720 100  -- 30 дней на 15m

