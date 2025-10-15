"""
Модуль аналитических команд для Telegram бота
Содержит команды для анализа Kelly Criterion, докупаний и статистики сигналов
"""

from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import (
    USE_KELLY_CRITERION, KELLY_FRACTION, MIN_TRADES_FOR_KELLY, KELLY_LOOKBACK_WINDOW,
    ENABLE_AVERAGING, MAX_AVERAGING_ATTEMPTS, AVERAGING_PRICE_DROP_PERCENT,
    AVERAGING_TIME_THRESHOLD_HOURS, MAX_TOTAL_RISK_MULTIPLIER,
    ENABLE_PYRAMID_UP, PYRAMID_ADX_THRESHOLD
)
from logger import logger
from telegram_formatters import TelegramFormatters


class TelegramAnalytics:
    """Класс для обработки аналитических команд"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.formatters = TelegramFormatters()
    
    def _is_authorized(self, update: Update) -> bool:
        """Проверяет, что пользователь является владельцем бота"""
        if self.bot.owner_chat_id is None:
            return True
        return update.effective_chat.id == self.bot.owner_chat_id

    async def kelly_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Информация о Kelly Criterion"""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return
        
        message = "📊 <b>Kelly Criterion</b>\n\n"
        message += f"Статус: {'✅ Включен' if USE_KELLY_CRITERION else '❌ Выключен'}\n"
        message += f"Kelly Fraction: {KELLY_FRACTION:.0%} (консервативный)\n"
        message += f"Min Trades: {MIN_TRADES_FOR_KELLY}\n"
        message += f"Lookback Window: {KELLY_LOOKBACK_WINDOW} сделок\n\n"
        
        # Рассчитываем текущий Kelly
        closed_trades = [
            t for t in self.bot.paper_trader.trades_history 
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
        
        message = "🔄 <b>Умное докупание (Averaging)</b>\n\n"
        message += f"Статус: {'✅ Включено' if ENABLE_AVERAGING else '❌ Выключено'}\n"
        message += f"Max Attempts: {MAX_AVERAGING_ATTEMPTS}\n"
        message += f"Price Drop: {AVERAGING_PRICE_DROP_PERCENT:.1%}\n"
        message += f"Time Threshold: {AVERAGING_TIME_THRESHOLD_HOURS}ч\n"
        message += f"Max Risk Multiplier: {MAX_TOTAL_RISK_MULTIPLIER}x\n"
        message += f"Pyramid Up: {'✅' if ENABLE_PYRAMID_UP else '❌'} (ADX > {PYRAMID_ADX_THRESHOLD})\n\n"
        
        # Статус по позициям
        if self.bot.paper_trader.positions:
            message += "<b>Текущие позиции:</b>\n\n"
            
            for symbol, position in self.bot.paper_trader.positions.items():
                averaging_count = position.averaging_count
                avg_entry = position.average_entry_price
                entry_price = position.entry_price
                mode = "PYRAMID" if position.pyramid_mode else "AVERAGE"
                
                message += f"<b>{symbol}</b>\n"
                message += f"• Вход: {self.formatters.format_price(entry_price)}\n"
                
                if averaging_count > 0:
                    message += f"• Средняя: {self.formatters.format_price(avg_entry)}\n"
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
        avg_trades = [t for t in self.bot.paper_trader.trades_history if "AVERAGE" in t.get("type", "")]
        
        if avg_trades:
            message += f"\n<b>Статистика:</b>\n"
            message += f"• Всего докупаний: {len(avg_trades)}\n"
            
            pyramid_trades = [t for t in avg_trades if "PYRAMID" in t.get("type", "")]
            average_trades = [t for t in avg_trades if "AVERAGE-AVERAGE" in t.get("type", "")]
            
            message += f"• Pyramid Up: {len(pyramid_trades)}\n"
            message += f"• Average Down: {len(average_trades)}\n"
        
        await update.message.reply_text(message, parse_mode="HTML")
    
    async def signal_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """📊 Статистика сигналов"""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return
        
        try:
            from signal_diagnostics import diagnostics
            
            total = diagnostics.buy_signals_count + diagnostics.hold_signals_count + diagnostics.sell_signals_count
            
            if total == 0:
                await update.message.reply_text("⚠️ Нет данных по сигналам. Бот ещё не запущен или не было проверок.")
                return
            
            message = "📊 <b>СТАТИСТИКА СИГНАЛОВ v5.5</b>\n\n"
            message += f"<b>Всего сигналов:</b> {total}\n"
            message += f"• BUY:  {diagnostics.buy_signals_count} ({diagnostics.buy_signals_count/total*100:.1f}%)\n"
            message += f"• HOLD: {diagnostics.hold_signals_count} ({diagnostics.hold_signals_count/total*100:.1f}%)\n"
            message += f"• SELL: {diagnostics.sell_signals_count} ({diagnostics.sell_signals_count/total*100:.1f}%)\n\n"
            
            if diagnostics.last_buy_time:
                message += f"<b>Последний BUY:</b> {diagnostics.last_buy_time}\n\n"
            else:
                message += "⚠️ <b>Ни одного BUY сигнала!</b>\n\n"
            
            if diagnostics.blocked_reasons:
                message += "<b>🚫 Причины блокировки BUY:</b>\n"
                for reason, count in sorted(diagnostics.blocked_reasons.items(), key=lambda x: x[1], reverse=True)[:5]:
                    message += f"• {reason}: {count}x\n"
                message += "\n"
            
            # Последние 5 сигналов
            if len(diagnostics.signal_history) > 0:
                recent = diagnostics.signal_history[-5:]
                message += "<b>📋 Последние 5 сигналов:</b>\n"
                for sig in recent:
                    symbol = sig["symbol"]
                    signal = sig["signal"]
                    delta = sig["votes_delta"]
                    mode = sig["mode"]
                    emoji = "✅" if sig["can_buy"] else "❌"
                    message += f"{emoji} {symbol}: {signal} (Δ{delta:+d}, {mode})\n"
            
            message += "\n💡 <i>Используйте /signal_analysis для детального анализа</i>"
            
            await update.message.reply_text(message, parse_mode="HTML")
            
        except ImportError:
            await update.message.reply_text("⚠️ Модуль signal_diagnostics не найден. Установите его для работы статистики.")
        except Exception as e:
            logger.error(f"Ошибка получения статистики сигналов: {e}")
            await update.message.reply_text(f"❌ Ошибка получения статистики: {e}")
    
    async def signal_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🔍 Детальный анализ сигналов"""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return
        
        try:
            from signal_diagnostics import diagnostics
            
            if not diagnostics.signal_history:
                await update.message.reply_text("⚠️ Нет данных для анализа. Подождите несколько циклов проверки.")
                return
            
            deltas = [s["votes_delta"] for s in diagnostics.signal_history]
            
            message = "🔍 <b>АНАЛИЗ РАСПРЕДЕЛЕНИЯ ГОЛОСОВ</b>\n\n"
            message += f"<b>Статистика:</b>\n"
            message += f"• Min delta: {min(deltas):+d}\n"
            message += f"• Max delta: {max(deltas):+d}\n"
            message += f"• Avg delta: {sum(deltas)/len(deltas):+.1f}\n"
            message += f"• Median: {sorted(deltas)[len(deltas)//2]:+d}\n\n"
            
            # Распределение (HYBRID v5.5 использует адаптивную логику, примерный порог ~5)
            min_buy_threshold = 5
            ranges = [
                (float('-inf'), -5, "Сильно bearish (&lt;-5)"),
                (-5, -3, "Средне bearish (-5..-3)"),
                (-3, 0, "Слабо bearish (-3..0)"),
                (0, 3, "Слабо bullish (0..3)"),
                (3, min_buy_threshold, f"Средне bullish (3..{min_buy_threshold-1})"),
                (min_buy_threshold, float('inf'), f"🎯 BUY (&gt;={min_buy_threshold})")
            ]
            
            message += "<b>Распределение:</b>\n"
            for low, high, label in ranges:
                count = len([d for d in deltas if low <= d < high])
                pct = count / len(deltas) * 100
                if count > 0:
                    message += f"• {label}: {count} ({pct:.1f}%)\n"
            
            # Рекомендации
            max_delta = max(deltas)
            avg_delta = sum(deltas)/len(deltas)
            buy_ready = len([d for d in deltas if d >= min_buy_threshold])
            
            message += "\n<b>💡 РЕКОМЕНДАЦИИ:</b>\n"
            
            if max_delta < min_buy_threshold:
                message += f"⚠️ Max delta ({max_delta:+d}) &lt; примерный порог BUY (~{min_buy_threshold})\n"
                message += f"→ Рынок слабый, дождаться более сильных сигналов\n"
            
            if avg_delta < 0:
                message += f"⚠️ Avg delta отрицательный ({avg_delta:+.1f})\n"
                message += "→ Рынок медвежий, стратегия работает корректно\n"
            
            if buy_ready == 0:
                message += "⚠️ Ни один сигнал не достиг порога BUY!\n"
                message += "→ Проверить фильтры или смягчить условия\n"
            else:
                message += f"✅ {buy_ready} сигналов готовы к BUY ({buy_ready/len(deltas)*100:.1f}%)\n"
            
            await update.message.reply_text(message, parse_mode="HTML")
            
        except ImportError:
            await update.message.reply_text("⚠️ Модуль signal_diagnostics не найден. Установите его для работы анализа.")
        except Exception as e:
            logger.error(f"Ошибка анализа сигналов: {e}")
            await update.message.reply_text(f"❌ Ошибка анализа: {e}")
