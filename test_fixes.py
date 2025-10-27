#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправлений TP и SELL сигналов
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

def main():
    print("Тестирование исправлений TP и SELL сигналов")
    print("=" * 50)
    
    # Проверяем SELL сигналы
    has_sell = test_sell_signals()
    
    # Показываем последние сигналы
    test_recent_signals()
    
    print("\n" + "=" * 50)
    if has_sell:
        print("SELL сигналы найдены - исправление работает!")
    else:
        print("SELL сигналов пока нет - возможно нужно время для генерации")
    
    print("\nСледующие шаги:")
    print("1. Мониторить /signal_stats в Telegram")
    print("2. Проверить логи на предмет TP срабатываний")
    print("3. Убедиться что частичное закрытие работает корректно")

if __name__ == "__main__":
    main()
