"""
Бэктест конфигурации V5.3 с визуализацией результатов
Сравнение V5.2 vs V5.3 на разных парах и таймфреймах
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import aiohttp
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json

from data_provider import DataProvider
from signal_generator import SignalGenerator
from paper_trader import PaperTrader
import config

# Настройка стиля графиков
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (15, 10)
plt.rcParams['font.size'] = 10

class BacktestV53:
	"""Класс для бэктестирования V5.3 параметров"""
	
	def __init__(self, session):
		self.data_provider = DataProvider(session)
		self.results = {}
		self.session = session
		
	async def run_backtest(
		self,
		symbol: str,
		interval: str,
		days: int,
		config_override: Dict = None
	) -> Dict:
		"""
		Запускает бэктест с заданными параметрами
		
		Args:
			symbol: Торговая пара
			interval: Таймфрейм
			days: Количество дней для теста
			config_override: Словарь параметров для перезаписи config
			
		Returns:
			Словарь с результатами
		"""
		print(f"\n{'='*70}")
		print(f"🔄 Бэктест: {symbol} @ {interval} ({days} дней)")
		print(f"{'='*70}")
		
		# Применяем перезапись конфига (временно)
		original_config = {}
		if config_override:
			for key, value in config_override.items():
				if hasattr(config, key):
					original_config[key] = getattr(config, key)
					setattr(config, key, value)
					print(f"⚙️  {key} = {value}")
		
		# Получаем данные
		df = await self.data_provider.fetch_historical_klines(
			symbol=symbol,
			interval=interval,
			days=days
		)
		
		if df is None or len(df) < 100:
			print(f"❌ Недостаточно данных для {symbol}")
			return None
		
		print(f"📊 Загружено {len(df)} свечей")
		
		# Создаём генератор сигналов
		signal_gen = SignalGenerator()
		
		# Создаём paper trader
		paper_trader = PaperTrader(
			initial_balance=100.0,
			commission_rate=config.COMMISSION_RATE
		)
		
		# Прогоняем бэктест
		signals_count = 0
		trades = []
		equity_curve = []
		
		for i in range(100, len(df)):
			# Берём данные до текущего момента
			historical_data = df.iloc[:i+1]
			
			# Генерируем сигнал
			signal = await signal_gen.generate_signal(
				symbol=symbol,
				interval=interval,
				historical_data=historical_data
			)
			
			# Записываем equity
			total_balance = paper_trader.balance
			for pos in paper_trader.positions:
				total_balance += pos['amount'] * historical_data['close'].iloc[-1]
			
			equity_curve.append({
				'timestamp': historical_data['timestamp'].iloc[-1],
				'equity': total_balance,
				'price': historical_data['close'].iloc[-1]
			})
			
			# Обрабатываем сигнал
			if signal and signal['action'] in ['BUY', 'SELL']:
				signals_count += 1
				current_price = historical_data['close'].iloc[-1]
				
				# Пытаемся открыть позицию
				result = paper_trader.open_position(
					symbol=symbol,
					side=signal['action'],
					entry_price=current_price,
					stop_loss_percent=config.MR_STOP_LOSS_PERCENT,
					take_profit_percent=config.MR_TAKE_PROFIT_PERCENT,
					timestamp=historical_data['timestamp'].iloc[-1],
					signal_data=signal
				)
				
				if result:
					print(f"📈 {signal['action']} сигнал #{signals_count} @ ${current_price:.4f}")
			
			# Обновляем позиции
			if paper_trader.positions:
				current_price = historical_data['close'].iloc[-1]
				closed = paper_trader.update_positions(
					current_price=current_price,
					timestamp=historical_data['timestamp'].iloc[-1]
				)
				
				if closed:
					for pos in closed:
						trades.append({
							'entry_price': pos['entry_price'],
							'exit_price': pos['exit_price'],
							'pnl': pos['pnl'],
							'pnl_percent': pos['pnl_percent'],
							'entry_time': pos['entry_time'],
							'exit_time': pos['exit_time'],
							'side': pos['side']
						})
						print(f"  ✅ Закрыта: PnL {pos['pnl_percent']:+.2f}%")
		
		# Закрываем оставшиеся позиции
		if paper_trader.positions:
			current_price = df['close'].iloc[-1]
			for pos in paper_trader.positions:
				pnl_percent = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
				if pos['side'] == 'SELL':
					pnl_percent = -pnl_percent
				
				trades.append({
					'entry_price': pos['entry_price'],
					'exit_price': current_price,
					'pnl': pos['amount'] * (current_price - pos['entry_price']),
					'pnl_percent': pnl_percent,
					'entry_time': pos['entry_time'],
					'exit_time': df['timestamp'].iloc[-1],
					'side': pos['side']
				})
		
		# Восстанавливаем оригинальный config
		for key, value in original_config.items():
			setattr(config, key, value)
		
		# Рассчитываем метрики
		final_balance = paper_trader.balance
		for pos in paper_trader.positions:
			final_balance += pos['amount'] * df['close'].iloc[-1]
		
		roi = ((final_balance - 100.0) / 100.0) * 100
		
		# Winrate и другие метрики
		if trades:
			wins = [t for t in trades if t['pnl_percent'] > 0]
			losses = [t for t in trades if t['pnl_percent'] <= 0]
			winrate = (len(wins) / len(trades)) * 100
			avg_win = sum(t['pnl_percent'] for t in wins) / len(wins) if wins else 0
			avg_loss = sum(t['pnl_percent'] for t in losses) / len(losses) if losses else 0
			
			# Sharpe Ratio
			returns = [t['pnl_percent'] for t in trades]
			sharpe = (sum(returns) / len(returns)) / (pd.Series(returns).std() + 0.0001)
			
			# Max Drawdown
			equity_series = pd.Series([e['equity'] for e in equity_curve])
			running_max = equity_series.expanding().max()
			drawdown = ((equity_series - running_max) / running_max) * 100
			max_dd = drawdown.min()
		else:
			winrate = 0
			avg_win = 0
			avg_loss = 0
			sharpe = 0
			max_dd = 0
		
		results = {
			'symbol': symbol,
			'interval': interval,
			'days': days,
			'signals': signals_count,
			'trades': len(trades),
			'roi': roi,
			'winrate': winrate,
			'avg_win': avg_win,
			'avg_loss': avg_loss,
			'sharpe': sharpe,
			'max_dd': max_dd,
			'final_balance': final_balance,
			'equity_curve': equity_curve,
			'trades_list': trades
		}
		
		print(f"\n📊 Результаты:")
		print(f"  Сигналов: {signals_count}")
		print(f"  Сделок: {len(trades)}")
		print(f"  ROI: {roi:+.2f}%")
		print(f"  Winrate: {winrate:.1f}%")
		print(f"  Sharpe: {sharpe:.2f}")
		print(f"  Max DD: {max_dd:.2f}%")
		
		return results
	
	def visualize_results(self, results_list: List[Dict], title: str = "Backtest Results"):
		"""
		Создаёт визуализацию результатов
		
		Args:
			results_list: Список результатов бэктестов
			title: Заголовок графика
		"""
		if not results_list:
			print("❌ Нет результатов для визуализации")
			return
		
		# Фильтруем None
		results_list = [r for r in results_list if r is not None]
		
		if not results_list:
			print("❌ Все результаты пустые")
			return
		
		fig, axes = plt.subplots(2, 3, figsize=(18, 12))
		fig.suptitle(title, fontsize=16, fontweight='bold')
		
		# 1. ROI Comparison
		ax1 = axes[0, 0]
		symbols = [r['symbol'] + f"\n{r['interval']}" for r in results_list]
		rois = [r['roi'] for r in results_list]
		colors = ['green' if roi > 0 else 'red' for roi in rois]
		ax1.barh(symbols, rois, color=colors, alpha=0.7)
		ax1.set_xlabel('ROI (%)')
		ax1.set_title('Return on Investment')
		ax1.axvline(x=0, color='black', linestyle='--', linewidth=0.5)
		ax1.grid(axis='x', alpha=0.3)
		
		# 2. Win Rate
		ax2 = axes[0, 1]
		winrates = [r['winrate'] for r in results_list]
		ax2.barh(symbols, winrates, color='skyblue', alpha=0.7)
		ax2.set_xlabel('Win Rate (%)')
		ax2.set_title('Win Rate')
		ax2.axvline(x=50, color='orange', linestyle='--', linewidth=1, label='50%')
		ax2.axvline(x=60, color='green', linestyle='--', linewidth=1, label='60%')
		ax2.legend()
		ax2.grid(axis='x', alpha=0.3)
		
		# 3. Sharpe Ratio
		ax3 = axes[0, 2]
		sharpes = [r['sharpe'] for r in results_list]
		colors_sharpe = ['green' if s > 1.0 else 'orange' if s > 0.5 else 'red' for s in sharpes]
		ax3.barh(symbols, sharpes, color=colors_sharpe, alpha=0.7)
		ax3.set_xlabel('Sharpe Ratio')
		ax3.set_title('Risk-Adjusted Returns')
		ax3.axvline(x=1.0, color='green', linestyle='--', linewidth=1, label='1.0 (Good)')
		ax3.legend()
		ax3.grid(axis='x', alpha=0.3)
		
		# 4. Max Drawdown
		ax4 = axes[1, 0]
		max_dds = [r['max_dd'] for r in results_list]
		colors_dd = ['green' if dd > -5 else 'orange' if dd > -10 else 'red' for dd in max_dds]
		ax4.barh(symbols, max_dds, color=colors_dd, alpha=0.7)
		ax4.set_xlabel('Max Drawdown (%)')
		ax4.set_title('Maximum Drawdown')
		ax4.axvline(x=-10, color='orange', linestyle='--', linewidth=1, label='-10%')
		ax4.axvline(x=-20, color='red', linestyle='--', linewidth=1, label='-20%')
		ax4.legend()
		ax4.grid(axis='x', alpha=0.3)
		
		# 5. Trades Count
		ax5 = axes[1, 1]
		trades = [r['trades'] for r in results_list]
		ax5.barh(symbols, trades, color='purple', alpha=0.7)
		ax5.set_xlabel('Number of Trades')
		ax5.set_title('Trading Activity')
		ax5.grid(axis='x', alpha=0.3)
		
		# 6. Metrics Table
		ax6 = axes[1, 2]
		ax6.axis('tight')
		ax6.axis('off')
		
		table_data = []
		for r in results_list:
			table_data.append([
				f"{r['symbol']}\n{r['interval']}",
				f"{r['roi']:+.2f}%",
				f"{r['winrate']:.1f}%",
				f"{r['sharpe']:.2f}",
				f"{r['trades']}"
			])
		
		table = ax6.table(
			cellText=table_data,
			colLabels=['Pair/TF', 'ROI', 'WR', 'Sharpe', 'Trades'],
			cellLoc='center',
			loc='center',
			colWidths=[0.25, 0.15, 0.15, 0.15, 0.15]
		)
		table.auto_set_font_size(False)
		table.set_fontsize(9)
		table.scale(1, 2)
		
		# Стиль заголовка
		for i in range(5):
			table[(0, i)].set_facecolor('#4CAF50')
			table[(0, i)].set_text_props(weight='bold', color='white')
		
		plt.tight_layout()
		
		# Сохраняем
		timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
		filename = f"tests/backtest_v53_comparison_{timestamp}.png"
		plt.savefig(filename, dpi=150, bbox_inches='tight')
		print(f"\n💾 График сохранён: {filename}")
		
		plt.show()
	
	def plot_equity_curves(self, results_list: List[Dict], title: str = "Equity Curves"):
		"""
		Рисует кривые капитала для сравнения
		"""
		if not results_list:
			return
		
		results_list = [r for r in results_list if r is not None and r.get('equity_curve')]
		
		if not results_list:
			print("❌ Нет данных equity curve для визуализации")
			return
		
		fig, ax = plt.subplots(figsize=(15, 8))
		
		for r in results_list:
			equity_curve = r['equity_curve']
			if equity_curve:
				df_equity = pd.DataFrame(equity_curve)
				label = f"{r['symbol']} {r['interval']} (ROI: {r['roi']:+.2f}%)"
				ax.plot(df_equity['timestamp'], df_equity['equity'], label=label, linewidth=2, alpha=0.8)
		
		ax.axhline(y=100, color='gray', linestyle='--', linewidth=1, label='Initial Balance')
		ax.set_xlabel('Time')
		ax.set_ylabel('Portfolio Value ($)')
		ax.set_title(title, fontsize=14, fontweight='bold')
		ax.legend(loc='best')
		ax.grid(alpha=0.3)
		
		plt.tight_layout()
		
		timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
		filename = f"tests/equity_curves_v53_{timestamp}.png"
		plt.savefig(filename, dpi=150, bbox_inches='tight')
		print(f"💾 Equity curves сохранены: {filename}")
		
		plt.show()


async def main():
	"""Главная функция для запуска бэктестов"""
	
	print("="*70)
	print("🚀 БЭКТЕСТ V5.3 ПАРАМЕТРОВ")
	print("="*70)
	
	async with aiohttp.ClientSession() as session:
		backtest = BacktestV53(session)
		
		# Конфигурации для тестирования
		configs = {
			'V5.2 (Current)': {},  # Текущие параметры из config.py
			'V5.3 (Recommended)': {
				'NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT': 0.07,
				'VOLUME_SPIKE_THRESHOLD': 2.2,
				'KELLY_FRACTION': 0.20,
				'MIN_TRADES_FOR_KELLY': 15,
				'MR_TRAILING_ACTIVATION': 0.018,
				'MR_TRAILING_DISTANCE': 0.012,
			}
		}
		
		# Тестируемые пары и таймфреймы
		test_cases = [
			('BNBUSDT', '1h', 45),   # Лучшая пара
			('BTCUSDT', '1h', 45),   # Стабильная
			('ETHUSDT', '1h', 45),   # Средняя
		]
		
		all_results = []
		
		# Запускаем бэктесты
		for config_name, config_override in configs.items():
			print(f"\n{'='*70}")
			print(f"📊 ТЕСТИРОВАНИЕ КОНФИГУРАЦИИ: {config_name}")
			print(f"{'='*70}")
			
			for symbol, interval, days in test_cases:
				result = await backtest.run_backtest(
					symbol=symbol,
					interval=interval,
					days=days,
					config_override=config_override
				)
				
				if result:
					result['config'] = config_name
					all_results.append(result)
				
				await asyncio.sleep(0.5)  # Небольшая задержка между запросами
		
		# Визуализация
		if all_results:
			print(f"\n{'='*70}")
			print(f"📊 ВИЗУАЛИЗАЦИЯ РЕЗУЛЬТАТОВ")
			print(f"{'='*70}")
			
			# Группируем результаты по конфигурациям
			v52_results = [r for r in all_results if r['config'] == 'V5.2 (Current)']
			v53_results = [r for r in all_results if r['config'] == 'V5.3 (Recommended)']
			
			# Визуализация V5.2
			if v52_results:
				backtest.visualize_results(v52_results, "Backtest V5.2 (Current Configuration)")
				backtest.plot_equity_curves(v52_results, "Equity Curves V5.2")
			
			# Визуализация V5.3
			if v53_results:
				backtest.visualize_results(v53_results, "Backtest V5.3 (Recommended Configuration)")
				backtest.plot_equity_curves(v53_results, "Equity Curves V5.3")
			
			# Сравнительная визуализация
			backtest.visualize_results(all_results, "Comparison: V5.2 vs V5.3")
			
			# Сохраняем результаты в CSV
			df_results = pd.DataFrame([{
				'config': r['config'],
				'symbol': r['symbol'],
				'interval': r['interval'],
				'roi': r['roi'],
				'winrate': r['winrate'],
				'sharpe': r['sharpe'],
				'max_dd': r['max_dd'],
				'trades': r['trades'],
				'signals': r['signals']
			} for r in all_results])
			
			timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
			csv_filename = f"tests/backtest_v53_results_{timestamp}.csv"
			df_results.to_csv(csv_filename, index=False)
			print(f"\n💾 Результаты сохранены: {csv_filename}")
			
			# Печатаем итоговую таблицу
			print(f"\n{'='*70}")
			print(f"📊 ИТОГОВАЯ ТАБЛИЦА")
			print(f"{'='*70}")
			print(df_results.to_string(index=False))
			
			# Сравнение средних метрик
			print(f"\n{'='*70}")
			print(f"📈 СРАВНЕНИЕ СРЕДНИХ МЕТРИК")
			print(f"{'='*70}")
			
			for config_name in ['V5.2 (Current)', 'V5.3 (Recommended)']:
				config_results = [r for r in all_results if r['config'] == config_name]
				if config_results:
					avg_roi = sum(r['roi'] for r in config_results) / len(config_results)
					avg_winrate = sum(r['winrate'] for r in config_results) / len(config_results)
					avg_sharpe = sum(r['sharpe'] for r in config_results) / len(config_results)
					avg_dd = sum(r['max_dd'] for r in config_results) / len(config_results)
					total_trades = sum(r['trades'] for r in config_results)
					
					print(f"\n{config_name}:")
					print(f"  Средний ROI:      {avg_roi:+.2f}%")
					print(f"  Средний Winrate:  {avg_winrate:.1f}%")
					print(f"  Средний Sharpe:   {avg_sharpe:.2f}")
					print(f"  Средний Max DD:   {avg_dd:.2f}%")
					print(f"  Всего сделок:     {total_trades}")
		else:
			print("❌ Нет результатов для визуализации")
		
		print(f"\n{'='*70}")
		print(f"✅ БЭКТЕСТ ЗАВЕРШЁН")
		print(f"{'='*70}")


if __name__ == "__main__":
	asyncio.run(main())

