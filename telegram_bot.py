import aiohttp
import asyncio
import json
import html
import math
import threading
from datetime import datetime
from telegram import Update, __version__ as tg_version
from telegram.ext import Application, CommandHandler, ContextTypes
from config import (
	TELEGRAM_TOKEN, OWNER_CHAT_ID, DEFAULT_SYMBOL, DEFAULT_INTERVAL,
	POLL_INTERVAL, POLL_INTERVAL_MIN, POLL_INTERVAL_MAX,
	VOLATILITY_WINDOW, VOLATILITY_THRESHOLD,
	POLL_VOLATILITY_HIGH_THRESHOLD, POLL_VOLATILITY_LOW_THRESHOLD, VOLATILITY_ALERT_COOLDOWN,
	INITIAL_BALANCE, STRATEGY_MODE, ADX_WINDOW,
	MODE_MEAN_REVERSION, MODE_TREND_FOLLOWING, MODE_TRANSITION,
	USE_STATISTICAL_MODELS
)
from signal_logger import log_signal
from data_provider import DataProvider
from signal_generator import SignalGenerator
from paper_trader import PaperTrader
from logger import logger
from database import db
from telegram_handlers import TelegramHandlers


class TelegramBot:
	def __init__(self, token: str, default_symbol: str = "BTCUSDT", default_interval: str = "1m"):
		if token is None:
			raise RuntimeError("TELEGRAM_TOKEN not set")
		self.token = token
		self.default_symbol = default_symbol
		self.default_interval = default_interval
		self.tracked_symbols: set[str] = set()
		
		# НОВОЕ: Lock для предотвращения race condition в paper_trader операциях
		self.paper_trader_lock = threading.Lock()
		
		# Устанавливаем владельца из переменной окружения
		if OWNER_CHAT_ID:
			try:
				self.owner_chat_id = int(OWNER_CHAT_ID)
				logger.info(f"Владелец бота: {self.owner_chat_id}")
			except ValueError:
				logger.error("OWNER_CHAT_ID должен быть числом!")
				self.owner_chat_id = None
		else:
			logger.warning("OWNER_CHAT_ID не установлен - бот доступен всем! Установите в .env для защиты.")
			self.owner_chat_id = None
		
		self._load_tracked_symbols()
		self.last_signals: dict[str, str] = {}
		self.last_volatility_alert: dict[str, float] = {}
		self.last_volatility_alert_time: dict[str, float] = {}  # Время последнего уведомления о волатильности
		self.current_poll_interval = POLL_INTERVAL  # Динамический интервал
		
		# Paper Trading
		self.paper_trader = PaperTrader()  # Использует INITIAL_BALANCE из config
		self.paper_trader.load_state()
		
		# Гибридная стратегия - отслеживание режима по символам
		self.symbol_modes: dict[str, str] = {}  # symbol -> "MR", "TF", "TRANSITION"
		self.symbol_mode_times: dict[str, float] = {}  # symbol -> время в режиме (часы)
		self.symbol_mode_updates: dict[str, datetime] = {}  # symbol -> время последнего обновления
		
		# Инициализируем обработчики команд ПЕРЕД регистрацией
		self.handlers = TelegramHandlers(self)
		
		# Теперь можем зарегистрировать обработчики
		self.application = Application.builder().token(self.token).build()
		self._register_handlers()

	def _is_authorized(self, update: Update) -> bool:
		"""Проверяет, что пользователь является владельцем бота"""
		if self.owner_chat_id is None:
			# Если владелец не установлен, разрешаем всем (небезопасный режим)
			return True
		return update.effective_chat.id == self.owner_chat_id
	
	def _generate_signal_with_strategy(self, generator: SignalGenerator, symbol: str = None, use_mtf: bool = None) -> dict:
		"""
		Генерирует сигнал в зависимости от выбранной стратегии (STRATEGY_MODE)
		
		Args:
			generator: SignalGenerator с загруженными данными
			symbol: торговая пара (нужна для MTF анализа)
			use_mtf: использовать multi-timeframe анализ (если None, берётся из USE_MULTI_TIMEFRAME)
		"""
		from config import USE_MULTI_TIMEFRAME
		
		# Определяем, использовать ли MTF
		if use_mtf is None:
			use_mtf = USE_MULTI_TIMEFRAME
		
		# Если MTF включен и символ указан - используем MTF анализ
		if use_mtf and symbol and hasattr(self, 'data_provider'):
			try:
				# MTF анализ - асинхронный
				loop = asyncio.get_event_loop()
				return loop.run_until_complete(
					generator.generate_signal_multi_timeframe(
						data_provider=self.data_provider,
						symbol=symbol,
						strategy=STRATEGY_MODE
					)
				)
			except Exception as e:
				logger.error(f"Ошибка MTF анализа: {e}, fallback на single TF")
				# Fallback на обычный анализ при ошибке
		
		# Обычный single-timeframe анализ
		try:
			if STRATEGY_MODE == "MEAN_REVERSION":
				return generator.generate_signal_mean_reversion()
			elif STRATEGY_MODE == "HYBRID":
				# Получаем режим для конкретного символа
				symbol = symbol or self.default_symbol
				last_mode = self.symbol_modes.get(symbol)
				last_mode_time = self.symbol_mode_times.get(symbol, 0)
				
				# Обновляем время в режиме для этого символа
				if symbol in self.symbol_mode_updates:
					time_diff = (datetime.now() - self.symbol_mode_updates[symbol]).total_seconds() / 3600
					last_mode_time += time_diff
					self.symbol_mode_times[symbol] = last_mode_time
				
				result = generator.generate_signal_hybrid(
					last_mode=last_mode,
					last_mode_time=last_mode_time
				)
				
				# Обновляем режим для этого символа
				active_mode = result.get("active_mode")
				if active_mode and active_mode in [MODE_MEAN_REVERSION, MODE_TREND_FOLLOWING, MODE_TRANSITION]:
					if active_mode != last_mode:
						# Режим изменился - сбрасываем время
						old_mode = last_mode
						self.symbol_modes[symbol] = active_mode
						self.symbol_mode_times[symbol] = 0
						logger.info(f"🔄 СМЕНА РЕЖИМА {symbol}: {old_mode} → {active_mode}, время сброшено")
					else:
						# Режим не изменился - время продолжает накапливаться
						logger.info(f"⏱ РЕЖИМ НЕ ИЗМЕНИЛСЯ {symbol}: {active_mode}, время накапливается: {last_mode_time:.2f}h")
				
				# Обновляем время последнего обновления для этого символа
				self.symbol_mode_updates[symbol] = datetime.now()
				return result
			else:  # TREND_FOLLOWING (default)
				return generator.generate_signal()
		except Exception as e:
			logger.error(f"Ошибка генерации сигнала: {e}")
			# Возвращаем HOLD при ошибке
			return {
				"signal": "HOLD",
				"reasons": [f"⚠️ Ошибка генерации сигнала: {str(e)}"],
				"price": float(generator.df["close"].iloc[-1]) if not generator.df.empty else 0,
				"market_regime": "NONE",
				"bullish_votes": 0,
				"bearish_votes": 0,
				"vote_delta": 0,
				"filters_passed": 0,
				"short_enabled": False,
				"short_conditions": [],
				"indicators": {
					"RSI": "н/д",
					"ADX": "н/д",
					"MACD": "н/д"
				}
			}
	
	def _register_handlers(self):
		# Основные команды
		self.application.add_handler(CommandHandler("start", self.handlers.start))
		self.application.add_handler(CommandHandler("help", self.handlers.help))
		self.application.add_handler(CommandHandler("status", self.handlers.status))
		self.application.add_handler(CommandHandler("analyze", self.handlers.analyze))
		self.application.add_handler(CommandHandler("mtf_signal", self.handlers.mtf_signal))
		self.application.add_handler(CommandHandler("add", self.handlers.add_symbol))
		self.application.add_handler(CommandHandler("remove", self.handlers.remove_symbol))
		self.application.add_handler(CommandHandler("list", self.handlers.list_symbols))
		self.application.add_handler(CommandHandler("settings", self.handlers.settings))
		
		# Paper Trading
		self.application.add_handler(CommandHandler("paper_start", self.handlers.paper_start))
		self.application.add_handler(CommandHandler("paper_stop", self.handlers.paper_stop))
		self.application.add_handler(CommandHandler("paper_status", self.handlers.paper_status))
		self.application.add_handler(CommandHandler("paper_balance", self.handlers.paper_balance))
		self.application.add_handler(CommandHandler("paper_trades", self.handlers.paper_trades))
		self.application.add_handler(CommandHandler("paper_reset", self.handlers.paper_reset))
		self.application.add_handler(CommandHandler("paper_backtest", self.handlers.paper_backtest))
		self.application.add_handler(CommandHandler("paper_debug", self.handlers.paper_debug))
		self.application.add_handler(CommandHandler("paper_candidates", self.handlers.paper_candidates))
		self.application.add_handler(CommandHandler("paper_force_buy", self.handlers.paper_force_buy))
		self.application.add_handler(CommandHandler("paper_force_sell", self.handlers.paper_force_sell))
		
		# Kelly Criterion и Averaging
		self.application.add_handler(CommandHandler("kelly_info", self.handlers.kelly_info))
		self.application.add_handler(CommandHandler("averaging_status", self.handlers.averaging_status))
		
		# Диагностика сигналов (v5.5)
		self.application.add_handler(CommandHandler("signal_stats", self.handlers.signal_stats))
		self.application.add_handler(CommandHandler("signal_analysis", self.handlers.signal_analysis))

	# -----------------------------
	# Работа с БД
	# -----------------------------
	def _load_tracked_symbols(self):
		try:
			# Загружаем из БД
			symbols = db.get_tracked_symbols()
			self.tracked_symbols = set(symbols)
			
			# Загружаем настройки
			settings = db.get_bot_settings()
			if settings:
				self.chat_id = settings.chat_id
				self.poll_interval = settings.poll_interval
				self.volatility_window = settings.volatility_window
				self.volatility_threshold = settings.volatility_threshold
			else:
				self.chat_id = None
				self.poll_interval = POLL_INTERVAL
				self.volatility_window = VOLATILITY_WINDOW
				self.volatility_threshold = VOLATILITY_THRESHOLD
			
			logger.info(f"Загружено {len(self.tracked_symbols)} пар из БД")
			
		except Exception as e:
			logger.error(f"Ошибка загрузки из БД: {e}")
			self.tracked_symbols = set()
			self.chat_id = None
			self.poll_interval = POLL_INTERVAL
			self.volatility_window = VOLATILITY_WINDOW
			self.volatility_threshold = VOLATILITY_THRESHOLD

	def _save_tracked_symbols(self):
		try:
			# Сохраняем в БД
			# Сначала получаем все символы из БД
			db_symbols = set(db.get_tracked_symbols())
			
			# Удаляем символы, которых нет в self.tracked_symbols
			for symbol in db_symbols:
				if symbol not in self.tracked_symbols:
					db.remove_tracked_symbol(symbol)
			
			# Добавляем новые символы
			for symbol in self.tracked_symbols:
				if symbol not in db_symbols:
					db.add_tracked_symbol(symbol)
			
			# Сохраняем настройки
			if self.chat_id:
				db.save_bot_settings(
					chat_id=self.chat_id,
					poll_interval=self.poll_interval,
					volatility_window=self.volatility_window,
					volatility_threshold=self.volatility_threshold
				)
			
		except Exception as e:
			logger.error(f"Ошибка сохранения в БД: {e}")
			raise

	def _calculate_adaptive_poll_interval(self, volatilities: list[float]) -> int:
		"""Вычисляет адаптивный интервал опроса на основе волатильности"""
		if not volatilities:
			return POLL_INTERVAL
		
		avg_volatility = sum(abs(v) for v in volatilities) / len(volatilities)
		
		# Высокая волатильность - проверяем реже (снижаем спам)
		if avg_volatility >= POLL_VOLATILITY_HIGH_THRESHOLD:
			interval = POLL_INTERVAL_MAX
			logger.info(f"Высокая волатильность {avg_volatility*100:.2f}%, увеличиваю интервал до {interval}с")
		# Низкая волатильность - можно проверять чаще
		elif avg_volatility <= POLL_VOLATILITY_LOW_THRESHOLD:
			interval = POLL_INTERVAL_MIN
			logger.info(f"Низкая волатильность {avg_volatility*100:.2f}%, интервал {interval}с")
		# Умеренная волатильность - линейная интерполяция
		else:
			# Интерполируем между MIN и MAX
			ratio = (avg_volatility - POLL_VOLATILITY_LOW_THRESHOLD) / (POLL_VOLATILITY_HIGH_THRESHOLD - POLL_VOLATILITY_LOW_THRESHOLD)
			interval = int(POLL_INTERVAL_MIN + (POLL_INTERVAL_MAX - POLL_INTERVAL_MIN) * ratio)
			logger.info(f"Умеренная волатильность {avg_volatility*100:.2f}%, интервал {interval}с")
		
		return interval

	# -------------------------
	# Отправка сообщений с retry
	# -------------------------
	async def _send_telegram_message_with_retry(self, message: str, max_retries: int = 3):
		"""Отправка сообщения в Telegram с retry логикой"""
		import asyncio
		from telegram.error import TimedOut, NetworkError
		
		for attempt in range(max_retries):
			try:
				await self.application.bot.send_message(
					chat_id=self.chat_id, 
					text=message, 
					parse_mode="HTML"
				)
				logger.info("Сообщение успешно отправлено (попытка %d)", attempt + 1)
				return
			except (TimedOut, NetworkError) as e:
				if attempt < max_retries - 1:
					wait_time = 2 ** attempt  # Экспоненциальный backoff: 1s, 2s, 4s
					logger.warning("Ошибка отправки (попытка %d/%d): %s. Повтор через %ds", 
						attempt + 1, max_retries, e, wait_time)
					await asyncio.sleep(wait_time)
				else:
					logger.error("Не удалось отправить сообщение после %d попыток: %s", max_retries, e)
			except Exception as e:
				logger.error("Неожиданная ошибка отправки сообщения: %s", e)
				break

	# -------------------------
	# Фоновая задача
	# -------------------------
	async def _background_task(self):
		import time
		
		while True:
			if not self.tracked_symbols:
				await asyncio.sleep(self.current_poll_interval)
				continue
			if self.chat_id is None:
				await asyncio.sleep(self.current_poll_interval)
				continue
			
			# Накапливаем все сообщения для отправки одним батчем
			all_messages = []
			
			# Для paper trading собираем цены и сигналы
			current_prices = {}
			trading_signals = {}
			
			# Для адаптивного интервала
			volatilities = []
			
			async with aiohttp.ClientSession() as session:
				provider = DataProvider(session)
				
				# Проверяем все открытые позиции paper trading
				if self.paper_trader.is_running and self.paper_trader.positions:
					for symbol in list(self.paper_trader.positions.keys()):
						try:
							klines = await provider.fetch_klines(symbol=symbol, interval=self.default_interval, limit=1)
							df = provider.klines_to_dataframe(klines)
							if not df.empty:
								current_prices[symbol] = float(df['close'].iloc[-1])
						except Exception as e:
							logger.error(f"Ошибка получения цены для позиции {symbol}: {e}")
					
					# Проверяем стоп-лоссы и тейк-профиты (с lock)
					with self.paper_trader_lock:
						actions = self.paper_trader.check_positions(current_prices)
					for action in actions:
						trade_type = action['type']
						symbol = action['symbol']
						price = action['price']
						profit = action.get('profit', 0)
						profit_percent = action.get('profit_percent', 0)
						
						if trade_type == "STOP-LOSS":
							msg = f"🛑 <b>STOP-LOSS</b> {symbol}\n  Цена: {self.handlers.formatters.format_price(price)}\n  Убыток: ${profit:+.2f} ({profit_percent:+.2f}%)"
						elif trade_type == "PARTIAL-TP":
							msg = f"💎 <b>PARTIAL TP</b> {symbol}\n  Цена: {self.handlers.formatters.format_price(price)}\n  Прибыль: ${profit:+.2f} ({profit_percent:+.2f}%)\n  Закрыто: 50%, активен trailing stop"
						elif trade_type == "TRAILING-STOP":
							msg = f"🔻 <b>TRAILING STOP</b> {symbol}\n  Цена: {self.handlers.formatters.format_price(price)}\n  Прибыль: ${profit:+.2f} ({profit_percent:+.2f}%)"
						else:
							msg = f"📊 <b>{trade_type}</b> {symbol} @ {self.handlers.formatters.format_price(price)}"
							
						all_messages.append(msg)
						logger.info(f"[PAPER] {trade_type} {symbol} @ {self.handlers.formatters.format_price(price)}")
						
						# Сохраняем состояние если были действия
						if actions:
							self.paper_trader.save_state()
				
				# Анализируем отслеживаемые символы
				for symbol in self.tracked_symbols:
					try:
						klines = await provider.fetch_klines(symbol=symbol, interval=self.default_interval, limit=500)
						df = provider.klines_to_dataframe(klines)
						if df.empty:
							logger.warning("Нет данных для %s, пропускаем", symbol)
							continue

						generator = SignalGenerator(df, use_statistical_models=USE_STATISTICAL_MODELS)
						generator.compute_indicators()
						result = self._generate_signal_with_strategy(generator, symbol=symbol)
						signal = result["signal"]
						current_price = float(df['close'].iloc[-1])
						
						# Сохраняем для paper trading
						current_prices[symbol] = current_price
						trading_signals[symbol] = result

						last = self.last_signals.get(symbol)
						if last != signal:
							text = self.handlers.formatters.format_analysis(result, symbol, self.default_interval)
							all_messages.append(text)
							self.last_signals[symbol] = signal
							log_signal(symbol, self.default_interval, signal, result["reasons"], result["price"])
							logger.info("Сигнал %s: %s", symbol, signal)

						# -------------------
						# Волатильность
						# -------------------
						if len(df) >= self.volatility_window + 1:
							recent_df = df.iloc[-self.volatility_window:]
							# Сравниваем текущую цену с ценой N свечей назад
							prev_close = df["close"].iloc[-(self.volatility_window + 1)]
							current_close = df["close"].iloc[-1]
							change = (current_close - prev_close) / prev_close
							
							# Собираем волатильность для адаптивного интервала
							volatilities.append(change)

							# Проверяем cooldown для уведомлений о волатильности
							current_time = time.time()
							last_alert_time = self.last_volatility_alert_time.get(symbol, 0)
							time_since_last_alert = current_time - last_alert_time
							
							# Отправляем уведомление только если:
							# 1. Волатильность выше порога
							# 2. Прошло достаточно времени с последнего уведомления (cooldown)
							# 3. Цена изменилась значительно с последнего уведомления
							last_alert_price = self.last_volatility_alert.get(symbol)
							price_changed_significantly = last_alert_price is None or abs(current_close - last_alert_price) / last_alert_price >= self.volatility_threshold * 0.5
							
							if abs(change) >= self.volatility_threshold and time_since_last_alert >= VOLATILITY_ALERT_COOLDOWN and price_changed_significantly:
								text = self.handlers.formatters.format_volatility(symbol, self.default_interval, change, current_close, self.volatility_window)
								all_messages.append(text)
								self.last_volatility_alert[symbol] = current_close
								self.last_volatility_alert_time[symbol] = current_time
								logger.info("Волатильность %s: %.2f%% (cooldown: %.1f мин)", symbol, change*100, VOLATILITY_ALERT_COOLDOWN/60)

					except Exception as e:
						logger.error("Ошибка фонового анализа %s: %s", symbol, e)
				
			# ==========================================
			# Paper Trading: Обработка сигналов
			# ==========================================
			if self.paper_trader.is_running:
				from signal_diagnostics import diagnostics
				
				# НОВОЕ: Обрабатываем все сигналы под lock для предотвращения race condition
				with self.paper_trader_lock:
					for symbol, result in trading_signals.items():
						signal = result["signal"]
						price = current_prices.get(symbol)
						
						if price is None:
							continue
						
						# Получаем метаданные сигнала (v5.5 HYBRID)
						signal_strength = abs(result.get("bullish_votes", 0) - result.get("bearish_votes", 0))
						atr = result.get("ATR", 0.0)
						bullish_votes = result.get("bullish_votes", 0)
						bearish_votes = result.get("bearish_votes", 0)
						active_mode = result.get("active_mode", "UNKNOWN")
						reasons = result.get("reasons", [])
						position_size_percent = result.get("position_size_percent", None)
						
						# BUY сигнал - открываем позицию
						if signal == "BUY" and symbol not in self.paper_trader.positions:
							can_buy = self.paper_trader.can_open_position(symbol)
							block_reason = None if can_buy else "Лимит позиций или баланс"
							
							# Диагностика сигнала
							diagnostics.log_signal_generation(
								symbol=symbol,
								signal_result=result,
								price=price,
								can_buy=can_buy,
								block_reason=block_reason
							)
							
							if can_buy:
								trade_info = self.paper_trader.open_position(
									symbol=symbol,
									price=price,
									signal_strength=signal_strength,
									atr=atr,
									position_size_percent=position_size_percent,
									reasons=reasons,
									active_mode=active_mode,
									bullish_votes=bullish_votes,
									bearish_votes=bearish_votes
								)
								if trade_info:
									# Безопасная обработка position_size_percent
									position_size_display = f"{position_size_percent*100:.0f}%" if position_size_percent is not None else "N/A"
									
									msg = (
										f"🟢 <b>КУПИЛ</b> {symbol} ({active_mode})\n"
										f"  Цена: {self.handlers.formatters.format_price(price)}\n"
										f"  Вложено: ${trade_info['invest_amount']:.2f} ({position_size_display})\n"
										f"  Голоса: +{bullish_votes}/-{bearish_votes} (Δ{bullish_votes-bearish_votes:+d})\n"
										f"  Баланс: ${trade_info['balance_after']:.2f}"
									)
									all_messages.append(msg)
								self.paper_trader.save_state()
					
						# BUY сигнал для открытой LONG позиции - докупание
						elif signal == "BUY" and symbol in self.paper_trader.positions:
							adx = result.get("ADX", 0.0)
							trade_info = self.paper_trader.average_position(
								symbol=symbol,
								price=price,
								signal_strength=signal_strength,
								adx=adx,
								atr=atr,
								reason="SIGNAL"
							)
							if trade_info:
								mode = trade_info.get("type", "AVERAGE")
								msg = (
									f"🟡 <b>ДОКУПИЛ</b> {symbol} ({mode})\n"
									f"  Цена: {self.handlers.formatters.format_price(price)}\n"
									f"  Докуплено: ${trade_info['invest_amount']:.2f}\n"
									f"  Попытка #{trade_info['averaging_count']}\n"
									f"  Средняя цена: {self.handlers.formatters.format_price(trade_info['average_entry_price'])}\n"
									f"  Баланс: ${trade_info['balance_after']:.2f}"
								)
								all_messages.append(msg)
								self.paper_trader.save_state()
				
						# SELL сигнал - закрываем LONG позицию (если не частично закрыта)
						elif signal == "SELL" and symbol in self.paper_trader.positions:
							position = self.paper_trader.positions[symbol]
							if not position.partial_closed:  # Только если не частично закрыта
								trade_info = self.paper_trader.close_position(symbol, price, "SELL")
								if trade_info:
									profit_emoji = "📈" if trade_info['profit'] > 0 else "📉"
									msg = (
										f"🔴 <b>ПРОДАЛ</b> {symbol}\n"
										f"  Цена: {self.handlers.formatters.format_price(price)}\n"
										f"  {profit_emoji} Прибыль: ${trade_info['profit']:+.2f} ({trade_info['profit_percent']:+.2f}%)\n"
										f"  Баланс: ${trade_info['balance_after']:.2f}"
									)
									all_messages.append(msg)
									self.paper_trader.save_state()
					
					
						# HOLD/SELL - логируем для диагностики (если нет позиции)
						else:
							if symbol not in self.paper_trader.positions:
								diagnostics.log_signal_generation(
									symbol=symbol,
									signal_result=result,
									price=price,
									can_buy=False,
									block_reason=f"Сигнал {signal}, не BUY"
								)
			
			# Отправляем все накопленные сообщения одним батчем
			if all_messages:
				combined_message = "\n\n".join(all_messages)
				await self._send_telegram_message_with_retry(combined_message)
			
			# Адаптивный интервал на основе волатильности
			if volatilities:
				self.current_poll_interval = self._calculate_adaptive_poll_interval(volatilities)
			else:
				self.current_poll_interval = POLL_INTERVAL
			
			await asyncio.sleep(self.current_poll_interval)

	# -------------------------
	# Запуск бота
	# -------------------------
	def run(self):
		logger.info("Запуск бота...")

		async def start_background(application):
			asyncio.create_task(self._background_task())

		self.application.post_init = start_background
		self.application.run_polling(stop_signals=None)
