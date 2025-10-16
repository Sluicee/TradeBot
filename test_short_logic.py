#!/usr/bin/env python3
"""
🔴 ТЕСТ ЛОГИКИ SHORT АКТИВАЦИИ

Быстрый тест для проверки условий активации SHORT сигналов
без реальных API вызовов.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Добавляем путь к модулям
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from signal_generator import SignalGenerator
from config import *
from logger import logger

# Импортируем все SHORT константы
from config import (
    SHORT_MIN_SCORE, SHORT_FUNDING_RATE_THRESHOLD, SHORT_LIQUIDATION_RATIO_THRESHOLD,
    SHORT_FEAR_EXTREME_THRESHOLD, SHORT_FEAR_HIGH_THRESHOLD, SHORT_FEAR_MODERATE_THRESHOLD,
    SHORT_GREED_THRESHOLD, SHORT_EMA_SLOPE_THRESHOLD, SHORT_MAX_VOTES,
    SHORT_V1_VOTES, SHORT_V1_MIN_CONDITIONS, SHORT_FEAR_INERTIA_THRESHOLD,
    SHORT_FEAR_INERTIA_CANDLES, SHORT_FEAR_INERTIA_BONUS, SHORT_FEAR_WEIGHT,
    SHORT_FUNDING_WEIGHT, SHORT_LIQUIDATION_WEIGHT, SHORT_RSI_WEIGHT,
    SHORT_EMA_WEIGHT, SHORT_VOLATILITY_WEIGHT, SHORT_VOLATILITY_MULTIPLIER,
    SHORT_VOLATILITY_BONUS, SHORT_BTC_DOMINANCE_THRESHOLD, SHORT_BTC_DOMINANCE_FEAR_THRESHOLD,
    SHORT_BTC_DOMINANCE_BONUS, SHORT_API_TIMEOUT, SHORT_FALLBACK_FUNDING_RATE,
    SHORT_FALLBACK_LONG_LIQUIDATIONS, SHORT_FALLBACK_SHORT_LIQUIDATIONS, SHORT_FALLBACK_BTC_DOMINANCE
)

def create_test_data():
    """Создает тестовые данные для проверки SHORT логики"""
    # Создаем 100 свечей с трендом вниз
    dates = pd.date_range(start='2025-10-14', periods=100, freq='1H')
    
    # Создаем падающий тренд
    base_price = 110000
    prices = []
    for i in range(100):
        # Падение с небольшими отскоками
        trend = -i * 50  # Основной тренд вниз
        noise = np.random.normal(0, 200)  # Шум
        price = base_price + trend + noise
        prices.append(max(price, 100000))  # Минимум 100k
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000] * 100
    })
    
    df.set_index('timestamp', inplace=True)
    return df

def test_short_conditions():
    """Тестирует условия активации SHORT"""
    logger.info("🔴 ТЕСТ ЛОГИКИ SHORT АКТИВАЦИИ")
    logger.info("=" * 50)
    
    # Создаем тестовые данные
    df = create_test_data()
    logger.info(f"📊 Создано {len(df)} тестовых свечей")
    
    # Создаем генератор сигналов
    generator = SignalGenerator(df)
    
    try:
        # Вычисляем индикаторы
        generator.compute_indicators()
        logger.info("✅ Индикаторы вычислены")
    except Exception as e:
        logger.error(f"❌ Ошибка вычисления индикаторов: {e}")
        return
    
    # Тестируем различные сценарии
    test_scenarios = [
        {
            'name': 'Сильный страх + медвежий тренд',
            'fear_greed_index': 25,  # Сильный страх
            'funding_rate': -0.01,  # Отрицательный funding
            'long_liquidations': 15.0,  # Высокие ликвидации long
            'short_liquidations': 5.0,  # Низкие ликвидации short
            'btc_dominance_change': 1.5,  # Рост доминирования BTC
            'expected_short': True
        },
        {
            'name': 'Умеренный страх + медвежий тренд',
            'fear_greed_index': 35,  # Умеренный страх
            'funding_rate': -0.005,  # Слабо отрицательный funding
            'long_liquidations': 10.0,
            'short_liquidations': 8.0,
            'btc_dominance_change': 0.5,
            'expected_short': True
        },
        {
            'name': 'Слабый страх + медвежий тренд',
            'fear_greed_index': 45,  # Слабый страх
            'funding_rate': 0.001,  # Положительный funding
            'long_liquidations': 5.0,
            'short_liquidations': 5.0,
            'btc_dominance_change': 0.0,
            'expected_short': False
        },
        {
            'name': 'Жадность + медвежий тренд',
            'fear_greed_index': 65,  # Жадность
            'funding_rate': 0.01,  # Положительный funding
            'long_liquidations': 3.0,
            'short_liquidations': 7.0,
            'btc_dominance_change': -0.5,
            'expected_short': False
        }
    ]
    
    results = []
    
    for scenario in test_scenarios:
        logger.info(f"\n🧪 ТЕСТ: {scenario['name']}")
        logger.info(f"   Страх: {scenario['fear_greed_index']}")
        logger.info(f"   Funding: {scenario['funding_rate']:.3f}%")
        logger.info(f"   Long liq: ${scenario['long_liquidations']:.1f}M")
        logger.info(f"   Short liq: ${scenario['short_liquidations']:.1f}M")
        logger.info(f"   BTC.D: {scenario['btc_dominance_change']:+.1f}%")
        
        try:
            # Создаем мок данные для тестирования
            mock_data = {
                'fear_greed_index': scenario['fear_greed_index'],
                'funding_rate': scenario['funding_rate'],
                'long_liquidations': scenario['long_liquidations'],
                'short_liquidations': scenario['short_liquidations'],
                'btc_dominance_change': scenario['btc_dominance_change']
            }
            
            # Тестируем SHORT активацию
            short_score, short_position_size, short_breakdown = generator.calculate_adaptive_short_score_v2_1(
                mock_data['fear_greed_index'],
                mock_data['funding_rate'],
                mock_data['long_liquidations'],
                mock_data['short_liquidations'],
                rsi=45,  # Нейтральный RSI
                ema_short=109000,  # EMA short
                ema_long=110000,  # EMA long (медвежий тренд)
                atr=500,  # ATR
                atr_mean=400,  # Средний ATR
                btc_dominance_change=mock_data['btc_dominance_change'],
                fear_history=[mock_data['fear_greed_index']] * 5
            )
            
            # Проверяем активацию
            short_enabled = short_score > SHORT_MIN_SCORE
            short_conditions = []
            
            if short_breakdown["fear_score"] > 0:
                short_conditions.append("Страх")
            if short_breakdown["funding_score"] > 0:
                short_conditions.append("Funding")
            if short_breakdown["liquidation_score"] > 0:
                short_conditions.append("Ликвидации")
            if short_breakdown["rsi_score"] > 0:
                short_conditions.append("RSI")
            if short_breakdown["ema_score"] > 0:
                short_conditions.append("EMA")
            if short_breakdown["volatility_score"] > 0:
                short_conditions.append("Волатильность")
            if short_breakdown["btc_dominance_bonus"] > 0:
                short_conditions.append("BTC.D")
            if short_breakdown["inertia_bonus"] > 0:
                short_conditions.append("Инерция")
            
            logger.info(f"   📊 Результат:")
            logger.info(f"      Скор: {short_score:.3f}")
            logger.info(f"      Размер позиции: {short_position_size:.1%}")
            logger.info(f"      Условия: {', '.join(short_conditions)}")
            logger.info(f"      Активация: {'✅ ДА' if short_enabled else '❌ НЕТ'}")
            
            # Проверяем ожидание
            expected = scenario['expected_short']
            actual = short_enabled
            status = "✅ ПРОШЕЛ" if expected == actual else "❌ ПРОВАЛЕН"
            
            logger.info(f"      Ожидание: {'✅ ДА' if expected else '❌ НЕТ'}")
            logger.info(f"      Статус: {status}")
            
            results.append({
                'scenario': scenario['name'],
                'expected': expected,
                'actual': actual,
                'score': short_score,
                'conditions': len(short_conditions),
                'status': status
            })
            
        except Exception as e:
            logger.error(f"❌ Ошибка в тесте: {e}")
            results.append({
                'scenario': scenario['name'],
                'expected': scenario['expected_short'],
                'actual': False,
                'score': 0,
                'conditions': 0,
                'status': f"❌ ОШИБКА: {e}"
            })
    
    # Выводим итоговый отчет
    print("\n" + "=" * 80)
    print("🔴 ИТОГОВЫЙ ОТЧЕТ ТЕСТИРОВАНИЯ SHORT ЛОГИКИ")
    print("=" * 80)
    
    passed = sum(1 for r in results if "ПРОШЕЛ" in r['status'])
    total = len(results)
    
    print(f"📊 Всего тестов: {total}")
    print(f"✅ Прошло: {passed}")
    print(f"❌ Провалено: {total - passed}")
    print(f"📈 Успешность: {passed/total*100:.1f}%")
    
    print(f"\n📋 ДЕТАЛИ ТЕСТОВ:")
    for result in results:
        print(f"   {result['scenario']}: {result['status']}")
        if "ПРОШЕЛ" in result['status']:
            print(f"      Скор: {result['score']:.3f}, Условия: {result['conditions']}")
    
    # Рекомендации
    print(f"\n💡 РЕКОМЕНДАЦИИ:")
    if passed == total:
        print("   ✅ Все тесты прошли - SHORT логика работает корректно")
    else:
        print("   ⚠️ Некоторые тесты провалены - требуется настройка параметров")
        failed_tests = [r for r in results if "ПРОВАЛЕН" in r['status']]
        for test in failed_tests:
            print(f"   - {test['scenario']}: ожидался {test['expected']}, получен {test['actual']}")
    
    return results

def main():
    """Основная функция"""
    try:
        results = test_short_conditions()
        logger.info("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
        return results
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return []

if __name__ == "__main__":
    main()
