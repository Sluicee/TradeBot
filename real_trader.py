"""
Модуль для реального трейдинга на Bybit
Аналог PaperTrader, но с реальным исполнением ордеров
"""

import aiohttp
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from logger import logger
from database import db
from config import (
	COMMISSION_RATE, MAX_POSITIONS, STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT,
	PARTIAL_CLOSE_PERCENT, TRAILING_STOP_PERCENT,
	ENABLE_AVERAGING, MAX_AVERAGING_ATTEMPTS, AVERAGING_PRICE_DROP_PERCENT,
	AVERAGING_TIME_THRESHOLD_HOURS, MAX_TOTAL_RISK_MULTIPLIER,
	ENABLE_PYRAMID_UP, PYRAMID_ADX_THRESHOLD, AVERAGING_SIZE_PERCENT,
	SIGNAL_STRENGTH_STRONG,
	MAX_POSITION_DRAWDOWN_PERCENT, MAX_AVERAGING_DRAWDOWN_PERCENT,
	STRATEGY_TYPE_TF, STRATEGY_TYPE_MR, STRATEGY_TYPE_HYBRID,
	# Real Trading configs
	REAL_MAX_DAILY_LOSS, REAL_MAX_POSITION_SIZE,
	REAL_ORDER_TYPE, REAL_LIMIT_ORDER_OFFSET_PERCENT, REAL_MIN_ORDER_VALUE,
	get_dynamic_max_positions
)

# Импорты из новых модулей
from position import Position, get_dynamic_stop_loss_percent
from correlation import check_correlation_risk
from position_sizing import get_position_size_percent, calculate_kelly_fraction
from bybit_trader import bybit_trader
from safety_limits import SafetyLimits

# Статистические модели
try:
	from bayesian_db import BayesianDecisionLayerDB
	STATISTICAL_MODELS_AVAILABLE = True
except ImportError:
	STATISTICAL_MODELS_AVAILABLE = False
	logger.warning("Статистические модели не доступны")


class RealTrader:
	"""Система реального трейдинга на Bybit"""
	
	def __init__(self):
		self.positions: Dict[str, Position] = {}  # symbol -> Position
		self.trades_history: List[Dict[str, Any]] = []
		self.stats = {
			"total_trades": 0,
			"winning_trades": 0,
			"losing_trades": 0,
			"total_commission": 0.0,
			"stop_loss_triggers": 0,
			"take_profit_triggers": 0,
			"trailing_stop_triggers": 0
		}
		self.is_running = False
		self.start_time = None
		self.safety_limits = SafetyLimits()
		
		# Проверяем API ключи
		from config import BYBIT_API_KEY, BYBIT_API_SECRET
		self.api_key = BYBIT_API_KEY
		self.api_secret = BYBIT_API_SECRET
		
		# Статистические модели для обучения
		self.bayesian = None
		if STATISTICAL_MODELS_AVAILABLE:
			self.bayesian = BayesianDecisionLayerDB()
			# Мигрируем данные из JSON если есть
			self.bayesian.migrate_from_json()
			logger.info("Статистические модели инициализированы с поддержкой БД")
	
	def _get_signal_signature(self, trade_info: Dict[str, Any] = None, position: Position = None) -> str:
		"""Создает сигнатуру сигнала для Bayesian модели"""
		if not self.bayesian:
			return ""
		
		# Создаем данные сигнала
		signal_data = {
			"RSI": 50,
			"EMA_short": 0,
			"EMA_long": 0,
			"ADX": 0,
			"market_regime": "NEUTRAL",
			"MACD_hist": 0
		}
		
		# Приоритет: данные из позиции, затем из trade_info
		if position:
			signal_data["RSI"] = position.rsi
			signal_data["ADX"] = position.adx
			signal_data["market_regime"] = position.market_regime
		elif trade_info:
			if "rsi" in trade_info:
				signal_data["RSI"] = trade_info["rsi"]
			if "adx" in trade_info:
				signal_data["ADX"] = trade_info["adx"]
			if "market_regime" in trade_info:
				signal_data["market_regime"] = trade_info["market_regime"]
		
		return self.bayesian.get_signal_signature(signal_data)
	
	def start(self):
		"""Запускает реальный трейдинг"""
		self.is_running = True
		self.start_time = datetime.now().isoformat()
		logger.info("Real Trading запущен")
		
		# Проверяем лимиты безопасности
		if not self.safety_limits.check_daily_loss_limit():
			logger.warning("Достигнут дневной лимит убытков, торговля заблокирована")
			self.is_running = False
			return False
		
		return True
	
	def stop(self):
		"""Останавливает реальный трейдинг"""
		self.is_running = False
		logger.info("Real Trading остановлен")
	
	async def stop_and_close_all(self):
		"""Останавливает торговлю и закрывает все позиции"""
		self.is_running = False
		logger.info("Real Trading остановлен, закрываем все позиции...")
		
		# Закрываем все позиции
		closed_count = 0
		for symbol in list(self.positions.keys()):
			try:
				# Получаем текущую цену
				from data_provider import DataProvider
				import aiohttp
				
				async with aiohttp.ClientSession() as session:
					provider = DataProvider(session)
					klines = await provider.fetch_klines(symbol=symbol, interval="1m", limit=1)
					df = provider.klines_to_dataframe(klines)
					
					if not df.empty:
						current_price = float(df['close'].iloc[-1])
						trade_info = await self.close_position(symbol, current_price, "MANUAL-STOP")
						if trade_info:
							closed_count += 1
							logger.info(f"✅ Закрыта позиция {symbol}: {trade_info['profit']:+.2f} USD")
					else:
						logger.warning(f"⚠️ Не удалось получить цену для {symbol}")
						
			except Exception as e:
				logger.error(f"❌ Ошибка закрытия позиции {symbol}: {e}")
		
		logger.info(f"Real Trading остановлен. Закрыто позиций: {closed_count}")
		return closed_count
	
	def reset(self):
		"""Сбрасывает состояние к начальному"""
		self.positions.clear()
		self.trades_history.clear()
		self.stats = {
			"total_trades": 0,
			"winning_trades": 0,
			"losing_trades": 0,
			"total_commission": 0.0,
			"stop_loss_triggers": 0,
			"take_profit_triggers": 0,
			"trailing_stop_triggers": 0
		}
		self.start_time = datetime.now().isoformat()
	
	async def can_open_position(self, symbol: str) -> bool:
		"""Проверяет, можно ли открыть позицию"""
		# Проверяем лимиты безопасности
		if not self.safety_limits.check_position_limits(symbol, self.positions):
			return False
		
		# Проверяем, нет ли уже позиции по этому символу
		if symbol in self.positions:
			return False
		
		# Проверяем динамический лимит позиций
		# Получаем текущий баланс для расчета
		balance = await bybit_trader.get_balance()
		usdt_balance = balance.get("USDT", 0.0)
		
		# Рассчитываем общий баланс (свободный + в позициях)
		total_pnl = sum(pos.calculate_pnl(0.0) for pos in self.positions.values())  # PnL будет пересчитан позже
		total_balance = usdt_balance + total_pnl
		
		# Рассчитываем динамический лимит позиций
		dynamic_max_positions = get_dynamic_max_positions(total_balance)
		
		if len(self.positions) >= dynamic_max_positions:
			logger.warning(f"[CAN_OPEN] ❌ {symbol}: достигнут лимит позиций {len(self.positions)}/{dynamic_max_positions} (баланс: ${total_balance:.2f})")
			return False
		
		return True
	
	async def open_position(
		self,
		symbol: str,
		price: float,
		signal_strength: int,
		atr: float = 0.0,
		position_size_percent: float = None,
		reasons: List[str] = None,
		active_mode: str = "UNKNOWN",
		bullish_votes: int = 0,
		bearish_votes: int = 0,
		rsi: float = 50.0,
		adx: float = 0.0,
		market_regime: str = "NEUTRAL",
		strategy_type: str = STRATEGY_TYPE_TF
	) -> Optional[Dict[str, Any]]:
		"""Открывает реальную позицию через Bybit API"""
		logger.info(f"\n{'='*60}")
		logger.info(f"[REAL_OPEN] 📊 Попытка открыть реальную позицию {symbol}")
		logger.info(f"[REAL_OPEN] Режим: {active_mode} | Цена: ${price:.4f}")
		logger.info(f"[REAL_OPEN] Голоса: +{bullish_votes}/-{bearish_votes} (delta={bullish_votes-bearish_votes})")
		logger.info(f"[REAL_OPEN] Сила сигнала: {signal_strength}, ATR: {atr:.4f}")
		if reasons:
			logger.info(f"[REAL_OPEN] 📋 Причины: {reasons[:3]}")
		
		if not await self.can_open_position(symbol):
			logger.warning(f"[REAL_OPEN] ❌ {symbol}: не пройдены базовые проверки")
			return None
		
		# Проверка корреляции - не открываем коррелированные позиции
		if not check_correlation_risk(symbol, self.positions):
			logger.warning(f"[REAL_OPEN] ❌ {symbol}: конфликт корреляции с открытыми позициями")
			return None
		
		# Получаем баланс с биржи
		async with aiohttp.ClientSession() as session:
			try:
				balance_data = await bybit_trader.get_balance()
				usdt_balance = balance_data.get("USDT", 0.0)
				
				if usdt_balance <= 0:
					logger.error(f"[REAL_OPEN] ❌ {symbol}: недостаточно USDT баланса (${usdt_balance:.2f})")
					return None
				
				# Рассчитываем Kelly multiplier
				atr_percent = (atr / price) * 100 if atr > 0 and price > 0 else 1.5
				kelly_multiplier = calculate_kelly_fraction(self.trades_history, atr_percent)
				
				# Используем переданный position_size_percent или рассчитываем
				if position_size_percent is None:
					position_size_percent = get_position_size_percent(signal_strength, atr, price, kelly_multiplier)
				
				# Ограничиваем размер позиции лимитами безопасности
				invest_amount = min(usdt_balance * position_size_percent, REAL_MAX_POSITION_SIZE)
				
				# Адаптивный расчет для малых балансов
				# Если рассчитанная сумма меньше минимального лимита Bybit, используем минимальную сумму
				if invest_amount < REAL_MIN_ORDER_VALUE and usdt_balance >= REAL_MIN_ORDER_VALUE:
					# Используем минимальную сумму Bybit ($10) только если процентный расчет дал меньше
					invest_amount = REAL_MIN_ORDER_VALUE
					position_size_percent = invest_amount / usdt_balance
					logger.info(f"[REAL_OPEN] 🔧 Адаптивный расчет: ${invest_amount:.2f} ({position_size_percent*100:.1f}%) - минимальная сумма Bybit")
				elif invest_amount < REAL_MIN_ORDER_VALUE and usdt_balance < REAL_MIN_ORDER_VALUE:
					# Если баланс меньше минимальной суммы, пропускаем
					logger.warning(f"[REAL_OPEN] ❌ {symbol}: баланс ${usdt_balance:.2f} < минимальной суммы ${REAL_MIN_ORDER_VALUE}")
					return None
				
				if invest_amount <= 0:
					logger.error(f"[REAL_OPEN] ❌ {symbol}: invest_amount <= 0")
					return None
				
				# Проверяем минимальные лимиты Bybit
				if invest_amount < REAL_MIN_ORDER_VALUE:
					logger.warning(f"[REAL_OPEN] ❌ {symbol}: сумма ордера ${invest_amount:.2f} < минимального лимита ${REAL_MIN_ORDER_VALUE}")
					return None
				
				# Рассчитываем количество для покупки
				quantity = invest_amount / price
				
				# Округляем количество до разумного количества знаков
				# Для большинства криптовалют достаточно 6-8 знаков
				rounded_quantity = round(quantity, 6)
				
				# Пересчитываем фактическую сумму с округленным количеством
				actual_invest_amount = rounded_quantity * price
				
				logger.info(f"[REAL_OPEN] 📊 Расчет: {invest_amount:.2f} USDT / {price:.4f} = {quantity:.8f} -> {rounded_quantity:.6f} (${actual_invest_amount:.2f})")
				
				# Размещаем ордер на бирже
				if REAL_ORDER_TYPE == "MARKET":
					order_result = await bybit_trader.place_market_order(
						symbol, "Buy", rounded_quantity, price
					)
				else:  # LIMIT
					# Добавляем небольшой оффсет для быстрого исполнения
					limit_price = price * (1 + REAL_LIMIT_ORDER_OFFSET_PERCENT)
					order_result = await bybit_trader.place_limit_order(
						symbol, "Buy", rounded_quantity, limit_price, actual_invest_amount
					)
				
				order_id = order_result["order_id"]
				logger.info(f"[REAL_OPEN] ✅ Ордер размещен: {order_id}")
				
				# Создаем позицию
				position = Position(
					symbol=symbol,
					entry_price=price,
					amount=rounded_quantity,
					entry_time=datetime.now().isoformat(),
					signal_strength=signal_strength,
					invest_amount=actual_invest_amount,
					commission=actual_invest_amount * COMMISSION_RATE,
					atr=atr,
					rsi=rsi,
					adx=adx,
					market_regime=market_regime,
					strategy_type=strategy_type
				)
				
				# Сохраняем позицию
				self.positions[symbol] = position
				
				# Добавляем в историю
				commission = actual_invest_amount * COMMISSION_RATE
				self.stats["total_commission"] += commission
				
				trade_info = {
					"type": "BUY",
					"symbol": symbol,
					"price": price,
					"amount": rounded_quantity,
					"invest_amount": actual_invest_amount,
					"commission": commission,
					"signal_strength": signal_strength,
					"time": position.entry_time,
					"order_id": order_id,
					"order_type": REAL_ORDER_TYPE,
					"status": "SUBMITTED",
					# v5.5 метаданные
					"bullish_votes": bullish_votes,
					"bearish_votes": bearish_votes,
					"votes_delta": bullish_votes - bearish_votes,
					"position_size_percent": position_size_percent,
					"reasons": reasons[:3] if reasons else []
				}
				self.trades_history.append(trade_info)
				self.stats["total_trades"] += 1
				
				# Сохраняем в БД
				try:
					db.add_real_trade(trade_info)
				except Exception as e:
					logger.error(f"[REAL_OPEN] ❌ Ошибка сохранения сделки в БД: {e}")
				
				# Записываем сигнал для обучения Bayesian модели
				if self.bayesian:
					signal_signature = self._get_signal_signature(position=position)
					if signal_signature:
						self.bayesian.record_signal(signal_signature, "BUY", price)
						logger.info(f"[REAL_OPEN] 📊 Записан сигнал для обучения: {signal_signature[:50]}...")
				
				logger.info(f"[REAL_OPEN] ✅ {symbol}: ${invest_amount:.2f} ({position_size_percent*100:.1f}%) | SL: {position.stop_loss_percent*100:.1f}% | TP: {TAKE_PROFIT_PERCENT*100:.1f}%")
				
				return trade_info
				
			except Exception as e:
				logger.error(f"[REAL_OPEN] ❌ Ошибка при размещении ордера: {e}")
				return None
	
	async def close_position(
		self,
		symbol: str,
		price: float,
		reason: str = "SELL"
	) -> Optional[Dict[str, Any]]:
		"""Закрывает реальную позицию через Bybit API"""
		logger.info(f"\n{'='*60}")
		logger.info(f"[REAL_CLOSE] 🔴 Закрытие реальной позиции {symbol}")
		logger.info(f"[REAL_CLOSE] Причина: {reason}, Цена: ${price:.4f}")
		
		if symbol not in self.positions:
			logger.warning(f"[REAL_CLOSE] ❌ Позиция {symbol} не найдена")
			return None
		
		position = self.positions[symbol]
		
		logger.info(f"[REAL_CLOSE] 📊 Вход: ${position.entry_price:.4f}, Количество: {position.amount:.6f}")
		
		# Получаем реальный баланс монет с биржи
		coin = symbol.replace("USDT", "")
		real_balance = await bybit_trader.get_coin_balance(coin)
		
		logger.info(f"[REAL_CLOSE] 📊 Реальный баланс {coin}: {real_balance:.8f}")
		logger.info(f"[REAL_CLOSE] 📊 Позиция в памяти: {position.amount:.8f}")
		
		# Используем реальный баланс, если он больше 0
		sell_amount = real_balance if real_balance > 0 else position.amount
		
		if real_balance > 0 and abs(real_balance - position.amount) > 0.001:
			logger.warning(f"[REAL_CLOSE] ⚠️ Несоответствие: позиция={position.amount:.8f}, баланс={real_balance:.8f}")
			logger.info(f"[REAL_CLOSE] 🔧 Используем реальный баланс: {sell_amount:.8f}")
		
		# Размещаем ордер на продажу
		async with aiohttp.ClientSession() as session:
			try:
				if REAL_ORDER_TYPE == "MARKET":
					order_result = await bybit_trader.place_market_order(
						symbol, "Sell", sell_amount
					)
				else:  # LIMIT
					limit_price = price * (1 - REAL_LIMIT_ORDER_OFFSET_PERCENT)
					order_result = await bybit_trader.place_limit_order(
						symbol, "Sell", sell_amount, limit_price
					)
				
				order_id = order_result["order_id"]
				logger.info(f"[REAL_CLOSE] ✅ Ордер на продажу размещен: {order_id}")
				
				# Рассчитываем прибыль
				total_investment = position.total_invested if position.averaging_count > 0 else position.invest_amount
				
				# Если позиция частично закрыта, учитываем только оставшуюся часть инвестиции
				if position.partial_closed:
					remaining_invested = total_investment * (1 - PARTIAL_CLOSE_PERCENT)
				else:
					remaining_invested = total_investment
				
				# Для LONG: обычный расчет
				sell_value = sell_amount * price
				commission = sell_value * COMMISSION_RATE
				profit = sell_value - remaining_invested + position.partial_close_profit - commission
				profit_percent = (profit / total_investment) * 100
				
				# Обновляем статистику
				self.stats["total_commission"] += commission
				
				if profit > 0:
					self.stats["winning_trades"] += 1
				else:
					self.stats["losing_trades"] += 1
					
				if reason == "STOP-LOSS":
					self.stats["stop_loss_triggers"] += 1
				elif reason == "TRAILING-STOP":
					self.stats["trailing_stop_triggers"] += 1
				
				holding_time = self._calculate_holding_time(position.entry_time)
				
				# Добавляем в историю
				trade_info = {
					"type": reason,
					"symbol": symbol,
					"price": price,
					"amount": sell_amount,  # Используем реальное количество
					"sell_value": sell_value,
					"commission": commission,
					"profit": profit,
					"profit_percent": profit_percent,
					"time": datetime.now().isoformat(),
					"order_id": order_id,
					"order_type": REAL_ORDER_TYPE,
					"status": "SUBMITTED",
					"holding_time": holding_time
				}
				self.trades_history.append(trade_info)
				
				# Сохраняем в БД
				try:
					db.add_real_trade(trade_info)
				except Exception as e:
					logger.error(f"[REAL_CLOSE] ❌ Ошибка сохранения сделки в БД: {e}")
				
				# Win Rate
				total_closed = self.stats["winning_trades"] + self.stats["losing_trades"]
				win_rate = (self.stats["winning_trades"] / total_closed * 100) if total_closed > 0 else 0
				
				# Завершаем сигнал для обучения Bayesian модели (ПЕРЕД удалением позиции)
				if self.bayesian:
					signal_signature = self._get_signal_signature(position=position)
					if signal_signature:
						self.bayesian.complete_signal(signal_signature, price, position.entry_price)
						logger.info(f"[REAL_CLOSE] 📊 Завершен сигнал для обучения: {signal_signature[:50]}... (P&L: {profit_percent:+.1f}%)")
				
				# Удаляем позицию
				del self.positions[symbol]
				
				# Краткий лог результата
				emoji = "💚" if profit > 0 else "💔"
				logger.info(f"[REAL_CLOSE] {emoji} {symbol}: {profit:+.2f} ({profit_percent:+.1f}%) | {holding_time} | WR: {win_rate:.1f}%")
				
				return trade_info
				
			except Exception as e:
				logger.error(f"[REAL_CLOSE] ❌ Ошибка при размещении ордера на продажу: {e}")
				return None
	
	async def check_positions(self, prices: Dict[str, float], strategy_type: str = None) -> List[Dict[str, Any]]:
		"""Проверяет все позиции на стоп-лоссы, тейк-профиты и время удержания"""
		actions = []
		
		if not self.positions:
			return actions
		
		for symbol, position in list(self.positions.items()):
			if symbol not in prices:
				continue
			
			# НОВОЕ: Изолируем ошибки каждой позиции
			try:
				current_price = prices[symbol]
				
				# Обновляем максимальную цену
				position.update_max_price(current_price)
				
				# 1. Проверяем время удержания
				if position.check_time_exit():
					trade_info = await self.close_position(symbol, current_price, "TIME-EXIT")
					if trade_info:
						actions.append(trade_info)
					continue
				
				# 2. Проверяем trailing stop (если позиция частично закрыта)
				if position.check_trailing_stop(current_price):
					trade_info = await self.close_position(symbol, current_price, "TRAILING-STOP")
					if trade_info:
						actions.append(trade_info)
					continue
					
				# 3. Проверяем стоп-лосс
				if position.check_stop_loss(current_price):
					trade_info = await self.close_position(symbol, current_price, "STOP-LOSS")
					if trade_info:
						actions.append(trade_info)
					continue
					
				# 4. Проверяем тейк-профит (частичное закрытие)
				if position.check_take_profit(current_price):
					# Для реального трейдинга частичное закрытие сложнее
					# Пока что закрываем полностью при достижении TP
					trade_info = await self.close_position(symbol, current_price, "TAKE-PROFIT")
					if trade_info:
						actions.append(trade_info)
					continue
					
			except Exception as e:
				# Изолируем ошибки отдельных позиций
				logger.error(f"[CHECK_POSITIONS] ❌ Ошибка при проверке позиции {symbol}: {e}")
				continue
		
		return actions
	
	async def get_status(self) -> Dict[str, Any]:
		"""Возвращает текущий статус реального трейдинга"""
		# Получаем актуальные данные с биржи
		async with aiohttp.ClientSession() as session:
			try:
				balance_data = await bybit_trader.get_balance()
				if not balance_data:
					raise Exception("Не удалось получить данные баланса")
				usdt_balance = balance_data.get("USDT", 0.0)
				
				# Получаем позиции с биржи
				exchange_positions = await bybit_trader.get_positions()
				
				positions_info = []
				total_pnl = 0.0
				
				# Показываем ТОЛЬКО позиции, которые были открыты через бота
				for symbol, local_pos in self.positions.items():
					# Ищем соответствующую позицию на бирже
					exchange_pos = None
					for pos in exchange_positions:
						if pos["symbol"] == symbol:
							exchange_pos = pos
							break
					
					if exchange_pos:
						# Позиция есть и на бирже, и в боте
						positions_info.append({
							"symbol": symbol,
							"quantity": exchange_pos["quantity"],
							"entry_price": local_pos.entry_price,
							"stop_loss": local_pos.stop_loss_price,
							"take_profit": local_pos.take_profit_price,
							"current_price": 0.0,  # Будет получена в telegram_real_trading.py
							"side": exchange_pos["side"]
						})
					else:
						# Позиция есть в боте, но нет на бирже - возможно закрыта
						logger.warning(f"Позиция {symbol} есть в боте, но отсутствует на бирже")
						# Не добавляем в positions_info - позиция закрыта
				
				# Рассчитываем общий PnL
				total_balance = usdt_balance + total_pnl
				
				# Рассчитываем динамический лимит позиций
				dynamic_max_positions = get_dynamic_max_positions(total_balance)
				
				win_rate = 0.0
				if self.stats["winning_trades"] + self.stats["losing_trades"] > 0:
					win_rate = (self.stats["winning_trades"] / (self.stats["winning_trades"] + self.stats["losing_trades"])) * 100
				
				return {
					"is_running": self.is_running,
					"usdt_balance": usdt_balance,
					"total_balance": total_balance,
					"positions_count": len(positions_info),
					"max_positions": dynamic_max_positions,
					"positions": positions_info,
					"stats": {
						**self.stats,
						"win_rate": win_rate
					},
					"start_time": self.start_time,
					"daily_loss": self.safety_limits.get_daily_loss(),
					"daily_loss_limit": REAL_MAX_DAILY_LOSS
				}
				
			except Exception as e:
				logger.error(f"Ошибка получения статуса с биржи: {e}")
				return {
					"is_running": self.is_running,
					"error": str(e)
				}
	
	def _calculate_holding_time(self, entry_time: str) -> str:
		"""Рассчитывает время удержания позиции"""
		try:
			entry_dt = datetime.fromisoformat(entry_time)
			now_dt = datetime.now()
			delta = now_dt - entry_dt
			
			hours = delta.seconds // 3600
			minutes = (delta.seconds % 3600) // 60
			
			if delta.days > 0:
				return f"{delta.days}д {hours}ч"
			elif hours > 0:
				return f"{hours}ч {minutes}м"
			else:
				return f"{minutes}м"
		except:
			return "N/A"
	
	def save_state(self):
		"""Сохраняет состояние в БД"""
		try:
			# Сохраняем основное состояние
			start_time = datetime.fromisoformat(self.start_time) if isinstance(self.start_time, str) and self.start_time else datetime.now()
			db.save_real_state(
				is_running=self.is_running,
				start_time=start_time,
				stats=self.stats
			)
			
			# Сохраняем позиции
			for symbol, pos in self.positions.items():
				pos_data = pos.to_dict()
				# Преобразуем entry_time в datetime
				if isinstance(pos_data.get("entry_time"), str):
					pos_data["entry_time"] = datetime.fromisoformat(pos_data["entry_time"])
				
				# Сохраняем позицию
				averaging_entries = pos_data.pop("averaging_entries", [])
				db_position = db.save_position(pos_data)
				
				# Сохраняем докупания (если есть новые)
				existing_entries = db.get_averaging_entries(db_position.id)
				if len(averaging_entries) > len(existing_entries):
					for entry in averaging_entries[len(existing_entries):]:
						entry_time = datetime.fromisoformat(entry["time"]) if isinstance(entry.get("time"), str) else datetime.now()
						db.add_averaging_entry(
							position_id=db_position.id,
							price=entry.get("price", 0),
							amount=entry.get("amount", 0),
							invest_amount=entry.get("invest_amount", 0),
							commission=entry.get("commission", 0),
							mode=entry.get("mode", ""),
							reason=entry.get("reason", ""),
							time=entry_time
						)
			
			# Удаляем закрытые позиции из БД
			db_positions = db.get_all_positions()
			for db_pos in db_positions:
				if db_pos.symbol not in self.positions:
					db.delete_position(db_pos.symbol)
			
		except Exception as e:
			logger.error(f"Ошибка сохранения состояния в БД: {e}")
			raise
			
	def load_state(self) -> bool:
		"""Загружает состояние из БД"""
		try:
			# Загружаем основное состояние
			db_state = db.get_real_state()
			if not db_state:
				logger.info("Real Trading: состояние не найдено, используем начальные значения")
				return False
			
			self.is_running = db_state.is_running
			self.start_time = db_state.start_time.isoformat() if db_state.start_time else None
			
			self.stats = {
				"total_trades": db_state.total_trades,
				"winning_trades": db_state.winning_trades,
				"losing_trades": db_state.losing_trades,
				"total_commission": db_state.total_commission,
				"stop_loss_triggers": db_state.stop_loss_triggers,
				"take_profit_triggers": db_state.take_profit_triggers,
				"trailing_stop_triggers": db_state.trailing_stop_triggers
			}
			
			# Загружаем позиции
			db_positions = db.get_all_positions()
			self.positions = {}
			
			for db_pos in db_positions:
				# Преобразуем DB модель в Position объект
				pos_data = {
					"symbol": db_pos.symbol,
					"entry_price": db_pos.entry_price,
					"amount": db_pos.amount,
					"entry_time": db_pos.entry_time.isoformat() if db_pos.entry_time else datetime.now().isoformat(),
					"signal_strength": db_pos.signal_strength,
					"invest_amount": db_pos.invest_amount,
					"commission": db_pos.entry_commission,
					"atr": db_pos.atr,
					"stop_loss_price": db_pos.stop_loss_price,
					"stop_loss_percent": db_pos.stop_loss_percent,
					"take_profit_price": db_pos.take_profit_price,
					"partial_closed": db_pos.partial_closed,
					"max_price": db_pos.max_price,
					"partial_close_profit": db_pos.partial_close_profit,
					"original_amount": db_pos.original_amount,
					"averaging_count": db_pos.averaging_count,
					"average_entry_price": db_pos.average_entry_price,
					"pyramid_mode": db_pos.pyramid_mode,
					"total_invested": db_pos.total_invested,
					"averaging_entries": db.get_averaging_entries(db_pos.id)
				}
				
				self.positions[db_pos.symbol] = Position.from_dict(pos_data)
			
			# Загружаем историю сделок (последние 1000)
			db_trades = db.get_real_trades_history(limit=1000)
			self.trades_history = db_trades
			
			logger.info(f"Real Trading загружен из БД: {len(self.positions)} позиций, {len(self.trades_history)} сделок")
			return True
			
		except Exception as e:
			logger.error(f"Ошибка загрузки состояния из БД: {e}")
			raise
	
	async def get_balance(self, session=None):
		"""Получает баланс с биржи"""
		try:
			return await bybit_trader.get_balance()
		except Exception as e:
			logger.error(f"Ошибка получения баланса: {e}")
			return {}
