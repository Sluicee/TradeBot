"""
Многопарное тестирование Mean Reversion (15m) vs Trend Following (1h)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pandas as pd
from datetime import datetime
from backtest_mean_reversion import MeanReversionBacktest
from backtest_hybrid import HybridBacktest

# Пары для тестирования
TEST_PAIRS = [
	"BTCUSDT",
	"ETHUSDT",
	"SOLUSDT",
	"BNBUSDT",
]

# Таймфреймы для тестирования
TIMEFRAMES = {
	"15m": "Mean Reversion (оптимальный для MR)",
	"1h": "Trend Following / Hybrid (оптимальный для TF)"
}

async def test_pair_timeframe(symbol: str, interval: str, strategy: str = "mean_reversion"):
	"""Тестирование одной пары на одном таймфрейме"""
	print(f"\n{'='*80}")
	print(f"Тестирование: {symbol} @ {interval} ({strategy})")
	print(f"{'='*80}")
	
	try:
		period_days = 90
		if strategy == "hybrid":
			backtest = HybridBacktest(symbol=symbol, interval=interval, period_days=period_days, start_balance=100.0)
		else:
			backtest = MeanReversionBacktest(symbol=symbol, interval=interval, period_days=period_days, start_balance=100.0)
		
		df = await backtest.fetch_data()
		
		if df is None or df.empty:
			print(f"❌ Не удалось загрузить данные для {symbol}")
			return None
		
		print(f"✓ Загружено {len(df)} свечей")
		
		if strategy == "hybrid":
			results = backtest.run_backtest(df)
		else:
			results = backtest.run_backtest(df, strategy=strategy)
		
		if results:
			print(f"\n📊 РЕЗУЛЬТАТЫ {symbol} @ {interval}:")
			print(f"  ROI: {results.get('total_return', 0):.2f}%")
			print(f"  Winrate: {results.get('win_rate', 0):.1f}%")
			print(f"  Сделок: {results.get('total_trades', 0)}")
			print(f"  Max DD: {results.get('max_drawdown', 0):.2f}%")
			print(f"  Sharpe: {results.get('sharpe_ratio', 0):.2f}")
			
			return {
				"symbol": symbol,
				"interval": interval,
				"strategy": strategy,
				"roi": results.get('total_return', 0),
				"winrate": results.get('win_rate', 0),
				"trades": results.get('total_trades', 0),
				"max_dd": results.get('max_drawdown', 0),
				"sharpe": results.get('sharpe_ratio', 0),
				"avg_win": results.get('avg_win', 0),
				"avg_loss": results.get('avg_loss', 0),
			}
		else:
			print(f"❌ Ошибка бэктеста для {symbol}")
			return None
			
	except Exception as e:
		print(f"❌ Исключение при тестировании {symbol}: {e}")
		return None

async def main():
	print("="*80)
	print("МНОГОПАРНОЕ ТЕСТИРОВАНИЕ СТРАТЕГИЙ")
	print("="*80)
	print(f"Пары: {', '.join(TEST_PAIRS)}")
	print(f"Таймфреймы: {', '.join(TIMEFRAMES.keys())}")
	print(f"Стратегии: Mean Reversion (15m), Hybrid (1h)")
	print("="*80)
	
	all_results = []
	
	# Тест 1: Mean Reversion на 15m для всех пар
	print("\n\n")
	print("🔄 ТЕСТ 1: MEAN REVERSION @ 15m")
	print("="*80)
	for symbol in TEST_PAIRS:
		result = await test_pair_timeframe(symbol, "15m", "mean_reversion")
		if result:
			all_results.append(result)
	
	# Тест 2: Hybrid на 1h для всех пар
	print("\n\n")
	print("🔄 ТЕСТ 2: HYBRID STRATEGY @ 1h")
	print("="*80)
	for symbol in TEST_PAIRS:
		result = await test_pair_timeframe(symbol, "1h", "hybrid")
		if result:
			all_results.append(result)
	
	# Итоговая таблица
	print("\n\n")
	print("="*80)
	print("ИТОГОВАЯ СВОДКА")
	print("="*80)
	
	if all_results:
		df_results = pd.DataFrame(all_results)
		
		# Группируем по стратегиям
		for strategy in ["mean_reversion", "hybrid"]:
			strategy_results = df_results[df_results["strategy"] == strategy]
			if not strategy_results.empty:
				print(f"\n{'='*80}")
				print(f"{strategy.upper().replace('_', ' ')}")
				print(f"{'='*80}")
				print(f"{'Symbol':<12} {'Interval':<10} {'ROI':<10} {'Winrate':<10} {'Trades':<8} {'MaxDD':<10} {'Sharpe':<8}")
				print("-"*80)
				
				for _, row in strategy_results.iterrows():
					print(f"{row['symbol']:<12} {row['interval']:<10} {row['roi']:>8.2f}% {row['winrate']:>8.1f}% {row['trades']:>6} {row['max_dd']:>8.2f}% {row['sharpe']:>6.2f}")
				
				# Средние значения
				avg_roi = strategy_results["roi"].mean()
				avg_winrate = strategy_results["winrate"].mean()
				total_trades = strategy_results["trades"].sum()
				avg_dd = strategy_results["max_dd"].mean()
				avg_sharpe = strategy_results["sharpe"].mean()
				
				print("-"*80)
				print(f"{'СРЕДНИЕ':<12} {'':<10} {avg_roi:>8.2f}% {avg_winrate:>8.1f}% {total_trades:>6} {avg_dd:>8.2f}% {avg_sharpe:>6.2f}")
		
		# Лучшая пара для каждой стратегии
		print(f"\n{'='*80}")
		print("ЛУЧШИЕ РЕЗУЛЬТАТЫ")
		print(f"{'='*80}")
		
		for strategy in ["mean_reversion", "hybrid"]:
			strategy_results = df_results[df_results["strategy"] == strategy]
			if not strategy_results.empty:
				best = strategy_results.loc[strategy_results["roi"].idxmax()]
				print(f"\n{strategy.upper().replace('_', ' ')}:")
				print(f"  Пара: {best['symbol']} @ {best['interval']}")
				print(f"  ROI: {best['roi']:.2f}%")
				print(f"  Winrate: {best['winrate']:.1f}%")
				print(f"  Сделок: {best['trades']}")
		
		# Сохраняем в CSV в папку tests
		results_path = os.path.join(os.path.dirname(__file__), "multi_pair_results.csv")
		df_results.to_csv(results_path, index=False)
		print(f"\n✓ Результаты сохранены в tests/multi_pair_results.csv")
	
	print("\n" + "="*80)
	print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
	print("="*80)

if __name__ == "__main__":
	asyncio.run(main())

