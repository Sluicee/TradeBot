#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправлений на сервере
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import db
from datetime import datetime, timedelta

def test_sell_signals():
    """Проверяем есть ли SELL сигналы в БД"""
    print("Проверка SELL сигналов в БД...")
    
    signals = db.get_signals(limit=1000)
    sell_signals = [s for s in signals if s["signal"] == "SELL"]
    buy_signals = [s for s in signals if s["signal"] == "BUY"]
    hold_signals = [s for s in signals if s["signal"] == "HOLD"]
    
    print(f"Статистика сигналов:")
    print(f"  Всего: {len(signals)}")
    print(f"  BUY: {len(buy_signals)} ({len(buy_signals)/len(signals)*100:.1f}%)")
    print(f"  HOLD: {len(hold_signals)} ({len(hold_signals)/len(signals)*100:.1f}%)")
    print(f"  SELL: {len(sell_signals)} ({len(sell_signals)/len(signals)*100:.1f}%)")
    
    if sell_signals:
        print(f"\nНайдено {len(sell_signals)} SELL сигналов!")
        print("Последние 5 SELL сигналов:")
        for s in sell_signals[-5:]:
            print(f"  {s['time']}: {s['symbol']} @ ${s['price']:.4f}")
    else:
        print("\nSELL сигналов не найдено")
    
    return len(sell_signals) > 0

def test_recent_signals():
    """Проверяем последние сигналы"""
    print("\nПоследние 10 сигналов:")
    signals = db.get_signals(limit=10)
    for s in signals:
        print(f"  {s['time']}: {s['symbol']} {s['signal']} @ ${s['price']:.2f}")

def test_signal_generation():
    """Тестируем генерацию сигналов с RSI > 70"""
    print("\nТестирование генерации SELL сигналов...")
    
    try:
        from signal_generator import SignalGenerator
        import pandas as pd
        import numpy as np
        
        # Создаем тестовые данные с RSI > 70
        data = {
            'close': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120],
            'high': [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121],
            'low': [99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119],
            'volume': [1000] * 21
        }
        
        df = pd.DataFrame(data)
        sg = SignalGenerator(df)
        
        # Вычисляем индикаторы
        df_with_indicators = sg.compute_indicators()
        
        # Генерируем сигнал
        result = sg.generate_signal()
        
        print(f"  Сигнал: {result['signal']}")
        print(f"  RSI: {result.get('RSI', 'N/A')}")
        print(f"  Bullish votes: {result.get('bullish_votes', 0)}")
        print(f"  Bearish votes: {result.get('bearish_votes', 0)}")
        print(f"  Причины: {result.get('reasons', [])}")
        
        return result['signal'] == 'SELL'
        
    except Exception as e:
        print(f"Ошибка тестирования: {e}")
        return False

def main():
    print("Тестирование исправлений TP и SELL сигналов на сервере")
    print("=" * 60)
    
    # Проверяем SELL сигналы в БД
    has_sell = test_sell_signals()
    
    # Показываем последние сигналы
    test_recent_signals()
    
    # Тестируем генерацию сигналов
    can_generate_sell = test_signal_generation()
    
    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    print(f"  SELL в БД: {'ДА' if has_sell else 'НЕТ'}")
    print(f"  Генерация SELL: {'ДА' if can_generate_sell else 'НЕТ'}")
    
    if has_sell or can_generate_sell:
        print("\nИсправления работают!")
    else:
        print("\nИсправления требуют дополнительной настройки")
    
    print("\nСледующие шаги:")
    print("1. Перезапустить бота для применения изменений")
    print("2. Мониторить /signal_stats в Telegram")
    print("3. Проверить логи на предмет TP срабатываний")

if __name__ == "__main__":
    main()
