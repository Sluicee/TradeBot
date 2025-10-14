"""
🔬 WALK-FORWARD OPTIMIZATION для HYBRID v5.3
Оптимизирует ключевые параметры:
- PARTIAL_TP_TRIGGER (0.015-0.025)
- PARTIAL_TP_REMAINING_TP (0.03-0.05)
- HYBRID_MIN_TIME_IN_MODE (0.5-2h)
- HYBRID_ADX_MR_THRESHOLD (18-25)
- HYBRID_ADX_TF_THRESHOLD (22-30)
"""

import pandas as pd
import numpy as np
import asyncio
import aiohttp
from datetime import datetime
from itertools import product
from typing import Dict, List, Any
import json

from data_provider import DataProvider
from signal_generator import SignalGenerator
from config import COMMISSION_RATE

class HybridOptimizerV53:
	"""Walk-Forward оптимизация HYBRID v5.3"""
	
	def __init__(self, symbol: str = "BTCUSDT", interval: str = "1h", start_balance: float = 100.0):
		self.symbol = symbol
		self.interval = interval
		self.start_balance = start_balance
		
		# Параметры для оптимизации (компактная сетка)
		self.param_grid = {
			'partial_tp_trigger': [0.015, 0.02, 0.025],  # Порог partial TP
			'partial_tp_remaining': [0.03, 0.04, 0.05],  # TP для остатка
			'min_time_in_mode': [0.5, 1.0, 1.5, 2.0],    # Мин время в режиме
			'adx_mr_threshold': [20, 22, 24],            # ADX для MR
			'adx_tf_threshold': [24, 26, 28],            # ADX для TF
		}
		
		# MR параметры (фиксированные из config)
		self.mr_tp = 0.035
		self.mr_sl = 0.028
		self.mr_max_holding = 24
		
		# TF параметры (фиксированные)
		self.tf_tp = 0.05
		self.tf_sl = 0.05
		self.tf_max_holding = 72
		
		self.results = []
	
	async def fetch_data(self, days: int = 90) -> pd.DataFrame:
		"""Загружаем исторические данные"""
		if self.interval.endswith('h'):
			hours_per_candle = int(self.interval[:-1])
		elif self.interval.endswith('m'):
			hours_per_candle = int(self.interval[:-1]) / 60
		else:
			hours_per_candle = 24
		
		candles_per_hour = 1 / hours_per_candle
		required_candles = min(int(days * 24 * candles_per_hour), 1500)
		
		async with aiohttp.ClientSession() as session:
			provider = DataProvider(session)
			df = await provider.fetch_klines(symbol=self.symbol, interval=self.interval, limit=required_candles)
			return df
	
	def backtest(self, df: pd.DataFrame, params: Dict[str, float]) -> Dict[str, Any]:
		"""
		Упрощённый бэктест с заданными параметрами
		Возвращает метрики: ROI, Sharpe, Winrate, Trades
		"""
		balance = self.start_balance
		position = 0.0
		entry_price = None
		entry_time = None
		entry_mode = None
		partial_tp_taken = False
		breakeven_sl_active = False
		
		trades = []
		last_mode = None
		last_mode_time = 0.0
		
		for i in range(len(df)):
			if i < 50:  # Минимум данных для индикаторов
				continue
			
			sub_df = df.iloc[:i+1]
			current_time = sub_df.index[-1]
			price = sub_df['close'].iloc[-1]
			
			# Генерируем сигнал с кастомными параметрами
			gen = SignalGenerator(sub_df)
			gen.compute_indicators()
			
			# Обновляем время в режиме
			if last_mode and i > 50:
				time_diff = (sub_df.index[-1] - sub_df.index[-2]).total_seconds() / 3600
				last_mode_time += time_diff
			
			res = gen.generate_signal_hybrid(
				last_mode=last_mode,
				last_mode_time=last_mode_time
			)
			
			signal = res['signal']
			active_mode = res.get('active_mode', 'NONE')
			adx = res.get('ADX', 0)
			
			# Применяем кастомные ADX пороги
			if adx < params['adx_mr_threshold']:
				active_mode = "MEAN_REVERSION"
			elif adx > params['adx_tf_threshold']:
				active_mode = "TREND_FOLLOWING"
			
			# Обновляем режим с учётом MIN_TIME
			if active_mode != last_mode and active_mode not in ["NONE", "TRANSITION"]:
				if last_mode_time >= params['min_time_in_mode']:
					last_mode = active_mode
					last_mode_time = 0.0
			
			# Управление позицией
			if position > 0 and entry_price:
				pnl_percent = (price - entry_price) / entry_price
				hours_held = (current_time - entry_time).total_seconds() / 3600 if entry_time else 0
				
				# Partial TP
				if not partial_tp_taken and pnl_percent >= params['partial_tp_trigger']:
					partial_position = position * 0.5
					sell_value = partial_position * price
					commission = sell_value * COMMISSION_RATE
					balance += sell_value - commission
					
					trades.append({
						'pnl_percent': pnl_percent * 100,
						'pnl_usd': (sell_value - commission) - (entry_price * partial_position),
						'reason': 'PARTIAL_TP'
					})
					
					position -= partial_position
					partial_tp_taken = True
					breakeven_sl_active = True
				
				# Break-even SL
				if breakeven_sl_active and price <= entry_price:
					sell_value = position * price
					commission = sell_value * COMMISSION_RATE
					balance += sell_value - commission
					
					trades.append({
						'pnl_percent': 0.0,
						'pnl_usd': -commission,
						'reason': 'BREAKEVEN_SL'
					})
					
					position = 0.0
					entry_price = None
					partial_tp_taken = False
					breakeven_sl_active = False
					continue
				
				# Определяем SL/TP для текущего режима
				if entry_mode == "MEAN_REVERSION":
					current_sl = self.mr_sl
					current_tp = params['partial_tp_remaining'] if partial_tp_taken else self.mr_tp
					max_holding = self.mr_max_holding
				else:  # TF
					current_sl = self.tf_sl
					current_tp = params['partial_tp_remaining'] if partial_tp_taken else self.tf_tp
					max_holding = self.tf_max_holding
				
				# Stop Loss
				if pnl_percent <= -current_sl:
					sell_value = position * price
					commission = sell_value * COMMISSION_RATE
					balance += sell_value - commission
					
					trades.append({
						'pnl_percent': pnl_percent * 100,
						'pnl_usd': (sell_value - commission) - (entry_price * position),
						'reason': 'STOP_LOSS'
					})
					
					position = 0.0
					entry_price = None
					partial_tp_taken = False
					breakeven_sl_active = False
					continue
				
				# Take Profit
				if pnl_percent >= current_tp:
					sell_value = position * price
					commission = sell_value * COMMISSION_RATE
					balance += sell_value - commission
					
					trades.append({
						'pnl_percent': pnl_percent * 100,
						'pnl_usd': (sell_value - commission) - (entry_price * position),
						'reason': 'TAKE_PROFIT'
					})
					
					position = 0.0
					entry_price = None
					partial_tp_taken = False
					breakeven_sl_active = False
					continue
				
				# Timeout
				if hours_held > max_holding:
					sell_value = position * price
					commission = sell_value * COMMISSION_RATE
					balance += sell_value - commission
					
					trades.append({
						'pnl_percent': pnl_percent * 100,
						'pnl_usd': (sell_value - commission) - (entry_price * position),
						'reason': 'TIMEOUT'
					})
					
					position = 0.0
					entry_price = None
					partial_tp_taken = False
					breakeven_sl_active = False
					continue
			
			# Вход (BUY)
			if signal == 'BUY' and position == 0:
				invest_amount = balance * 0.5
				commission = invest_amount * COMMISSION_RATE
				position = (invest_amount - commission) / price
				entry_price = price
				entry_time = current_time
				entry_mode = active_mode
				balance -= invest_amount
		
		# Закрываем оставшуюся позицию
		if position > 0:
			final_price = df['close'].iloc[-1]
			sell_value = position * final_price
			commission = sell_value * COMMISSION_RATE
			balance += sell_value - commission
			
			pnl_percent = (final_price - entry_price) / entry_price
			trades.append({
				'pnl_percent': pnl_percent * 100,
				'pnl_usd': (sell_value - commission) - (entry_price * position),
				'reason': 'FINAL'
			})
		
		# Расчёт метрик
		if not trades:
			return {
				'roi': 0.0,
				'sharpe': 0.0,
				'winrate': 0.0,
				'trades': 0,
				'avg_win': 0.0,
				'avg_loss': 0.0
			}
		
		df_trades = pd.DataFrame(trades)
		total_return = ((balance - self.start_balance) / self.start_balance) * 100
		
		wins = len(df_trades[df_trades['pnl_usd'] > 0])
		losses = len(df_trades[df_trades['pnl_usd'] <= 0])
		win_rate = (wins / len(df_trades)) * 100 if len(df_trades) > 0 else 0
		
		avg_win = df_trades[df_trades['pnl_usd'] > 0]['pnl_percent'].mean() if wins > 0 else 0
		avg_loss = df_trades[df_trades['pnl_usd'] <= 0]['pnl_percent'].mean() if losses > 0 else 0
		
		# Sharpe Ratio
		if len(df_trades) > 1:
			returns = df_trades['pnl_percent'].values
			sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(len(returns)) if np.std(returns) > 0 else 0
		else:
			sharpe = 0
		
		return {
			'roi': total_return,
			'sharpe': sharpe,
			'winrate': win_rate,
			'trades': len(df_trades),
			'avg_win': avg_win,
			'avg_loss': avg_loss,
			'final_balance': balance
		}
	
	async def optimize(self, df: pd.DataFrame) -> Dict[str, Any]:
		"""Оптимизация параметров на данных"""
		print(f"\nОптимизация на {len(df)} свечах...")
		
		# Генерируем все комбинации параметров
		param_combinations = []
		for values in product(*self.param_grid.values()):
			params = dict(zip(self.param_grid.keys(), values))
			# Фильтруем невалидные комбинации (ADX_TF должен быть > ADX_MR)
			if params['adx_tf_threshold'] > params['adx_mr_threshold']:
				param_combinations.append(params)
		
		print(f"Тестирую {len(param_combinations)} комбинаций параметров...")
		
		best_params = None
		best_score = -float('inf')
		
		for idx, params in enumerate(param_combinations):
			if (idx + 1) % 10 == 0:
				print(f"  Прогресс: {idx+1}/{len(param_combinations)}")
			
			metrics = self.backtest(df, params)
			
			# Scoring function: комбинация ROI и Sharpe
			score = metrics['roi'] + (metrics['sharpe'] * 10)  # Sharpe важнее
			
			if score > best_score:
				best_score = score
				best_params = params.copy()
				best_params['metrics'] = metrics
		
		print(f"\n✅ Лучшие параметры найдены!")
		print(f"  ROI: {best_params['metrics']['roi']:.2f}%")
		print(f"  Sharpe: {best_params['metrics']['sharpe']:.2f}")
		print(f"  Winrate: {best_params['metrics']['winrate']:.1f}%")
		print(f"  Trades: {best_params['metrics']['trades']}")
		
		return best_params
	
	async def walk_forward(self, df: pd.DataFrame, train_ratio: float = 0.6) -> Dict[str, Any]:
		"""
		Walk-Forward анализ:
		- Train: 60% данных (оптимизация)
		- Test: 40% данных (валидация)
		"""
		train_size = int(len(df) * train_ratio)
		
		train_df = df.iloc[:train_size]
		test_df = df.iloc[train_size:]
		
		print(f"\n{'='*80}")
		print(f"WALK-FORWARD ANALYSIS")
		print(f"{'='*80}")
		print(f"Train: {len(train_df)} свечей ({train_df.index[0]} - {train_df.index[-1]})")
		print(f"Test:  {len(test_df)} свечей ({test_df.index[0]} - {test_df.index[-1]})")
		
		# Оптимизация на train
		print(f"\n📈 TRAIN PERIOD (оптимизация):")
		best_params = await self.optimize(train_df)
		
		# Тестирование на test
		print(f"\n📊 TEST PERIOD (валидация):")
		test_metrics = self.backtest(test_df, best_params)
		
		print(f"\nРезультаты на TEST:")
		print(f"  ROI: {test_metrics['roi']:.2f}%")
		print(f"  Sharpe: {test_metrics['sharpe']:.2f}")
		print(f"  Winrate: {test_metrics['winrate']:.1f}%")
		print(f"  Trades: {test_metrics['trades']}")
		
		return {
			'best_params': best_params,
			'train_metrics': best_params['metrics'],
			'test_metrics': test_metrics
		}
	
	async def run(self, days: int = 90):
		"""Запускает полный процесс оптимизации"""
		print(f"\n{'='*80}")
		print(f"HYBRID v5.3 - WALK-FORWARD OPTIMIZATION")
		print(f"{'='*80}")
		print(f"Symbol: {self.symbol}")
		print(f"Interval: {self.interval}")
		print(f"Period: {days} days")
		print(f"Start balance: ${self.start_balance}")
		
		# Загружаем данные
		df = await self.fetch_data(days)
		if df is None or len(df) < 100:
			print("❌ Недостаточно данных")
			return None
		
		print(f"\nДанные загружены: {len(df)} свечей")
		print(f"Период: {df.index[0]} - {df.index[-1]}")
		
		# Walk-Forward анализ
		results = await self.walk_forward(df)
		
		# Сохраняем результаты
		timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
		filename = f"optimization_results_{self.symbol}_{timestamp}.json"
		
		with open(filename, 'w') as f:
			# Конвертируем в JSON-совместимый формат
			results_json = {
				'best_params': {k: v for k, v in results['best_params'].items() if k != 'metrics'},
				'train_metrics': results['train_metrics'],
				'test_metrics': results['test_metrics']
			}
			json.dump(results_json, f, indent=2)
		
		print(f"\n✅ Результаты сохранены: {filename}")
		print(f"\n{'='*80}")
		print(f"РЕКОМЕНДУЕМЫЕ ПАРАМЕТРЫ:")
		print(f"{'='*80}")
		for param, value in results['best_params'].items():
			if param != 'metrics':
				print(f"  {param}: {value}")
		print(f"{'='*80}")
		
		return results


async def main():
	"""Запуск оптимизации для BTCUSDT"""
	optimizer = HybridOptimizerV53(
		symbol="BTCUSDT",
		interval="1h",
		start_balance=100.0
	)
	
	results = await optimizer.run(days=90)
	
	if results:
		print(f"\n🎯 Оптимизация завершена!")
		print(f"\nСледующий шаг: обновить config.py с найденными параметрами")


if __name__ == "__main__":
	asyncio.run(main())

