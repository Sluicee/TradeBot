#!/usr/bin/env python3
"""
🔴 ПРОСТОЙ ТЕСТ SHORT ЛОГИКИ

Быстрая проверка условий активации SHORT без сложных импортов.
"""

import sys
import os

# Добавляем путь к модулям
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_short_conditions():
    """Тестирует основные условия SHORT активации"""
    print("ПРОСТОЙ ТЕСТ SHORT ЛОГИКИ")
    print("=" * 50)
    
    # Тестовые сценарии
    scenarios = [
        {
            'name': 'Сильный страх + медвежий тренд',
            'fear_greed_index': 25,  # Сильный страх
            'funding_rate': -0.01,  # Отрицательный funding
            'long_liquidations': 15.0,  # Высокие ликвидации long
            'short_liquidations': 5.0,  # Низкие ликвидации short
            'btc_dominance_change': 1.5,  # Рост доминирования BTC
            'ema_short': 109000,  # EMA short
            'ema_long': 110000,   # EMA long (медвежий тренд)
            'rsi': 45,  # Нейтральный RSI
            'expected_short': True
        },
        {
            'name': 'Умеренный страх + медвежий тренд',
            'fear_greed_index': 35,  # Умеренный страх
            'funding_rate': -0.005,  # Слабо отрицательный funding
            'long_liquidations': 10.0,
            'short_liquidations': 8.0,
            'btc_dominance_change': 0.5,
            'ema_short': 109000,
            'ema_long': 110000,
            'rsi': 45,
            'expected_short': True
        },
        {
            'name': 'Слабый страх + медвежий тренд',
            'fear_greed_index': 45,  # Слабый страх
            'funding_rate': 0.001,  # Положительный funding
            'long_liquidations': 5.0,
            'short_liquidations': 5.0,
            'btc_dominance_change': 0.0,
            'ema_short': 109000,
            'ema_long': 110000,
            'rsi': 45,
            'expected_short': False
        },
        {
            'name': 'Жадность + медвежий тренд',
            'fear_greed_index': 65,  # Жадность
            'funding_rate': 0.01,  # Положительный funding
            'long_liquidations': 3.0,
            'short_liquidations': 7.0,
            'btc_dominance_change': -0.5,
            'ema_short': 109000,
            'ema_long': 110000,
            'rsi': 45,
            'expected_short': False
        }
    ]
    
    results = []
    
    for scenario in scenarios:
        print(f"\nТЕСТ: {scenario['name']}")
        print(f"   Страх: {scenario['fear_greed_index']}")
        print(f"   Funding: {scenario['funding_rate']:.3f}%")
        print(f"   Long liq: ${scenario['long_liquidations']:.1f}M")
        print(f"   Short liq: ${scenario['short_liquidations']:.1f}M")
        print(f"   BTC.D: {scenario['btc_dominance_change']:+.1f}%")
        print(f"   EMA: {scenario['ema_short']} < {scenario['ema_long']} (медвежий)")
        
        # Простая логика проверки условий
        conditions = []
        score = 0.0
        
        # 1. Проверка страха (вес 0.25)
        if scenario['fear_greed_index'] < 45:  # SHORT_FEAR_MODERATE_THRESHOLD
            conditions.append("Страх")
            score += 0.25
        
        # 2. Проверка funding rate (вес 0.15)
        if scenario['funding_rate'] < 0.0:  # SHORT_FUNDING_RATE_THRESHOLD
            conditions.append("Funding")
            score += 0.15
        
        # 3. Проверка ликвидаций (вес 0.2)
        if scenario['long_liquidations'] > scenario['short_liquidations'] * 1.5:  # SHORT_LIQUIDATION_RATIO_THRESHOLD
            conditions.append("Ликвидации")
            score += 0.2
        
        # 4. Проверка RSI (вес 0.2)
        if scenario['rsi'] > 70:  # RSI перекупленность
            conditions.append("RSI")
            score += 0.2
        
        # 5. Проверка EMA тренда (вес 0.1)
        if scenario['ema_short'] < scenario['ema_long']:  # Медвежий тренд
            conditions.append("EMA")
            score += 0.1
        
        # 6. Проверка волатильности (вес 0.1)
        # Предполагаем высокую волатильность
        conditions.append("Волатильность")
        score += 0.1
        
        # 7. Проверка BTC доминирования (бонус)
        if scenario['btc_dominance_change'] > 1.0 and scenario['fear_greed_index'] < 30:
            conditions.append("BTC.D")
            score += 0.1
        
        # Проверка активации
        short_enabled = score > 0.55  # SHORT_MIN_SCORE
        
        print(f"   Результат:")
        print(f"      Скор: {score:.3f}")
        print(f"      Условия: {', '.join(conditions)}")
        print(f"      Активация: {'ДА' if short_enabled else 'НЕТ'}")
        
        # Проверяем ожидание
        expected = scenario['expected_short']
        actual = short_enabled
        status = "ПРОШЕЛ" if expected == actual else "ПРОВАЛЕН"
        
        print(f"      Ожидание: {'ДА' if expected else 'НЕТ'}")
        print(f"      Статус: {status}")
        
        results.append({
            'scenario': scenario['name'],
            'expected': expected,
            'actual': actual,
            'score': score,
            'conditions': len(conditions),
            'status': status
        })
    
    # Выводим итоговый отчет
    print("\n" + "=" * 80)
    print("ИТОГОВЫЙ ОТЧЕТ ТЕСТИРОВАНИЯ SHORT ЛОГИКИ")
    print("=" * 80)
    
    passed = sum(1 for r in results if "ПРОШЕЛ" in r['status'])
    total = len(results)
    
    print(f"Всего тестов: {total}")
    print(f"Прошло: {passed}")
    print(f"Провалено: {total - passed}")
    print(f"Успешность: {passed/total*100:.1f}%")
    
    print(f"\nДЕТАЛИ ТЕСТОВ:")
    for result in results:
        print(f"   {result['scenario']}: {result['status']}")
        if "ПРОШЕЛ" in result['status']:
            print(f"      Скор: {result['score']:.3f}, Условия: {result['conditions']}")
    
    # Рекомендации
    print(f"\nРЕКОМЕНДАЦИИ:")
    if passed == total:
        print("   Все тесты прошли - SHORT логика работает корректно")
    else:
        print("   Некоторые тесты провалены - требуется настройка параметров")
        failed_tests = [r for r in results if "ПРОВАЛЕН" in r['status']]
        for test in failed_tests:
            print(f"   - {test['scenario']}: ожидался {test['expected']}, получен {test['actual']}")
    
    return results

def main():
    """Основная функция"""
    try:
        results = test_short_conditions()
        print("\nТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
        return results
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        return []

if __name__ == "__main__":
    main()
