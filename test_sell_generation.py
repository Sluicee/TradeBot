#!/usr/bin/env python3
"""
Тест генерации SELL сигналов
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from signal_generator import SignalGenerator
import pandas as pd
import numpy as np

def test_sell_generation():
    """Тестируем генерацию SELL сигналов с достаточными данными"""
    print("Тестирование генерации SELL сигналов...")
    
    # Создаем 100 свечей с растущим трендом (RSI > 70)
    np.random.seed(42)
    base_price = 100
    prices = [base_price]
    
    for i in range(99):
        # Растущий тренд с небольшими колебаниями
        change = np.random.normal(0.5, 0.3)  # Средний рост 0.5% с волатильностью 0.3%
        new_price = prices[-1] * (1 + change/100)
        prices.append(new_price)
    
    # Создаем OHLCV данные
    data = {
        'close': prices,
        'high': [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices],
        'low': [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices],
        'volume': [1000 + np.random.randint(-200, 200) for _ in prices]
    }
    
    df = pd.DataFrame(data)
    print(f"Создано {len(df)} свечей, цена от ${df['close'].iloc[0]:.2f} до ${df['close'].iloc[-1]:.2f}")
    
    # Создаем генератор сигналов
    sg = SignalGenerator(df)
    
    # Вычисляем индикаторы
    try:
        df_with_indicators = sg.compute_indicators()
        print("Индикаторы вычислены успешно")
    except Exception as e:
        print(f"Ошибка вычисления индикаторов: {e}")
        return False
    
    # Генерируем сигнал
    try:
        result = sg.generate_signal()
        
        print(f"\n📊 Результат генерации сигнала:")
        print(f"  Сигнал: {result['signal']}")
        print(f"  RSI: {result.get('RSI', 'N/A')}")
        print(f"  Bullish votes: {result.get('bullish_votes', 0)}")
        print(f"  Bearish votes: {result.get('bearish_votes', 0)}")
        print(f"  Vote delta: {result.get('bearish_votes', 0) - result.get('bullish_votes', 0)}")
        print(f"  Market regime: {result.get('market_regime', 'N/A')}")
        
        print(f"\n📋 Причины:")
        for reason in result.get('reasons', []):
            print(f"  - {reason}")
        
        return result['signal'] == 'SELL'
        
    except Exception as e:
        print(f"Ошибка генерации сигнала: {e}")
        return False

if __name__ == "__main__":
    success = test_sell_generation()
    print(f"\n{'='*50}")
    if success:
        print("SELL сигнал сгенерирован успешно!")
    else:
        print("SELL сигнал не сгенерирован")
        print("Возможные причины:")
        print("  - RSI не достиг 70+")
        print("  - Недостаточно bearish голосов")
        print("  - Фильтры блокируют сигнал")
