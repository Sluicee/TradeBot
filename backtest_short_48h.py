#!/usr/bin/env python3
"""
🔴 БЭКТЕСТ SHORT МЕХАНИКИ ЗА ПОСЛЕДНИЕ 48 ЧАСОВ

Проверяет работу SHORT v2.1 на реальных данных за последние 48 часов.
Анализирует активацию SHORT сигналов и их эффективность.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import json
from typing import Dict, Any, List
import sys
import os

# Добавляем путь к модулям
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from signal_generator import SignalGenerator
from config import *
from logger import logger

class ShortBacktest48h:
    """Бэктест SHORT механики за 48 часов"""
    
    def __init__(self, symbol: str = "BTCUSDT", interval: str = "1h"):
        self.symbol = symbol
        self.interval = interval
        self.results = []
        self.short_signals = []
        self.total_signals = 0
        self.short_activated = 0
        
    def get_historical_data(self, hours: int = 24) -> pd.DataFrame:
        """Получает исторические данные за указанное количество часов"""
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
            if hours < 24:
                cutoff_time = df.index[-1] - timedelta(hours=hours)
                df = df[df.index >= cutoff_time]
            
            logger.info(f"📊 Получено {len(df)} свечей для {self.symbol}")
            return df
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения данных: {e}")
            return pd.DataFrame()
    
    def run_backtest(self) -> Dict[str, Any]:
        """Запускает бэктест SHORT механики"""
        logger.info("🚀 ЗАПУСК БЭКТЕСТА SHORT МЕХАНИКИ ЗА 24 ЧАСА")
        logger.info("=" * 60)
        
        # Получаем данные
        df = self.get_historical_data(24)
        if df.empty:
            return {"error": "Не удалось получить данные"}
        
        # Создаем генератор сигналов
        generator = SignalGenerator(df)
        
        # Вычисляем индикаторы
        try:
            generator.compute_indicators()
        except Exception as e:
            logger.error(f"❌ Ошибка вычисления индикаторов: {e}")
            return {"error": f"Ошибка индикаторов: {e}"}
        
        # Проходим по каждой свече
        for i in range(50, len(df)):  # Начинаем с 50-й свечи для стабильности индикаторов
            current_df = df.iloc[:i+1].copy()
            
            try:
                # Создаем новый генератор для текущего среза
                current_generator = SignalGenerator(current_df)
                current_generator.compute_indicators()
                
                # Генерируем сигнал
                signal_result = current_generator.generate_signal()
                
                # Анализируем результат
                signal = signal_result.get("signal", "HOLD")
                price = signal_result.get("price", 0)
                timestamp = current_df.index[-1]
                
                self.total_signals += 1
                
                # Проверяем SHORT активацию
                if signal == "SHORT":
                    self.short_activated += 1
                    self.short_signals.append({
                        'timestamp': timestamp,
                        'price': price,
                        'signal': signal,
                        'short_score': signal_result.get("short_score", 0),
                        'short_conditions': signal_result.get("short_conditions", []),
                        'fear_greed_index': signal_result.get("fear_greed_index", 50),
                        'bearish_votes': signal_result.get("bearish_votes", 0),
                        'bullish_votes': signal_result.get("bullish_votes", 0),
                        'market_regime': signal_result.get("market_regime", "NEUTRAL")
                    })
                    
                    logger.info(f"🔴 SHORT СИГНАЛ: {timestamp} @ ${price:.2f}")
                    logger.info(f"   Скор: {signal_result.get('short_score', 0):.2f}")
                    logger.info(f"   Условия: {len(signal_result.get('short_conditions', []))}")
                    logger.info(f"   Страх: {signal_result.get('fear_greed_index', 50)}")
                
                # Сохраняем все результаты
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
                logger.warning(f"⚠️ Ошибка на свече {i}: {e}")
                continue
        
        return self.analyze_results()
    
    def analyze_results(self) -> Dict[str, Any]:
        """Анализирует результаты бэктеста"""
        if not self.results:
            return {"error": "Нет результатов для анализа"}
        
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
            'backtest_period': '48 hours',
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
            'short_signals': self.short_signals[-10:] if self.short_signals else [],  # Последние 10 SHORT сигналов
            'recommendations': self.generate_recommendations()
        }
    
    def generate_recommendations(self) -> List[str]:
        """Генерирует рекомендации на основе результатов"""
        recommendations = []
        
        if len(self.short_signals) == 0:
            recommendations.append("❌ SHORT сигналы не генерировались - проверьте настройки")
        
        if self.short_activated / self.total_signals * 100 < 1:
            recommendations.append("⚠️ Очень низкая частота SHORT сигналов - возможно, пороги слишком строгие")
        
        fear_periods = sum(1 for r in self.results if r['fear_greed_index'] < 45)
        if fear_periods < len(self.results) * 0.1:
            recommendations.append("📊 Мало периодов страха - SHORT механика может не активироваться")
        
        bearish_dominance = sum(1 for r in self.results if r['bearish_votes'] > r['bullish_votes'])
        if bearish_dominance < len(self.results) * 0.3:
            recommendations.append("📉 Мало медвежьих периодов - SHORT условия редко выполняются")
        
        return recommendations
    
    def print_report(self, results: Dict[str, Any]):
        """Выводит отчет о результатах"""
        print("\n" + "=" * 80)
        print("🔴 ОТЧЕТ БЭКТЕСТА SHORT МЕХАНИКИ ЗА 48 ЧАСОВ")
        print("=" * 80)
        
        print(f"📊 Символ: {results['symbol']}")
        print(f"⏰ Период: {results['backtest_period']}")
        print(f"📈 Интервал: {results['interval']}")
        print(f"🕯️ Всего свечей: {results['total_candles']}")
        
        print(f"\n📊 РАСПРЕДЕЛЕНИЕ СИГНАЛОВ:")
        for signal, count in results['signal_distribution'].items():
            percentage = count / results['total_candles'] * 100
            print(f"   {signal}: {count} ({percentage:.1f}%)")
        
        print(f"\n🔴 АНАЛИЗ SHORT СИГНАЛОВ:")
        short_analysis = results['short_analysis']
        print(f"   Всего SHORT сигналов: {short_analysis['total_short_signals']}")
        print(f"   Частота активации: {short_analysis['short_activation_rate']:.2f}%")
        print(f"   Средний скор: {short_analysis['avg_short_score']:.2f}")
        print(f"   Средний индекс страха: {short_analysis['avg_fear_index']:.1f}")
        print(f"   Среднее количество условий: {short_analysis['avg_conditions']:.1f}")
        
        print(f"\n📈 АНАЛИЗ РЫНКА:")
        market = results['market_analysis']
        print(f"   Медвежьи периоды: {market['bearish_dominance_periods']}")
        print(f"   Бычьи периоды: {market['bullish_dominance_periods']}")
        print(f"   Периоды страха: {market['fear_periods']} ({market['fear_percentage']:.1f}%)")
        
        if results['short_signals']:
            print(f"\n🔴 ПОСЛЕДНИЕ SHORT СИГНАЛЫ:")
            for signal in results['short_signals'][-5:]:  # Последние 5
                print(f"   {signal['timestamp']} @ ${signal['price']:.2f}")
                print(f"      Скор: {signal['short_score']:.2f}, Страх: {signal['fear_greed_index']}")
                print(f"      Голоса: {signal['bearish_votes']} vs {signal['bullish_votes']}")
        
        print(f"\n💡 РЕКОМЕНДАЦИИ:")
        for rec in results['recommendations']:
            print(f"   {rec}")
        
        print("=" * 80)

def main():
    """Основная функция"""
    logger.info("🚀 ЗАПУСК БЭКТЕСТА SHORT МЕХАНИКИ")
    
    # Создаем бэктест
    backtest = ShortBacktest48h(symbol="BTCUSDT", interval="1h")
    
    # Запускаем тест
    results = backtest.run_backtest()
    
    if "error" in results:
        logger.error(f"❌ Ошибка бэктеста: {results['error']}")
        return
    
    # Выводим отчет
    backtest.print_report(results)
    
    logger.info("✅ БЭКТЕСТ ЗАВЕРШЕН")

if __name__ == "__main__":
    main()
