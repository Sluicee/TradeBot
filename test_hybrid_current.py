"""
Проверка текущего HYBRID режима (TF + MR long-only)
Цель: понять работает ли стратегия вообще
"""

import asyncio
import pandas as pd
from datetime import datetime, timedelta
from data_provider import DataProvider
from signal_generator import SignalGenerator
import config

class HybridBacktest:
	"""Простой бэктест для проверки HYBRID"""
	
	def __init__(self, symbol="BTCUSDT", start_balance=1000.0):
		self.symbol = symbol
		self.start_balance = start_balance
		self.balance = start_balance
		self.position = None
		self.trades = []
	
	def enter_trade(self, date, price, mode, reason):
		"""Открыть позицию"""
		if self.position:
			return False
		
		position_value = self.balance * 0.5  # 50% позиция
		position_qty = position_value / price
		
		self.position = {
			'entry_date': date,
			'entry_price': price,
			'qty': position_qty,
			'value': position_value,
			'mode': mode,
			'reason': reason,
			'tp_price': price * 1.03,  # TP 3%
			'sl_price': price * 0.985,  # SL 1.5%
			'max_exit_date': date + pd.Timedelta(hours=48)
		}
		return True
	
	def check_exit(self, date, high, low, close):
		"""Проверить условия выхода"""
		if not self.position:
			return None
		
		reason = None
		exit_price = close
		
		# Check TP
		if high >= self.position['tp_price']:
			reason = "TAKE_PROFIT"
			exit_price = self.position['tp_price']
		# Check SL
		elif low <= self.position['sl_price']:
			reason = "STOP_LOSS"
			exit_price = self.position['sl_price']
		# Check timeout
		elif date >= self.position['max_exit_date']:
			reason = "TIMEOUT"
		
		if reason:
			pnl_usd = (exit_price - self.position['entry_price']) * self.position['qty']
			pnl_percent = ((exit_price / self.position['entry_price']) - 1) * 100
			
			self.balance += pnl_usd
			hours_held = (date - self.position['entry_date']).total_seconds() / 3600
			
			trade = {
				'symbol': self.symbol,
				'entry_time': self.position['entry_date'],
				'entry_price': self.position['entry_price'],
				'entry_mode': self.position['mode'],
				'entry_reason': self.position['reason'],
				'exit_time': date,
				'exit_price': exit_price,
				'pnl_percent': pnl_percent,
				'pnl_usd': pnl_usd,
				'exit_reason': reason,
				'hours_held': hours_held
			}
			
			self.trades.append(trade)
			self.position = None
			return trade
		
		return None
	
	def run(self, df):
		"""Запустить бэктест"""
		gen = SignalGenerator(df)
		gen.compute_indicators()
		
		signals_generated = 0
		buy_signals = 0
		hold_signals = 0
		
		# Проходим по свечам
		for i in range(200, len(gen.df)):
			current_date = gen.df.index[i]
			current_high = gen.df['high'].iloc[i]
			current_low = gen.df['low'].iloc[i]
			current_close = gen.df['close'].iloc[i]
			
			# Проверяем выход
			self.check_exit(current_date, current_high, current_low, current_close)
			
			if self.position:
				continue
			
			# Генерируем сигнал
			sub_df = gen.df.iloc[:i+1].copy()
			temp_gen = SignalGenerator(sub_df)
			temp_gen.df = sub_df
			
			result = temp_gen.generate_signal_hybrid(last_mode="HOLD", last_mode_time=0)
			signals_generated += 1
			
			if result['signal'] == 'BUY':
				buy_signals += 1
				bullish = result.get('bullish_votes', 0)
				bearish = result.get('bearish_votes', 0)
				delta = bullish - bearish
				
				# Порог - 5 голосов (как в оригинале)
				if delta >= 5:
					mode = result.get('active_mode', 'HYBRID')
					reasons = result.get('reasons', [])
					reason_str = " | ".join(reasons[:3]) if reasons else "Unknown"
					
					self.enter_trade(current_date, current_close, mode, reason_str)
			else:
				hold_signals += 1
		
		# Закрыть открытую позицию
		if self.position:
			last_date = gen.df.index[-1]
			last_close = gen.df['close'].iloc[-1]
			self.check_exit(last_date, last_close, last_close, last_close)
		
		# Метрики
		return self.calculate_metrics(), signals_generated, buy_signals, hold_signals
	
	def calculate_metrics(self):
		"""Метрики"""
		if not self.trades:
			return {
				'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
				'total_return': 0, 'final_balance': self.balance,
				'avg_profit': 0, 'avg_loss': 0, 'profit_factor': 0,
				'trades_df': pd.DataFrame()
			}
		
		df_trades = pd.DataFrame(self.trades)
		wins = len(df_trades[df_trades['pnl_usd'] > 0])
		losses = len(df_trades) - wins
		win_rate = (wins / len(df_trades) * 100) if len(df_trades) > 0 else 0
		total_return = ((self.balance / self.start_balance) - 1) * 100
		
		profit_trades = df_trades[df_trades['pnl_usd'] > 0]['pnl_usd']
		loss_trades = df_trades[df_trades['pnl_usd'] <= 0]['pnl_usd']
		
		avg_profit = profit_trades.mean() if len(profit_trades) > 0 else 0
		avg_loss = abs(loss_trades.mean()) if len(loss_trades) > 0 else 0
		profit_factor = (profit_trades.sum() / abs(loss_trades.sum())) if len(loss_trades) > 0 and loss_trades.sum() != 0 else 0
		
		return {
			'total_trades': len(df_trades),
			'wins': wins,
			'losses': losses,
			'win_rate': win_rate,
			'total_return': total_return,
			'final_balance': self.balance,
			'avg_profit': avg_profit,
			'avg_loss': avg_loss,
			'profit_factor': profit_factor,
			'trades_df': df_trades
		}

async def test_hybrid(symbol, interval, days):
	"""Тест одной пары"""
	print(f"\n{'='*80}")
	print(f"TESTING HYBRID: {symbol} ({interval}, {days}d)")
	print(f"{'='*80}")
	
	# Загружаем данные
	interval_hours = {"15m": 0.25, "1h": 1, "4h": 4}
	hours_per_candle = interval_hours.get(interval, 1)
	limit = int((days * 24) / hours_per_candle)
	
	import aiohttp
	async with aiohttp.ClientSession() as session:
		provider = DataProvider(session=session)
		df = await provider.fetch_klines(symbol=symbol, interval=interval, limit=limit)
		
		if df is None or len(df) < 200:
			print(f"ERROR: Not enough data")
			return None
		
		print(f"Data: {len(df)} candles")
		print(f"Period: {df.index[0]} to {df.index[-1]}")
		print(f"Price: ${df['close'].iloc[0]:.2f} -> ${df['close'].iloc[-1]:.2f} ({((df['close'].iloc[-1]/df['close'].iloc[0])-1)*100:+.1f}%)")
		
		# Запускаем бэктест
		backtest = HybridBacktest(symbol=symbol, start_balance=1000.0)
		metrics, total_signals, buy_signals, hold_signals = backtest.run(df)
		
		print(f"\nSIGNALS GENERATED:")
		print(f"  Total signals checked: {total_signals}")
		print(f"  BUY signals: {buy_signals} ({(buy_signals/total_signals*100) if total_signals > 0 else 0:.1f}%)")
		print(f"  HOLD signals: {hold_signals} ({(hold_signals/total_signals*100) if total_signals > 0 else 0:.1f}%)")
		
		print(f"\nTRADES EXECUTED:")
		print(f"  Total Trades: {metrics['total_trades']}")
		print(f"  Wins: {metrics['wins']} | Losses: {metrics['losses']}")
		print(f"  Win Rate: {metrics['win_rate']:.1f}%")
		print(f"  Avg Profit: ${metrics['avg_profit']:.2f} | Avg Loss: ${metrics['avg_loss']:.2f}")
		print(f"  Profit Factor: {metrics['profit_factor']:.2f}")
		
		print(f"\nPERFORMANCE:")
		print(f"  ROI: {metrics['total_return']:.2f}%")
		print(f"  Final Balance: ${metrics['final_balance']:.2f}")
		print(f"  Buy & Hold: {((df['close'].iloc[-1]/df['close'].iloc[0])-1)*100:+.2f}%")
		
		# Детали трейдов
		if metrics['total_trades'] > 0:
			df_trades = metrics['trades_df']
			
			print(f"\nTRADE BREAKDOWN:")
			for mode in df_trades['entry_mode'].unique():
				mode_trades = df_trades[df_trades['entry_mode'] == mode]
				mode_pnl = mode_trades['pnl_usd'].sum()
				mode_wins = len(mode_trades[mode_trades['pnl_usd'] > 0])
				mode_wr = (mode_wins / len(mode_trades) * 100)
				print(f"  {mode}: {len(mode_trades)} trades, {mode_wins} wins ({mode_wr:.0f}%), PnL=${mode_pnl:.2f}")
			
			print(f"\nEXIT REASONS:")
			for reason in df_trades['exit_reason'].unique():
				count = len(df_trades[df_trades['exit_reason'] == reason])
				print(f"  {reason}: {count} ({count/len(df_trades)*100:.0f}%)")
			
			# Сохраняем детали
			csv_name = f"hybrid_test_{symbol}_{interval}_{days}d.csv"
			df_trades.to_csv(csv_name, index=False)
			print(f"\nSaved: {csv_name}")
		
		return {
			'symbol': symbol,
			'interval': interval,
			'days': days,
			'metrics': metrics,
			'signals': {'total': total_signals, 'buy': buy_signals, 'hold': hold_signals}
		}

async def main():
	print("\n" + "="*80)
	print("HYBRID STRATEGY VERIFICATION TEST")
	print("="*80)
	print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
	print(f"\nТекущие параметры из config.py:")
	print(f"  Voting threshold: 5 голосов")
	print(f"  RSI window: {config.RSI_WINDOW}")
	print(f"  ADX window: {config.ADX_WINDOW}")
	
	# Тестируем на разных периодах и парах
	test_configs = [
		# Короткий период (последние 30 дней)
		{"symbol": "BTCUSDT", "interval": "1h", "days": 30},
		{"symbol": "BNBUSDT", "interval": "1h", "days": 30},
		
		# Средний период (90 дней)
		{"symbol": "BTCUSDT", "interval": "1h", "days": 90},
		{"symbol": "ETHUSDT", "interval": "1h", "days": 90},
	]
	
	all_results = []
	
	for cfg in test_configs:
		result = await test_hybrid(cfg['symbol'], cfg['interval'], cfg['days'])
		if result:
			all_results.append(result)
		await asyncio.sleep(0.5)
	
	# Сводка
	print("\n" + "="*80)
	print("SUMMARY")
	print("="*80)
	
	if all_results:
		summary_data = []
		for res in all_results:
			m = res['metrics']
			s = res['signals']
			summary_data.append({
				'Symbol': res['symbol'],
				'Period': f"{res['days']}d",
				'Signals': s['total'],
				'BUY%': f"{(s['buy']/s['total']*100) if s['total'] > 0 else 0:.1f}",
				'Trades': m['total_trades'],
				'Winrate%': m['win_rate'],
				'ROI%': m['total_return'],
				'PF': m['profit_factor']
			})
		
		df_summary = pd.DataFrame(summary_data)
		print("\n" + df_summary.to_string(index=False))
		
		# Общая статистика
		total_trades = sum([r['metrics']['total_trades'] for r in all_results])
		avg_winrate = sum([r['metrics']['win_rate'] for r in all_results if r['metrics']['total_trades'] > 0]) / len([r for r in all_results if r['metrics']['total_trades'] > 0]) if any(r['metrics']['total_trades'] > 0 for r in all_results) else 0
		
		print(f"\n{'='*80}")
		print("OVERALL STATS")
		print(f"{'='*80}")
		print(f"Total Trades Across All Tests: {total_trades}")
		print(f"Average Winrate: {avg_winrate:.1f}%")
		
		if total_trades == 0:
			print(f"\n{'='*80}")
			print("⚠️  WARNING: HYBRID НЕ ГЕНЕРИРУЕТ ТРЕЙДЫ!")
			print(f"{'='*80}")
			print("Возможные причины:")
			print("1. Порог 5 голосов слишком высокий")
			print("2. Конфликты индикаторов блокируют сигналы")
			print("3. ADX фильтры слишком строгие")
			print("4. Falling knife фильтры слишком агрессивные")
			print("\nРекомендуется:")
			print("- Снизить порог до 3 голосов")
			print("- Упростить фильтры")
			print("- Добавить адаптивные пороги")
		else:
			print(f"\n✅ HYBRID работает! Сгенерировано {total_trades} трейдов")
	
	print("\n" + "="*80)
	print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
	print("="*80)

if __name__ == "__main__":
	asyncio.run(main())

