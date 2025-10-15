"""
Модуль форматирования сообщений для Telegram бота
Содержит все функции форматирования текста и данных
"""

import math
import html
from config import MTF_TIMEFRAMES, ADX_WINDOW


class TelegramFormatters:
    """Класс для форматирования сообщений Telegram бота"""
    
    def format_price(self, price: float) -> str:
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

    def format_analysis(self, result, symbol, interval):
        """Форматирует результат анализа для отображения"""
        def html_escape(s):
            s = str(s)
            s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            return s

        def fmt_price(val):
            """Форматирование цены (2 знака для USDT пар)"""
            if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
                return 'н/д'
            if isinstance(val, float):
                # Для больших цен (>1000) показываем 2 знака, для маленьких (<1) - 8
                if val > 1000:
                    return f'{val:.2f}'
                elif val > 1:
                    return f'{val:.4f}'
                else:
                    return f'{val:.8f}'
            return str(val)
        
        def fmt_indicator(val):
            """Форматирование индикаторов (RSI, ADX) - 1 знак после запятой"""
            if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
                return 'н/д'
            if isinstance(val, (int, float)) and val == 0:
                return 'н/д'
            return f'{val:.1f}' if isinstance(val, float) else str(val)

        # Извлекаем данные
        signal = html_escape(result.get('signal', 'HOLD'))
        emoji = result.get('signal_emoji', '⚠️')
        price = result.get('price', 0)
        rsi = result.get('RSI', 0)
        adx = result.get('ADX', 0)
        
        # Определяем режим
        market_regime = result.get('market_regime', 'NEUTRAL')
        strategy_mode = result.get('strategy', 'UNKNOWN')
        
        # Проверяем MTF
        is_mtf = result.get('mtf_enabled', False)
        alignment = result.get('alignment_strength', 0)
        
        # Основная информация
        lines = [
            f"<b>{html_escape(symbol)}</b> {emoji} <b>{signal}</b>",
            f"💰 Цена: <code>${fmt_price(price)}</code> | 📊 RSI: <code>{fmt_indicator(rsi)}</code> | ADX: <code>{fmt_indicator(adx)}</code>"
        ]
        
        # Режим стратегии
        if market_regime != 'NEUTRAL':
            lines.append(f"🎯 Режим: <b>{market_regime}</b>")
        
        # MTF информация
        if is_mtf:
            lines.append(f"🔀 MTF: согласованность {alignment*100:.0f}%")
        
        # Первые 2 причины (самые важные)
        if result.get("reasons"):
            lines.append(f"\n📝 <i>{html_escape(result['reasons'][0])}</i>")
            if len(result["reasons"]) > 1:
                lines.append(f"<i>{html_escape(result['reasons'][1])}</i>")
        
        return "\n".join(lines)

    def format_volatility(self, symbol, interval, change, close_price, window):
        """Форматирует уведомление о волатильности"""
        direction = "↑" if change > 0 else "↓"
        return f"<b>{symbol}</b> ⚠️ {change*100:.2f}% {direction} | Цена: {close_price:.8f}"

    def _format_mtf_analysis(self, result: dict, symbol: str) -> str:
        """Форматирует вывод MTF анализа"""
        signal = result.get("signal", "HOLD")
        emoji = result.get("signal_emoji", "⚠️")
        price = result.get("price", 0)
        
        # Основная информация
        lines = [
            f"🔀 <b>Multi-Timeframe Анализ: {symbol}</b>",
            f"💰 Цена: <code>${price:.4f}</code>",
            f"",
            f"{emoji} <b>Итоговый сигнал: {signal}</b>",
            f""
        ]
        
        # Информация по каждому таймфрейму
        timeframe_signals = result.get("timeframe_signals", {})
        if timeframe_signals:
            lines.append("📊 <b>Сигналы по таймфреймам:</b>")
            for tf in MTF_TIMEFRAMES:
                tf_data = timeframe_signals.get(tf, {})
                tf_signal = tf_data.get("signal", "HOLD")
                tf_weight = tf_data.get("weight", 0)
                tf_rsi = tf_data.get("RSI", 0)
                tf_adx = tf_data.get("ADX", 0)
                
                # Emoji для сигнала
                if tf_signal == "BUY":
                    tf_emoji = "🟢"
                elif tf_signal == "SELL":
                    tf_emoji = "🔴"
                else:
                    tf_emoji = "⚠️"
                
                lines.append(
                    f"  {tf_emoji} <b>{tf}</b>: {tf_signal} "
                    f"(вес: {tf_weight:.2f}, RSI: {tf_rsi:.1f}, ADX: {tf_adx:.1f})"
                )
            lines.append("")
        
        # Согласованность
        alignment_strength = result.get("alignment_strength", 0)
        buy_count = result.get("buy_count", 0)
        sell_count = result.get("sell_count", 0)
        hold_count = result.get("hold_count", 0)
        
        lines.append(f"🎯 <b>Согласованность:</b> {alignment_strength*100:.0f}%")
        lines.append(f"   BUY: {buy_count} | SELL: {sell_count} | HOLD: {hold_count}")
        lines.append("")
        
        # Weighted scores
        buy_score = result.get("buy_score", 0)
        sell_score = result.get("sell_score", 0)
        hold_score = result.get("hold_score", 0)
        
        lines.append(f"⚖️ <b>Взвешенные оценки:</b>")
        lines.append(f"   BUY: {buy_score:.2f} | SELL: {sell_score:.2f} | HOLD: {hold_score:.2f}")
        lines.append("")
        
        # Причины
        reasons = result.get("reasons", [])
        if reasons:
            lines.append("<b>📝 Причины:</b>")
            for reason in reasons[:10]:  # Показываем первые 10
                # Убираем emoji из причин для чистоты
                clean_reason = reason.replace("📊", "").replace("✅", "").replace("⚠️", "").strip()
                lines.append(f"  • {clean_reason}")
        
        return "\n".join(lines)

    def format_paper_trade_message(self, trade_type: str, symbol: str, price: float, 
                                 profit: float = 0, profit_percent: float = 0, 
                                 invest_amount: float = 0, balance_after: float = 0,
                                 **kwargs) -> str:
        """Форматирует сообщение о сделке Paper Trading"""
        if trade_type == "STOP-LOSS":
            return (
                f"🛑 <b>STOP-LOSS</b> {symbol}\n"
                f"  Цена: {self.format_price(price)}\n"
                f"  Убыток: ${profit:+.2f} ({profit_percent:+.2f}%)"
            )
        elif trade_type == "PARTIAL-TP":
            return (
                f"💎 <b>PARTIAL TP</b> {symbol}\n"
                f"  Цена: {self.format_price(price)}\n"
                f"  Прибыль: ${profit:+.2f} ({profit_percent:+.2f}%)\n"
                f"  Закрыто: 50%, активен trailing stop"
            )
        elif trade_type == "TRAILING-STOP":
            return (
                f"🔻 <b>TRAILING STOP</b> {symbol}\n"
                f"  Цена: {self.format_price(price)}\n"
                f"  Прибыль: ${profit:+.2f} ({profit_percent:+.2f}%)"
            )
        elif trade_type == "BUY":
            return (
                f"🟢 <b>КУПИЛ</b> {symbol}\n"
                f"  Цена: {self.format_price(price)}\n"
                f"  Вложено: ${invest_amount:.2f}\n"
                f"  Баланс: ${balance_after:.2f}"
            )
        elif trade_type == "SELL":
            profit_emoji = "📈" if profit > 0 else "📉"
            return (
                f"🔴 <b>ПРОДАЛ</b> {symbol}\n"
                f"  Цена: {self.format_price(price)}\n"
                f"  {profit_emoji} Прибыль: ${profit:+.2f} ({profit_percent:+.2f}%)\n"
                f"  Баланс: ${balance_after:.2f}"
            )
        else:
            return f"📊 <b>{trade_type}</b> {symbol} @ {self.format_price(price)}"

    def format_debug_analysis(self, symbol: str, result: dict, df) -> str:
        """Форматирует отладочную информацию по сигналу"""
        signal = result["signal"]
        price = result["price"]
        bullish = result.get("bullish_votes", 0)
        bearish = result.get("bearish_votes", 0)
        
        # Собираем информацию об индикаторах (из result или из DataFrame)
        last = df.iloc[-1]
        
        # Используем значения из result, если доступны, иначе из DataFrame
        rsi = float(result.get("RSI", last.get("RSI", 50)))
        adx = float(result.get("ADX", last.get(f"ADX_{ADX_WINDOW}", 0)))
        ema_s = float(result.get("EMA_short", last.get("EMA_short", 0)))
        ema_l = float(result.get("EMA_long", last.get("EMA_long", 0)))
        sma_20 = float(last.get("SMA_20", 0))
        sma_50 = float(last.get("SMA_50", 0))
        macd = float(result.get("MACD", last.get("MACD", 0)))
        macd_signal = float(result.get("MACD_signal", last.get("MACD_signal", 0)))
        macd_hist = float(result.get("MACD_hist", last.get("MACD_hist", 0)))
        
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
            f"💰 Цена: {self.format_price(price)}\n\n"
            f"<b>📊 Голосование:</b>\n"
            f"  Бычьи: {bullish} | Медвежьи: {bearish}\n"
            f"  Разница: {vote_diff} (порог: 5)\n\n"
            f"<b>📈 Индикаторы:</b>\n"
            f"  EMA: {ema_s:.2f} vs {ema_l:.2f} {'✅' if ema_s > ema_l else '❌'}\n"
            f"  SMA: {sma_20:.2f} vs {sma_50:.2f} {'✅' if sma_20 > sma_50 else '❌'}\n"
            f"  RSI: {rsi:.1f} (35-70 для BUY) {'✅' if buy_rsi_ok else '❌'}\n"
            f"  MACD: {macd:.4f} vs {macd_signal:.4f} {'✅' if macd > macd_signal else '❌'}\n"
            f"  MACD hist: {macd_hist:.4f} {'✅' if macd_hist > 0 else '❌'}\n"
            f"  ADX: {adx:.1f} (&gt;25 для сигнала) {'✅' if strong_trend else '❌'}\n\n"
            f"<b>🎯 Фильтры BUY:</b>\n"
            f"  {'✅' if vote_diff >= 5 else '❌'} Голосов &gt;= 5: {vote_diff}/5\n"
            f"  {'✅' if strong_trend else '❌'} Сильный тренд: ADX {adx:.1f}/25\n"
            f"  {'✅' if buy_trend_ok else '❌'} Тренд вверх: EMA+SMA\n"
            f"  {'✅' if buy_rsi_ok else '❌'} RSI в зоне: {rsi:.1f}\n"
            f"  {'✅' if macd_buy_ok else '❌'} MACD подтверждает\n\n"
        )
        
        # Добавляем причины
        text += "<b>📝 Причины:</b>\n"
        for i, reason in enumerate(result["reasons"][-5:], 1):
            escaped_reason = html.escape(reason)
            text += f"{i}. {escaped_reason[:80]}...\n" if len(escaped_reason) > 80 else f"{i}. {escaped_reason}\n"
        
        return text

    def format_candidates_list(self, candidates: list) -> str:
        """Форматирует список кандидатов на сигнал"""
        if not candidates:
            return "⚠️ Нет кандидатов близких к сигналу.\n\nПопробуйте позже или добавьте больше пар."
        
        # Сортируем по количеству голосов (больше = ближе к сигналу)
        candidates.sort(key=lambda x: x['votes'], reverse=True)
        
        text = f"<b>🎯 Кандидаты на сигнал ({len(candidates)}):</b>\n\n"
        
        for c in candidates[:10]:  # Топ 10
            emoji = "🟢" if c['direction'] == "BUY" else "🔴"
            text += (
                f"{emoji} <b>{c['symbol']}</b> → {c['direction']}\n"
                f"  Голосов: {c['votes']}/5 | ADX: {c['adx']:.1f}/25\n"
                f"  RSI: {c['rsi']:.1f} | Цена: {self.format_price(c['price'])}\n\n"
            )
        
        text += "<i>Эти пары близки к генерации сигнала</i>"
        return text
