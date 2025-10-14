"""
🔄 MEAN REVERSION BACKTEST
Полный бэктест стратегии mean reversion с:
- CSV логированием сделок
- Сравнением с trend-following
- Визуализацией результатов
"""

import os
import pandas as pd
import numpy as np
import aiohttp
import asyncio
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from data_provider import DataProvider
from signal_generator import SignalGenerator
from config import (
	COMMISSION_RATE, INITIAL_BALANCE,
	# Mean Reversion параметры v4
	MR_TAKE_PROFIT_PERCENT, MR_STOP_LOSS_PERCENT, MR_MAX_HOLDING_HOURS,
	# Трейлинг стоп v4 (двухуровневый)
	USE_TRAILING_STOP_MR, MR_TRAILING_ACTIVATION, MR_TRAILING_DISTANCE,
	MR_TRAILING_AGGRESSIVE_ACTIVATION, MR_TRAILING_AGGRESSIVE_DISTANCE
)

class MeanReversionBacktest:
	"""Бэктест для mean reversion стратегии"""
	
	def __init__(self, symbol: str, interval: str, period_days: int, start_balance: float):
		self.symbol = symbol
		self.interval = interval
		self.period_days = period_days
		self.start_balance = start_balance
		self.balance = start_balance
		self.position = 0.0
		self.entry_price = None
		self.entry_time = None
		self.entry_zscore = None
		self.entry_sl = None  # Динамический SL для текущей позиции
		self.entry_tp = None  # v4: Динамический TP для текущей позиции
		self.max_price = 0.0  # Для трейлинг стопа
		self.trailing_active = False  # Флаг активации обычного трейлинг стопа
		self.trailing_aggressive_active = False  # v4: Флаг агрессивного трейлинга
		self.trades = []
		self.equity_curve = []
		self.zscore_pnl_data = []  # Для scatter графика
		
	async def fetch_data(self) -> pd.DataFrame:
		"""Получаем данные с Binance"""
		candles_per_hour = int(60 / int(self.interval.replace('m',''))) if 'm' in self.interval else 1
		required_candles = self.period_days * 24 * candles_per_hour
		
		# Binance API лимит обычно 1000-1500, но для большого периода берём максимум
		# Если требуется больше - будет меньше дней, чем запросили
		limit = min(required_candles, 1500)
		
		async with aiohttp.ClientSession() as session:
			provider = DataProvider(session)
			df = await provider.fetch_klines(symbol=self.symbol, interval=self.interval, limit=limit)
			
			if df is not None and not df.empty:
				# Пересчитываем реальное количество дней
				actual_days = len(df) / (24 * candles_per_hour)
				if actual_days < self.period_days:
					print(f"NOTE: Loaded {actual_days:.1f} days instead of {self.period_days} (API limit)")
			
			return df
	
	def run_backtest(self, df: pd.DataFrame, strategy: str = "mean_reversion") -> Dict[str, Any]:
		"""
		Запуск бэктеста
		strategy: "mean_reversion" или "trend_following"
		"""
		if df is None or df.empty:
			print(f"Нет данных для {self.symbol}")
			return None
		
		# Генерируем сигналы
		signals = []
		min_window = 50  # Для Z-score нужно 50 свечей
		
		for i in range(len(df)):
			sub_df = df.iloc[:i+1]
			if len(sub_df) < min_window:
				signals.append({
					"time": sub_df.index[-1],
					"price": sub_df["close"].iloc[-1],
					"signal": "HOLD",
					"zscore": 0,
					"rsi": 50,
					"adx": 0
				})
				continue
			
			gen = SignalGenerator(sub_df)
			gen.compute_indicators()
			
			if strategy == "mean_reversion":
				res = gen.generate_signal_mean_reversion()
			else:
				res = gen.generate_signal()
			
			signals.append({
				"time": sub_df.index[-1],
				"price": res["price"],
				"signal": res["signal"],
				"zscore": res.get("zscore", 0),
				"rsi": res.get("RSI", 50),
				"adx": res.get("ADX", 0),
				"position_size_percent": res.get("position_size_percent", 0.5),
				"dynamic_sl": res.get("dynamic_sl", None),
				"dynamic_tp": res.get("dynamic_tp", None),  # v4: Динамический TP
				"falling_knife": res.get("falling_knife_detected", False)
			})
		
		# Симулируем торговлю
		self.balance = self.start_balance
		self.position = 0.0
		self.entry_price = None
		self.entry_time = None
		self.entry_zscore = None
		self.entry_sl = None
		self.entry_tp = None  # v4
		self.max_price = 0.0
		self.trailing_active = False
		self.trailing_aggressive_active = False  # v4
		self.trades = []
		self.equity_curve = []
		
		total_commission = 0.0
		wins = 0
		losses = 0
		max_equity = self.start_balance
		max_drawdown = 0.0
		
		for i, sig in enumerate(signals):
			current_time = sig["time"]
			price = sig["price"]
			signal = sig["signal"]
			zscore = sig["zscore"]
			
			# Расчёт equity
			if self.position > 0:
				position_value = self.position * price
				total_equity = self.balance + position_value
			else:
				total_equity = self.balance
			
			self.equity_curve.append({
				"time": current_time,
				"equity": total_equity,
				"price": price
			})
			
			# Обновляем max equity и drawdown
			if total_equity > max_equity:
				max_equity = total_equity
			
			current_dd = (max_equity - total_equity) / max_equity if max_equity > 0 else 0
			if current_dd > max_drawdown:
				max_drawdown = current_dd
			
			# Проверка выхода из позиции
			if self.position > 0 and self.entry_price:
				pnl_percent = (price - self.entry_price) / self.entry_price
				hours_held = (current_time - self.entry_time).total_seconds() / 3600 if self.entry_time else 0
				
				# Обновляем максимальную цену для трейлинг стопа
				if price > self.max_price:
					self.max_price = price
				
				# v4: Двухуровневый трейлинг стоп
				if USE_TRAILING_STOP_MR:
					# Агрессивный трейлинг (после +2%)
					if not self.trailing_aggressive_active and pnl_percent >= MR_TRAILING_AGGRESSIVE_ACTIVATION:
						self.trailing_aggressive_active = True
					
					# Обычный трейлинг (после +0.8%)
					if not self.trailing_active and pnl_percent >= MR_TRAILING_ACTIVATION:
						self.trailing_active = True
					
					# Проверяем агрессивный трейлинг (приоритет)
					if self.trailing_aggressive_active:
						trailing_drop = (self.max_price - price) / self.max_price
						if trailing_drop >= MR_TRAILING_AGGRESSIVE_DISTANCE:
							sell_value = self.position * price
							commission = sell_value * COMMISSION_RATE
							total_commission += commission
							self.balance += sell_value - commission
							
							reason = "TRAILING_AGGRESSIVE" if self.trailing_aggressive_active else "TRAILING_STOP"
							self.trades.append({
								"symbol": self.symbol,
								"entry_time": self.entry_time,
								"entry_price": self.entry_price,
								"entry_zscore": self.entry_zscore,
								"exit_time": current_time,
								"exit_price": price,
								"pnl_percent": pnl_percent * 100,
								"pnl_usd": (sell_value - commission) - (self.entry_price * self.position),
								"reason": reason,
								"hours_held": hours_held
							})
							
							self.zscore_pnl_data.append({
								"zscore": self.entry_zscore,
								"pnl": pnl_percent * 100
							})
							
							if pnl_percent > 0:
								wins += 1
							else:
								losses += 1
							
							self.position = 0.0
							self.entry_price = None
							self.trailing_active = False
							self.trailing_aggressive_active = False
							self.max_price = 0.0
							continue
					
					# Проверяем обычный трейлинг
					elif self.trailing_active:
						trailing_drop = (self.max_price - price) / self.max_price
						if trailing_drop >= MR_TRAILING_DISTANCE:
							sell_value = self.position * price
							commission = sell_value * COMMISSION_RATE
							total_commission += commission
							self.balance += sell_value - commission
							
							self.trades.append({
								"symbol": self.symbol,
								"entry_time": self.entry_time,
								"entry_price": self.entry_price,
								"entry_zscore": self.entry_zscore,
								"exit_time": current_time,
								"exit_price": price,
								"pnl_percent": pnl_percent * 100,
								"pnl_usd": (sell_value - commission) - (self.entry_price * self.position),
								"reason": "TRAILING_STOP",
								"hours_held": hours_held
							})
							
							self.zscore_pnl_data.append({
								"zscore": self.entry_zscore,
								"pnl": pnl_percent * 100
							})
							
							if pnl_percent > 0:
								wins += 1
							else:
								losses += 1
							
							self.position = 0.0
							self.entry_price = None
							self.trailing_active = False
							self.trailing_aggressive_active = False
							self.max_price = 0.0
							continue
				
				# Используем динамический SL если доступен
				current_sl = self.entry_sl if self.entry_sl else MR_STOP_LOSS_PERCENT
				
				# Стоп-лосс (динамический или фиксированный)
				if pnl_percent <= -current_sl:
					sell_value = self.position * price
					commission = sell_value * COMMISSION_RATE
					total_commission += commission
					self.balance += sell_value - commission
					
					sl_type = "DYNAMIC_SL" if self.entry_sl else "STOP_LOSS"
					
					self.trades.append({
						"symbol": self.symbol,
						"entry_time": self.entry_time,
						"entry_price": self.entry_price,
						"entry_zscore": self.entry_zscore,
						"exit_time": current_time,
						"exit_price": price,
						"pnl_percent": pnl_percent * 100,
						"pnl_usd": (sell_value - commission) - (self.entry_price * self.position),
						"reason": sl_type,
						"hours_held": hours_held
					})
					
					self.zscore_pnl_data.append({
						"zscore": self.entry_zscore,
						"pnl": pnl_percent * 100
					})
					
					losses += 1
					self.position = 0.0
					self.entry_price = None
					self.entry_sl = None
					self.trailing_active = False
					self.max_price = 0.0
					continue
				
				# v5: Таймаут (max holding time) - проверяем до TP
				if hours_held > MR_MAX_HOLDING_HOURS:
					sell_value = self.position * price
					commission = sell_value * COMMISSION_RATE
					total_commission += commission
					self.balance += sell_value - commission
					
					self.trades.append({
						"symbol": self.symbol,
						"entry_time": self.entry_time,
						"entry_price": self.entry_price,
						"entry_zscore": self.entry_zscore,
						"exit_time": current_time,
						"exit_price": price,
						"pnl_percent": pnl_percent * 100,
						"pnl_usd": (sell_value - commission) - (self.entry_price * self.position),
						"reason": "TIMEOUT",
						"hours_held": hours_held
					})
					
					self.zscore_pnl_data.append({
						"zscore": self.entry_zscore,
						"pnl": pnl_percent * 100
					})
					
					if pnl_percent > 0:
						wins += 1
					else:
						losses += 1
					
					self.position = 0.0
					self.entry_price = None
					continue
				
				# v4: Тейк-профит (динамический или фиксированный)
				current_tp = self.entry_tp if self.entry_tp else MR_TAKE_PROFIT_PERCENT
				if pnl_percent >= current_tp or signal == "SELL":
					sell_value = self.position * price
					commission = sell_value * COMMISSION_RATE
					total_commission += commission
					self.balance += sell_value - commission
					
					exit_reason = "TAKE_PROFIT" if pnl_percent >= current_tp else "SIGNAL_EXIT"
					
					self.trades.append({
						"symbol": self.symbol,
						"entry_time": self.entry_time,
						"entry_price": self.entry_price,
						"entry_zscore": self.entry_zscore,
						"exit_time": current_time,
						"exit_price": price,
						"pnl_percent": pnl_percent * 100,
						"pnl_usd": (sell_value - commission) - (self.entry_price * self.position),
						"reason": exit_reason,
						"hours_held": hours_held
					})
					
					self.zscore_pnl_data.append({
						"zscore": self.entry_zscore,
						"pnl": pnl_percent * 100
					})
					
				if pnl_percent > 0:
					wins += 1
				else:
					losses += 1
				
				self.position = 0.0
				self.entry_price = None
				continue
			
			# Вход в позицию
			if signal == "BUY" and self.position == 0 and self.balance > 0:
				position_size_percent = sig.get("position_size_percent", 0.5)
				invest_amount = self.balance * position_size_percent
				commission = invest_amount * COMMISSION_RATE
				total_commission += commission
				self.position = (invest_amount - commission) / price
				self.entry_price = price
				self.entry_time = current_time
				self.entry_zscore = zscore
				self.entry_sl = sig.get("dynamic_sl", None)  # Сохраняем динамический SL
				self.entry_tp = sig.get("dynamic_tp", None)  # v4: Сохраняем динамический TP
				self.max_price = price  # Инициализируем для трейлинг стопа
				self.trailing_active = False
				self.trailing_aggressive_active = False
				self.balance -= invest_amount
		
		# Закрываем открытую позицию
		if self.position > 0:
			final_price = signals[-1]["price"]
			sell_value = self.position * final_price
			commission = sell_value * COMMISSION_RATE
			total_commission += commission
			self.balance += sell_value - commission
			
			pnl_percent = (final_price - self.entry_price) / self.entry_price
			hours_held = (signals[-1]["time"] - self.entry_time).total_seconds() / 3600
			
			self.trades.append({
				"symbol": self.symbol,
				"entry_time": self.entry_time,
				"entry_price": self.entry_price,
				"entry_zscore": self.entry_zscore,
				"exit_time": signals[-1]["time"],
				"exit_price": final_price,
				"pnl_percent": pnl_percent * 100,
				"pnl_usd": (sell_value - commission) - (self.entry_price * self.position),
				"reason": "FINAL_CLOSE",
				"hours_held": hours_held
			})
			
			self.zscore_pnl_data.append({
				"zscore": self.entry_zscore,
				"pnl": pnl_percent * 100
			})
			
			if pnl_percent > 0:
				wins += 1
			else:
				losses += 1
			
			self.position = 0.0
		
		# Расчёт метрик
		total_return = self.balance - self.start_balance
		total_return_pct = (total_return / self.start_balance) * 100
		win_rate = (wins / (wins + losses)) * 100 if (wins + losses) > 0 else 0
		
		# Average win/loss
		profitable_trades = [t for t in self.trades if t["pnl_percent"] > 0]
		losing_trades = [t for t in self.trades if t["pnl_percent"] < 0]
		
		avg_win = np.mean([t["pnl_percent"] for t in profitable_trades]) if profitable_trades else 0
		avg_loss = np.mean([t["pnl_percent"] for t in losing_trades]) if losing_trades else 0
		
		# Среднее время удержания
		avg_holding_time = np.mean([t["hours_held"] for t in self.trades]) if self.trades else 0
		
		# Sharpe Ratio (упрощённый)
		returns = [t["pnl_percent"] for t in self.trades]
		sharpe_ratio = (np.mean(returns) / np.std(returns)) if len(returns) > 1 and np.std(returns) > 0 else 0
		
		return {
			"strategy": strategy,
			"symbol": self.symbol,
			"start_balance": self.start_balance,
			"final_balance": self.balance,
			"total_return": total_return,
			"total_return_pct": total_return_pct,
			"total_commission": total_commission,
			"trades_count": len(self.trades),
			"wins": wins,
			"losses": losses,
			"win_rate": win_rate,
			"avg_win": avg_win,
			"avg_loss": avg_loss,
			"max_drawdown": max_drawdown * 100,
			"avg_holding_hours": avg_holding_time,
			"sharpe_ratio": sharpe_ratio
		}
	
	def save_trades_to_csv(self, filename: str):
		"""Сохраняем сделки в CSV"""
		if not self.trades:
			return
		
		with open(filename, 'w', newline='', encoding='utf-8') as f:
			fieldnames = ["symbol", "entry_time", "entry_price", "entry_zscore", 
						  "exit_time", "exit_price", "pnl_percent", "pnl_usd", 
						  "reason", "hours_held"]
			writer = csv.DictWriter(f, fieldnames=fieldnames)
			writer.writeheader()
			writer.writerows(self.trades)
		
		print(f"CSV saved: {filename}")
	
	def plot_equity_curve(self, compare_with: 'MeanReversionBacktest' = None, save_path: str = None):
		"""Рисуем equity curve"""
		if not self.equity_curve:
			return
		
		df_equity = pd.DataFrame(self.equity_curve)
		df_equity['time'] = pd.to_datetime(df_equity['time'])
		
		fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
		
		# График 1: Equity curve
		ax1.plot(df_equity['time'], df_equity['equity'], label='Mean Reversion', linewidth=2, color='blue')
		
		if compare_with and compare_with.equity_curve:
			df_compare = pd.DataFrame(compare_with.equity_curve)
			df_compare['time'] = pd.to_datetime(df_compare['time'])
			ax1.plot(df_compare['time'], df_compare['equity'], label='Trend Following', 
					linewidth=2, color='orange', alpha=0.7)
		
		ax1.axhline(y=self.start_balance, color='gray', linestyle='--', alpha=0.5, label='Начальный баланс')
		ax1.set_ylabel('Equity ($)', fontsize=12)
		ax1.set_title(f'📈 Equity Curve Comparison - {self.symbol}', fontsize=14, fontweight='bold')
		ax1.legend(loc='best')
		ax1.grid(True, alpha=0.3)
		
		# График 2: Цена актива
		ax2.plot(df_equity['time'], df_equity['price'], label=f'{self.symbol} Price', 
				linewidth=2, color='green', alpha=0.7)
		ax2.set_ylabel('Цена ($)', fontsize=12)
		ax2.set_xlabel('Дата', fontsize=12)
		ax2.legend(loc='best')
		ax2.grid(True, alpha=0.3)
		
		# Форматирование оси X
		ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
		ax2.xaxis.set_major_locator(mdates.DayLocator(interval=7))
		plt.xticks(rotation=45)
		
		plt.tight_layout()
		
		if save_path:
			plt.savefig(save_path, dpi=150, bbox_inches='tight')
			print(f"Chart saved: {save_path}")
		else:
			plt.savefig('equity_curve.png', dpi=150, bbox_inches='tight')
			print("Chart saved: equity_curve.png")
		
		plt.close()
	
	def plot_zscore_vs_pnl(self, save_path: str = None):
		"""Scatter график Z-score vs P&L"""
		if not self.zscore_pnl_data:
			return
		
		df_scatter = pd.DataFrame(self.zscore_pnl_data)
		
		fig, ax = plt.subplots(figsize=(12, 8))
		
		# Разделяем на прибыльные и убыточные
		profitable = df_scatter[df_scatter['pnl'] > 0]
		losing = df_scatter[df_scatter['pnl'] <= 0]
		
		ax.scatter(profitable['zscore'], profitable['pnl'], 
				  c='green', alpha=0.6, s=100, label='Прибыльные', edgecolors='black', linewidth=0.5)
		ax.scatter(losing['zscore'], losing['pnl'], 
				  c='red', alpha=0.6, s=100, label='Убыточные', edgecolors='black', linewidth=0.5)
		
		# Линии для порогов
		ax.axvline(x=-2.5, color='blue', linestyle='--', alpha=0.5, label='Z-score порог входа (-2.5)')
		ax.axhline(y=0, color='gray', linestyle='-', alpha=0.5)
		ax.axhline(y=3, color='green', linestyle='--', alpha=0.5, label='TP 3%')
		ax.axhline(y=-2, color='red', linestyle='--', alpha=0.5, label='SL -2%')
		
		ax.set_xlabel('Z-score при входе', fontsize=12)
		ax.set_ylabel('P&L (%)', fontsize=12)
		ax.set_title(f'📊 Z-score vs P&L - {self.symbol}', fontsize=14, fontweight='bold')
		ax.legend(loc='best')
		ax.grid(True, alpha=0.3)
		
		plt.tight_layout()
		
		if save_path:
			plt.savefig(save_path, dpi=150, bbox_inches='tight')
			print(f"Chart saved: {save_path}")
		else:
			plt.savefig('zscore_vs_pnl.png', dpi=150, bbox_inches='tight')
			print("Chart saved: zscore_vs_pnl.png")
		
		plt.close()


async def main():
	"""Главная функция - запуск бэктеста для обеих стратегий"""
	
	# Параметры
	symbol = "BTCUSDT"
	interval = "1h"  # 1 час (для получения большего периода)
	period_days = 90  # 90 дней
	start_balance = 100.0
	
	print("="*80)
	print("MEAN REVERSION BACKTEST")
	print("="*80)
	print(f"Symbol: {symbol}")
	print(f"Interval: {interval}")
	print(f"Period: {period_days} days")
	print(f"Start balance: ${start_balance}")
	print("="*80)
	
	# Создаём экземпляры бэктеста
	mr_backtest = MeanReversionBacktest(symbol, interval, period_days, start_balance)
	tf_backtest = MeanReversionBacktest(symbol, interval, period_days, start_balance)
	
	# Получаем данные (один раз)
	print("\nLoading data...")
	df = await mr_backtest.fetch_data()
	
	if df is None or df.empty:
		print("ERROR: Failed to load data")
		return
	
	print(f"OK: Loaded {len(df)} candles")
	
	# Запускаем бэктест Mean Reversion
	print("\n" + "="*80)
	print("Running MEAN REVERSION strategy...")
	print("="*80)
	mr_results = mr_backtest.run_backtest(df, strategy="mean_reversion")
	
	# Запускаем бэктест Trend Following
	print("\n" + "="*80)
	print("Running TREND FOLLOWING strategy (baseline)...")
	print("="*80)
	tf_results = tf_backtest.run_backtest(df, strategy="trend_following")
	
	# Сохраняем сделки в CSV
	mr_backtest.save_trades_to_csv("mean_reversion_trades.csv")
	tf_backtest.save_trades_to_csv("trend_following_trades.csv")
	
	# Визуализация
	print("\nCreating charts...")
	mr_backtest.plot_equity_curve(compare_with=tf_backtest, save_path="equity_curve_comparison.png")
	mr_backtest.plot_zscore_vs_pnl(save_path="zscore_vs_pnl.png")
	
	# ====================================================================
	# СРАВНИТЕЛЬНАЯ ТАБЛИЦА
	# ====================================================================
	
	print("\n" + "="*100)
	print("STRATEGY COMPARISON")
	print("="*100)
	
	print(f"\n{'Metric':<30} {'Trend-Following':<20} {'Mean Reversion':<20} {'Delta Change':<20}")
	print("-"*100)
	
	# Доходность
	tf_return = tf_results['total_return_pct']
	mr_return = mr_results['total_return_pct']
	delta_return = mr_return - tf_return
	print(f"{'Total Return':<30} {tf_return:>18.2f}% {mr_return:>18.2f}% {delta_return:>+18.2f}%")
	
	# Win Rate
	tf_wr = tf_results['win_rate']
	mr_wr = mr_results['win_rate']
	delta_wr = mr_wr - tf_wr
	print(f"{'Win Rate':<30} {tf_wr:>18.1f}% {mr_wr:>18.1f}% {delta_wr:>+18.1f}%")
	
	# Max Drawdown
	tf_dd = tf_results['max_drawdown']
	mr_dd = mr_results['max_drawdown']
	delta_dd = mr_dd - tf_dd
	print(f"{'Max Drawdown':<30} {tf_dd:>18.2f}% {mr_dd:>18.2f}% {delta_dd:>+18.2f}%")
	
	# Среднее удержание
	tf_hold = tf_results['avg_holding_hours']
	mr_hold = mr_results['avg_holding_hours']
	print(f"{'Avg Holding (hours)':<30} {tf_hold:>18.1f}h {mr_hold:>18.1f}h {'DOWN' if mr_hold < tf_hold else 'UP':<20}")
	
	# Количество сделок
	tf_trades = tf_results['trades_count']
	mr_trades = mr_results['trades_count']
	delta_trades_pct = ((mr_trades - tf_trades) / tf_trades * 100) if tf_trades > 0 else 0
	print(f"{'Trades Count':<30} {tf_trades:>18} {mr_trades:>18} {delta_trades_pct:>+17.0f}%")
	
	# Average Win
	tf_avg_win = tf_results['avg_win']
	mr_avg_win = mr_results['avg_win']
	print(f"{'Average Win':<30} {tf_avg_win:>18.2f}% {mr_avg_win:>18.2f}% {mr_avg_win - tf_avg_win:>+18.2f}%")
	
	# Average Loss
	tf_avg_loss = tf_results['avg_loss']
	mr_avg_loss = mr_results['avg_loss']
	print(f"{'Average Loss':<30} {tf_avg_loss:>18.2f}% {mr_avg_loss:>18.2f}% {mr_avg_loss - tf_avg_loss:>+18.2f}%")
	
	# Sharpe Ratio
	tf_sharpe = tf_results['sharpe_ratio']
	mr_sharpe = mr_results['sharpe_ratio']
	print(f"{'Sharpe Ratio':<30} {tf_sharpe:>18.2f} {mr_sharpe:>18.2f} {mr_sharpe - tf_sharpe:>+18.2f}")
	
	print("-"*100)
	
	# ====================================================================
	# РЕЗЮМЕ
	# ====================================================================
	
	print("\n" + "="*100)
	print("SUMMARY")
	print("="*100)
	
	print(f"""
Mean Reversion strategy {'OUTPERFORMS' if mr_return > tf_return else 'UNDERPERFORMS'} Trend-Following by return ({mr_return:+.2f}% vs {tf_return:+.2f}%).

MR Win Rate is {'higher' if mr_wr > tf_wr else 'lower'} ({mr_wr:.1f}% vs {tf_wr:.1f}%), which {'confirms' if mr_wr > tf_wr else 'refutes'} 
the hypothesis about more frequent profitable trades on local bounces.

MR Max Drawdown is {'lower' if mr_dd < tf_dd else 'higher'} ({mr_dd:.2f}% vs {tf_dd:.2f}%), making the strategy 
{'less' if mr_dd < tf_dd else 'more'} risky.

MR generates {'more' if mr_trades > tf_trades else 'fewer'} trades ({mr_trades} vs {tf_trades}) with average holding 
{mr_hold:.1f}h vs {tf_hold:.1f}h for TF. These are {'short' if mr_hold < 24 else 'long'} positions, which matches 
the mean reversion concept.

Sharpe Ratio is {'better' if mr_sharpe > tf_sharpe else 'worse'} for MR ({mr_sharpe:.2f} vs {tf_sharpe:.2f}), indicating 
{'higher risk-adjusted efficiency' if mr_sharpe > tf_sharpe else 'lower risk-adjusted performance'}.
	""")
	
	print("="*100)
	print("\nBacktest completed!")
	print(f"CSV files: mean_reversion_trades.csv, trend_following_trades.csv")
	print(f"Charts: equity_curve_comparison.png, zscore_vs_pnl.png")
	print("="*100)


if __name__ == "__main__":
	asyncio.run(main())

