import os
import pandas as pd
import numpy as np
from data_provider import DataProvider
from signal_generator import SignalGenerator
from paper_trader import get_position_size_percent
import aiohttp
import asyncio
import json
from datetime import datetime, timedelta
from itertools import product
from typing import Dict, List, Tuple, Any
from config import (
	COMMISSION_RATE, INITIAL_BALANCE,
	STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT,
	PARTIAL_CLOSE_PERCENT, TRAILING_STOP_PERCENT
)

# ====================================================================
# WALK-FORWARD ОПТИМИЗАЦИЯ
# ====================================================================

class WalkForwardOptimizer:
	"""
	Walk-Forward бэктестинг с оптимизацией параметров.
	
	Процесс:
	1. Делим данные на окна IS/OOS
	2. На IS-окне оптимизируем параметры
	3. На OOS-окне тестируем с лучшими параметрами
	4. Сдвигаем окно и повторяем
	5. Агрегируем результаты всех OOS периодов
	"""
	
	def __init__(
		self,
		symbol: str,
		interval: str = "15m",
		is_period_hours: int = 168,  # 7 дней (1 неделя) - реалистично для Bybit API
		oos_period_hours: int = 48,   # 2 дня - тестовый период
		start_balance: float = None,
		anchored: bool = False,  # False = Rolling, True = Anchored
		use_statistical_models: bool = False  # Использовать статистические модели
	):
		self.symbol = symbol
		self.interval = interval
		self.is_period_hours = is_period_hours
		self.oos_period_hours = oos_period_hours
		self.start_balance = start_balance or INITIAL_BALANCE
		self.anchored = anchored
		self.use_statistical_models = use_statistical_models
		
		# Параметры для оптимизации (сокращенная сетка для скорости)
		# 🚀 БЫСТРЫЙ режим: ~12 комбинаций, ~5 минут
		self.param_grid = {
			'ema_short': [12],  # Фиксируем стандартное
			'ema_long': [26],   # Фиксируем стандартное
			'rsi_window': [14],  # Фиксируем стандартное
			'macd_fast': [12],   # Фиксируем стандартное
			'macd_slow': [26],   # Фиксируем стандартное
			'macd_signal': [9],  # Фиксируем стандартное
            'vote_threshold_trending': [1, 2, 3],      # было [2, 3]
            'vote_threshold_ranging': [2, 3, 4, 5],    # было [3, 4, 5]
            'min_filters': [1, 2, 3],                  # было [2, 3]
		}
		
		# 🐢 ПОЛНЫЙ режим: ~400 комбинаций, ~1-2 часа (раскомментируй для production)
		# self.param_grid = {
		# 	'ema_short': [10, 12, 14],
		# 	'ema_long': [24, 26, 28],
		# 	'rsi_window': [12, 14, 16],
		# 	'macd_fast': [12],
		# 	'macd_slow': [26],
		# 	'macd_signal': [9],
		# 	'vote_threshold_trending': [2, 3],
		# 	'vote_threshold_ranging': [3, 4, 5],
		# 	'min_filters': [2, 3]
		# }
		
		self.results = {
			'iterations': [],
			'oos_aggregate': {},
			'parameter_stability': {}
		}
	
	async def run(self) -> Dict[str, Any]:
		"""Запускает полный Walk-Forward анализ"""
		models_label = " [СТАТИСТИЧЕСКИЕ МОДЕЛИ]" if self.use_statistical_models else ""
		print(f"\n{'='*100}")
		print(f"WALK-FORWARD БЭКТЕСТИНГ: {self.symbol}{models_label}")
		print(f"{'='*100}")
		print(f"Параметры:")
		print(f"  • Режим: {'Anchored' if self.anchored else 'Rolling'}")
		print(f"  • IS период: {self.is_period_hours}ч ({self.is_period_hours/24:.0f} дней)")
		print(f"  • OOS период: {self.oos_period_hours}ч ({self.oos_period_hours/24:.0f} дней)")
		print(f"  • Начальный баланс: ${self.start_balance}")
		print(f"  • Статистические модели: {'ДА' if self.use_statistical_models else 'НЕТ'}")
		print(f"{'='*100}\n")
		
		# Загружаем полный датасет
		# Пытаемся получить данные для 6 итераций, но адаптируемся к доступным данным
		desired_hours = self.is_period_hours + self.oos_period_hours * 6
		df = await self._fetch_data(desired_hours)
		
		if df is None or len(df) == 0:
			print("❌ Не удалось загрузить данные")
			return None
		
		# Проверяем минимальное требование: 1 IS + 1 OOS
		candles_per_hour = int(60 / int(self.interval.replace('m',''))) if 'm' in self.interval else 1
		min_candles = (self.is_period_hours + self.oos_period_hours) * candles_per_hour
		
		if len(df) < min_candles:
			print(f"❌ Недостаточно данных для Walk-Forward анализа")
			print(f"   Требуется минимум: {min_candles} свечей ({(self.is_period_hours + self.oos_period_hours)/24:.0f} дней)")
			print(f"   Доступно: {len(df)} свечей ({len(df)/candles_per_hour/24:.0f} дней)")
			print(f"\n💡 Попробуйте:")
			print(f"   • Уменьшить IS/OOS периоды")
			print(f"   • Использовать больший интервал (30m, 1h, 4h)")
			return None
		
		print(f"✓ Загружено {len(df)} свечей (период: {df.index[0]} - {df.index[-1]})\n")
		
		# Разбиваем на окна
		windows = self._create_windows(df)
		print(f"✓ Создано {len(windows)} окон Walk-Forward\n")
		
		# Итерации Walk-Forward
		iteration_num = 1
		oos_balances = []
		oos_trades = []
		
		for is_data, oos_data in windows:
			print(f"\n{'─'*100}")
			print(f"📊 ИТЕРАЦИЯ {iteration_num}/{len(windows)}")
			print(f"{'─'*100}")
			print(f"IS период:  {is_data.index[0]} — {is_data.index[-1]} ({len(is_data)} свечей)")
			print(f"OOS период: {oos_data.index[0]} — {oos_data.index[-1]} ({len(oos_data)} свечей)")
			
			# Шаг 1: Оптимизация на IS
			print(f"\n🔧 Оптимизация параметров на IS...")
			best_params, is_metrics = await self._optimize_on_is(is_data)
			
			print(f"\n✓ Лучшие параметры найдены:")
			for param, value in best_params.items():
				print(f"  • {param}: {value}")
			print(f"\nМетрики IS:")
			print(f"  • Прибыль: {is_metrics['profit_percent']:+.2f}%")
			print(f"  • Sharpe: {is_metrics['sharpe_ratio']:.2f}")
			print(f"  • Win Rate: {is_metrics['win_rate']:.1f}%")
			print(f"  • Max DD: {is_metrics['max_drawdown']:.2f}%")
			
			# Шаг 2: Валидация на OOS
			print(f"\n📈 Тестирование на OOS (невиденные данные)...")
			oos_metrics, oos_trades_list = await self._test_on_oos(oos_data, best_params)
			
			print(f"\n✅ Результаты OOS:")
			print(f"  • Прибыль: {oos_metrics['profit_percent']:+.2f}%")
			print(f"  • Sharpe: {oos_metrics['sharpe_ratio']:.2f}")
			print(f"  • Win Rate: {oos_metrics['win_rate']:.1f}%")
			print(f"  • Max DD: {oos_metrics['max_drawdown']:.2f}%")
			print(f"  • Сделок: {oos_metrics['trades_count']}")
			
			# Сравнение IS vs OOS
			profit_degradation = (oos_metrics['profit_percent'] / is_metrics['profit_percent'] * 100) if is_metrics['profit_percent'] != 0 else 0
			print(f"\n📉 Деградация IS→OOS: {profit_degradation:.1f}% от IS прибыли")
			if profit_degradation < 50:
				print(f"   ⚠️ ПРЕДУПРЕЖДЕНИЕ: Сильная деградация! Возможный overfitting")
			elif profit_degradation > 80:
				print(f"   ✅ Хорошая стабильность параметров")
			
			# Сохраняем результаты итерации
			self.results['iterations'].append({
				'iteration': iteration_num,
				'is_period': (str(is_data.index[0]), str(is_data.index[-1])),
				'oos_period': (str(oos_data.index[0]), str(oos_data.index[-1])),
				'best_params': best_params,
				'is_metrics': is_metrics,
				'oos_metrics': oos_metrics,
				'degradation': profit_degradation
			})
			
			oos_balances.append(oos_metrics['final_balance'])
			oos_trades.extend(oos_trades_list)
			
			iteration_num += 1
		
		# Агрегируем результаты всех OOS периодов
		self._aggregate_results(oos_balances, oos_trades)
		
		# Анализ стабильности параметров
		self._analyze_parameter_stability()
		
		# Сохраняем отчет
		self._save_report()
		
		return self.results
	
	async def _fetch_data(self, hours: int) -> pd.DataFrame:
		"""Загружает исторические данные"""
		candles_per_hour = int(60 / int(self.interval.replace('m',''))) if 'm' in self.interval else 1
		total_candles_needed = hours * candles_per_hour
		
		# Bybit API лимит - обычно 200-1000 свечей
		api_limit = 1000
		
		print(f"Загрузка данных: {total_candles_needed} свечей (~{hours/24:.0f} дней)...")
		
		if total_candles_needed > api_limit:
			print(f"⚠️ ВНИМАНИЕ: Запрошено {total_candles_needed} свечей, но Bybit API ограничен ~{api_limit} свечами")
			print(f"   Будет загружено только последние ~{api_limit} свечей (~{api_limit/candles_per_hour/24:.0f} дней)")
			print(f"\n💡 Для длительных периодов используйте больший интервал:")
			print(f"   • 15m → подходит для периодов до 10 дней")
			print(f"   • 1h → подходит для периодов до 40 дней")
			print(f"   • 4h → подходит для периодов до 160 дней")
			print()
			total_candles_needed = api_limit
		
		async with aiohttp.ClientSession() as session:
			provider = DataProvider(session)
			df = await provider.fetch_klines(
				symbol=self.symbol,
				interval=self.interval,
				limit=total_candles_needed
			)
			return df
	
	def _create_windows(self, df: pd.DataFrame) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
		"""Создает окна IS/OOS для Walk-Forward"""
		windows = []
		
		candles_per_hour = int(60 / int(self.interval.replace('m',''))) if 'm' in self.interval else 1
		is_candles = self.is_period_hours * candles_per_hour
		oos_candles = self.oos_period_hours * candles_per_hour
		
		if self.anchored:
			# Anchored: IS растет, начало фиксировано
			start_idx = 0
			while start_idx + is_candles + oos_candles <= len(df):
				is_end = start_idx + is_candles
				oos_end = is_end + oos_candles
				
				is_data = df.iloc[start_idx:is_end].copy()
				oos_data = df.iloc[is_end:oos_end].copy()
				
				windows.append((is_data, oos_data))
				
				# Для Anchored: начало не двигается, но берем больше IS данных
				is_candles += oos_candles
		else:
			# Rolling: окно скользит
			start_idx = 0
			while start_idx + is_candles + oos_candles <= len(df):
				is_end = start_idx + is_candles
				oos_end = is_end + oos_candles
				
				is_data = df.iloc[start_idx:is_end].copy()
				oos_data = df.iloc[is_end:oos_end].copy()
				
				windows.append((is_data, oos_data))
				
				# Сдвигаем окно на OOS период
				start_idx += oos_candles
		
		return windows
	
	async def _optimize_on_is(self, is_data: pd.DataFrame) -> Tuple[Dict, Dict]:
		"""Оптимизирует параметры на IS периоде"""
		best_sharpe = -999
		best_params = None
		best_metrics = None
		
		# Генерируем комбинации параметров
		param_names = list(self.param_grid.keys())
		param_values = [self.param_grid[k] for k in param_names]
		
		total_combinations = np.prod([len(v) for v in param_values])
		print(f"  Тестируем {total_combinations} комбинаций параметров...")
		
		tested = 0
		for combination in product(*param_values):
			params = dict(zip(param_names, combination))
			
			# Проверка валидности: short < long
			if params['ema_short'] >= params['ema_long']:
				continue
			if params['macd_fast'] >= params['macd_slow']:
				continue
			
			tested += 1
			print(f"  [{tested}/{total_combinations}] Тестирую: vote_trend={params.get('vote_threshold_trending', '?')}, vote_range={params.get('vote_threshold_ranging', '?')}, min_filters={params.get('min_filters', '?')}", end='')
			
			# Бэктест с этими параметрами
			metrics, _ = await self._backtest_with_params(is_data, params)
			
			print(f" → Sharpe={metrics['sharpe_ratio']:.2f}, Profit={metrics['profit_percent']:+.1f}%")
			
			# Оптимизируем по Sharpe Ratio (риск-скорректированная доходность)
			if metrics['sharpe_ratio'] > best_sharpe:
				best_sharpe = metrics['sharpe_ratio']
				best_params = params
				best_metrics = metrics
				print(f"     ✓ Новый лучший результат!")
		
		print(f"\n  ✓ Оптимизация завершена ({tested} комбинаций протестировано)")
		
		return best_params, best_metrics
	
	async def _test_on_oos(self, oos_data: pd.DataFrame, params: Dict) -> Tuple[Dict, List]:
		"""Тестирует параметры на OOS периоде"""
		metrics, trades = await self._backtest_with_params(oos_data, params)
		return metrics, trades
	
	async def _backtest_with_params(
		self, df: pd.DataFrame, params: Dict
	) -> Tuple[Dict, List]:
		"""Выполняет бэктест с заданными параметрами"""
		# Генерируем сигналы с параметрами
		signals = []
		min_window = max(params['rsi_window'], params['ema_long'])
		
		for i in range(len(df)):
			sub_df = df.iloc[:i+1]
			if len(sub_df) < min_window:
				signals.append({
					"time": sub_df.index[-1],
					"price": sub_df["close"].iloc[-1],
					"signal": "HOLD",
					"bullish_votes": 0,
					"bearish_votes": 0,
					"ATR": 0
				})
				continue
			
			gen = SignalGenerator(sub_df, use_statistical_models=self.use_statistical_models)
			gen.compute_indicators(
				ema_short_window=params['ema_short'],
				ema_long_window=params['ema_long'],
				rsi_window=params['rsi_window'],
				macd_fast=params['macd_fast'],
				macd_slow=params['macd_slow'],
				macd_signal=params['macd_signal']
			)
			res = gen.generate_signal()
			
			signals.append({
				"time": sub_df.index[-1],
				"price": res["price"],
				"signal": res["signal"],
				"bullish_votes": res["bullish_votes"],
				"bearish_votes": res["bearish_votes"],
				"ATR": res.get("ATR", 0)
			})
		
		# Симуляция торговли
		balance = self.start_balance
		position = 0.0
		entry_price = None
		trades = []
		equity_curve = [balance]
		total_commission = 0.0
		
		stop_loss_triggers = 0
		take_profit_triggers = 0
		partial_closed = False
		max_price = 0.0
		
		for s in signals:
			price = s["price"]
			sig = s["signal"]
			signal_strength = abs(s["bullish_votes"] - s["bearish_votes"])
			atr = s.get("ATR", 0.0)
			
			# Проверка стоп-лосса и тейк-профита
			if position > 0 and entry_price:
				price_change = (price - entry_price) / entry_price
				
				if partial_closed:
					if price > max_price:
						max_price = price
					
					trailing_drop = (max_price - price) / max_price
					if trailing_drop >= TRAILING_STOP_PERCENT:
						sell_value = position * price
						commission = sell_value * COMMISSION_RATE
						total_commission += commission
						balance += sell_value - commission
						trades.append({
							'type': 'TRAILING-STOP',
							'price': price,
							'profit_pct': ((price - entry_price) / entry_price) * 100
						})
						position = 0.0
						entry_price = None
						partial_closed = False
						max_price = 0.0
						continue
				else:
					if price_change <= -STOP_LOSS_PERCENT:
						sell_value = position * price
						commission = sell_value * COMMISSION_RATE
						total_commission += commission
						balance += sell_value - commission
						trades.append({
							'type': 'STOP-LOSS',
							'price': price,
							'profit_pct': price_change * 100
						})
						position = 0.0
						entry_price = None
						stop_loss_triggers += 1
						continue
					
					if price_change >= TAKE_PROFIT_PERCENT:
						close_amount = position * PARTIAL_CLOSE_PERCENT
						keep_amount = position - close_amount
						
						sell_value = close_amount * price
						commission = sell_value * COMMISSION_RATE
						total_commission += commission
						balance += sell_value - commission
						
						trades.append({
							'type': 'PARTIAL-TP',
							'price': price,
							'profit_pct': price_change * 100
						})
						
						position = keep_amount
						partial_closed = True
						max_price = price
						take_profit_triggers += 1
						continue
			
			# Логика входа/выхода
			if sig == "BUY" and position == 0 and balance > 0:
				position_size_percent = get_position_size_percent(signal_strength, atr, price)
				invest_amount = balance * position_size_percent
				
				commission = invest_amount * COMMISSION_RATE
				total_commission += commission
				position = (invest_amount - commission) / price
				entry_price = price
				balance -= invest_amount
				
				trades.append({
					'type': 'BUY',
					'price': price,
					'profit_pct': 0
				})
				
			elif sig == "SELL" and position > 0 and not partial_closed:
				sell_value = position * price
				commission = sell_value * COMMISSION_RATE
				total_commission += commission
				balance += sell_value - commission
				
				profit_on_trade = ((price - entry_price) / entry_price) * 100
				trades.append({
					'type': 'SELL',
					'price': price,
					'profit_pct': profit_on_trade
				})
				position = 0.0
				entry_price = None
			
			# Обновляем equity curve
			total_equity = balance + (position * price if position > 0 else 0)
			equity_curve.append(total_equity)
		
		# Закрываем оставшуюся позицию
		if position > 0:
			final_price = signals[-1]["price"]
			sell_value = position * final_price
			commission = sell_value * COMMISSION_RATE
			total_commission += commission
			balance += sell_value - commission
			profit_on_trade = ((final_price - entry_price) / entry_price) * 100
			trades.append({
				'type': 'FINAL-CLOSE',
				'price': final_price,
				'profit_pct': profit_on_trade
			})
			position = 0.0
		
		# Расчет метрик
		final_balance = balance
		profit = final_balance - self.start_balance
		profit_percent = (profit / self.start_balance) * 100
		
		# Win Rate
		profitable_trades = [t for t in trades if t['type'] in ['SELL', 'PARTIAL-TP', 'FINAL-CLOSE'] and t['profit_pct'] > 0]
		losing_trades = [t for t in trades if t['type'] in ['SELL', 'STOP-LOSS', 'TRAILING-STOP', 'FINAL-CLOSE'] and t['profit_pct'] < 0]
		win_rate = (len(profitable_trades) / (len(profitable_trades) + len(losing_trades)) * 100) if (len(profitable_trades) + len(losing_trades)) > 0 else 0
		
		# Sharpe Ratio (упрощенный: доходность / волатильность доходности)
		returns = np.diff(equity_curve) / equity_curve[:-1]
		sharpe_ratio = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if len(returns) > 0 and np.std(returns) > 0 else 0
		
		# Max Drawdown
		max_drawdown = self._calculate_max_drawdown(equity_curve)
		
		metrics = {
			'final_balance': final_balance,
			'profit': profit,
			'profit_percent': profit_percent,
			'sharpe_ratio': sharpe_ratio,
			'win_rate': win_rate,
			'max_drawdown': max_drawdown,
			'trades_count': len(trades),
			'total_commission': total_commission
		}
		
		return metrics, trades
	
	def _calculate_max_drawdown(self, equity_curve: List[float]) -> float:
		"""Рассчитывает максимальную просадку"""
		peak = equity_curve[0]
		max_dd = 0
		
		for value in equity_curve:
			if value > peak:
				peak = value
			dd = (peak - value) / peak * 100
			if dd > max_dd:
				max_dd = dd
		
		return max_dd
	
	def _aggregate_results(self, oos_balances: List[float], oos_trades: List[Dict]):
		"""Агрегирует результаты всех OOS периодов"""
		print(f"\n\n{'='*100}")
		print("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ WALK-FORWARD")
		print(f"{'='*100}\n")
		
		# Итоговый баланс = результат последнего OOS
		final_balance = oos_balances[-1]
		total_profit = final_balance - self.start_balance
		total_profit_pct = (total_profit / self.start_balance) * 100
		
		print(f"Начальный баланс: ${self.start_balance:.2f}")
		print(f"Итоговый баланс: ${final_balance:.2f}")
		print(f"Общая доходность: ${total_profit:+.2f} ({total_profit_pct:+.2f}%)")
		print(f"Количество итераций: {len(oos_balances)}")
		print(f"Общее количество сделок (OOS): {len(oos_trades)}\n")
		
		# Win Rate агрегированный
		profitable = [t for t in oos_trades if t['profit_pct'] > 0]
		losing = [t for t in oos_trades if t['profit_pct'] < 0]
		total_wr = (len(profitable) / (len(profitable) + len(losing)) * 100) if (len(profitable) + len(losing)) > 0 else 0
		
		print(f"Агрегированный Win Rate: {total_wr:.1f}% ({len(profitable)}W / {len(losing)}L)")
		
		# Средняя прибыль по OOS периодам
		oos_profits = []
		oos_sharpes = []
		for it in self.results['iterations']:
			oos_profits.append(it['oos_metrics']['profit_percent'])
			oos_sharpes.append(it['oos_metrics']['sharpe_ratio'])
		
		avg_oos_profit = np.mean(oos_profits)
		std_oos_profit = np.std(oos_profits)
		avg_sharpe = np.mean(oos_sharpes)
		
		print(f"Средняя прибыль OOS: {avg_oos_profit:+.2f}% (±{std_oos_profit:.2f}%)")
		print(f"Средний Sharpe OOS: {avg_sharpe:.2f}")
		
		# Детализация по итерациям
		print(f"\n{'─'*100}")
		print("Результаты по итерациям:")
		print(f"{'─'*100}")
		print(f"{'Итер':<6} {'IS Profit':<12} {'OOS Profit':<12} {'Деградация':<12} {'OOS Sharpe':<12} {'OOS WR':<10}")
		print(f"{'─'*100}")
		
		for it in self.results['iterations']:
			print(f"{it['iteration']:<6} "
				  f"{it['is_metrics']['profit_percent']:>+10.2f}% "
				  f"{it['oos_metrics']['profit_percent']:>+10.2f}% "
				  f"{it['degradation']:>10.1f}% "
				  f"{it['oos_metrics']['sharpe_ratio']:>10.2f} "
				  f"{it['oos_metrics']['win_rate']:>8.1f}%")
		
		print(f"{'─'*100}\n")
		
		# Сохраняем агрегированные метрики
		self.results['oos_aggregate'] = {
			'final_balance': final_balance,
			'total_profit': total_profit,
			'total_profit_pct': total_profit_pct,
			'avg_oos_profit': avg_oos_profit,
			'std_oos_profit': std_oos_profit,
			'avg_sharpe': avg_sharpe,
			'total_win_rate': total_wr,
			'iterations_count': len(oos_balances),
			'total_trades': len(oos_trades)
		}
	
	def _analyze_parameter_stability(self):
		"""Анализирует стабильность параметров между итерациями"""
		print(f"\n{'='*100}")
		print("🔍 АНАЛИЗ СТАБИЛЬНОСТИ ПАРАМЕТРОВ")
		print(f"{'='*100}\n")
		
		# Собираем параметры по итерациям
		param_history = {}
		for it in self.results['iterations']:
			for param, value in it['best_params'].items():
				if param not in param_history:
					param_history[param] = []
				param_history[param].append(value)
		
		# Анализируем каждый параметр
		for param, values in param_history.items():
			unique_values = len(set(values))
			most_common = max(set(values), key=values.count)
			frequency = values.count(most_common) / len(values) * 100
			
			print(f"{param}:")
			print(f"  • Уникальных значений: {unique_values}/{len(values)}")
			print(f"  • Наиболее частое: {most_common} ({frequency:.0f}%)")
			print(f"  • История: {values}")
			
			if frequency > 70:
				print(f"  ✅ Высокая стабильность")
			elif frequency > 50:
				print(f"  ⚠️ Умеренная стабильность")
			else:
				print(f"  ❌ Низкая стабильность - параметр сильно меняется")
			print()
		
		self.results['parameter_stability'] = param_history
	
	def _save_report(self):
		"""Сохраняет отчет в JSON"""
		output_dir = "backtests"
		os.makedirs(output_dir, exist_ok=True)
		
		timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
		models_suffix = "_statmodels" if self.use_statistical_models else ""
		filename = f"walkforward_{self.symbol}_{self.interval}{models_suffix}_{timestamp}.json"
		filepath = os.path.join(output_dir, filename)
		
		with open(filepath, "w", encoding="utf-8") as f:
			json.dump(self.results, f, ensure_ascii=False, indent=2, default=str)
		
		print(f"\n✅ Отчет сохранен: {filepath}\n")


# ====================================================================
# CLI
# ====================================================================

async def main():
	import sys
	
	if len(sys.argv) < 2:
		print("Использование:")
		print("  python backtest_walkforward.py <SYMBOL> [interval] [is_hours] [oos_hours] [balance] [--anchored] [--statmodels]")
		print("\nПримеры:")
		print("  # Дефолтные параметры (7 дней IS / 2 дня OOS)")
		print("  python backtest_walkforward.py BTCUSDT")
		print()
		print("  # Кастомные параметры (15m интервал)")
		print("  python backtest_walkforward.py BTCUSDT 15m 168 48 100")
		print()
		print("  # Anchored режим (IS растет)")
		print("  python backtest_walkforward.py BTCUSDT 15m 168 48 100 --anchored")
		print()
		print("  # Со статистическими моделями")
		print("  python backtest_walkforward.py BTCUSDT 15m 168 48 100 --statmodels")
		print()
		print("  # Для длительных периодов - используйте больший интервал")
		print("  python backtest_walkforward.py BTCUSDT 1h 720 240 100  # 30 дней IS / 10 дней OOS")
		print("  python backtest_walkforward.py BTCUSDT 4h 2160 720 100  # 90 дней IS / 30 дней OOS")
		print()
		print("⚠️ Ограничения Bybit API: ~1000 свечей максимум")
		print("  • 15m → до 10 дней истории")
		print("  • 1h → до 40 дней истории")
		print("  • 4h → до 160 дней истории")
		return
	
	symbol = sys.argv[1]
	interval = sys.argv[2] if len(sys.argv) > 2 else "15m"
	is_hours = int(sys.argv[3]) if len(sys.argv) > 3 else 168  # 7 дней (реалистично)
	oos_hours = int(sys.argv[4]) if len(sys.argv) > 4 else 48  # 2 дня
	balance = float(sys.argv[5]) if len(sys.argv) > 5 else INITIAL_BALANCE
	anchored = "--anchored" in sys.argv
	use_statistical_models = "--statmodels" in sys.argv
	
	optimizer = WalkForwardOptimizer(
		symbol=symbol,
		interval=interval,
		is_period_hours=is_hours,
		oos_period_hours=oos_hours,
		start_balance=balance,
		anchored=anchored,
		use_statistical_models=use_statistical_models
	)
	
	await optimizer.run()


if __name__ == "__main__":
	asyncio.run(main())

