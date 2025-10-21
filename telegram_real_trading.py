"""
Модуль Real Trading команд для Telegram бота
Содержит все команды связанные с реальной торговлей на Bybit
"""

import aiohttp
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import (
	REAL_MAX_DAILY_LOSS, REAL_MAX_POSITION_SIZE,
	REAL_ORDER_TYPE, REAL_LIMIT_ORDER_OFFSET_PERCENT
)
from data_provider import DataProvider
from signal_generator import SignalGenerator
from logger import logger
from telegram_formatters import TelegramFormatters
from safety_limits import SafetyLimits


class TelegramRealTrading:
	"""Класс для обработки Real Trading команд"""
	
	def __init__(self, bot_instance):
		self.bot = bot_instance
		self.formatters = TelegramFormatters()
		self.safety_limits = SafetyLimits()
	
	def _is_authorized(self, update: Update) -> bool:
		"""Проверяет, что пользователь является владельцем бота"""
		if self.bot.owner_chat_id is None:
			return True
		return update.effective_chat.id == self.bot.owner_chat_id
	
	def _check_real_trader(self, update):
		"""Проверяет, инициализирован ли RealTrader"""
		if not hasattr(self.bot, 'real_trader') or self.bot.real_trader is None:
			return False, "❌ Real Trading не инициализирован"
		return True, None

	async def real_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Запускает реальный трейдинг"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		# Проверяем инициализацию RealTrader
		is_ready, error_msg = self._check_real_trader(update)
		if not is_ready:
			await update.message.reply_text(error_msg)
			return
		
		if self.bot.real_trader.is_running:
			await update.message.reply_text("⚠️ Real Trading уже запущен!")
			return
		
		# Проверяем лимиты безопасности
		if not self.safety_limits.check_daily_loss_limit():
			await update.message.reply_text(f"❌ Достигнут дневной лимит убытков: ${self.safety_limits.get_daily_loss():.2f}")
			return
		
		# Проверяем API ключи
		if not hasattr(self.bot.real_trader, 'api_key') or not self.bot.real_trader.api_key or not self.bot.real_trader.api_secret:
			await update.message.reply_text("❌ BYBIT_API_KEY и BYBIT_API_SECRET не установлены в .env")
			return
		
		# Тестируем подключение к API
		try:
			async with aiohttp.ClientSession() as session:
				balance = await self.bot.real_trader.get_balance(session)
				if not balance:
					await update.message.reply_text("❌ Не удалось получить баланс с биржи")
					return
				usdt_balance = balance.get("USDT", 0.0)
				
				if usdt_balance <= 0:
					await update.message.reply_text("❌ Недостаточно USDT баланса на бирже")
					return
				
		except Exception as e:
			await update.message.reply_text(f"❌ Ошибка подключения к Bybit API: {e}")
			return
		
		# Запускаем реальный трейдинг
		success = self.bot.real_trader.start()
		if success:
			self.bot.real_trader.save_state()
			
			text = (
				f"<b>🚀 Real Trading запущен!</b>\n\n"
				f"💰 USDT баланс: ${usdt_balance:.2f}\n"
				f"📊 Тип ордеров: {REAL_ORDER_TYPE}\n"
				f"🛡️ Лимиты безопасности:\n"
				f"  • Макс убыток в день: ${REAL_MAX_DAILY_LOSS}\n"
				f"  • Макс размер позиции: ${REAL_MAX_POSITION_SIZE}\n"
				f"  • Макс позиций: динамический (зависит от баланса)\n\n"
				f"⚠️ <b>ВНИМАНИЕ:</b> Реальная торговля с реальными деньгами!\n"
				f"Используйте /real_status для проверки состояния."
			)
			await update.message.reply_text(text, parse_mode="HTML")
		else:
			await update.message.reply_text("❌ Не удалось запустить Real Trading")

	async def real_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Останавливает реальный трейдинг и закрывает все позиции"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		# Проверяем инициализацию RealTrader
		is_ready, error_msg = self._check_real_trader(update)
		if not is_ready:
			await update.message.reply_text(error_msg)
			return
		
		if not self.bot.real_trader.is_running:
			await update.message.reply_text("⚠️ Real Trading не запущен.")
			return
		
		# Закрываем все открытые позиции
		if self.bot.real_trader.positions:
			msg = await update.message.reply_text("⏳ Закрываю все позиции...")
			
			# Используем новую функцию для закрытия всех позиций
			closed_count = await self.bot.real_trader.stop_and_close_all()
			
			positions_text = f"Закрыто позиций: {closed_count}" if closed_count > 0 else "Нет позиций для закрытия"
		else:
			positions_text = "Нет открытых позиций"
			self.bot.real_trader.stop()
		
		self.bot.real_trader.save_state()
		
		# Получаем финальный статус
		status = await self.bot.real_trader.get_status()
		
		text = (
			f"<b>⏸ Real Trading остановлен</b>\n\n"
			f"Закрыто позиций:\n{positions_text}\n\n"
			f"💰 USDT баланс: ${status.get('usdt_balance', 0):.2f}\n"
			f"📊 Дневной убыток: ${status.get('daily_loss', 0):.2f}"
		)
		
		if self.bot.real_trader.positions:
			await msg.edit_text(text, parse_mode="HTML")
		else:
			await update.message.reply_text(text, parse_mode="HTML")

	async def real_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Показывает текущий статус реального трейдинга"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		# Проверяем инициализацию RealTrader
		is_ready, error_msg = self._check_real_trader(update)
		if not is_ready:
			await update.message.reply_text(error_msg)
			return
		
		status = await self.bot.real_trader.get_status()
		
		if "error" in status:
			await update.message.reply_text(f"❌ Ошибка получения статуса: {status['error']}")
			return
		
		# Получаем текущие цены для расчета PnL
		current_prices = {}
		if status['positions']:
			async with aiohttp.ClientSession() as session:
				provider = DataProvider(session)
				for pos in status['positions']:
					symbol = pos['symbol']
					try:
						klines = await provider.fetch_klines(symbol=symbol, interval=self.bot.default_interval, limit=1)
						df = provider.klines_to_dataframe(klines)
						if not df.empty:
							current_prices[symbol] = float(df['close'].iloc[-1])
					except:
						current_prices[symbol] = pos.get('current_price', 0)
		
		# Формируем информацию о позициях
		positions_text = ""
		total_pnl = 0.0
		total_current_value = 0.0
		
		for pos in status['positions']:
			symbol = pos['symbol']
			quantity = pos['quantity']
			entry_price = pos.get('entry_price', 0)
			current_price = current_prices.get(symbol, pos.get('current_price', entry_price))
			
			if current_price > 0:
				# Рассчитываем PnL правильно
				entry_value = quantity * entry_price
				current_value = quantity * current_price
				pnl = current_value - entry_value
				pnl_percent = (pnl / entry_value) * 100 if entry_value > 0 else 0
				total_pnl += pnl
				total_current_value += current_value
				
				emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
				
				# Получаем SL/TP из позиции
				stop_loss = pos.get('stop_loss', 0)
				take_profit = pos.get('take_profit', 0)
				
				positions_text += (
					f"  {emoji} <b>{symbol}</b>\n"
					f"    Вход: {self.formatters.format_price(entry_price)} → Сейчас: {self.formatters.format_price(current_price)}\n"
					f"    PnL: ${pnl:+.2f} ({pnl_percent:+.2f}%)\n"
					f"    Стоимость: ${current_value:.2f}\n"
				)
				
				# Добавляем SL/TP если они установлены
				if stop_loss > 0 or take_profit > 0:
					sl_text = f"SL: {self.formatters.format_price(stop_loss)}" if stop_loss > 0 else "SL: —"
					tp_text = f"TP: {self.formatters.format_price(take_profit)}" if take_profit > 0 else "TP: —"
					positions_text += f"    {sl_text} | {tp_text}\n"
				
				positions_text += "\n"
		
		status_emoji = "🟢" if status['is_running'] else "⏸"
		
		# Рассчитываем общий баланс включая позиции
		usdt_balance = status.get('usdt_balance', 0)
		total_balance = usdt_balance + total_current_value
		
		text = (
			f"<b>{status_emoji} Real Trading Status</b>\n\n"
			f"💰 <b>Баланс:</b>\n"
			f"  • USDT: ${usdt_balance:.2f}\n"
			f"  • Позиции: ${total_current_value:.2f}\n"
			f"  • Общий: ${total_balance:.2f}\n"
			f"  • PnL: ${total_pnl:+.2f}\n\n"
			f"📊 <b>Позиции ({len(status['positions'])}/{status.get('max_positions', 'N/A')}):</b>\n"
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
			f"  • Trailing-stop: {status['stats']['trailing_stop_triggers']}\n\n"
			f"🛡️ <b>Лимиты:</b>\n"
			f"  • Дневной убыток: ${status.get('daily_loss', 0):.2f} / ${status.get('daily_loss_limit', REAL_MAX_DAILY_LOSS)}\n"
			f"  • Статус: {'🔴 Заблокирован' if status.get('daily_loss', 0) >= status.get('daily_loss_limit', REAL_MAX_DAILY_LOSS) else '🟢 Активен'}"
		)
		
		await update.message.reply_text(text, parse_mode="HTML")

	async def real_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Показывает детальный баланс с Bybit"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		# Проверяем инициализацию RealTrader
		is_ready, error_msg = self._check_real_trader(update)
		if not is_ready:
			await update.message.reply_text(error_msg)
			return
		
		try:
			async with aiohttp.ClientSession() as session:
				balance_data = await self.bot.real_trader.get_balance(session)
				
				text = "<b>💰 Bybit Balance</b>\n\n"
				
				if balance_data:
					for coin, balance in balance_data.items():
						if balance > 0:
							text += f"<b>{coin}:</b> {balance:.6f}\n"
				else:
					text += "Нет данных о балансе"
				
				await update.message.reply_text(text, parse_mode="HTML")
				
		except Exception as e:
			logger.error(f"Ошибка получения баланса: {e}")
			await update.message.reply_text(f"❌ Ошибка получения баланса: {e}")

	async def real_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Показывает историю реальных сделок"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		# Проверяем инициализацию RealTrader
		is_ready, error_msg = self._check_real_trader(update)
		if not is_ready:
			await update.message.reply_text(error_msg)
			return
		
		limit = 10
		if context.args and len(context.args) > 0:
			try:
				limit = int(context.args[0])
				limit = min(max(limit, 1), 50)  # От 1 до 50
			except ValueError:
				pass
		
		trades = self.bot.real_trader.trades_history[-limit:]
		
		if not trades:
			await update.message.reply_text("📝 История реальных сделок пуста.")
			return
		
		text = f"<b>📝 Последние {len(trades)} реальных сделок:</b>\n\n"
		
		for trade in reversed(trades):
			trade_type = trade['type']
			symbol = trade.get('symbol', 'N/A')
			price = trade.get('price', 0)
			order_id = trade.get('order_id', 'N/A')
			
			if trade_type == "BUY":
				emoji = "🟢"
				details = f"  Купил {trade['amount']:.6f} @ {self.formatters.format_price(price)}\n  Вложено: ${trade['invest_amount']:.2f}\n  Order ID: {order_id}"
			elif trade_type in ["SELL", "MANUAL-CLOSE"]:
				emoji = "🔴"
				profit_emoji = "📈" if trade['profit'] >= 0 else "📉"
				details = f"  Продал {trade['amount']:.6f} @ {self.formatters.format_price(price)}\n  {profit_emoji} Прибыль: ${trade['profit']:+.2f} ({trade['profit_percent']:+.2f}%)\n  Order ID: {order_id}"
			elif trade_type == "STOP-LOSS":
				emoji = "🛑"
				details = f"  Стоп-лосс {trade['amount']:.6f} @ {self.formatters.format_price(price)}\n  📉 Убыток: ${trade['profit']:+.2f} ({trade['profit_percent']:+.2f}%)\n  Order ID: {order_id}"
			elif trade_type == "TAKE-PROFIT":
				emoji = "💎"
				details = f"  Тейк-профит {trade['amount']:.6f} @ {self.formatters.format_price(price)}\n  📈 Прибыль: ${trade['profit']:+.2f} ({trade['profit_percent']:+.2f}%)\n  Order ID: {order_id}"
			else:
				emoji = "⚪"
				details = f"  {trade.get('amount', 0):.6f} @ {self.formatters.format_price(price)}\n  Order ID: {order_id}"
			
			time_str = trade.get('time', 'N/A')
			if isinstance(time_str, datetime):
				time_str = time_str.strftime('%H:%M:%S')
			elif isinstance(time_str, str) and 'T' in time_str:
				time_str = time_str.split('T')[1].split('.')[0]
			
			text += f"{emoji} <b>{trade_type}</b> {symbol} [{time_str}]\n{details}\n\n"
		
		await update.message.reply_text(text, parse_mode="HTML")

	async def real_limits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Показывает/изменяет лимиты безопасности"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		limits_status = self.safety_limits.get_status()
		
		text = (
			f"<b>🛡️ Лимиты безопасности</b>\n\n"
			f"<b>Дневной лимит убытков:</b>\n"
			f"  • Текущий убыток: ${limits_status['daily_loss']:.2f}\n"
			f"  • Лимит: ${limits_status['daily_loss_limit']:.2f}\n"
			f"  • Осталось: ${limits_status['remaining_daily_loss']:.2f}\n"
			f"  • Статус: {'🔴 Превышен' if limits_status['is_daily_limit_reached'] else '🟢 В норме'}\n\n"
			f"<b>Лимиты позиций:</b>\n"
			f"  • Макс размер: ${limits_status['max_position_size']:.2f}\n"
			f"  • Макс количество: {limits_status['max_positions']}\n\n"
			f"<b>Настройки ордеров:</b>\n"
			f"  • Тип: {REAL_ORDER_TYPE}\n"
			f"  • Оффсет лимитных: {REAL_LIMIT_ORDER_OFFSET_PERCENT*100:.1f}%"
		)
		
		await update.message.reply_text(text, parse_mode="HTML")

	async def real_emergency_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		"""Экстренная остановка торговли"""
		if not self._is_authorized(update):
			await update.message.reply_text("🚫 Доступ запрещен")
			return
		
		# Проверяем инициализацию RealTrader
		is_ready, error_msg = self._check_real_trader(update)
		if not is_ready:
			await update.message.reply_text(error_msg)
			return
		
		# Немедленно останавливаем
		self.bot.real_trader.stop()
		self.bot.real_trader.save_state()
		
		# Закрываем все позиции принудительно
		closed_count = 0
		if self.bot.real_trader.positions:
			async with aiohttp.ClientSession() as session:
				provider = DataProvider(session)
				for symbol in list(self.bot.real_trader.positions.keys()):
					try:
						klines = await provider.fetch_klines(symbol=symbol, interval=self.bot.default_interval, limit=1)
						df = provider.klines_to_dataframe(klines)
						if not df.empty:
							current_price = float(df['close'].iloc[-1])
							await self.bot.real_trader.close_position(symbol, current_price, "EMERGENCY-STOP")
							closed_count += 1
					except Exception as e:
						logger.error(f"Ошибка экстренного закрытия {symbol}: {e}")
		
		text = (
			f"<b>🚨 ЭКСТРЕННАЯ ОСТАНОВКА</b>\n\n"
			f"Real Trading остановлен немедленно!\n"
			f"Закрыто позиций: {closed_count}\n\n"
			f"⚠️ Проверьте состояние через /real_status"
		)
		
		await update.message.reply_text(text, parse_mode="HTML")
