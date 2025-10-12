import aiohttp
import asyncio
import json
from datetime import datetime
from telegram import Update, __version__ as tg_version
from telegram.ext import Application, CommandHandler, ContextTypes
from config import (
	TELEGRAM_TOKEN, OWNER_CHAT_ID, DEFAULT_SYMBOL, DEFAULT_INTERVAL,
	POLL_INTERVAL, POLL_INTERVAL_MIN, POLL_INTERVAL_MAX,
	VOLATILITY_WINDOW, VOLATILITY_THRESHOLD,
	VOLATILITY_HIGH_THRESHOLD, VOLATILITY_LOW_THRESHOLD, VOLATILITY_ALERT_COOLDOWN,
	INITIAL_BALANCE
)
from signal_logger import log_signal
from data_provider import DataProvider
from signal_generator import SignalGenerator
from paper_trader import PaperTrader
from logger import logger
from database import db
import math

def format_price(price: float) -> str:
	"""Адаптивное форматирование цены в зависимости от величины"""
	if price >= 1000:
		return f"${price:,.2f}"  # 1,234.56
	elif price >= 1:
		return f"${price:.4f}"  # 12.3456
	elif price >= 0.0001:
		# Для маленьких цен показываем значащие цифры
		decimals = max(4, abs(int(math.log10(abs(price)))) + 3)
		return f"${price:.{decimals}f}"
	else:
		return f"${price:.8f}"  # Совсем маленькие цены

class TelegramBot:
	def __init__(self, token: str, default_symbol: str = "BTCUSDT", default_interval: str = "1m"):
		if token is None:
			raise RuntimeError("TELEGRAM_TOKEN not set")
		self.token = token
		self.default_symbol = default_symbol
		self.default_interval = default_interval
		self.tracked_symbols: set[str] = set()
		
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
		self.application = Application.builder().token(self.token).build()
		self._register_handlers()
		self.last_signals: dict[str, str] = {}
		self.last_volatility_alert: dict[str, float] = {}
		self.last_volatility_alert_time: dict[str, float] = {}  # Время последнего уведомления о волатильности
		self.current_poll_interval = POLL_INTERVAL  # Динамический интервал
		
		# Paper Trading
		self.paper_trader = PaperTrader()  # Использует INITIAL_BALANCE из config
		self.paper_trader.load_state()

	def _is_authorized(self, update: Update) -> bool:
		"""Проверяет, что пользователь является владельцем бота"""
		if self.owner_chat_id is None:
			# Если владелец не установлен, разрешаем всем (небезопасный режим)
			return True
		return update.effective_chat.id == self.owner_chat_id
	
	def _register_handlers(self):
		self.application.add_handler(CommandHandler("start", self.start))
		self.application.add_handler(CommandHandler("help", self.help))
		self.application.add_handler(CommandHandler("status", self.status))
		self.application.add_handler(CommandHandler("analyze", self.analyze))
		self.application.add_handler(CommandHandler("add", self.add_symbol))
		self.application.add_handler(CommandHandler("remove", self.remove_symbol))
		self.application.add_handler(CommandHandler("list", self.list_symbols))
		self.application.add_handler(CommandHandler("settings", self.settings))
		
		# Paper Trading
		self.application.add_handler(CommandHandler("paper_start", self.paper_start))
		self.application.add_handler(CommandHandler("paper_stop", self.paper_stop))
		self.application.add_handler(CommandHandler("paper_status", self.paper_status))
		self.application.add_handler(CommandHandler("paper_balance", self.paper_balance))
		self.application.add_handler(CommandHandler("paper_trades", self.paper_trades))
		self.application.add_handler(CommandHandler("paper_reset", self.paper_reset))
		self.application.add_handler(CommandHandler("paper_backtest", self.paper_backtest))
		self.application.add_handler(CommandHandler("paper_debug", self.paper_debug))
		self.application.add_handler(CommandHandler("paper_candidates", self.paper_candidates))
		self.application.add_handler(CommandHandler("paper_force_buy", self.paper_force_buy))
		
		# Kelly Criterion и Averaging
		self.application.add_handler(CommandHandler("kelly_info", self.kelly_info))
		self.application.add_handler(CommandHandler("averaging_status", self.averaging_status))

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

	# -------------------------
	# Форматирование вывода
	# -------------------------
	def format_analysis(self, result, symbol, interval):
		def html_escape(s):
			s = str(s)
			s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
			return s

		def fmt(val):
			if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
				return 'н/д'
			return f'{val:.8f}' if isinstance(val, float) else str(val)

		# Берём первую причину как основную
		main_reason = html_escape(result["reasons"][0]) if result["reasons"] else "нет данных"
		
		return (
			f"<b>{html_escape(symbol)}</b> {result['signal_emoji']} <b>{html_escape(result['signal'])}</b>\n"
			f"  ₿{fmt(result['price'])} | RSI {fmt(result['RSI'])}\n"
			f"  {main_reason}"
		)

	def format_volatility(self, symbol, interval, change, close_price, window):
		direction = "↑" if change > 0 else "↓"
		return f"<b>{symbol}</b> ⚠️ {change*100:.2f}% {direction} | Цена: {close_price:.8f}"

	# -------------------------
	# Основные команды
	# -------------------------
	async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			await update.message.reply_text(
				"🚫 <b>Доступ запрещен</b>\n\n"
				"Этот бот настроен только для владельца.\n"
				f"Ваш ID: <code>{update.effective_chat.id}</code>\n\n"
				"Если это ваш бот, добавьте свой ID в файл .env:\n"
				"<code>OWNER_CHAT_ID={}</code>".format(update.effective_chat.id),
				parse_mode="HTML"
			)
			return
		
		text = (
			"<b>👋 Привет! Я — бот для анализа криптовалют.</b>\n\n"
			"<b>Основные команды:</b>\n"
			"• /start — показать это сообщение\n"
			"• /help — помощь по командам\n"
			"• /status — статус бота и отслеживаемые пары\n"
			"• /analyze [SYMBOL] [INTERVAL] — анализ пары\n"
			"• /add SYMBOL — добавить пару в отслеживаемые\n"
			"• /remove SYMBOL — удалить пару из отслеживаемых\n"
			"• /list — показать все отслеживаемые пары\n\n"
			"<b>📊 Paper Trading:</b>\n"
			"• /paper_start [баланс] — запустить виртуальную торговлю\n"
			"• /paper_stop — остановить и закрыть все позиции\n"
			"• /paper_status — текущий статус и позиции\n"
			"• /paper_balance — детали баланса\n"
			"• /paper_trades [N] — последние N сделок\n"
			"• /paper_backtest [часы] — быстрая симуляция на истории\n"
			"• /paper_debug [SYMBOL] — отладка сигналов\n"
			"• /paper_candidates — показать кандидатов на сделку\n"
			"• /paper_reset — сбросить баланс и историю"
		)
		await update.message.reply_text(text, parse_mode="HTML")
		
		if self.chat_id is None:
			self.chat_id = update.effective_chat.id
			self._save_tracked_symbols()

	async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		text = (
			"<b>🆘 Помощь:</b>\n\n"
			"<b>Анализ:</b>\n"
			"• /analyze SYMBOL INTERVAL — анализ указанной пары\n"
			"• /add SYMBOL — добавить пару в отслеживаемые\n"
			"• /remove SYMBOL — удалить пару из отслеживаемых\n"
			"• /list — показать все отслеживаемые пары\n\n"
			"<b>Paper Trading:</b>\n"
			"• /paper_start [баланс] — запустить виртуальную торговлю\n"
			"• /paper_stop — остановить и закрыть все позиции\n"
			"• /paper_status — текущий статус и позиции\n"
			"• /paper_balance — детали баланса\n"
			"• /paper_trades [N] — последние N сделок\n"
			"• /paper_backtest [часы] — быстрая симуляция на истории\n"
			"• /paper_debug [SYMBOL] — отладка сигналов\n"
			"• /paper_candidates — показать кандидатов на сделку\n"
			"• /paper_force_buy [SYMBOL] — принудительная покупка\n"
			"• /paper_reset — сбросить баланс и историю\n\n"
			"<i>Если SYMBOL и INTERVAL не указаны, используются значения по умолчанию.</i>"
		)
		await update.message.reply_text(text, parse_mode="HTML")

	async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		symbols = ", ".join(self.tracked_symbols) if self.tracked_symbols else "нет"
		text = (
			f"<b>ℹ️ Статус бота</b>\n"
			f"• Версия библиотеки: python-telegram-bot {tg_version}\n"
			f"• Символ по умолчанию: {self.default_symbol}\n"
			f"• Интервал по умолчанию: {self.default_interval}\n"
			f"• Отслеживаемые пары: {symbols}\n"
			f"• Статус: ✅ OK"
		)
		await update.message.reply_text(text, parse_mode="HTML")
		
		if self.chat_id is None:
			self.chat_id = update.effective_chat.id
			self._save_tracked_symbols()

	# -------------------------
	# Управление парами
	# -------------------------
	async def add_symbol(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		if not context.args:
			await update.message.reply_text("⚠️ Использование: /add SYMBOL")
			return
		symbol = context.args[0].upper()
		if symbol in self.tracked_symbols:
			await update.message.reply_text(f"ℹ️ {symbol} уже в списке отслеживаемых.")
		else:
			self.tracked_symbols.add(symbol)
			self._save_tracked_symbols()
			await update.message.reply_text(f"✅ {symbol} добавлен в список отслеживаемых.")

	async def remove_symbol(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		if not context.args:
			await update.message.reply_text("⚠️ Использование: /remove SYMBOL")
			return
		symbol = context.args[0].upper()
		if symbol in self.tracked_symbols:
			self.tracked_symbols.remove(symbol)
			self._save_tracked_symbols()
			await update.message.reply_text(f"✅ {symbol} удалён из списка отслеживаемых.")
		else:
			await update.message.reply_text(f"ℹ️ {symbol} нет в списке отслеживаемых.")

	async def list_symbols(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		if self.tracked_symbols:
			text = "<b>📋 Отслеживаемые пары:</b>\n" + "\n".join([f"• {s}" for s in self.tracked_symbols])
		else:
			text = "📋 Список отслеживаемых пар пуст."
		await update.message.reply_text(text, parse_mode="HTML")


	# -------------------------
	# Анализ пары
	# -------------------------
	async def analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		args = context.args or []
		symbol = args[0].upper() if len(args) >= 1 else self.default_symbol
		interval = args[1] if len(args) >= 2 else self.default_interval

		msg = await update.message.reply_text(f"Запрашиваю данные для {symbol} {interval}...")

		try:
			async with aiohttp.ClientSession() as session:
				provider = DataProvider(session)
				klines = await provider.fetch_klines(symbol=symbol, interval=interval, limit=500)
				df = provider.klines_to_dataframe(klines)

			if df.empty:
				await msg.edit_text("Не удалось получить данные от ByBIT.")
				return

			generator = SignalGenerator(df)
			generator.compute_indicators()
			result = generator.generate_signal()

			text = self.format_analysis(result, symbol, interval)
			await msg.edit_text(text, parse_mode="HTML")
		except Exception as e:
			await msg.edit_text(f"Ошибка при анализе: {e}")

	def _calculate_adaptive_poll_interval(self, volatilities: list[float]) -> int:
		"""Вычисляет адаптивный интервал опроса на основе волатильности"""
		if not volatilities:
			return POLL_INTERVAL
		
		avg_volatility = sum(abs(v) for v in volatilities) / len(volatilities)
		
		# Высокая волатильность - проверяем реже (снижаем спам)
		if avg_volatility >= VOLATILITY_HIGH_THRESHOLD:
			interval = POLL_INTERVAL_MAX
			logger.info(f"Высокая волатильность {avg_volatility*100:.2f}%, увеличиваю интервал до {interval}с")
		# Низкая волатильность - можно проверять чаще
		elif avg_volatility <= VOLATILITY_LOW_THRESHOLD:
			interval = POLL_INTERVAL_MIN
			logger.info(f"Низкая волатильность {avg_volatility*100:.2f}%, интервал {interval}с")
		# Умеренная волатильность - линейная интерполяция
		else:
			# Интерполируем между MIN и MAX
			ratio = (avg_volatility - VOLATILITY_LOW_THRESHOLD) / (VOLATILITY_HIGH_THRESHOLD - VOLATILITY_LOW_THRESHOLD)
			interval = int(POLL_INTERVAL_MIN + (POLL_INTERVAL_MAX - POLL_INTERVAL_MIN) * ratio)
			logger.info(f"Умеренная волатильность {avg_volatility*100:.2f}%, интервал {interval}с")
		
		return interval

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
					
					# Проверяем стоп-лоссы и тейк-профиты
					actions = self.paper_trader.check_positions(current_prices)
					for action in actions:
						trade_type = action['type']
						symbol = action['symbol']
						price = action['price']
						profit = action.get('profit', 0)
						profit_percent = action.get('profit_percent', 0)
						
						if trade_type == "STOP-LOSS":
							msg = f"🛑 <b>STOP-LOSS</b> {symbol}\n  Цена: {format_price(price)}\n  Убыток: ${profit:+.2f} ({profit_percent:+.2f}%)"
						elif trade_type == "PARTIAL-TP":
							msg = f"💎 <b>PARTIAL TP</b> {symbol}\n  Цена: {format_price(price)}\n  Прибыль: ${profit:+.2f} ({profit_percent:+.2f}%)\n  Закрыто: 50%, активен trailing stop"
						elif trade_type == "TRAILING-STOP":
							msg = f"🔻 <b>TRAILING STOP</b> {symbol}\n  Цена: {format_price(price)}\n  Прибыль: ${profit:+.2f} ({profit_percent:+.2f}%)"
						else:
							msg = f"📊 <b>{trade_type}</b> {symbol} @ {format_price(price)}"
							
						all_messages.append(msg)
						logger.info(f"[PAPER] {trade_type} {symbol} @ {format_price(price)}")
						
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

						generator = SignalGenerator(df)
						generator.compute_indicators()
						result = generator.generate_signal()
						signal = result["signal"]
						current_price = float(df['close'].iloc[-1])
						
						# Сохраняем для paper trading
						current_prices[symbol] = current_price
						trading_signals[symbol] = result

						last = self.last_signals.get(symbol)
						if last != signal:
							text = self.format_analysis(result, symbol, self.default_interval)
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
								text = self.format_volatility(symbol, self.default_interval, change, current_close, self.volatility_window)
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
					for symbol, result in trading_signals.items():
						signal = result["signal"]
						price = current_prices.get(symbol)
						
						if price is None:
							continue
						
						# Получаем силу сигнала и ATR
						signal_strength = abs(result.get("bullish_votes", 0) - result.get("bearish_votes", 0))
						atr = result.get("ATR", 0.0)
						
						# BUY сигнал - открываем позицию
						if signal == "BUY" and symbol not in self.paper_trader.positions:
							if self.paper_trader.can_open_position(symbol):
								trade_info = self.paper_trader.open_position(symbol, price, signal_strength, atr)
								if trade_info:
									msg = (
										f"🟢 <b>КУПИЛ</b> {symbol}\n"
										f"  Цена: {format_price(price)}\n"
										f"  Вложено: ${trade_info['invest_amount']:.2f}\n"
										f"  Сила сигнала: {signal_strength}\n"
										f"  Баланс: ${trade_info['balance_after']:.2f}"
									)
									all_messages.append(msg)
									self.paper_trader.save_state()
						
						# SELL сигнал - закрываем позицию (если не частично закрыта)
						elif signal == "SELL" and symbol in self.paper_trader.positions:
							position = self.paper_trader.positions[symbol]
							if not position.partial_closed:  # Только если не частично закрыта
								trade_info = self.paper_trader.close_position(symbol, price, "SELL")
								if trade_info:
									profit_emoji = "📈" if trade_info['profit'] > 0 else "📉"
									msg = (
										f"🔴 <b>ПРОДАЛ</b> {symbol}\n"
										f"  Цена: {format_price(price)}\n"
										f"  {profit_emoji} Прибыль: ${trade_info['profit']:+.2f} ({trade_info['profit_percent']:+.2f}%)\n"
										f"  Баланс: ${trade_info['balance_after']:.2f}"
									)
									all_messages.append(msg)
									self.paper_trader.save_state()
			
			# Отправляем все накопленные сообщения одним батчем
			if all_messages:
				combined_message = "\n\n".join(all_messages)
				await self.application.bot.send_message(chat_id=self.chat_id, text=combined_message, parse_mode="HTML")
				logger.info("Отправлено %d изменений", len(all_messages))
			
			# Адаптивный интервал на основе волатильности
			if volatilities:
				self.current_poll_interval = self._calculate_adaptive_poll_interval(volatilities)
			else:
				self.current_poll_interval = POLL_INTERVAL
			
			await asyncio.sleep(self.current_poll_interval)

	# -------------------------
	# Настройки
	# -------------------------
	async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		args = context.args
		if not args:
			text = (
				f"<b>⚙️ Текущие настройки:</b>\n\n"
				f"<b>Интервал опроса:</b>\n"
				f"  • Текущий: {self.current_poll_interval} сек\n"
				f"  • Базовый: {self.poll_interval} сек\n"
				f"  • Диапазон: {POLL_INTERVAL_MIN}-{POLL_INTERVAL_MAX} сек\n\n"
				f"<b>Волатильность:</b>\n"
				f"  • Окно: {self.volatility_window} свечей\n"
				f"  • Порог алерта: {self.volatility_threshold*100:.2f}%\n"
				f"  • Порог высокой: {VOLATILITY_HIGH_THRESHOLD*100:.2f}%\n"
				f"  • Порог низкой: {VOLATILITY_LOW_THRESHOLD*100:.2f}%\n"
				f"  • Cooldown: {VOLATILITY_ALERT_COOLDOWN/60:.0f} мин\n\n"
				f"<i>При высокой волатильности интервал автоматически\n"
				f"увеличивается до {POLL_INTERVAL_MAX}с для снижения спама</i>"
			)
			await update.message.reply_text(text, parse_mode="HTML")
			return

		try:
			if len(args) >= 1:
				self.poll_interval = int(args[0])
			if len(args) >= 2:
				self.volatility_window = int(args[1])
			if len(args) >= 3:
				self.volatility_threshold = float(args[2])
			self._save_tracked_symbols()
			await update.message.reply_text(
				f"✅ Настройки обновлены:\n"
				f"poll_interval = {self.poll_interval} сек\n"
				f"volatility_window = {self.volatility_window} свечей\n"
				f"volatility_threshold = {self.volatility_threshold*100:.2f}%"
			)
		except Exception as e:
			await update.message.reply_text(f"Ошибка при обновлении настроек: {e}")

	# -------------------------
	# Paper Trading команды
	# -------------------------
	async def paper_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Запускает paper trading"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		if self.paper_trader.is_running:
			await update.message.reply_text("⚠️ Paper Trading уже запущен!")
			return
		
		# Опционально можно задать стартовый баланс
		if context.args and len(context.args) > 0:
			try:
				initial_balance = float(context.args[0])
				self.paper_trader = PaperTrader(initial_balance=initial_balance)
			except ValueError:
				await update.message.reply_text("⚠️ Неверный формат баланса. Используется значение по умолчанию $100")
		
		self.paper_trader.start()
		self.paper_trader.save_state()
		
		text = (
			f"<b>🚀 Paper Trading запущен!</b>\n\n"
			f"💰 Стартовый баланс: ${self.paper_trader.initial_balance:.2f}\n"
			f"📊 Стратегия: как в бэктестинге\n"
			f"• Стоп-лосс: 5%\n"
			f"• Тейк-профит: 10% (частичное 50%)\n"
			f"• Trailing stop: 2%\n"
			f"• Макс. позиций: 3\n\n"
			f"Бот будет автоматически торговать по сигналам.\n"
			f"Используйте /paper_status для проверки состояния."
		)
		await update.message.reply_text(text, parse_mode="HTML")
		
		if self.chat_id is None:
			self.chat_id = update.effective_chat.id
			self._save_tracked_symbols()

	async def paper_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Останавливает paper trading и закрывает все позиции"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		if not self.paper_trader.is_running:
			await update.message.reply_text("⚠️ Paper Trading не запущен.")
			return
		
		# Закрываем все открытые позиции по текущим ценам
		if self.paper_trader.positions:
			msg = await update.message.reply_text("⏳ Закрываю все позиции...")
			
			closed_positions = []
			async with aiohttp.ClientSession() as session:
				provider = DataProvider(session)
				for symbol in list(self.paper_trader.positions.keys()):
					try:
						klines = await provider.fetch_klines(symbol=symbol, interval=self.default_interval, limit=1)
						df = provider.klines_to_dataframe(klines)
						if not df.empty:
							current_price = float(df['close'].iloc[-1])
							trade_info = self.paper_trader.close_position(symbol, current_price, "MANUAL-CLOSE")
							if trade_info:
								closed_positions.append(f"• {symbol}: {trade_info['profit']:+.2f} USD ({trade_info['profit_percent']:+.2f}%)")
					except Exception as e:
						logger.error(f"Ошибка закрытия позиции {symbol}: {e}")
			
			positions_text = "\n".join(closed_positions) if closed_positions else "Нет позиций для закрытия"
		else:
			positions_text = "Нет открытых позиций"
		
		self.paper_trader.stop()
		self.paper_trader.save_state()
		
		status = self.paper_trader.get_status()
		text = (
			f"<b>⏸ Paper Trading остановлен</b>\n\n"
			f"Закрыто позиций:\n{positions_text}\n\n"
			f"💰 Итоговый баланс: ${status['total_balance']:.2f}\n"
			f"📈 Прибыль: {status['total_profit']:+.2f} USD ({status['total_profit_percent']:+.2f}%)"
		)
		
		if self.paper_trader.positions:
			await msg.edit_text(text, parse_mode="HTML")
		else:
			await update.message.reply_text(text, parse_mode="HTML")

	async def paper_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Показывает текущий статус paper trading"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		status = self.paper_trader.get_status()
		
		# Получаем текущие цены для расчета PnL
		current_prices = {}
		if status['positions']:
			async with aiohttp.ClientSession() as session:
				provider = DataProvider(session)
				for pos in status['positions']:
					symbol = pos['symbol']
					try:
						klines = await provider.fetch_klines(symbol=symbol, interval=self.default_interval, limit=1)
						df = provider.klines_to_dataframe(klines)
						if not df.empty:
							current_prices[symbol] = float(df['close'].iloc[-1])
					except:
						current_prices[symbol] = pos['entry_price']
		
		# Пересчитываем PnL с текущими ценами
		total_pnl = 0.0
		positions_text = ""
		for pos in status['positions']:
			symbol = pos['symbol']
			current_price = current_prices.get(symbol, pos['entry_price'])
			position_obj = self.paper_trader.positions[symbol]
			pnl_info = position_obj.get_pnl(current_price)
			total_pnl += pnl_info['pnl']
			
			emoji = "🟢" if pnl_info['pnl'] > 0 else "🔴" if pnl_info['pnl'] < 0 else "⚪"
			partial_mark = " [частично]" if pos['partial_closed'] else ""
			
			positions_text += (
				f"  {emoji} <b>{symbol}</b>{partial_mark}\n"
				f"    Вход: {format_price(pos['entry_price'])} → Сейчас: {format_price(current_price)}\n"
				f"    PnL: ${pnl_info['pnl']:+.2f} ({pnl_info['pnl_percent']:+.2f}%)\n"
				f"    SL: {format_price(pos['stop_loss'])} | TP: {format_price(pos['take_profit'])}\n\n"
			)
		
		total_balance = status['current_balance'] + sum(
			self.paper_trader.positions[pos['symbol']].get_pnl(current_prices.get(pos['symbol'], pos['entry_price']))['current_value']
			for pos in status['positions']
		)
		
		total_profit = total_balance - status['initial_balance']
		total_profit_percent = (total_profit / status['initial_balance']) * 100
		
		status_emoji = "🟢" if status['is_running'] else "⏸"
		
		text = (
			f"<b>{status_emoji} Paper Trading Status</b>\n\n"
			f"💰 <b>Баланс:</b>\n"
			f"  • Свободно: ${status['current_balance']:.2f}\n"
			f"  • Всего: ${total_balance:.2f}\n"
			f"  • Прибыль: {total_profit:+.2f} USD ({total_profit_percent:+.2f}%)\n\n"
			f"📊 <b>Позиции ({len(status['positions'])}/3):</b>\n"
		)
		
		if positions_text:
			text += positions_text
		else:
			text += "  Нет открытых позиций\n\n"
		
		text += (
			f"📈 <b>Статистика:</b>\n"
			f"  • Всего сделок: {status['stats']['total_trades']}\n"
			f"  • Винрейт: {status['stats']['win_rate']:.1f}%\n"
			f"  • Комиссии: ${status['stats']['total_commission']:.4f}\n"
			f"  • Stop-loss: {status['stats']['stop_loss_triggers']}\n"
			f"  • Take-profit: {status['stats']['take_profit_triggers']}\n"
			f"  • Trailing-stop: {status['stats']['trailing_stop_triggers']}"
		)
		
		await update.message.reply_text(text, parse_mode="HTML")

	async def paper_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Показывает детальную информацию о балансе"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		status = self.paper_trader.get_status()
		
		# Получаем текущие цены
		current_prices = {}
		if status['positions']:
			async with aiohttp.ClientSession() as session:
				provider = DataProvider(session)
				for pos in status['positions']:
					symbol = pos['symbol']
					try:
						klines = await provider.fetch_klines(symbol=symbol, interval=self.default_interval, limit=1)
						df = provider.klines_to_dataframe(klines)
						if not df.empty:
							current_prices[symbol] = float(df['close'].iloc[-1])
					except:
						current_prices[symbol] = pos['entry_price']
		
		# Рассчитываем детали
		total_invested = sum(
			self.paper_trader.positions[pos['symbol']].invest_amount
			for pos in status['positions']
		)
		
		total_current_value = sum(
			self.paper_trader.positions[pos['symbol']].get_pnl(current_prices.get(pos['symbol'], pos['entry_price']))['current_value']
			for pos in status['positions']
		)
		
		total_balance = status['current_balance'] + total_current_value
		total_profit = total_balance - status['initial_balance']
		total_profit_percent = (total_profit / status['initial_balance']) * 100
		
		text = (
			f"<b>💰 Paper Trading Balance</b>\n\n"
			f"<b>Начальный баланс:</b> ${status['initial_balance']:.2f}\n"
			f"<b>Свободные средства:</b> ${status['current_balance']:.2f}\n"
			f"<b>Инвестировано:</b> ${total_invested:.2f}\n"
			f"<b>Текущая стоимость позиций:</b> ${total_current_value:.2f}\n"
			f"<b>Общая стоимость:</b> ${total_balance:.2f}\n\n"
			f"<b>{'📈' if total_profit >= 0 else '📉'} Прибыль/Убыток:</b> {total_profit:+.2f} USD ({total_profit_percent:+.2f}%)\n"
			f"<b>💸 Комиссии:</b> ${status['stats']['total_commission']:.4f}\n\n"
			f"<b>Процент использования капитала:</b> {(total_invested / status['initial_balance'] * 100):.1f}%"
		)
		
		await update.message.reply_text(text, parse_mode="HTML")

	async def paper_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Показывает последние сделки"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
			
		limit = 10
		if context.args and len(context.args) > 0:
			try:
				limit = int(context.args[0])
				limit = min(max(limit, 1), 50)  # От 1 до 50
			except ValueError:
				pass
		
		trades = self.paper_trader.trades_history[-limit:]
		
		if not trades:
			await update.message.reply_text("📝 История сделок пуста.")
			return
		
		text = f"<b>📝 Последние {len(trades)} сделок:</b>\n\n"
		
		for trade in reversed(trades):
			trade_type = trade['type']
			symbol = trade.get('symbol', 'N/A')
			price = trade.get('price', 0)
			
			if trade_type == "BUY":
				emoji = "🟢"
				details = f"  Купил {trade['amount']:.6f} @ {format_price(price)}\n  Вложено: ${trade['invest_amount']:.2f}"
			elif trade_type in ["SELL", "MANUAL-CLOSE"]:
				emoji = "🔴"
				profit_emoji = "📈" if trade['profit'] >= 0 else "📉"
				details = f"  Продал {trade['amount']:.6f} @ {format_price(price)}\n  {profit_emoji} Прибыль: ${trade['profit']:+.2f} ({trade['profit_percent']:+.2f}%)"
			elif trade_type == "STOP-LOSS":
				emoji = "🛑"
				details = f"  Стоп-лосс {trade['amount']:.6f} @ {format_price(price)}\n  📉 Убыток: ${trade['profit']:+.2f} ({trade['profit_percent']:+.2f}%)"
			elif trade_type == "PARTIAL-TP":
				emoji = "💎"
				details = f"  Частичный тейк {trade['amount']:.6f} @ {format_price(price)}\n  📈 Прибыль: ${trade['profit']:+.2f} ({trade['profit_percent']:+.2f}%)"
			elif trade_type == "TRAILING-STOP":
				emoji = "🔻"
				details = f"  Trailing stop {trade['amount']:.6f} @ {format_price(price)}\n  📊 Прибыль: ${trade['profit']:+.2f} ({trade['profit_percent']:+.2f}%)"
			else:
				emoji = "⚪"
				details = f"  {trade.get('amount', 0):.6f} @ {format_price(price)}"
			
			time_str = trade.get('time', 'N/A')
			if isinstance(time_str, datetime):
				time_str = time_str.strftime('%H:%M:%S')
			elif isinstance(time_str, str) and 'T' in time_str:
				time_str = time_str.split('T')[1].split('.')[0]
			
			text += f"{emoji} <b>{trade_type}</b> {symbol} [{time_str}]\n{details}\n\n"
		
		await update.message.reply_text(text, parse_mode="HTML")

	async def paper_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Сбрасывает paper trading"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		if self.paper_trader.is_running:
			await update.message.reply_text("⚠️ Сначала остановите Paper Trading командой /paper_stop")
			return
		
		old_balance = self.paper_trader.balance
		old_trades = len(self.paper_trader.trades_history)
		
		self.paper_trader.reset()
		self.paper_trader.save_state()
		
		text = (
			f"<b>🔄 Paper Trading сброшен</b>\n\n"
			f"Баланс сброшен с ${old_balance:.2f} → ${self.paper_trader.initial_balance:.2f}\n"
			f"Удалено сделок: {old_trades}\n\n"
			f"Используйте /paper_start для запуска."
		)
		await update.message.reply_text(text, parse_mode="HTML")

	async def paper_backtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Быстрая симуляция paper trading на исторических данных"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		period_hours = 24  # По умолчанию 24 часа
		if context.args and len(context.args) > 0:
			try:
				period_hours = int(context.args[0])
				period_hours = min(max(period_hours, 1), 168)  # От 1 до 168 часов (неделя)
			except ValueError:
				await update.message.reply_text("⚠️ Неверный формат. Использую 24 часа.")
		
		if not self.tracked_symbols:
			await update.message.reply_text("⚠️ Нет отслеживаемых символов. Используйте /add SYMBOL")
			return
		
		msg = await update.message.reply_text(f"⏳ Запускаю симуляцию за {period_hours}ч на {len(self.tracked_symbols)} парах...")
		
		from backtest import run_backtest_multiple
		import asyncio as aio_backtest
		
		try:
			# Запускаем бэктест
			symbols = list(self.tracked_symbols)
			results = []
			
			async with aiohttp.ClientSession() as session:
				provider = DataProvider(session)
				
				for i, symbol in enumerate(symbols):
					await msg.edit_text(f"⏳ Симуляция {i+1}/{len(symbols)}: {symbol}...")
					
					# Получаем данные
					candles_per_hour = int(60 / int(self.default_interval.replace('m',''))) if 'm' in self.default_interval else 1
					limit = period_hours * candles_per_hour
					
					df = await provider.fetch_klines(symbol=symbol, interval=self.default_interval, limit=limit)
					
					if df is None or df.empty:
						continue
					
					# Симулируем как в backtest.py
					generator = SignalGenerator(df)
					generator.compute_indicators()
					
					signals = []
					min_window = 14
					
					for j in range(len(df)):
						sub_df = df.iloc[:j+1]
						if len(sub_df) < min_window:
							signals.append({"signal": "HOLD", "price": sub_df["close"].iloc[-1]})
							continue
						gen = SignalGenerator(sub_df)
						gen.compute_indicators()
						res = gen.generate_signal()
						signals.append(res)
					
					# Симулируем торговлю
					from paper_trader import COMMISSION_RATE, STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT, PARTIAL_CLOSE_PERCENT, TRAILING_STOP_PERCENT, get_position_size_percent
					
					balance = 100.0
					position = 0.0
					entry_price = None
					trades = 0
					wins = 0
					losses = 0
					partial_closed = False
					max_price = 0.0
					
					for s in signals:
						price = s.get("price", 0)
						sig = s.get("signal", "HOLD")
						signal_strength = abs(s.get("bullish_votes", 0) - s.get("bearish_votes", 0))
						atr = s.get("ATR", 0.0)
						
						# Проверка стоп-лоссов
						if position > 0 and entry_price:
							price_change = (price - entry_price) / entry_price
							
							if partial_closed:
								if price > max_price:
									max_price = price
								trailing_drop = (max_price - price) / max_price
								if trailing_drop >= TRAILING_STOP_PERCENT:
									sell_value = position * price
									commission = sell_value * COMMISSION_RATE
									balance += sell_value - commission
									trades += 1
									if (price - entry_price) > 0:
										wins += 1
									else:
										losses += 1
									position = 0.0
									entry_price = None
									partial_closed = False
									max_price = 0.0
									continue
							else:
								if price_change <= -STOP_LOSS_PERCENT:
									sell_value = position * price
									commission = sell_value * COMMISSION_RATE
									balance += sell_value - commission
									trades += 1
									losses += 1
									position = 0.0
									entry_price = None
									continue
								
								if price_change >= TAKE_PROFIT_PERCENT:
									close_amount = position * PARTIAL_CLOSE_PERCENT
									keep_amount = position - close_amount
									sell_value = close_amount * price
									commission = sell_value * COMMISSION_RATE
									balance += sell_value - commission
									position = keep_amount
									partial_closed = True
									max_price = price
									trades += 1
									wins += 1
									continue
						
						# Открытие/закрытие позиций
						if sig == "BUY" and position == 0 and balance > 0:
							position_size_percent = get_position_size_percent(signal_strength, atr, price)
							invest_amount = balance * position_size_percent
							commission = invest_amount * COMMISSION_RATE
							position = (invest_amount - commission) / price
							entry_price = price
							balance -= invest_amount
							trades += 1
						elif sig == "SELL" and position > 0 and not partial_closed:
							sell_value = position * price
							commission = sell_value * COMMISSION_RATE
							balance += sell_value - commission
							if (price - entry_price) > 0:
								wins += 1
							else:
								losses += 1
							position = 0.0
							entry_price = None
					
					# Закрываем оставшуюся позицию
					if position > 0:
						final_price = signals[-1]["price"]
						sell_value = position * final_price
						commission = sell_value * COMMISSION_RATE
						balance += sell_value - commission
						if (final_price - entry_price) > 0:
							wins += 1
						else:
							losses += 1
						position = 0.0
						partial_closed = False
					
					profit = balance - 100.0
					profit_percent = profit
					win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
					
					results.append({
						"symbol": symbol,
						"profit": profit,
						"profit_percent": profit_percent,
						"trades": trades,
						"win_rate": win_rate
					})
			
			# Формируем отчет
			if results:
				text = f"<b>📊 Симуляция за {period_hours}ч ({self.default_interval})</b>\n\n"
				
				total_profit = 0
				total_trades = 0
				
				for r in sorted(results, key=lambda x: x['profit'], reverse=True):
					emoji = "🟢" if r['profit'] > 0 else "🔴" if r['profit'] < 0 else "⚪"
					text += (
						f"{emoji} <b>{r['symbol']}</b>\n"
						f"  Прибыль: {r['profit']:+.2f} USD ({r['profit_percent']:+.2f}%)\n"
						f"  Сделок: {r['trades']} | Винрейт: {r['win_rate']:.0f}%\n\n"
					)
					total_profit += r['profit']
					total_trades += r['trades']
				
				avg_profit = total_profit / len(results)
				text += (
					f"<b>{'📈' if total_profit >= 0 else '📉'} ИТОГО:</b>\n"
					f"  Общая прибыль: {total_profit:+.2f} USD\n"
					f"  Средняя: {avg_profit:+.2f} USD\n"
					f"  Всего сделок: {total_trades}\n\n"
					f"<i>Это симуляция на исторических данных.\n"
					f"Реальные результаты могут отличаться.</i>"
				)
				
				await msg.edit_text(text, parse_mode="HTML")
			else:
				await msg.edit_text("⚠️ Нет данных для симуляции")
				
		except Exception as e:
			logger.error(f"Ошибка при симуляции: {e}")
			await msg.edit_text(f"❌ Ошибка при симуляции: {e}")

	async def paper_debug(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Отладочная информация по сигналу"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		if not context.args:
			await update.message.reply_text("⚠️ Использование: /paper_debug SYMBOL")
			return
		
		symbol = context.args[0].upper()
		
		msg = await update.message.reply_text(f"🔍 Анализирую {symbol}...")
		
		try:
			async with aiohttp.ClientSession() as session:
				provider = DataProvider(session)
				klines = await provider.fetch_klines(symbol=symbol, interval=self.default_interval, limit=500)
				df = provider.klines_to_dataframe(klines)
				
				if df.empty:
					await msg.edit_text("⚠️ Нет данных")
					return
				
				generator = SignalGenerator(df)
				generator.compute_indicators()
				result = generator.generate_signal()
				
				signal = result["signal"]
				price = result["price"]
				bullish = result["bullish_votes"]
				bearish = result["bearish_votes"]
				
				# Собираем информацию о фильтрах
				last = df.iloc[-1]
				ema_s = float(last["EMA_short"])
				ema_l = float(last["EMA_long"])
				sma_20 = float(last.get("SMA_20", 0))
				sma_50 = float(last.get("SMA_50", 0))
				rsi = float(last["RSI"])
				macd = float(last["MACD"])
				macd_signal = float(last["MACD_signal"])
				macd_hist = float(last["MACD_hist"])
				adx = float(last.get("ADX_14", 0))
				
				# Проверяем фильтры для BUY
				buy_trend_ok = ema_s > ema_l and sma_20 > sma_50
				buy_rsi_ok = 35 < rsi < 70
				macd_buy_ok = macd > macd_signal and macd_hist > 0
				strong_trend = adx > 25
				vote_diff = bullish - bearish
				
				# Проверяем фильтры для SELL
				sell_trend_ok = ema_s < ema_l and sma_20 < sma_50
				sell_rsi_ok = 30 < rsi < 65
				macd_sell_ok = macd < macd_signal and macd_hist < 0
				
				signal_emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "⚠️"
				
				text = (
					f"<b>🔍 Debug: {symbol}</b> [{signal_emoji} {signal}]\n\n"
					f"💰 Цена: {format_price(price)}\n\n"
					f"<b>📊 Голосование:</b>\n"
					f"  Бычьи: {bullish} | Медвежьи: {bearish}\n"
					f"  Разница: {vote_diff} (порог: 5)\n\n"
					f"<b>📈 Индикаторы:</b>\n"
					f"  EMA: {ema_s:.2f} vs {ema_l:.2f} {'✅' if ema_s > ema_l else '❌'}\n"
					f"  SMA: {sma_20:.2f} vs {sma_50:.2f} {'✅' if sma_20 > sma_50 else '❌'}\n"
					f"  RSI: {rsi:.1f} (35-70 для BUY) {'✅' if buy_rsi_ok else '❌'}\n"
					f"  MACD: {macd:.4f} vs {macd_signal:.4f} {'✅' if macd > macd_signal else '❌'}\n"
					f"  MACD hist: {macd_hist:.4f} {'✅' if macd_hist > 0 else '❌'}\n"
					f"  ADX: {adx:.1f} (>25 для сигнала) {'✅' if strong_trend else '❌'}\n\n"
					f"<b>🎯 Фильтры BUY:</b>\n"
					f"  {'✅' if vote_diff >= 5 else '❌'} Голосов >= 5: {vote_diff}/5\n"
					f"  {'✅' if strong_trend else '❌'} Сильный тренд: ADX {adx:.1f}/25\n"
					f"  {'✅' if buy_trend_ok else '❌'} Тренд вверх: EMA+SMA\n"
					f"  {'✅' if buy_rsi_ok else '❌'} RSI в зоне: {rsi:.1f}\n"
					f"  {'✅' if macd_buy_ok else '❌'} MACD подтверждает\n\n"
				)
				
				# Добавляем причины
				text += "<b>📝 Причины:</b>\n"
				for i, reason in enumerate(result["reasons"][-5:], 1):
					text += f"{i}. {reason[:80]}...\n" if len(reason) > 80 else f"{i}. {reason}\n"
				
				await msg.edit_text(text, parse_mode="HTML")
				
		except Exception as e:
			logger.error(f"Ошибка debug для {symbol}: {e}")
			await msg.edit_text(f"❌ Ошибка: {e}")

	async def paper_candidates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Показывает пары близкие к сигналу"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		if not self.tracked_symbols:
			await update.message.reply_text("⚠️ Нет отслеживаемых символов")
			return
		
		msg = await update.message.reply_text(f"🔍 Ищу кандидатов среди {len(self.tracked_symbols)} пар...")
		
		candidates = []
		
		try:
			async with aiohttp.ClientSession() as session:
				provider = DataProvider(session)
				
				for symbol in self.tracked_symbols:
					try:
						klines = await provider.fetch_klines(symbol=symbol, interval=self.default_interval, limit=500)
						df = provider.klines_to_dataframe(klines)
						
						if df.empty:
							continue
						
						generator = SignalGenerator(df)
						generator.compute_indicators()
						result = generator.generate_signal()
						
						signal = result["signal"]
						price = result["price"]
						bullish = result["bullish_votes"]
						bearish = result["bearish_votes"]
						
						last = df.iloc[-1]
						adx = float(last.get("ADX_14", 0))
						rsi = float(last["RSI"])
						
						# Кандидат если:
						# 1. Голосов 3-5 (близко к порогу)
						# 2. ADX > 20 (приближается к 25)
						vote_diff_buy = bullish - bearish
						vote_diff_sell = bearish - bullish
						
						if (3 <= vote_diff_buy < 5 or 3 <= vote_diff_sell < 5) and adx > 20:
							direction = "BUY" if vote_diff_buy > vote_diff_sell else "SELL"
							votes = vote_diff_buy if direction == "BUY" else vote_diff_sell
							
							candidates.append({
								"symbol": symbol,
								"direction": direction,
								"votes": votes,
								"adx": adx,
								"rsi": rsi,
								"price": price
							})
							
					except Exception as e:
						logger.error(f"Ошибка анализа {symbol}: {e}")
			
			if candidates:
				# Сортируем по количеству голосов (больше = ближе к сигналу)
				candidates.sort(key=lambda x: x['votes'], reverse=True)
				
				text = f"<b>🎯 Кандидаты на сигнал ({len(candidates)}):</b>\n\n"
				
				for c in candidates[:10]:  # Топ 10
					emoji = "🟢" if c['direction'] == "BUY" else "🔴"
					text += (
						f"{emoji} <b>{c['symbol']}</b> → {c['direction']}\n"
						f"  Голосов: {c['votes']}/5 | ADX: {c['adx']:.1f}/25\n"
						f"  RSI: {c['rsi']:.1f} | Цена: {format_price(c['price'])}\n\n"
					)
				
				text += "<i>Эти пары близки к генерации сигнала</i>"
				await msg.edit_text(text, parse_mode="HTML")
			else:
				await msg.edit_text("⚠️ Нет кандидатов близких к сигналу.\n\nПопробуйте позже или добавьте больше пар.")
				
		except Exception as e:
			logger.error(f"Ошибка поиска кандидатов: {e}")
			await msg.edit_text(f"❌ Ошибка: {e}")

	async def paper_force_buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Принудительно открывает позицию для тестирования"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		if not self.paper_trader.is_running:
			await update.message.reply_text("⚠️ Paper Trading не запущен. Используйте /paper_start")
			return
		
		if not context.args:
			await update.message.reply_text("⚠️ Использование: /paper_force_buy SYMBOL")
			return
		
		symbol = context.args[0].upper()
		
		if symbol in self.paper_trader.positions:
			await update.message.reply_text(f"⚠️ Позиция по {symbol} уже открыта")
			return
		
		if not self.paper_trader.can_open_position(symbol):
			await update.message.reply_text(f"⚠️ Невозможно открыть позицию (лимит или нет баланса)")
			return
		
		try:
			async with aiohttp.ClientSession() as session:
				provider = DataProvider(session)
				klines = await provider.fetch_klines(symbol=symbol, interval=self.default_interval, limit=500)
				df = provider.klines_to_dataframe(klines)
				
				if df.empty:
					await update.message.reply_text("⚠️ Нет данных для получения цены")
					return
				
				# Генерируем сигнал чтобы получить ATR
				generator = SignalGenerator(df)
				generator.compute_indicators()
				result = generator.generate_signal()
				
				price = float(df['close'].iloc[-1])
				signal_strength = 5  # Средняя сила для теста
				atr = result.get("ATR", 0.0)
				
				trade_info = self.paper_trader.open_position(symbol, price, signal_strength, atr)
				
				if trade_info:
					self.paper_trader.save_state()
					
					text = (
						f"<b>🟢 ПРИНУДИТЕЛЬНАЯ ПОКУПКА</b>\n\n"
						f"Символ: {symbol}\n"
						f"Цена: {format_price(price)}\n"
						f"Вложено: ${trade_info['invest_amount']:.2f}\n"
						f"Баланс: ${trade_info['balance_after']:.2f}\n\n"
						f"⚠️ Это тестовая сделка!\n"
						f"Проверьте /paper_status"
					)
					await update.message.reply_text(text, parse_mode="HTML")
				else:
					await update.message.reply_text("❌ Не удалось открыть позицию")
					
		except Exception as e:
			logger.error(f"Ошибка force_buy для {symbol}: {e}")
			await update.message.reply_text(f"❌ Ошибка: {e}")

	async def kelly_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Информация о Kelly Criterion"""
		if not self._is_authorized(update):
			await update.message.reply_text("❌ У вас нет доступа к этому боту.")
			return
		
		from config import USE_KELLY_CRITERION, KELLY_FRACTION, MIN_TRADES_FOR_KELLY, KELLY_LOOKBACK_WINDOW
		
		message = "📊 <b>Kelly Criterion</b>\n\n"
		message += f"Статус: {'✅ Включен' if USE_KELLY_CRITERION else '❌ Выключен'}\n"
		message += f"Kelly Fraction: {KELLY_FRACTION:.0%} (консервативный)\n"
		message += f"Min Trades: {MIN_TRADES_FOR_KELLY}\n"
		message += f"Lookback Window: {KELLY_LOOKBACK_WINDOW} сделок\n\n"
		
		# Рассчитываем текущий Kelly
		closed_trades = [
			t for t in self.paper_trader.trades_history 
			if t.get("type") in ["SELL", "STOP-LOSS", "TRAILING-STOP", "TIME-EXIT"]
			and t.get("profit") is not None
		]
		
		if len(closed_trades) >= MIN_TRADES_FOR_KELLY:
			recent_trades = closed_trades[-KELLY_LOOKBACK_WINDOW:]
			
			winning_trades = [t for t in recent_trades if t.get("profit", 0) > 0]
			losing_trades = [t for t in recent_trades if t.get("profit", 0) <= 0]
			
			win_rate = len(winning_trades) / len(recent_trades) if recent_trades else 0
			
			if winning_trades:
				avg_win = sum(t.get("profit_percent", 0) for t in winning_trades) / len(winning_trades)
			else:
				avg_win = 0
			
			if losing_trades:
				avg_loss = abs(sum(t.get("profit_percent", 0) for t in losing_trades) / len(losing_trades))
			else:
				avg_loss = 1.0
			
			if avg_win > 0 and avg_loss > 0:
				kelly_full = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
				kelly_conservative = kelly_full * KELLY_FRACTION
				
				message += f"<b>Текущая статистика ({len(recent_trades)} сделок):</b>\n"
				message += f"• Win Rate: {win_rate:.1%}\n"
				message += f"• Avg Win: {avg_win:.2f}%\n"
				message += f"• Avg Loss: {avg_loss:.2f}%\n\n"
				message += f"<b>Kelly (полный):</b> {kelly_full:.2%}\n"
				message += f"<b>Kelly (1/4):</b> {kelly_conservative:.2%}\n\n"
				
				if kelly_conservative > 0:
					message += f"✅ Рекомендация: размер позиции {kelly_conservative:.1%} от баланса"
				else:
					message += "⚠️ Kelly отрицательный - стратегия убыточна на текущей выборке"
			else:
				message += "⚠️ Недостаточно данных для расчёта Kelly"
		else:
			message += f"⏳ Недостаточно сделок: {len(closed_trades)}/{MIN_TRADES_FOR_KELLY}\n"
			message += "Необходимо больше сделок для расчёта Kelly Criterion"
		
		await update.message.reply_text(message, parse_mode="HTML")
	
	async def averaging_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Статус докупаний по позициям"""
		if not self._is_authorized(update):
			await update.message.reply_text("❌ У вас нет доступа к этому боту.")
			return
		
		from config import (
			ENABLE_AVERAGING, MAX_AVERAGING_ATTEMPTS, AVERAGING_PRICE_DROP_PERCENT,
			AVERAGING_TIME_THRESHOLD_HOURS, MAX_TOTAL_RISK_MULTIPLIER,
			ENABLE_PYRAMID_UP, PYRAMID_ADX_THRESHOLD
		)
		
		message = "🔄 <b>Умное докупание (Averaging)</b>\n\n"
		message += f"Статус: {'✅ Включено' if ENABLE_AVERAGING else '❌ Выключено'}\n"
		message += f"Max Attempts: {MAX_AVERAGING_ATTEMPTS}\n"
		message += f"Price Drop: {AVERAGING_PRICE_DROP_PERCENT:.1%}\n"
		message += f"Time Threshold: {AVERAGING_TIME_THRESHOLD_HOURS}ч\n"
		message += f"Max Risk Multiplier: {MAX_TOTAL_RISK_MULTIPLIER}x\n"
		message += f"Pyramid Up: {'✅' if ENABLE_PYRAMID_UP else '❌'} (ADX > {PYRAMID_ADX_THRESHOLD})\n\n"
		
		# Статус по позициям
		if self.paper_trader.positions:
			message += "<b>Текущие позиции:</b>\n\n"
			
			for symbol, position in self.paper_trader.positions.items():
				averaging_count = position.averaging_count
				avg_entry = position.average_entry_price
				entry_price = position.entry_price
				mode = "PYRAMID" if position.pyramid_mode else "AVERAGE"
				
				message += f"<b>{symbol}</b>\n"
				message += f"• Вход: {format_price(entry_price)}\n"
				
				if averaging_count > 0:
					message += f"• Средняя: {format_price(avg_entry)}\n"
					message += f"• Докупания: {averaging_count}/{MAX_AVERAGING_ATTEMPTS} ({mode})\n"
					message += f"• Инвестировано: ${position.total_invested:.2f}\n"
					
					# История докупаний
					if position.averaging_entries:
						message += f"  Записи:\n"
						for i, entry in enumerate(position.averaging_entries[:3], 1):  # Максимум 3
							message += f"  {i}. ${entry['price']:.2f} - {entry['mode']}\n"
				else:
					message += f"• Докупания: 0/{MAX_AVERAGING_ATTEMPTS}\n"
				
				message += "\n"
		else:
			message += "Нет открытых позиций\n"
		
		# Статистика по докупаниям
		avg_trades = [t for t in self.paper_trader.trades_history if "AVERAGE" in t.get("type", "")]
		
		if avg_trades:
			message += f"\n<b>Статистика:</b>\n"
			message += f"• Всего докупаний: {len(avg_trades)}\n"
			
			pyramid_trades = [t for t in avg_trades if "PYRAMID" in t.get("type", "")]
			average_trades = [t for t in avg_trades if "AVERAGE-AVERAGE" in t.get("type", "")]
			
			message += f"• Pyramid Up: {len(pyramid_trades)}\n"
			message += f"• Average Down: {len(average_trades)}\n"
		
		await update.message.reply_text(message, parse_mode="HTML")

	# -------------------------
	# Запуск бота
	# -------------------------
	def run(self):
		logger.info("Запуск бота...")

		async def start_background(application):
			asyncio.create_task(self._background_task())

		self.application.post_init = start_background
		self.application.run_polling(stop_signals=None)
