import aiohttp
import asyncio
import json
from telegram import Update, __version__ as tg_version
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TELEGRAM_TOKEN, DEFAULT_SYMBOL, DEFAULT_INTERVAL
from data_provider import DataProvider
from signal_generator import SignalGenerator
from logger import logger
import math

class TelegramBot:
    def __init__(self, token: str, default_symbol: str = "BTCUSDT", default_interval: str = "1m"):
        if token is None:
            raise RuntimeError("TELEGRAM_TOKEN not set")
        self.token = token
        self.default_symbol = default_symbol
        self.default_interval = default_interval
        self.tracked_symbols: set[str] = set()
        self.json_file = "tracked_symbols.json"
        self._load_tracked_symbols()
        self.application = Application.builder().token(self.token).build()
        self._register_handlers()
        self.poll_interval = 60
        self.last_signals: dict[str, str] = {}
        self.chat_id: int | None = None
        self.volatility_window = 10
        self.volatility_threshold = 0.02
        self.last_volatility_alert: dict[str, float] = {}

    def _register_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("status", self.status))
        self.application.add_handler(CommandHandler("analyze", self.analyze))
        self.application.add_handler(CommandHandler("add", self.add_symbol))
        self.application.add_handler(CommandHandler("remove", self.remove_symbol))
        self.application.add_handler(CommandHandler("list", self.list_symbols))
        self.application.add_handler(CommandHandler("settings", self.settings))

    # -----------------------------
    # Работа с JSON
    # -----------------------------
    def _load_tracked_symbols(self):
        try:
            with open(self.json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.tracked_symbols = set(s.upper() for s in data.get("symbols", []))
                self.chat_id = data.get("chat_id")
                settings = data.get("settings", {})
                self.poll_interval = settings.get("poll_interval", 60)
                self.volatility_window = settings.get("volatility_window", 10)
                self.volatility_threshold = settings.get("volatility_threshold", 0.02)
                logger.info("Загружено %d пар, chat_id=%s, настройки=%s",
                            len(self.tracked_symbols), self.chat_id, settings)
        except FileNotFoundError:
            logger.info("JSON-файл %s не найден, создаём новый", self.json_file)
            self.tracked_symbols = set()
            self.chat_id = None
            self.poll_interval = 60
            self.volatility_window = 10
            self.volatility_threshold = 0.05
        except Exception as e:
            logger.error("Ошибка загрузки %s: %s", self.json_file, e)
            self.tracked_symbols = set()
            self.chat_id = None
            self.poll_interval = 60
            self.volatility_window = 10
            self.volatility_threshold = 0.05

    def _save_tracked_symbols(self):
        try:
            with open(self.json_file, "w", encoding="utf-8") as f:
                json.dump({
                    "chat_id": self.chat_id,
                    "symbols": sorted(self.tracked_symbols),
                    "settings": {
                        "poll_interval": self.poll_interval,
                        "volatility_window": self.volatility_window,
                        "volatility_threshold": self.volatility_threshold
                    }
                }, f, indent=2)
            logger.info("Сохранено %d пар и chat_id=%s, настройки=%s",
                        len(self.tracked_symbols), self.chat_id,
                        {"poll_interval": self.poll_interval,
                        "volatility_window": self.volatility_window,
                        "volatility_threshold": self.volatility_threshold})
        except Exception as e:
            logger.error("Ошибка сохранения %s: %s", self.json_file, e)

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
                return 'нет данных'
            return f'{val:.5f}' if isinstance(val, float) else str(val)

        header = f"<b>📊 Авто-анализ {html_escape(symbol)} ({html_escape(interval)})</b>\n"
        price_line = f"💰 Цена: <b>{fmt(result['price'])}</b>\n"
        signal_line = f"⚡ Сигнал: <b>{html_escape(result['signal'])}</b> {result['signal_emoji']}\n"
        reasons = '\n'.join([f"• {html_escape(r)}" for r in result["reasons"]])
        reasons_block = f"\n<b>📖 Обоснование:</b>\n{reasons}\n"

        ind = result
        indicators_block = (
            "<b>📈 Индикаторы:</b>\n"
            f"<code>EMA_short    : {fmt(ind['EMA_short'])}\n"
            f"EMA_long     : {fmt(ind['EMA_long'])}\n"
            f"RSI          : {fmt(ind['RSI'])}\n"
            f"MACD         : {fmt(ind['MACD'])}\n"
            f"MACD_signal  : {fmt(ind['MACD_signal'])}\n"
            f"MACD_hist    : {fmt(ind['MACD_hist'])}</code>\n"
        )

        footer = "<i>Простой индикаторный сигнал — не торговая рекомендация.</i>"

        return header + price_line + signal_line + reasons_block + indicators_block + footer

    def format_volatility(self, symbol, interval, change, close_price, window):
        direction = "↑" if change > 0 else "↓"
        impact = "Резкое движение цены, возможна волатильность в ближайшие минуты"
        text = (
            f"<b>⚠️ Волатильность {symbol} ({interval})</b>\n"
            f"За последние {window} свечей: {change*100:.2f}% {direction}\n"
            f"Текущая цена: <b>{close_price:.8f}</b>\n"
            f"<i>{impact}</i>"
        )
        return text

    # -------------------------
    # Основные команды
    # -------------------------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            "<b>👋 Привет! Я — бот для анализа криптовалют.</b>\n\n"
            "<b>Основные команды:</b>\n"
            "• /start — показать это сообщение\n"
            "• /help — помощь по командам\n"
            "• /status — статус бота и отслеживаемые пары\n"
            "• /analyze [SYMBOL] [INTERVAL] — анализ пары\n"
            "• /add SYMBOL — добавить пару в отслеживаемые\n"
            "• /remove SYMBOL — удалить пару из отслеживаемых\n"
            "• /list — показать все отслеживаемые пары"
        )
        await update.message.reply_text(text, parse_mode="HTML")
        
        if self.chat_id is None:
            self.chat_id = update.effective_chat.id
            self._save_tracked_symbols()

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            "<b>🆘 Помощь:</b>\n"
            "• /analyze SYMBOL INTERVAL — анализ указанной пары\n"
            "• /add SYMBOL — добавить пару в отслеживаемые\n"
            "• /remove SYMBOL — удалить пару из отслеживаемых\n"
            "• /list — показать все отслеживаемые пары\n\n"
            "<i>Если SYMBOL и INTERVAL не указаны, используются значения по умолчанию.</i>"
        )
        await update.message.reply_text(text, parse_mode="HTML")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        if self.tracked_symbols:
            text = "<b>📋 Отслеживаемые пары:</b>\n" + "\n".join([f"• {s}" for s in self.tracked_symbols])
        else:
            text = "📋 Список отслеживаемых пар пуст."
        await update.message.reply_text(text, parse_mode="HTML")


    # -------------------------
    # Анализ пары
    # -------------------------
    async def analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # -------------------------
    # Фоновая задача
    # -------------------------
    async def _background_task(self):
        while True:
            if not self.tracked_symbols or self.chat_id is None:
                await asyncio.sleep(self.poll_interval)
                continue

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

                        last = self.last_signals.get(symbol)
                        if last != signal:
                            text = self.format_analysis(result, symbol, self.default_interval)
                            await self.application.bot.send_message(chat_id=self.chat_id, text=text, parse_mode="HTML")
                            self.last_signals[symbol] = signal

                        # -------------------
                        # Волатильность
                        # -------------------
                        if len(df) >= self.volatility_window:
                            recent_df = df.iloc[-self.volatility_window:]
                            open_price = recent_df["open"].iloc[0]
                            close_price = recent_df["close"].iloc[-1]
                            change = (close_price - open_price) / open_price

                            last_alert_price = self.last_volatility_alert.get(symbol)
                            if abs(change) >= self.volatility_threshold and last_alert_price != close_price:
                                text = self.format_volatility(symbol, self.default_interval, change, close_price, self.volatility_window)
                                await self.application.bot.send_message(chat_id=self.chat_id, text=text, parse_mode="HTML")
                                self.last_volatility_alert[symbol] = close_price

                    except Exception as e:
                        logger.error("Ошибка фонового анализа %s: %s", symbol, e)
            await asyncio.sleep(self.poll_interval)

    # -------------------------
    # Настройки
    # -------------------------
    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if not args:
            text = (
                f"Текущие настройки:\n"
                f"Фоновый интервал (poll_interval): {self.poll_interval} сек\n"
                f"Окно волатильности (volatility_window): {self.volatility_window} свечей\n"
                f"Порог волатильности (volatility_threshold): {self.volatility_threshold*100:.2f}%"
            )
            await update.message.reply_text(text)
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
                f"Настройки обновлены:\n"
                f"poll_interval = {self.poll_interval} сек\n"
                f"volatility_window = {self.volatility_window} свечей\n"
                f"volatility_threshold = {self.volatility_threshold*100:.2f}%"
            )
        except Exception as e:
            await update.message.reply_text(f"Ошибка при обновлении настроек: {e}")

    # -------------------------
    # Запуск бота
    # -------------------------
    def run(self):
        logger.info("Запуск бота...")

        async def start_background(application):
            asyncio.create_task(self._background_task())

        self.application.post_init = start_background
        self.application.run_polling(stop_signals=None)
