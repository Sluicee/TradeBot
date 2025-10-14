"""
🔀 HYBRID STRATEGY BACKTEST
Бэктест гибридной стратегии MR + TF с переключением по ADX
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
	# Mean Reversion параметры v5
	MR_TAKE_PROFIT_PERCENT, MR_STOP_LOSS_PERCENT, MR_MAX_HOLDING_HOURS,
	# Трейлинг стоп v5
	USE_TRAILING_STOP_MR, MR_TRAILING_ACTIVATION, MR_TRAILING_DISTANCE,
	MR_TRAILING_AGGRESSIVE_ACTIVATION, MR_TRAILING_AGGRESSIVE_DISTANCE,
	# Trend Following параметры
	MAX_HOLDING_HOURS,
	# Гибридные параметры
	HYBRID_ADX_MR_THRESHOLD, HYBRID_ADX_TF_THRESHOLD, HYBRID_MIN_TIME_IN_MODE
)

class HybridBacktest:
	"""Бэктест для гибридной стратегии (MR + TF)"""
	
	def __init__(self, symbol: str, interval: str, period_days: int, start_balance: float):
		self.symbol = symbol
		self.interval = interval
		self.period_days = period_days
		self.start_balance = start_balance
		self.balance = start_balance
		self.position = 0.0
		self.entry_price = None
		self.entry_time = None
		self.entry_mode = None  # "MR" или "TF"
		self.entry_sl = None  # Динамический SL для MR
		self.entry_tp = None  # Динамический TP для MR
		self.max_price = 0.0
		self.trailing_active = False
		self.trailing_aggressive_active = False
		self.trades = []
		self.equity_curve = []
		self.mode_switches = []  # История переключений режимов
		self.last_mode = None
		self.last_mode_time = None
		
	async def fetch_data(self) -> pd.DataFrame:
		"""Получаем данные с Binance"""
		# Вычисляем сколько свечей нужно
		if self.interval.endswith('h'):
			hours_per_candle = int(self.interval[:-1])
		elif self.interval.endswith('m'):
			hours_per_candle = int(self.interval[:-1]) / 60
		else:
			hours_per_candle = 24
		
		candles_per_hour = 1 / hours_per_candle
		required_candles = int(self.period_days * 24 * candles_per_hour)
		
		# Binance API лимит обычно 1000-1500
		limit = min(required_candles, 1500)
		
		print(f"\nLoading data...")
		print(f"NOTE: Requesting {limit} candles")
		
		async with aiohttp.ClientSession() as session:
			provider = DataProvider(session)
			df = await provider.fetch_klines(symbol=self.symbol, interval=self.interval, limit=limit)
			
			if df is not None and not df.empty:
				# Пересчитываем реальное количество дней
				actual_days = len(df) / (24 * candles_per_hour)
				print(f"OK: Loaded {len(df)} candles ({actual_days:.1f} days)\n")
			
			return df
	
	def run_backtest(self, df: pd.DataFrame) -> Dict[str, Any]:
		"""
		Запуск бэктеста гибридной стратегии
		"""
		if df is None or df.empty:
			print(f"Нет данных для {self.symbol}")
			return None
		
		# Генерируем сигналы
		signals = []
		min_window = 50
		
		self.last_mode = None
		self.last_mode_time = None
		
		for i in range(len(df)):
			sub_df = df.iloc[:i+1]
			if len(sub_df) < min_window:
				signals.append({
					"time": sub_df.index[-1],
					"price": sub_df["close"].iloc[-1],
					"signal": "HOLD",
					"active_mode": "NONE",
					"adx": 0
				})
				continue
			
			gen = SignalGenerator(sub_df)
			gen.compute_indicators()
			
			# Вычисляем время в последнем режиме
			if self.last_mode_time is not None and i > 0:
				time_diff = (sub_df.index[-1] - sub_df.index[-2]).total_seconds() / 3600
				self.last_mode_time += time_diff
			
			res = gen.generate_signal_hybrid(
				last_mode=self.last_mode,
				last_mode_time=self.last_mode_time if self.last_mode_time else 0
			)
			
			# Отслеживаем переключения режимов
			current_mode = res.get("active_mode")
			if current_mode != self.last_mode and current_mode not in ["NONE", "TRANSITION"]:
				self.mode_switches.append({
					"time": sub_df.index[-1],
					"from_mode": self.last_mode,
					"to_mode": current_mode,
					"adx": res.get("ADX", 0)
				})
				self.last_mode = current_mode
				self.last_mode_time = 0
			
			signals.append({
				"time": sub_df.index[-1],
				"price": res["price"],
				"signal": res["signal"],
				"active_mode": res.get("active_mode", "NONE"),
				"adx": res.get("ADX", 0),
				"zscore": res.get("zscore", 0),
				"rsi": res.get("RSI", 50),
				"position_size_percent": res.get("position_size_percent", 0.5),
				"dynamic_sl": res.get("dynamic_sl", None),
				"dynamic_tp": res.get("dynamic_tp", None),
				"falling_knife": res.get("falling_knife_detected", False)
			})
		
		# Симулируем торговлю
		self.balance = self.start_balance
		self.position = 0.0
		self.entry_price = None
		self.entry_time = None
		self.entry_mode = None
		self.entry_sl = None
		self.entry_tp = None
		self.max_price = 0.0
		self.trailing_active = False
		self.trailing_aggressive_active = False
		self.trades = []
		self.equity_curve = []
		
		total_commission = 0.0
		wins = 0
		losses = 0
		max_equity = self.start_balance
		max_drawdown = 0.0
		
		mr_trades = 0
		tf_trades = 0
		
		for i, sig in enumerate(signals):
			current_time = sig["time"]
			price = sig["price"]
			signal = sig["signal"]
			active_mode = sig["active_mode"]
			
			# Расчёт equity
			if self.position > 0:
				position_value = self.position * price
				total_equity = self.balance + position_value
			else:
				total_equity = self.balance
			
			self.equity_curve.append({
				"time": current_time,
				"equity": total_equity,
				"price": price,
				"mode": active_mode
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
				
				# Трейлинг стоп (только для MR)
				if self.entry_mode == "MEAN_REVERSION" and USE_TRAILING_STOP_MR:
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
							
							self.trades.append({
								"symbol": self.symbol,
								"entry_time": self.entry_time,
								"entry_price": self.entry_price,
								"entry_mode": self.entry_mode,
								"exit_time": current_time,
								"exit_price": price,
								"pnl_percent": pnl_percent * 100,
								"pnl_usd": (sell_value - commission) - (self.entry_price * self.position),
								"reason": "TRAILING_AGGRESSIVE",
								"hours_held": hours_held
							})
							
							if pnl_percent > 0:
								wins += 1
							else:
								losses += 1
							
							self.position = 0.0
							self.entry_price = None
							self.entry_mode = None
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
								"entry_mode": self.entry_mode,
								"exit_time": current_time,
								"exit_price": price,
								"pnl_percent": pnl_percent * 100,
								"pnl_usd": (sell_value - commission) - (self.entry_price * self.position),
								"reason": "TRAILING_STOP",
								"hours_held": hours_held
							})
							
							if pnl_percent > 0:
								wins += 1
							else:
								losses += 1
							
							self.position = 0.0
							self.entry_price = None
							self.entry_mode = None
							self.trailing_active = False
							self.trailing_aggressive_active = False
							self.max_price = 0.0
							continue
				
				# Используем динамический SL если доступен (для MR)
				if self.entry_mode == "MEAN_REVERSION":
				current_sl = self.entry_sl if self.entry_sl else MR_STOP_LOSS_PERCENT
				current_tp = self.entry_tp if self.entry_tp else MR_TAKE_PROFIT_PERCENT
				max_holding = MR_MAX_HOLDING_HOURS
			else:  # TF
					current_sl = 0.05  # 5% SL для TF
					current_tp = 0.05  # 5% TP для TF
					max_holding = MAX_HOLDING_HOURS
				
				# Стоп-лосс
				if pnl_percent <= -current_sl:
					sell_value = self.position * price
					commission = sell_value * COMMISSION_RATE
					total_commission += commission
					self.balance += sell_value - commission
					
					self.trades.append({
						"symbol": self.symbol,
						"entry_time": self.entry_time,
						"entry_price": self.entry_price,
						"entry_mode": self.entry_mode,
						"exit_time": current_time,
						"exit_price": price,
						"pnl_percent": pnl_percent * 100,
						"pnl_usd": (sell_value - commission) - (self.entry_price * self.position),
						"reason": "STOP_LOSS" if not self.entry_sl else "DYNAMIC_SL",
						"hours_held": hours_held
					})
					
					losses += 1
					self.position = 0.0
					self.entry_price = None
					self.entry_mode = None
					self.entry_sl = None
					self.entry_tp = None
					self.trailing_active = False
					self.trailing_aggressive_active = False
					self.max_price = 0.0
					continue
				
				# Таймаут
				if hours_held > max_holding:
					sell_value = self.position * price
					commission = sell_value * COMMISSION_RATE
					total_commission += commission
					self.balance += sell_value - commission
					
					self.trades.append({
						"symbol": self.symbol,
						"entry_time": self.entry_time,
						"entry_price": self.entry_price,
						"entry_mode": self.entry_mode,
						"exit_time": current_time,
						"exit_price": price,
						"pnl_percent": pnl_percent * 100,
						"pnl_usd": (sell_value - commission) - (self.entry_price * self.position),
						"reason": "TIMEOUT",
						"hours_held": hours_held
					})
					
					if pnl_percent > 0:
						wins += 1
					else:
						losses += 1
					
					self.position = 0.0
					self.entry_price = None
					self.entry_mode = None
					self.entry_sl = None
					self.entry_tp = None
					self.trailing_active = False
					self.trailing_aggressive_active = False
					self.max_price = 0.0
					continue
				
				# Тейк-профит или сигнал выхода
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
						"entry_mode": self.entry_mode,
						"exit_time": current_time,
						"exit_price": price,
						"pnl_percent": pnl_percent * 100,
						"pnl_usd": (sell_value - commission) - (self.entry_price * self.position),
						"reason": exit_reason,
						"hours_held": hours_held
					})
					
					if pnl_percent > 0:
						wins += 1
					else:
						losses += 1
					
					self.position = 0.0
					self.entry_price = None
					self.entry_mode = None
					self.entry_sl = None
					self.entry_tp = None
					continue
			
			# ВХОД (BUY)
			if signal == "BUY" and self.position == 0:
				position_size_percent = sig.get("position_size_percent", 0.5)
				invest_amount = self.balance * position_size_percent
				commission = invest_amount * COMMISSION_RATE
				total_commission += commission
				self.position = (invest_amount - commission) / price
				self.entry_price = price
				self.entry_time = current_time
				self.entry_mode = active_mode
				self.entry_sl = sig.get("dynamic_sl", None)
				self.entry_tp = sig.get("dynamic_tp", None)
				self.max_price = price
				self.trailing_active = False
				self.trailing_aggressive_active = False
				self.balance -= invest_amount
				
				if active_mode == "MEAN_REVERSION":
					mr_trades += 1
				elif active_mode == "TREND_FOLLOWING":
					tf_trades += 1
		
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
				"entry_mode": self.entry_mode,
				"exit_time": signals[-1]["time"],
				"exit_price": final_price,
				"pnl_percent": pnl_percent * 100,
				"pnl_usd": (sell_value - commission) - (self.entry_price * self.position),
				"reason": "FINAL",
				"hours_held": hours_held
			})
			
			if pnl_percent > 0:
				wins += 1
			else:
				losses += 1
		
		# Расчёт метрик
		total_return = ((self.balance - self.start_balance) / self.start_balance) * 100
		win_rate = (wins / len(self.trades)) * 100 if len(self.trades) > 0 else 0
		
		# Avg win/loss
		winning_trades = [t for t in self.trades if t["pnl_percent"] > 0]
		losing_trades = [t for t in self.trades if t["pnl_percent"] <= 0]
		avg_win = np.mean([t["pnl_percent"] for t in winning_trades]) if winning_trades else 0
		avg_loss = np.mean([t["pnl_percent"] for t in losing_trades]) if losing_trades else 0
		
		# Sharpe Ratio
		if len(self.trades) > 1:
			returns = [t["pnl_percent"] for t in self.trades]
			sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(len(self.trades)) if np.std(returns) > 0 else 0
		else:
			sharpe = 0
		
		# Average holding time
		avg_holding = np.mean([t["hours_held"] for t in self.trades]) if self.trades else 0
		
		return {
			"total_return": total_return,
			"win_rate": win_rate,
			"max_drawdown": max_drawdown * 100,
			"trades_count": len(self.trades),
			"wins": wins,
			"losses": losses,
			"avg_win": avg_win,
			"avg_loss": avg_loss,
			"sharpe_ratio": sharpe,
			"avg_holding_hours": avg_holding,
			"total_commission": total_commission,
			"final_balance": self.balance,
			"mr_trades": mr_trades,
			"tf_trades": tf_trades,
			"mode_switches": len(self.mode_switches)
		}
	
	def save_trades_to_csv(self, filename: str):
		"""Сохраняет сделки в CSV"""
		if not self.trades:
			print(f"No trades to save")
			return
		
		with open(filename, 'w', newline='') as f:
			writer = csv.DictWriter(f, fieldnames=self.trades[0].keys())
			writer.writeheader()
			writer.writerows(self.trades)
		
		print(f"CSV saved: {filename}")
	
	def plot_equity_curve(self, save_path: str = "equity_curve_hybrid.png"):
		"""Строит график equity curve с отметками режимов"""
		if not self.equity_curve:
			print("No equity data to plot")
			return
		
		df_equity = pd.DataFrame(self.equity_curve)
		
		fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
		
		# График equity
		ax1.plot(df_equity["time"], df_equity["equity"], label="Equity", color="green", linewidth=2)
		ax1.axhline(y=self.start_balance, color="gray", linestyle="--", label="Start Balance")
		ax1.set_ylabel("Balance (USD)", fontsize=12)
		ax1.set_title(f"Hybrid Strategy Equity Curve - {self.symbol}", fontsize=14, fontweight="bold")
		ax1.legend()
		ax1.grid(True, alpha=0.3)
		
		# График цены с отметками режимов
		ax2.plot(df_equity["time"], df_equity["price"], label="Price", color="blue", alpha=0.7)
		
		# Отмечаем переключения режимов
		for switch in self.mode_switches:
			color = "orange" if switch["to_mode"] == "MEAN_REVERSION" else "purple"
			ax2.axvline(x=switch["time"], color=color, linestyle=":", alpha=0.5)
			ax2.text(switch["time"], df_equity["price"].max() * 0.95, 
					f"→ {switch['to_mode'][:2]}", 
					rotation=90, fontsize=8, color=color)
		
		ax2.set_ylabel("Price (USDT)", fontsize=12)
		ax2.set_xlabel("Time", fontsize=12)
		ax2.legend()
		ax2.grid(True, alpha=0.3)
		
		plt.tight_layout()
		plt.savefig(save_path, dpi=150, bbox_inches='tight')
		plt.close()
		print(f"Chart saved: {save_path}")


async def main():
	# Параметры бэктеста
	symbol = "BTCUSDT"
	interval = "1h"
	period_days = 90
	start_balance = 100.0
	
	print("="*80)
	print("HYBRID STRATEGY BACKTEST (MR + TF with ADX switching)")
	print("="*80)
	print(f"Symbol: {symbol}")
	print(f"Interval: {interval}")
	print(f"Period: {period_days} days")
	print(f"Start balance: ${start_balance}")
	print(f"MR threshold: ADX < {HYBRID_ADX_MR_THRESHOLD}")
	print(f"TF threshold: ADX > {HYBRID_ADX_TF_THRESHOLD}")
	print(f"Min time in mode: {HYBRID_MIN_TIME_IN_MODE}h")
	print("="*80)
	
	# Запуск бэктеста
	backtest = HybridBacktest(symbol, interval, period_days, start_balance)
	df = await backtest.fetch_data()
	
	if df is None or df.empty:
		print("Failed to fetch data")
		return
	
	print("Running HYBRID strategy...")
	print("="*80)
	
	results = backtest.run_backtest(df)
	
	if not results:
		print("Backtest failed")
		return
	
	# Сохраняем CSV
	backtest.save_trades_to_csv("hybrid_trades.csv")
	
	# Создаём графики
	print("\nCreating charts...")
	backtest.plot_equity_curve()
	
	# Выводим результаты
	print("\n" + "="*80)
	print("HYBRID STRATEGY RESULTS")
	print("="*80)
	print(f"Total Return: {results['total_return']:.2f}%")
	print(f"Win Rate: {results['win_rate']:.1f}%")
	print(f"Max Drawdown: {results['max_drawdown']:.2f}%")
	print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
	print(f"Trades: {results['trades_count']} (MR: {results['mr_trades']}, TF: {results['tf_trades']})")
	print(f"Wins/Losses: {results['wins']}/{results['losses']}")
	print(f"Avg Win: {results['avg_win']:.2f}%")
	print(f"Avg Loss: {results['avg_loss']:.2f}%")
	print(f"Avg Holding: {results['avg_holding_hours']:.1f}h")
	print(f"Mode Switches: {results['mode_switches']}")
	print(f"Final Balance: ${results['final_balance']:.2f}")
	print("="*80)
	
	print("\nBacktest completed!")
	print(f"CSV file: hybrid_trades.csv")
	print(f"Chart: equity_curve_hybrid.png")
	print("="*80)


if __name__ == "__main__":
	asyncio.run(main())

