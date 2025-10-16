#!/usr/bin/env python3
"""
🔴 БЭКТЕСТ SHORT МЕХАНИКИ С PAPER TRADER

Проверяет работу SHORT v2.1 на реальных данных с использованием paper_trader.py.
Анализирует торговые результаты, статистику и эффективность.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import json
import sys
import os
from typing import Dict, Any, List

# Добавляем путь к модулям
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from signal_generator import SignalGenerator
from paper_trader import PaperTrader
from config import *
from logger import logger

class ShortPaperBacktest:
    """Бэктест SHORT механики с Paper Trader"""
    
    def __init__(self, symbol: str = "BTCUSDT", interval: str = "1h", hours: int = 24):
        self.symbol = symbol
        self.interval = interval
        self.hours = hours
        self.paper_trader = PaperTrader(initial_balance=10000.0)  # $10,000 начальный баланс
        self.results = []
        self.short_signals = []
        self.total_signals = 0
        self.short_activated = 0
        
    def get_historical_data(self) -> pd.DataFrame:
        """Получает исторические данные"""
        try:
            # Получаем данные с Binance (последние 1000 свечей)
            url = "https://api.binance.com/api/v3/klines"
            params = {
                'symbol': self.symbol,
                'interval': self.interval,
                'limit': 1000
            }
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                raise ValueError("Нет данных от API")
            
            # Конвертируем в DataFrame
            df = pd.DataFrame(data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            # Конвертируем типы данных
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Устанавливаем индекс времени
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Сортируем по времени
            df.sort_index(inplace=True)
            
            # Фильтруем последние N часов
            if self.hours < 24:
                cutoff_time = df.index[-1] - timedelta(hours=self.hours)
                df = df[df.index >= cutoff_time]
            
            logger.info(f"Получено {len(df)} свечей для {self.symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Ошибка получения данных: {e}")
            return pd.DataFrame()
    
    def run_backtest(self) -> Dict[str, Any]:
        """Запускает бэктест SHORT механики с Paper Trader"""
        logger.info("ЗАПУСК БЭКТЕСТА SHORT МЕХАНИКИ С PAPER TRADER")
        logger.info("=" * 60)
        
        # Получаем данные
        df = self.get_historical_data()
        if df.empty:
            return {"error": "Не удалось получить данные"}
        
        # Запускаем Paper Trader
        self.paper_trader.start()
        
        # Создаем генератор сигналов
        generator = SignalGenerator(df)
        
        # Вычисляем индикаторы
        try:
            generator.compute_indicators()
        except Exception as e:
            logger.error(f"Ошибка вычисления индикаторов: {e}")
            return {"error": f"Ошибка индикаторов: {e}"}
        
        # Проходим по каждой свече
        for i in range(50, len(df)):  # Начинаем с 50-й свечи для стабильности индикаторов
            current_df = df.iloc[:i+1].copy()
            current_price = float(current_df.iloc[-1]['close'])
            timestamp = current_df.index[-1]
            
            try:
                # Создаем новый генератор для текущего среза
                current_generator = SignalGenerator(current_df)
                current_generator.compute_indicators()
                
                # Генерируем сигнал
                signal_result = current_generator.generate_signal()
                
                # Анализируем результат
                signal = signal_result.get("signal", "HOLD")
                price = signal_result.get("price", current_price)
                
                self.total_signals += 1
                
                # Обрабатываем сигналы через Paper Trader
                if signal == "BUY":
                    # Открываем LONG позицию
                    if self.paper_trader.can_open_position(self.symbol):
                        trade_info = self.paper_trader.open_position(
                            symbol=self.symbol,
                            price=price,
                            signal_strength=signal_result.get("signal_strength", 1),
                            atr=signal_result.get("atr", 0),
                            position_type="LONG",
                            reasons=signal_result.get("reasons", []),
                            active_mode=signal_result.get("active_mode", "UNKNOWN"),
                            bullish_votes=signal_result.get("bullish_votes", 0),
                            bearish_votes=signal_result.get("bearish_votes", 0)
                        )
                        if trade_info:
                            logger.info(f"LONG позиция открыта: {timestamp} @ ${price:.2f}")
                
                elif signal == "SHORT":
                    # Открываем SHORT позицию
                    if self.paper_trader.can_open_position(self.symbol):
                        trade_info = self.paper_trader.open_position(
                            symbol=self.symbol,
                            price=price,
                            signal_strength=signal_result.get("signal_strength", 1),
                            atr=signal_result.get("atr", 0),
                            position_type="SHORT",
                            reasons=signal_result.get("reasons", []),
                            active_mode=signal_result.get("active_mode", "UNKNOWN"),
                            bullish_votes=signal_result.get("bullish_votes", 0),
                            bearish_votes=signal_result.get("bearish_votes", 0)
                        )
                        if trade_info:
                            self.short_activated += 1
                            self.short_signals.append({
                                'timestamp': timestamp,
                                'price': price,
                                'signal': signal,
                                'short_score': signal_result.get("short_score", 0),
                                'short_conditions': signal_result.get("short_conditions", []),
                                'fear_greed_index': signal_result.get("fear_greed_index", 50),
                                'bearish_votes': signal_result.get("bearish_votes", 0),
                                'bullish_votes': signal_result.get("bullish_votes", 0)
                            })
                            logger.info(f"SHORT позиция открыта: {timestamp} @ ${price:.2f}")
                            logger.info(f"   Скор: {signal_result.get('short_score', 0):.2f}")
                            logger.info(f"   Условия: {len(signal_result.get('short_conditions', []))}")
                
                elif signal == "SELL":
                    # Закрываем позицию
                    if self.symbol in self.paper_trader.positions:
                        trade_info = self.paper_trader.close_position(
                            symbol=self.symbol,
                            price=price,
                            reason="SELL"
                        )
                        if trade_info:
                            logger.info(f"Позиция закрыта: {timestamp} @ ${price:.2f}")
                
                # Проверяем позиции на стоп-лоссы и тейк-профиты
                actions = self.paper_trader.check_positions({self.symbol: price})
                for action in actions:
                    if action.get("type") in ["STOP-LOSS", "TRAILING-STOP", "TIME-EXIT"]:
                        logger.info(f"Автозакрытие: {action['type']} @ ${action['price']:.2f}")
                
                # Сохраняем результаты
                self.results.append({
                    'timestamp': timestamp,
                    'price': price,
                    'signal': signal,
                    'bearish_votes': signal_result.get("bearish_votes", 0),
                    'bullish_votes': signal_result.get("bullish_votes", 0),
                    'short_enabled': signal_result.get("short_enabled", False),
                    'short_score': signal_result.get("short_score", 0),
                    'fear_greed_index': signal_result.get("fear_greed_index", 50)
                })
                
            except Exception as e:
                logger.warning(f"Ошибка на свече {i}: {e}")
                continue
        
        # Останавливаем Paper Trader
        self.paper_trader.stop()
        
        return self.analyze_results()
    
    def analyze_results(self) -> Dict[str, Any]:
        """Анализирует результаты бэктеста"""
        if not self.results:
            return {"error": "Нет результатов для анализа"}
        
        # Получаем статус Paper Trader
        status = self.paper_trader.get_status()
        
        # Статистика сигналов
        signal_counts = {}
        for result in self.results:
            signal = result['signal']
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
        
        # Анализ SHORT сигналов
        short_analysis = {
            'total_short_signals': len(self.short_signals),
            'short_activation_rate': len(self.short_signals) / self.total_signals * 100 if self.total_signals > 0 else 0,
            'avg_short_score': np.mean([s['short_score'] for s in self.short_signals]) if self.short_signals else 0,
            'avg_fear_index': np.mean([s['fear_greed_index'] for s in self.short_signals]) if self.short_signals else 0,
            'avg_conditions': np.mean([len(s['short_conditions']) for s in self.short_signals]) if self.short_signals else 0
        }
        
        # Анализ голосования
        bearish_dominance = sum(1 for r in self.results if r['bearish_votes'] > r['bullish_votes'])
        bullish_dominance = sum(1 for r in self.results if r['bullish_votes'] > r['bearish_votes'])
        
        # Анализ страха
        fear_periods = sum(1 for r in self.results if r['fear_greed_index'] < 45)
        
        return {
            'backtest_period': f'{self.hours} hours',
            'symbol': self.symbol,
            'interval': self.interval,
            'total_candles': len(self.results),
            'signal_distribution': signal_counts,
            'short_analysis': short_analysis,
            'market_analysis': {
                'bearish_dominance_periods': bearish_dominance,
                'bullish_dominance_periods': bullish_dominance,
                'fear_periods': fear_periods,
                'fear_percentage': fear_periods / len(self.results) * 100 if self.results else 0
            },
            'trading_results': {
                'initial_balance': status['initial_balance'],
                'final_balance': status['current_balance'],
                'total_balance': status['total_balance'],
                'total_profit': status['total_profit'],
                'total_profit_percent': status['total_profit_percent'],
                'positions_count': status['positions_count'],
                'max_positions': status['max_positions'],
                'stats': status['stats']
            },
            'short_signals': self.short_signals[-10:] if self.short_signals else [],  # Последние 10 SHORT сигналов
            'recommendations': self.generate_recommendations(status)
        }
    
    def generate_recommendations(self, status: Dict[str, Any]) -> List[str]:
        """Генерирует рекомендации на основе результатов"""
        recommendations = []
        
        # Анализ прибыльности
        profit_percent = status['total_profit_percent']
        if profit_percent > 0:
            recommendations.append(f"✅ Положительная прибыль: +{profit_percent:.2f}%")
        else:
            recommendations.append(f"❌ Отрицательная прибыль: {profit_percent:.2f}%")
        
        # Анализ SHORT сигналов
        if len(self.short_signals) == 0:
            recommendations.append("❌ SHORT сигналы не генерировались - проверьте настройки")
        else:
            recommendations.append(f"✅ SHORT сигналы генерировались: {len(self.short_signals)} раз")
        
        # Анализ Win Rate
        win_rate = status['stats']['win_rate']
        if win_rate > 60:
            recommendations.append(f"✅ Высокий Win Rate: {win_rate:.1f}%")
        elif win_rate > 40:
            recommendations.append(f"⚠️ Средний Win Rate: {win_rate:.1f}%")
        else:
            recommendations.append(f"❌ Низкий Win Rate: {win_rate:.1f}%")
        
        # Анализ количества сделок
        total_trades = status['stats']['total_trades']
        if total_trades == 0:
            recommendations.append("❌ Ни одной сделки не было совершено")
        elif total_trades < 5:
            recommendations.append(f"⚠️ Мало сделок: {total_trades} (возможно, слишком строгие условия)")
        else:
            recommendations.append(f"✅ Достаточно сделок: {total_trades}")
        
        return recommendations
    
    def print_report(self, results: Dict[str, Any]):
        """Выводит отчет о результатах"""
        print("\n" + "=" * 80)
        print("ОТЧЕТ БЭКТЕСТА SHORT МЕХАНИКИ С PAPER TRADER")
        print("=" * 80)
        
        print(f"Символ: {results['symbol']}")
        print(f"Период: {results['backtest_period']}")
        print(f"Интервал: {results['interval']}")
        print(f"Всего свечей: {results['total_candles']}")
        
        print(f"\nРАСПРЕДЕЛЕНИЕ СИГНАЛОВ:")
        for signal, count in results['signal_distribution'].items():
            percentage = count / results['total_candles'] * 100
            print(f"   {signal}: {count} ({percentage:.1f}%)")
        
        print(f"\nАНАЛИЗ SHORT СИГНАЛОВ:")
        short_analysis = results['short_analysis']
        print(f"   Всего SHORT сигналов: {short_analysis['total_short_signals']}")
        print(f"   Частота активации: {short_analysis['short_activation_rate']:.2f}%")
        print(f"   Средний скор: {short_analysis['avg_short_score']:.2f}")
        print(f"   Средний индекс страха: {short_analysis['avg_fear_index']:.1f}")
        print(f"   Среднее количество условий: {short_analysis['avg_conditions']:.1f}")
        
        print(f"\nТОРГОВЫЕ РЕЗУЛЬТАТЫ:")
        trading = results['trading_results']
        print(f"   Начальный баланс: ${trading['initial_balance']:.2f}")
        print(f"   Финальный баланс: ${trading['final_balance']:.2f}")
        print(f"   Общий баланс: ${trading['total_balance']:.2f}")
        print(f"   Общая прибыль: ${trading['total_profit']:.2f}")
        print(f"   Процент прибыли: {trading['total_profit_percent']:.2f}%")
        print(f"   Позиций: {trading['positions_count']}/{trading['max_positions']}")
        
        print(f"\nСТАТИСТИКА СДЕЛОК:")
        stats = trading['stats']
        print(f"   Всего сделок: {stats['total_trades']}")
        print(f"   Прибыльных: {stats['winning_trades']}")
        print(f"   Убыточных: {stats['losing_trades']}")
        print(f"   Win Rate: {stats['win_rate']:.1f}%")
        print(f"   Комиссия: ${stats['total_commission']:.2f}")
        print(f"   Стоп-лоссы: {stats['stop_loss_triggers']}")
        print(f"   Тейк-профиты: {stats['take_profit_triggers']}")
        print(f"   Трейлинг-стопы: {stats['trailing_stop_triggers']}")
        
        print(f"\nАНАЛИЗ РЫНКА:")
        market = results['market_analysis']
        print(f"   Медвежьи периоды: {market['bearish_dominance_periods']}")
        print(f"   Бычьи периоды: {market['bullish_dominance_periods']}")
        print(f"   Периоды страха: {market['fear_periods']} ({market['fear_percentage']:.1f}%)")
        
        if results['short_signals']:
            print(f"\nПОСЛЕДНИЕ SHORT СИГНАЛЫ:")
            for signal in results['short_signals'][-5:]:  # Последние 5
                print(f"   {signal['timestamp']} @ ${signal['price']:.2f}")
                print(f"      Скор: {signal['short_score']:.2f}, Страх: {signal['fear_greed_index']}")
                print(f"      Голоса: {signal['bearish_votes']} vs {signal['bullish_votes']}")
        
        print(f"\nРЕКОМЕНДАЦИИ:")
        for rec in results['recommendations']:
            print(f"   {rec}")
        
        print("=" * 80)

def main():
    """Основная функция"""
    logger.info("ЗАПУСК БЭКТЕСТА SHORT МЕХАНИКИ С PAPER TRADER")
    
    # Создаем бэктест
    backtest = ShortPaperBacktest(symbol="BTCUSDT", interval="1h", hours=24)
    
    # Запускаем тест
    results = backtest.run_backtest()
    
    if "error" in results:
        logger.error(f"Ошибка бэктеста: {results['error']}")
        return
    
    # Выводим отчет
    backtest.print_report(results)
    
    logger.info("БЭКТЕСТ ЗАВЕРШЕН")

if __name__ == "__main__":
    main()
