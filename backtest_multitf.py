#!/usr/bin/env python3
"""
Multi-Timeframe Backtest
Сравнение single TF vs MTF анализа на исторических данных
"""

import asyncio
import aiohttp
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json

from data_provider import DataProvider
from signal_generator import SignalGenerator
from logger import logger
from config import (
	STRATEGY_MODE,
	USE_MULTI_TIMEFRAME,
	MTF_TIMEFRAMES,
	COMMISSION_RATE,
	STOP_LOSS_PERCENT,
	TAKE_PROFIT_PERCENT
)


class MTFBacktest:
	"""Бэктест для сравнения single TF и MTF анализа"""
	
	def __init__(self, symbol: str, interval: str = "1h", lookback_days: int = 30):
		self.symbol = symbol
		self.interval = interval
		self.lookback_days = lookback_days
		
		# Результаты
		self.single_tf_results = []
		self.mtf_results = []
		
	async def run(self):
		"""Запускает бэктест"""
		logger.info(f"Запуск MTF бэктеста для {self.symbol} ({self.interval}, {self.lookback_days} дней)")
		
		async with aiohttp.ClientSession() as session:
			provider = DataProvider(session)
			
			# Загружаем данные
			# Для бэктеста нужно больше данных (lookback_days * 24 * 2 для запаса)
			if self.interval == "1h":
				limit = self.lookback_days * 24 * 2
			elif self.interval == "15m":
				limit = self.lookback_days * 96 * 2
			elif self.interval == "4h":
				limit = self.lookback_days * 6 * 2
			else:
				limit = 1000
			
			limit = min(limit, 1000)  # API limit
			
			try:
				klines = await provider.fetch_klines(
					symbol=self.symbol,
					interval=self.interval,
					limit=limit
				)
				df = provider.klines_to_dataframe(klines)
				
				if df.empty:
					logger.error(f"Нет данных для {self.symbol}")
					return
				
				logger.info(f"Загружено {len(df)} свечей")
				
				# Бэктест single TF
				logger.info("Запуск Single TF бэктеста...")
				single_tf_stats = await self._backtest_single_tf(df, provider)
				
				# Бэктест MTF
				logger.info("Запуск MTF бэктеста...")
				mtf_stats = await self._backtest_mtf(df, provider)
				
				# Сравнение результатов
				self._compare_results(single_tf_stats, mtf_stats)
				
			except Exception as e:
				logger.error(f"Ошибка бэктеста: {e}")
	
	async def _backtest_single_tf(self, df: pd.DataFrame, provider: DataProvider) -> Dict:
		"""Бэктест single timeframe"""
		
		trades = []
		balance = 1000.0
		initial_balance = balance
		
		# Минимальное окно для индикаторов
		min_window = 200
		
		for i in range(min_window, len(df)):
			# Берём данные до текущей свечи
			sub_df = df.iloc[:i+1].copy()
			
			try:
				# Генерируем сигнал
				generator = SignalGenerator(sub_df)
				generator.compute_indicators()
				
				if STRATEGY_MODE == "MEAN_REVERSION":
					result = generator.generate_signal_mean_reversion()
				elif STRATEGY_MODE == "HYBRID":
					result = generator.generate_signal_hybrid()
				else:
					result = generator.generate_signal()
				
				signal = result.get("signal", "HOLD")
				price = float(sub_df['close'].iloc[-1])
				
				# Симулируем сделку
				if signal == "BUY" and balance > 0:
					# Открываем позицию
					invest = balance * 0.3  # 30% от баланса
					commission = invest * COMMISSION_RATE
					amount = (invest - commission) / price
					
					# Ищем выход
					entry_idx = i
					entry_price = price
					stop_loss = entry_price * (1 - STOP_LOSS_PERCENT)
					take_profit = entry_price * (1 + TAKE_PROFIT_PERCENT)
					
					exit_price = None
					exit_reason = None
					
					# Проверяем следующие свечи
					for j in range(i+1, min(i+100, len(df))):
						future_price = float(df['close'].iloc[j])
						
						if future_price <= stop_loss:
							exit_price = stop_loss
							exit_reason = "SL"
							break
						elif future_price >= take_profit:
							exit_price = take_profit
							exit_reason = "TP"
							break
					
					# Если не вышли - выходим по текущей цене
					if exit_price is None:
						exit_idx = min(i+50, len(df)-1)
						exit_price = float(df['close'].iloc[exit_idx])
						exit_reason = "TIME"
					
					# Считаем PnL
					sell_value = amount * exit_price
					sell_commission = sell_value * COMMISSION_RATE
					net_value = sell_value - sell_commission
					pnl = net_value - invest
					pnl_percent = (pnl / invest) * 100
					
					balance += pnl
					
					trades.append({
						"entry_price": entry_price,
						"exit_price": exit_price,
						"pnl": pnl,
						"pnl_percent": pnl_percent,
						"reason": exit_reason
					})
					
			except Exception as e:
				logger.warning(f"Ошибка на свече {i}: {e}")
				continue
		
		# Статистика
		total_trades = len(trades)
		winning_trades = len([t for t in trades if t['pnl'] > 0])
		losing_trades = len([t for t in trades if t['pnl'] < 0])
		
		total_pnl = sum(t['pnl'] for t in trades)
		avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
		
		win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
		
		final_balance = balance
		roi = ((final_balance - initial_balance) / initial_balance) * 100
		
		return {
			"total_trades": total_trades,
			"winning_trades": winning_trades,
			"losing_trades": losing_trades,
			"win_rate": win_rate,
			"total_pnl": total_pnl,
			"avg_pnl": avg_pnl,
			"roi": roi,
			"final_balance": final_balance,
			"trades": trades
		}
	
	async def _backtest_mtf(self, df: pd.DataFrame, provider: DataProvider) -> Dict:
		"""Бэктест multi-timeframe"""
		
		trades = []
		balance = 1000.0
		initial_balance = balance
		
		# Минимальное окно для индикаторов
		min_window = 200
		
		for i in range(min_window, len(df)):
			# Берём данные до текущей свечи
			sub_df = df.iloc[:i+1].copy()
			
			try:
				# Генерируем MTF сигнал
				generator = SignalGenerator(sub_df)
				generator.compute_indicators()
				
				# Используем MTF анализ
				result = await generator.generate_signal_multi_timeframe(
					data_provider=provider,
					symbol=self.symbol,
					strategy=STRATEGY_MODE
				)
				
				signal = result.get("signal", "HOLD")
				price = float(sub_df['close'].iloc[-1])
				alignment_strength = result.get("alignment_strength", 0)
				buy_score = result.get("buy_score", 0)
				
				# MTF сигнал - принимаем любой BUY, но адаптируем размер
				if signal == "BUY" and balance > 0:
					# Адаптивный размер позиции на основе согласованности и buy_score
					if alignment_strength >= 1.0:
						# Полное согласие всех TF
						position_size = 0.5
					elif buy_score >= 1.0:
						# Высокий weighted score
						position_size = 0.4
					elif buy_score >= 0.6:
						# Средний score
						position_size = 0.3
					else:
						# Низкий score - пропускаем
						continue
					
					invest = balance * position_size
					commission = invest * COMMISSION_RATE
					amount = (invest - commission) / price
					
					# Ищем выход
					entry_idx = i
					entry_price = price
					stop_loss = entry_price * (1 - STOP_LOSS_PERCENT)
					take_profit = entry_price * (1 + TAKE_PROFIT_PERCENT)
					
					exit_price = None
					exit_reason = None
					
					# Проверяем следующие свечи
					for j in range(i+1, min(i+100, len(df))):
						future_price = float(df['close'].iloc[j])
						
						if future_price <= stop_loss:
							exit_price = stop_loss
							exit_reason = "SL"
							break
						elif future_price >= take_profit:
							exit_price = take_profit
							exit_reason = "TP"
							break
					
					# Если не вышли - выходим по текущей цене
					if exit_price is None:
						exit_idx = min(i+50, len(df)-1)
						exit_price = float(df['close'].iloc[exit_idx])
						exit_reason = "TIME"
					
					# Считаем PnL
					sell_value = amount * exit_price
					sell_commission = sell_value * COMMISSION_RATE
					net_value = sell_value - sell_commission
					pnl = net_value - invest
					pnl_percent = (pnl / invest) * 100
					
					balance += pnl
					
					trades.append({
						"entry_price": entry_price,
						"exit_price": exit_price,
						"pnl": pnl,
						"pnl_percent": pnl_percent,
						"reason": exit_reason,
						"alignment": alignment_strength
					})
					
			except Exception as e:
				logger.warning(f"Ошибка MTF на свече {i}: {e}")
				continue
		
		# Статистика
		total_trades = len(trades)
		winning_trades = len([t for t in trades if t['pnl'] > 0])
		losing_trades = len([t for t in trades if t['pnl'] < 0])
		
		total_pnl = sum(t['pnl'] for t in trades)
		avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
		
		win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
		
		final_balance = balance
		roi = ((final_balance - initial_balance) / initial_balance) * 100
		
		return {
			"total_trades": total_trades,
			"winning_trades": winning_trades,
			"losing_trades": losing_trades,
			"win_rate": win_rate,
			"total_pnl": total_pnl,
			"avg_pnl": avg_pnl,
			"roi": roi,
			"final_balance": final_balance,
			"trades": trades
		}
	
	def _compare_results(self, single_tf: Dict, mtf: Dict):
		"""Сравнивает результаты single TF vs MTF"""
		
		print("\n" + "="*80)
		print(f"[*] РЕЗУЛЬТАТЫ БЭКТЕСТА: {self.symbol} ({self.interval}, {self.lookback_days} дней)")
		print("="*80)
		
		print("\n[1] SINGLE TIMEFRAME:")
		print(f"   Сделок: {single_tf['total_trades']}")
		print(f"   Win Rate: {single_tf['win_rate']:.1f}%")
		print(f"   Всего P/L: ${single_tf['total_pnl']:.2f}")
		print(f"   Средний P/L: ${single_tf['avg_pnl']:.2f}")
		print(f"   ROI: {single_tf['roi']:.2f}%")
		print(f"   Финальный баланс: ${single_tf['final_balance']:.2f}")
		
		print("\n[2] MULTI-TIMEFRAME:")
		print(f"   Сделок: {mtf['total_trades']}")
		print(f"   Win Rate: {mtf['win_rate']:.1f}%")
		print(f"   Всего P/L: ${mtf['total_pnl']:.2f}")
		print(f"   Средний P/L: ${mtf['avg_pnl']:.2f}")
		print(f"   ROI: {mtf['roi']:.2f}%")
		print(f"   Финальный баланс: ${mtf['final_balance']:.2f}")
		
		print("\n[3] СРАВНЕНИЕ:")
		
		# Win Rate improvement
		win_rate_diff = mtf['win_rate'] - single_tf['win_rate']
		win_rate_marker = "[+]" if win_rate_diff > 0 else "[-]" if win_rate_diff < 0 else "[=]"
		print(f"   {win_rate_marker} Win Rate: {win_rate_diff:+.1f}% ({mtf['win_rate']:.1f}% vs {single_tf['win_rate']:.1f}%)")
		
		# ROI improvement
		roi_diff = mtf['roi'] - single_tf['roi']
		roi_marker = "[+]" if roi_diff > 0 else "[-]" if roi_diff < 0 else "[=]"
		print(f"   {roi_marker} ROI: {roi_diff:+.2f}% ({mtf['roi']:.2f}% vs {single_tf['roi']:.2f}%)")
		
		# Trade quality
		if mtf['total_trades'] > 0 and single_tf['total_trades'] > 0:
			avg_pnl_diff = mtf['avg_pnl'] - single_tf['avg_pnl']
			pnl_marker = "[+]" if avg_pnl_diff > 0 else "[-]" if avg_pnl_diff < 0 else "[=]"
			print(f"   {pnl_marker} Средний P/L: ${avg_pnl_diff:+.2f} (${mtf['avg_pnl']:.2f} vs ${single_tf['avg_pnl']:.2f})")
		
		# Trade count
		trade_diff = mtf['total_trades'] - single_tf['total_trades']
		trade_marker = "[+]" if abs(trade_diff) < single_tf['total_trades'] * 0.3 else "[!]"
		print(f"   {trade_marker} Количество сделок: {trade_diff:+d} ({mtf['total_trades']} vs {single_tf['total_trades']})")
		
		print("\n" + "="*80)
		
		# Сохраняем результаты
		timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
		filename = f"backtests/mtf_backtest_{self.symbol}_{self.interval}_{timestamp}.json"
		
		results = {
			"symbol": self.symbol,
			"interval": self.interval,
			"lookback_days": self.lookback_days,
			"timestamp": timestamp,
			"single_tf": single_tf,
			"mtf": mtf,
			"comparison": {
				"win_rate_diff": win_rate_diff,
				"roi_diff": roi_diff,
				"avg_pnl_diff": mtf['avg_pnl'] - single_tf['avg_pnl'],
				"trade_count_diff": trade_diff
			}
		}
		
		try:
			import os
			os.makedirs("backtests", exist_ok=True)
			with open(filename, 'w') as f:
				json.dump(results, f, indent=2)
			logger.info(f"Результаты сохранены в {filename}")
		except Exception as e:
			logger.error(f"Ошибка сохранения результатов: {e}")


async def main():
	"""Запуск бэктеста"""
	import sys
	
	# Параметры из командной строки
	if len(sys.argv) < 2:
		print("Использование: python backtest_multitf.py SYMBOL [INTERVAL] [DAYS]")
		print("Пример: python backtest_multitf.py BTCUSDT 1h 30")
		sys.exit(1)
	
	symbol = sys.argv[1].upper()
	interval = sys.argv[2] if len(sys.argv) > 2 else "1h"
	lookback_days = int(sys.argv[3]) if len(sys.argv) > 3 else 30
	
	backtest = MTFBacktest(symbol, interval, lookback_days)
	await backtest.run()


if __name__ == "__main__":
	asyncio.run(main())

