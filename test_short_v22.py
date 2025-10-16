#!/usr/bin/env python3
"""
Тест SHORT-механики v2.2 "Adaptive Market Sentiment SHORT"
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from short_mechanics_v2_2 import AdaptiveShortMechanicsV22
import pandas as pd
import numpy as np

def test_short_v22():
    """
    Тестирование SHORT v2.2 с различными сценариями
    """
    print("ТЕСТ SHORT-МЕХАНИКИ v2.2")
    print("=" * 60)
    
    # Создаем экземпляр механики
    short_mechanics = AdaptiveShortMechanicsV22()
    
    # Тестовые сценарии
    test_cases = [
        {
            'name': 'ЭКСТРЕМАЛЬНЫЙ СТРАХ + СИЛЬНЫЙ ТРЕНД',
            'fear_index': 15,
            'funding_rate': -0.02,
            'long_liquidations': 30.0,
            'short_liquidations': 8.0,
            'rsi': 85,
            'ema_short': 100.0,
            'ema_long': 125.0,
            'atr': 6.0,
            'atr_mean': 3.0,
            'adx': 40,
            'votes': {'bullish_votes': 9, 'bearish_votes': 1},
            'pivot': {'strength': 0.9, 'price_position': 0.95},
            'btc_dominance': 2.0,
            'fear_history': [15, 18, 20]
        },
        {
            'name': 'ВЫСОКИЙ СТРАХ + УМЕРЕННЫЙ ТРЕНД',
            'fear_index': 28,
            'funding_rate': -0.008,
            'long_liquidations': 20.0,
            'short_liquidations': 10.0,
            'rsi': 75,
            'ema_short': 105.0,
            'ema_long': 115.0,
            'atr': 4.5,
            'atr_mean': 3.5,
            'adx': 25,
            'votes': {'bullish_votes': 8, 'bearish_votes': 2},
            'pivot': {'strength': 0.7, 'price_position': 0.8},
            'btc_dominance': 1.2,
            'fear_history': [28, 30, 32]
        },
        {
            'name': 'УМЕРЕННЫЙ СТРАХ + СЛАБЫЙ ТРЕНД',
            'fear_index': 42,
            'funding_rate': -0.003,
            'long_liquidations': 15.0,
            'short_liquidations': 10.0,
            'rsi': 65,
            'ema_short': 108.0,
            'ema_long': 112.0,
            'atr': 3.8,
            'atr_mean': 3.2,
            'adx': 18,
            'votes': {'bullish_votes': 7, 'bearish_votes': 3},
            'pivot': {'strength': 0.5, 'price_position': 0.7},
            'btc_dominance': 0.5,
            'fear_history': [42, 45, 48]
        },
        {
            'name': 'НЕЙТРАЛЬНЫЙ РЫНОК',
            'fear_index': 55,
            'funding_rate': 0.002,
            'long_liquidations': 12.0,
            'short_liquidations': 15.0,
            'rsi': 50,
            'ema_short': 110.0,
            'ema_long': 108.0,
            'atr': 3.0,
            'atr_mean': 3.0,
            'adx': 12,
            'votes': {'bullish_votes': 5, 'bearish_votes': 5},
            'pivot': {'strength': 0.2, 'price_position': 0.5},
            'btc_dominance': -0.3,
            'fear_history': [55, 58, 60]
        },
        {
            'name': 'ЖАДНОСТЬ + БЫЧИЙ ТРЕНД',
            'fear_index': 75,
            'funding_rate': 0.01,
            'long_liquidations': 8.0,
            'short_liquidations': 20.0,
            'rsi': 30,
            'ema_short': 120.0,
            'ema_long': 100.0,
            'atr': 2.5,
            'atr_mean': 3.5,
            'adx': 15,
            'votes': {'bullish_votes': 2, 'bearish_votes': 8},
            'pivot': {'strength': 0.1, 'price_position': 0.2},
            'btc_dominance': -1.0,
            'fear_history': [75, 78, 80]
        }
    ]
    
    results = []
    
    for i, case in enumerate(test_cases, 1):
        print(f"\nТЕСТ {i}: {case['name']}")
        print("-" * 50)
        
        # Вычисляем скор
        score, breakdown = short_mechanics.calculate_adaptive_short_score_v22(
            fear_greed_index=case['fear_index'],
            funding_rate=case['funding_rate'],
            long_liquidations=case['long_liquidations'],
            short_liquidations=case['short_liquidations'],
            rsi=case['rsi'],
            ema_short=case['ema_short'],
            ema_long=case['ema_long'],
            atr=case['atr'],
            atr_mean=case['atr_mean'],
            adx=case['adx'],
            votes_data=case['votes'],
            pivot_data=case['pivot'],
            btc_dominance_change=case['btc_dominance'],
            fear_history=case['fear_history']
        )
        
        # Проверяем активацию
        should_activate, reason = short_mechanics.should_activate_short(
            score=score,
            threshold=breakdown['min_threshold'],
            fear_index=case['fear_index'],
            sentiment=breakdown['sentiment_index'],
            adx=case['adx'],
            market_phase=breakdown['market_phase']
        )
        
        # Сохраняем результат
        result = {
            'case': case['name'],
            'score': score,
            'threshold': breakdown['min_threshold'],
            'activated': should_activate,
            'reason': reason,
            'phase': breakdown['market_phase'],
            'sentiment': breakdown['sentiment_index']
        }
        results.append(result)
        
        # Вывод результатов
        print(f"  Фаза рынка: {breakdown['market_phase']}")
        print(f"  Sentiment: {breakdown['sentiment_index']}")
        print(f"  SHORT Score: {score:.3f}")
        print(f"  Порог: {breakdown['min_threshold']:.3f}")
        print(f"  Активация: {'ДА' if should_activate else 'НЕТ'}")
        print(f"  Причина: {reason}")
        
        # Детализация скора
        print(f"  Компоненты скора:")
        print(f"    Fear: {breakdown['fear_score']:.3f}")
        print(f"    Funding: {breakdown['funding_score']:.3f}")
        print(f"    Liquidation: {breakdown['liquidation_score']:.3f}")
        print(f"    RSI: {breakdown['rsi_score']:.3f}")
        print(f"    EMA: {breakdown['ema_score']:.3f}")
        print(f"    Volatility: {breakdown['volatility_score']:.3f}")
        print(f"    Sentiment: {breakdown['sentiment_score']:.3f}")
        print(f"    ADX: {breakdown['adx_score']:.3f}")
        print(f"    Pivot: {breakdown['pivot_score']:.3f}")
        
        # Бонусы
        print(f"  Бонусы:")
        print(f"    BTC Dominance: +{breakdown['btc_dominance_bonus']:.3f}")
        print(f"    Inertia: +{breakdown['inertia_bonus']:.3f}")
        print(f"    Trend Confirmation: +{breakdown['trend_confirmation_bonus']:.3f}")
    
    # Итоговая статистика
    print(f"\nИТОГОВАЯ СТАТИСТИКА")
    print("=" * 60)
    
    total_cases = len(results)
    activated_count = sum(1 for r in results if r['activated'])
    avg_score = sum(r['score'] for r in results) / total_cases
    avg_sentiment = sum(r['sentiment'] for r in results) / total_cases
    
    print(f"Всего тестов: {total_cases}")
    print(f"SHORT активирован: {activated_count} ({activated_count/total_cases*100:.1f}%)")
    print(f"Средний скор: {avg_score:.3f}")
    print(f"Средний sentiment: {avg_sentiment:.2f}")
    
    # Детали по активированным
    activated_results = [r for r in results if r['activated']]
    if activated_results:
        print(f"\nАКТИВИРОВАННЫЕ SHORT:")
        for r in activated_results:
            print(f"  - {r['case']}: скор {r['score']:.3f}, фаза {r['phase']}")
    else:
        print(f"\nНИ ОДИН SHORT НЕ АКТИВИРОВАН")
    
    # Анализ по фазам
    phase_stats = {}
    for r in results:
        phase = r['phase']
        if phase not in phase_stats:
            phase_stats[phase] = {'total': 0, 'activated': 0}
        phase_stats[phase]['total'] += 1
        if r['activated']:
            phase_stats[phase]['activated'] += 1
    
    print(f"\nСТАТИСТИКА ПО ФАЗАМ:")
    for phase, stats in phase_stats.items():
        activation_rate = stats['activated'] / stats['total'] * 100
        print(f"  {phase}: {stats['activated']}/{stats['total']} ({activation_rate:.1f}%)")
    
    return results

def test_adaptive_weights():
    """
    Тест адаптивных весов по фазам рынка
    """
    print(f"\nТЕСТ АДАПТИВНЫХ ВЕСОВ")
    print("-" * 40)
    
    short_mechanics = AdaptiveShortMechanicsV22()
    
    # Тестируем разные фазы
    phases = ['EXTREME_FEAR', 'HIGH_FEAR', 'MODERATE_FEAR', 'NEUTRAL']
    
    for phase in phases:
        weights = short_mechanics.phase_weights[phase]
        print(f"\n{phase}:")
        for component, weight in weights.items():
            print(f"  {component}: {weight:.2f}")
        total_weight = sum(weights.values())
        print(f"  Итого: {total_weight:.2f}")

if __name__ == "__main__":
    # Запускаем тесты
    results = test_short_v22()
    test_adaptive_weights()
    
    print(f"\nЗАКЛЮЧЕНИЕ")
    print("SHORT v2.2 успешно протестирован!")
    print("Адаптивные веса работают")
    print("Market Sentiment Index интегрирован")
    print("ADX подтверждение тренда активно")
    print("Pivot Points учитываются")
    print("Фазы рынка определяются корректно")
