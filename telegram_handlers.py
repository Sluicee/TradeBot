"""
Модуль обработчиков команд Telegram бота
Содержит все команды и их логику
"""

import aiohttp
import asyncio
import math
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import (
    DEFAULT_SYMBOL, DEFAULT_INTERVAL, POLL_INTERVAL, POLL_INTERVAL_MIN, POLL_INTERVAL_MAX,
    VOLATILITY_WINDOW, VOLATILITY_THRESHOLD, POLL_VOLATILITY_HIGH_THRESHOLD, 
    POLL_VOLATILITY_LOW_THRESHOLD, VOLATILITY_ALERT_COOLDOWN, ADX_WINDOW,
    STRATEGY_MODE, USE_MULTI_TIMEFRAME, MTF_TIMEFRAMES
)
from data_provider import DataProvider
from signal_generator import SignalGenerator
from logger import logger
from database import db
from telegram_formatters import TelegramFormatters
from telegram_paper_trading import TelegramPaperTrading
from telegram_analytics import TelegramAnalytics


class TelegramHandlers:
    """Класс для обработки команд Telegram бота"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.formatters = TelegramFormatters()
        self.paper_trading = TelegramPaperTrading(bot_instance)
        self.analytics = TelegramAnalytics(bot_instance)
    
    def _is_authorized(self, update: Update) -> bool:
        """Проверяет, что пользователь является владельцем бота"""
        if self.bot.owner_chat_id is None:
            return True
        return update.effective_chat.id == self.bot.owner_chat_id
    
    
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
            "• /mtf_signal SYMBOL — multi-timeframe анализ\n"
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
            "• /paper_reset — сбросить баланс и историю\n\n"
            "<b>🔬 Аналитика и настройки:</b>\n"
            "• /kelly_info — информация о Kelly Criterion\n"
            "• /averaging_status — статус докупаний\n"
            "• /settings — настройки бота"
        )
        await update.message.reply_text(text, parse_mode="HTML")
        
        if self.bot.chat_id is None:
            self.bot.chat_id = update.effective_chat.id
            self.bot._save_tracked_symbols()

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            await update.message.reply_text("🚫 Доступ запрещен")
            return
        
        text = (
            "<b>🆘 Помощь:</b>\n\n"
            "<b>Анализ:</b>\n"
            "• /analyze SYMBOL INTERVAL — анализ указанной пары\n"
            "• /mtf_signal SYMBOL — multi-timeframe анализ (15m+1h+4h)\n"
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
            "• /paper_force_sell [SYMBOL] — принудительная продажа\n"
            "• /paper_reset — сбросить баланс и историю\n\n"
            "<b>Аналитика:</b>\n"
            "• /kelly_info — информация о Kelly Criterion\n"
            "• /averaging_status — статус докупаний\n"
            "• /signal_stats — статистика сигналов v5.5 🆕\n"
            "• /signal_analysis — детальный анализ голосов 🆕\n\n"
            "<b>Настройки:</b>\n"
            "• /settings — настройки интервала опроса и волатильности\n\n"
            "<i>Если SYMBOL и INTERVAL не указаны, используются значения по умолчанию.</i>"
        )
        await update.message.reply_text(text, parse_mode="HTML")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            await update.message.reply_text("🚫 Доступ запрещен")
            return
        
        from telegram import __version__ as tg_version
        symbols = ", ".join(self.bot.tracked_symbols) if self.bot.tracked_symbols else "нет"
        text = (
            f"<b>ℹ️ Статус бота</b>\n"
            f"• Версия библиотеки: python-telegram-bot {tg_version}\n"
            f"• Символ по умолчанию: {self.bot.default_symbol}\n"
            f"• Интервал по умолчанию: {self.bot.default_interval}\n"
            f"• Отслеживаемые пары: {symbols}\n"
            f"• Статус: ✅ OK"
        )
        await update.message.reply_text(text, parse_mode="HTML")
        
        if self.bot.chat_id is None:
            self.bot.chat_id = update.effective_chat.id
            self.bot._save_tracked_symbols()

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
        if symbol in self.bot.tracked_symbols:
            await update.message.reply_text(f"ℹ️ {symbol} уже в списке отслеживаемых.")
        else:
            self.bot.tracked_symbols.add(symbol)
            self.bot._save_tracked_symbols()
            await update.message.reply_text(f"✅ {symbol} добавлен в список отслеживаемых.")

    async def remove_symbol(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            await update.message.reply_text("🚫 Доступ запрещен")
            return
        
        if not context.args:
            await update.message.reply_text("⚠️ Использование: /remove SYMBOL")
            return
        symbol = context.args[0].upper()
        if symbol in self.bot.tracked_symbols:
            self.bot.tracked_symbols.remove(symbol)
            self.bot._save_tracked_symbols()
            await update.message.reply_text(f"✅ {symbol} удалён из списка отслеживаемых.")
        else:
            await update.message.reply_text(f"ℹ️ {symbol} нет в списке отслеживаемых.")

    async def list_symbols(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            await update.message.reply_text("🚫 Доступ запрещен")
            return
        
        if self.bot.tracked_symbols:
            text = "<b>📋 Отслеживаемые пары:</b>\n" + "\n".join([f"• {s}" for s in self.bot.tracked_symbols])
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
        symbol = args[0].upper() if len(args) >= 1 else self.bot.default_symbol
        interval = args[1] if len(args) >= 2 else self.bot.default_interval

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
                
                # Если MTF включен - используем MTF анализ напрямую
                if USE_MULTI_TIMEFRAME:
                    result = await generator.generate_signal_multi_timeframe(
                        data_provider=provider,
                        symbol=symbol,
                        strategy=STRATEGY_MODE
                    )
                else:
                    result = self.bot._generate_signal_with_strategy(generator, symbol=symbol)

            text = self.formatters.format_analysis(result, symbol, interval)
            await msg.edit_text(text, parse_mode="HTML")
        except Exception as e:
            await msg.edit_text(f"Ошибка при анализе: {e}")
    
    async def mtf_signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🔀 Multi-timeframe анализ сигнала"""
        if not self._is_authorized(update):
            await update.message.reply_text("🚫 Доступ запрещен")
            return
        
        if not context.args:
            await update.message.reply_text("⚠️ Использование: /mtf_signal SYMBOL")
            return
        
        symbol = context.args[0].upper()
        msg = await update.message.reply_text(f"🔍 Multi-timeframe анализ {symbol}...")
        
        try:
            async with aiohttp.ClientSession() as session:
                provider = DataProvider(session)
                
                # Загружаем данные для основного таймфрейма
                klines = await provider.fetch_klines(symbol=symbol, interval=self.bot.default_interval, limit=200)
                df = provider.klines_to_dataframe(klines)
                
                if df.empty:
                    await msg.edit_text("⚠️ Не удалось получить данные")
                    return
                
                # Генерируем MTF сигнал напрямую (async) - ВНУТРИ async with!
                generator = SignalGenerator(df)
                generator.compute_indicators()
                result = await generator.generate_signal_multi_timeframe(
                    data_provider=provider,
                    symbol=symbol,
                    strategy=STRATEGY_MODE
                )
            
            # Форматируем вывод (после async with, но данные уже получены)
            text = self.formatters._format_mtf_analysis(result, symbol)
            await msg.edit_text(text, parse_mode="HTML")
        
        except Exception as e:
            logger.error(f"Ошибка MTF анализа: {e}")
            await msg.edit_text(f"❌ Ошибка: {e}")

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
                f"  • Текущий: {self.bot.current_poll_interval} сек\n"
                f"  • Базовый: {self.bot.poll_interval} сек\n"
                f"  • Диапазон: {POLL_INTERVAL_MIN}-{POLL_INTERVAL_MAX} сек\n\n"
                f"<b>Волатильность:</b>\n"
                f"  • Окно: {self.bot.volatility_window} свечей\n"
                f"  • Порог алерта: {self.bot.volatility_threshold*100:.2f}%\n"
                f"  • Порог высокой: {POLL_VOLATILITY_HIGH_THRESHOLD*100:.2f}%\n"
                f"  • Порог низкой: {POLL_VOLATILITY_LOW_THRESHOLD*100:.2f}%\n"
                f"  • Cooldown: {VOLATILITY_ALERT_COOLDOWN/60:.0f} мин\n\n"
                f"<i>При высокой волатильности интервал автоматически\n"
                f"увеличивается до {POLL_INTERVAL_MAX}с для снижения спама</i>"
            )
            await update.message.reply_text(text, parse_mode="HTML")
            return

        try:
            if len(args) >= 1:
                self.bot.poll_interval = int(args[0])
            if len(args) >= 2:
                self.bot.volatility_window = int(args[1])
            if len(args) >= 3:
                self.bot.volatility_threshold = float(args[2])
            self.bot._save_tracked_symbols()
            await update.message.reply_text(
                f"✅ Настройки обновлены:\n"
                f"poll_interval = {self.bot.poll_interval} сек\n"
                f"volatility_window = {self.bot.volatility_window} свечей\n"
                f"volatility_threshold = {self.bot.volatility_threshold*100:.2f}%"
            )
        except Exception as e:
            await update.message.reply_text(f"Ошибка при обновлении настроек: {e}")

    # -------------------------
    # Paper Trading команды (делегируем в отдельный модуль)
    # -------------------------
    async def paper_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.paper_trading.paper_start(update, context)
    
    async def paper_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.paper_trading.paper_stop(update, context)
    
    async def paper_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.paper_trading.paper_status(update, context)
    
    async def paper_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.paper_trading.paper_balance(update, context)
    
    async def paper_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.paper_trading.paper_trades(update, context)
    
    async def paper_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.paper_trading.paper_reset(update, context)
    
    async def paper_backtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.paper_trading.paper_backtest(update, context)
    
    async def paper_debug(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.paper_trading.paper_debug(update, context)
    
    async def paper_candidates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.paper_trading.paper_candidates(update, context)
    
    async def paper_force_buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.paper_trading.paper_force_buy(update, context)
    
    async def paper_force_sell(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.paper_trading.paper_force_sell(update, context)
    
    async def paper_force_short(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.paper_trading.paper_force_short(update, context)

    # -------------------------
    # Аналитические команды (делегируем в отдельный модуль)
    # -------------------------
    async def kelly_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.analytics.kelly_info(update, context)
    
    async def averaging_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.analytics.averaging_status(update, context)
    
    async def signal_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.analytics.signal_stats(update, context)
    
    async def signal_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.analytics.signal_analysis(update, context)
