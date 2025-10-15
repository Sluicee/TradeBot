"""
Модуль Paper Trading команд для Telegram бота
Содержит все команды связанные с виртуальной торговлей
"""

import aiohttp
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import (
    INITIAL_BALANCE, STRATEGY_MODE, USE_MULTI_TIMEFRAME, ADX_WINDOW,
    COMMISSION_RATE, STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT, 
    PARTIAL_CLOSE_PERCENT, TRAILING_STOP_PERCENT
)
from data_provider import DataProvider
from signal_generator import SignalGenerator
from logger import logger
from telegram_formatters import TelegramFormatters


class TelegramPaperTrading:
    """Класс для обработки Paper Trading команд"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.formatters = TelegramFormatters()
    
    def _is_authorized(self, update: Update) -> bool:
        """Проверяет, что пользователь является владельцем бота"""
        if self.bot.owner_chat_id is None:
            return True
        return update.effective_chat.id == self.bot.owner_chat_id

    async def paper_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запускает paper trading"""
        if not self._is_authorized(update):
            await update.message.reply_text("🚫 Доступ запрещен")
            return
        
        if self.bot.paper_trader.is_running:
            await update.message.reply_text("⚠️ Paper Trading уже запущен!")
            return
        
        # Опционально можно задать стартовый баланс
        if context.args and len(context.args) > 0:
            try:
                initial_balance = float(context.args[0])
                self.bot.paper_trader = self.bot.paper_trader.__class__(initial_balance=initial_balance)
            except ValueError:
                await update.message.reply_text("⚠️ Неверный формат баланса. Используется значение по умолчанию $100")
        
        self.bot.paper_trader.start()
        self.bot.paper_trader.save_state()
        
        text = (
            f"<b>🚀 Paper Trading запущен!</b>\n\n"
            f"💰 Стартовый баланс: ${self.bot.paper_trader.initial_balance:.2f}\n"
            f"📊 Стратегия: как в бэктестинге\n"
            f"• Стоп-лосс: 5%\n"
            f"• Тейк-профит: 10% (частичное 50%)\n"
            f"• Trailing stop: 2%\n"
            f"• Макс. позиций: 3\n\n"
            f"Бот будет автоматически торговать по сигналам.\n"
            f"Используйте /paper_status для проверки состояния."
        )
        await update.message.reply_text(text, parse_mode="HTML")
        
        if self.bot.chat_id is None:
            self.bot.chat_id = update.effective_chat.id
            self.bot._save_tracked_symbols()

    async def paper_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Останавливает paper trading и закрывает все позиции"""
        if not self._is_authorized(update):
            await update.message.reply_text("🚫 Доступ запрещен")
            return
        
        if not self.bot.paper_trader.is_running:
            await update.message.reply_text("⚠️ Paper Trading не запущен.")
            return
        
        # Закрываем все открытые позиции по текущим ценам
        if self.bot.paper_trader.positions:
            msg = await update.message.reply_text("⏳ Закрываю все позиции...")
            
            closed_positions = []
            async with aiohttp.ClientSession() as session:
                provider = DataProvider(session)
                for symbol in list(self.bot.paper_trader.positions.keys()):
                    try:
                        klines = await provider.fetch_klines(symbol=symbol, interval=self.bot.default_interval, limit=1)
                        df = provider.klines_to_dataframe(klines)
                        if not df.empty:
                            current_price = float(df['close'].iloc[-1])
                            trade_info = self.bot.paper_trader.close_position(symbol, current_price, "MANUAL-CLOSE")
                            if trade_info:
                                closed_positions.append(f"• {symbol}: {trade_info['profit']:+.2f} USD ({trade_info['profit_percent']:+.2f}%)")
                    except Exception as e:
                        logger.error(f"Ошибка закрытия позиции {symbol}: {e}")
            
            positions_text = "\n".join(closed_positions) if closed_positions else "Нет позиций для закрытия"
        else:
            positions_text = "Нет открытых позиций"
        
        self.bot.paper_trader.stop()
        self.bot.paper_trader.save_state()
        
        status = self.bot.paper_trader.get_status()
        text = (
            f"<b>⏸ Paper Trading остановлен</b>\n\n"
            f"Закрыто позиций:\n{positions_text}\n\n"
            f"💰 Итоговый баланс: ${status['total_balance']:.2f}\n"
            f"📈 Прибыль: {status['total_profit']:+.2f} USD ({status['total_profit_percent']:+.2f}%)"
        )
        
        if self.bot.paper_trader.positions:
            await msg.edit_text(text, parse_mode="HTML")
        else:
            await update.message.reply_text(text, parse_mode="HTML")

    async def paper_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает текущий статус paper trading"""
        if not self._is_authorized(update):
            await update.message.reply_text("🚫 Доступ запрещен")
            return
        
        status = self.bot.paper_trader.get_status()
        
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
                        current_prices[symbol] = pos['entry_price']
        
        # Пересчитываем PnL с текущими ценами
        total_pnl = 0.0
        positions_text = ""
        for pos in status['positions']:
            symbol = pos['symbol']
            current_price = current_prices.get(symbol, pos['entry_price'])
            position_obj = self.bot.paper_trader.positions[symbol]
            pnl_info = position_obj.get_pnl(current_price)
            total_pnl += pnl_info['pnl']
            
            emoji = "🟢" if pnl_info['pnl'] > 0 else "🔴" if pnl_info['pnl'] < 0 else "⚪"
            partial_mark = " [частично]" if pos['partial_closed'] else ""
            
            positions_text += (
                f"  {emoji} <b>{symbol}</b>{partial_mark}\n"
                f"    Вход: {self.formatters.format_price(pos['entry_price'])} → Сейчас: {self.formatters.format_price(current_price)}\n"
                f"    PnL: ${pnl_info['pnl']:+.2f} ({pnl_info['pnl_percent']:+.2f}%)\n"
                f"    SL: {self.formatters.format_price(pos['stop_loss'])} | TP: {self.formatters.format_price(pos['take_profit'])}\n\n"
            )
        
        total_balance = status['current_balance'] + sum(
            self.bot.paper_trader.positions[pos['symbol']].get_pnl(current_prices.get(pos['symbol'], pos['entry_price']))['current_value']
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
            f"📊 <b>Позиции ({len(status['positions'])}/{status.get('max_positions', 3)}):</b>\n"
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
        
        status = self.bot.paper_trader.get_status()
        
        # Получаем текущие цены
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
                        current_prices[symbol] = pos['entry_price']
        
        # Рассчитываем детали
        total_invested = sum(
            self.bot.paper_trader.positions[pos['symbol']].invest_amount
            for pos in status['positions']
        )
        
        total_current_value = sum(
            self.bot.paper_trader.positions[pos['symbol']].get_pnl(current_prices.get(pos['symbol'], pos['entry_price']))['current_value']
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
        
        trades = self.bot.paper_trader.trades_history[-limit:]
        
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
                details = f"  Купил {trade['amount']:.6f} @ {self.formatters.format_price(price)}\n  Вложено: ${trade['invest_amount']:.2f}"
            elif trade_type in ["SELL", "MANUAL-CLOSE"]:
                emoji = "🔴"
                profit_emoji = "📈" if trade['profit'] >= 0 else "📉"
                details = f"  Продал {trade['amount']:.6f} @ {self.formatters.format_price(price)}\n  {profit_emoji} Прибыль: ${trade['profit']:+.2f} ({trade['profit_percent']:+.2f}%)"
            elif trade_type == "STOP-LOSS":
                emoji = "🛑"
                details = f"  Стоп-лосс {trade['amount']:.6f} @ {self.formatters.format_price(price)}\n  📉 Убыток: ${trade['profit']:+.2f} ({trade['profit_percent']:+.2f}%)"
            elif trade_type == "PARTIAL-TP":
                emoji = "💎"
                details = f"  Частичный тейк {trade['amount']:.6f} @ {self.formatters.format_price(price)}\n  📈 Прибыль: ${trade['profit']:+.2f} ({trade['profit_percent']:+.2f}%)"
            elif trade_type == "TRAILING-STOP":
                emoji = "🔻"
                details = f"  Trailing stop {trade['amount']:.6f} @ {self.formatters.format_price(price)}\n  📊 Прибыль: ${trade['profit']:+.2f} ({trade['profit_percent']:+.2f}%)"
            else:
                emoji = "⚪"
                details = f"  {trade.get('amount', 0):.6f} @ {self.formatters.format_price(price)}"
            
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
        
        if self.bot.paper_trader.is_running:
            await update.message.reply_text("⚠️ Сначала остановите Paper Trading командой /paper_stop")
            return
        
        old_balance = self.bot.paper_trader.balance
        old_trades = len(self.bot.paper_trader.trades_history)
        
        self.bot.paper_trader.reset()
        self.bot.paper_trader.save_state()
        
        text = (
            f"<b>🔄 Paper Trading сброшен</b>\n\n"
            f"Баланс сброшен с ${old_balance:.2f} → ${self.bot.paper_trader.initial_balance:.2f}\n"
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
        
        if not self.bot.tracked_symbols:
            await update.message.reply_text("⚠️ Нет отслеживаемых символов. Используйте /add SYMBOL")
            return
        
        msg = await update.message.reply_text(f"⏳ Запускаю симуляцию за {period_hours}ч на {len(self.bot.tracked_symbols)} парах...")
        
        try:
            # Запускаем бэктест
            symbols = list(self.bot.tracked_symbols)
            results = []
            
            async with aiohttp.ClientSession() as session:
                provider = DataProvider(session)
                
                for i, symbol in enumerate(symbols):
                    await msg.edit_text(f"⏳ Симуляция {i+1}/{len(symbols)}: {symbol}...")
                    
                    # Получаем данные
                    candles_per_hour = int(60 / int(self.bot.default_interval.replace('m',''))) if 'm' in self.bot.default_interval else 1
                    limit = period_hours * candles_per_hour
                    
                    df = await provider.fetch_klines(symbol=symbol, interval=self.bot.default_interval, limit=limit)
                    
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
                        res = self.bot._generate_signal_with_strategy(gen)
                        signals.append(res)
                    
                    # Симулируем торговлю
                    from position_sizing import get_position_size_percent
                    
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
                text = f"<b>📊 Симуляция за {period_hours}ч ({self.bot.default_interval})</b>\n\n"
                
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
                klines = await provider.fetch_klines(symbol=symbol, interval=self.bot.default_interval, limit=500)
                df = provider.klines_to_dataframe(klines)
                
                if df.empty:
                    await msg.edit_text("⚠️ Нет данных")
                    return
                
                generator = SignalGenerator(df)
                generator.compute_indicators()
                result = self.bot._generate_signal_with_strategy(generator, symbol=symbol)
                
            text = self.formatters.format_debug_analysis(symbol, result, df)
            await msg.edit_text(text, parse_mode="HTML")
                
        except Exception as e:
            logger.error(f"Ошибка debug для {symbol}: {e}")
            await msg.edit_text(f"❌ Ошибка: {e}")

    async def paper_candidates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает пары близкие к сигналу"""
        if not self._is_authorized(update):
            await update.message.reply_text("🚫 Доступ запрещен")
            return
        
        if not self.bot.tracked_symbols:
            await update.message.reply_text("⚠️ Нет отслеживаемых символов")
            return
        
        msg = await update.message.reply_text(f"🔍 Ищу кандидатов среди {len(self.bot.tracked_symbols)} пар...")
        
        candidates = []
        
        try:
            async with aiohttp.ClientSession() as session:
                provider = DataProvider(session)
                
                for symbol in self.bot.tracked_symbols:
                    try:
                        klines = await provider.fetch_klines(symbol=symbol, interval=self.bot.default_interval, limit=500)
                        df = provider.klines_to_dataframe(klines)
                        
                        if df.empty:
                            continue
                        
                        generator = SignalGenerator(df)
                        generator.compute_indicators()
                        result = self.bot._generate_signal_with_strategy(generator, symbol=symbol)
                        
                        signal = result["signal"]
                        price = result["price"]
                        bullish = result.get("bullish_votes", 0)
                        bearish = result.get("bearish_votes", 0)
                        
                        # Берем индикаторы из result или DataFrame
                        last = df.iloc[-1]
                        adx = float(result.get("ADX", last.get(f"ADX_{ADX_WINDOW}", 0)))
                        rsi = float(result.get("RSI", last.get("RSI", 50)))
                        
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
                
                text = self.formatters.format_candidates_list(candidates)
                await msg.edit_text(text, parse_mode="HTML")
                
        except Exception as e:
            logger.error(f"Ошибка поиска кандидатов: {e}")
            await msg.edit_text(f"❌ Ошибка: {e}")

    async def paper_force_buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Принудительно открывает позицию для тестирования"""
        if not self._is_authorized(update):
            await update.message.reply_text("🚫 Доступ запрещен")
            return
        
        if not self.bot.paper_trader.is_running:
            await update.message.reply_text("⚠️ Paper Trading не запущен. Используйте /paper_start")
            return
        
        if not context.args:
            await update.message.reply_text("⚠️ Использование: /paper_force_buy SYMBOL")
            return
        
        symbol = context.args[0].upper()
        
        if symbol in self.bot.paper_trader.positions:
            await update.message.reply_text(f"⚠️ Позиция по {symbol} уже открыта")
            return
        
        if not self.bot.paper_trader.can_open_position(symbol):
            await update.message.reply_text(f"⚠️ Невозможно открыть позицию (лимит или нет баланса)")
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                provider = DataProvider(session)
                klines = await provider.fetch_klines(symbol=symbol, interval=self.bot.default_interval, limit=500)
                df = provider.klines_to_dataframe(klines)
                
                if df.empty:
                    await update.message.reply_text("⚠️ Нет данных для получения цены")
                    return
                
            # Генерируем сигнал чтобы получить ATR
            generator = SignalGenerator(df)
            generator.compute_indicators()
            result = self.bot._generate_signal_with_strategy(generator, symbol=symbol)
            
            price = float(df['close'].iloc[-1])
            signal_strength = 5  # Средняя сила для теста
            atr = result.get("ATR", 0.0)
            
            trade_info = self.bot.paper_trader.open_position(symbol, price, signal_strength, atr)
            
            if trade_info:
                self.bot.paper_trader.save_state()
                
                text = (
                    f"<b>🟢 ПРИНУДИТЕЛЬНАЯ ПОКУПКА</b>\n\n"
                    f"Символ: {symbol}\n"
                    f"Цена: {self.formatters.format_price(price)}\n"
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
