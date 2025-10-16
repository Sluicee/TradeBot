#!/usr/bin/env python3
"""
SHORT-механика v2.2 "Adaptive Market Sentiment SHORT"
Улучшенная версия с адаптивными порогами и Market Sentiment Index
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, List
from datetime import datetime
import requests
import json

class AdaptiveShortMechanicsV22:
    """
    🔴 SHORT-механика v2.2 "Adaptive Market Sentiment SHORT"
    
    Ключевые улучшения:
    - Адаптивные пороги по фазам рынка
    - Market Sentiment Index из голосов
    - Усиленная фильтрация тренда (ADX)
    - Динамические веса факторов
    - Pivot Points для подтверждения разворота
    """
    
    def __init__(self):
        # Конфигурация v2.2
        self.config = {
            # Адаптивные пороги страха по фазам рынка
            'FEAR_EXTREME': 20,      # Экстремальный страх
            'FEAR_HIGH': 35,         # Высокий страх  
            'FEAR_MODERATE': 45,     # Умеренный страх
            'FEAR_NEUTRAL': 55,      # Нейтральный
            'FEAR_GREED': 70,        # Жадность
            
            # Market Sentiment пороги
            'SENTIMENT_BEARISH': -3,    # Сильно медвежий
            'SENTIMENT_NEGATIVE': -1,   # Медвежий
            'SENTIMENT_NEUTRAL': 0,     # Нейтральный
            'SENTIMENT_POSITIVE': 1,   # Бычий
            
            # ADX для подтверждения тренда
            'ADX_TREND_STRONG': 25,     # Сильный тренд
            'ADX_TREND_MODERATE': 20,   # Умеренный тренд
            'ADX_TREND_WEAK': 15,       # Слабый тренд
            
            # Волатильность
            'VOLATILITY_HIGH': 1.5,    # Высокая волатильность
            'VOLATILITY_MODERATE': 1.2, # Умеренная волатильность
            
            # Минимальные пороги активации
            'MIN_SCORE_BASIC': 0.4,     # Базовый порог
            'MIN_SCORE_STRONG': 0.6,    # Сильный сигнал
            'MIN_SCORE_EXTREME': 0.8,   # Экстремальный сигнал
        }
        
        # Динамические веса по фазам рынка
        self.phase_weights = {
            'EXTREME_FEAR': {
                'fear': 0.35, 'funding': 0.20, 'liquidation': 0.25,
                'rsi': 0.10, 'ema': 0.05, 'volatility': 0.05
            },
            'HIGH_FEAR': {
                'fear': 0.30, 'funding': 0.15, 'liquidation': 0.20,
                'rsi': 0.15, 'ema': 0.10, 'volatility': 0.10
            },
            'MODERATE_FEAR': {
                'fear': 0.25, 'funding': 0.15, 'liquidation': 0.20,
                'rsi': 0.20, 'ema': 0.10, 'volatility': 0.10
            },
            'NEUTRAL': {
                'fear': 0.20, 'funding': 0.10, 'liquidation': 0.15,
                'rsi': 0.25, 'ema': 0.15, 'volatility': 0.15
            }
        }
    
    def get_market_phase(self, fear_index: int, sentiment: float) -> str:
        """
        Определяет фазу рынка для адаптации весов
        """
        if fear_index < self.config['FEAR_EXTREME']:
            return 'EXTREME_FEAR'
        elif fear_index < self.config['FEAR_HIGH']:
            return 'HIGH_FEAR'
        elif fear_index < self.config['FEAR_MODERATE']:
            return 'MODERATE_FEAR'
        else:
            return 'NEUTRAL'
    
    def calculate_market_sentiment_index(self, votes_data: Dict) -> float:
        """
        Вычисляет Market Sentiment Index из голосов
        """
        bullish_votes = votes_data.get('bullish_votes', 0)
        bearish_votes = votes_data.get('bearish_votes', 0)
        total_votes = bullish_votes + bearish_votes
        
        if total_votes == 0:
            return 0.0
        
        # Нормализованный sentiment (-5 до +5)
        # Положительный = медвежий (больше bearish_votes)
        # Отрицательный = бычий (больше bullish_votes)
        sentiment = (bearish_votes - bullish_votes) / max(total_votes, 1) * 5
        return round(sentiment, 2)
    
    def calculate_pivot_points(self, df: pd.DataFrame, period: int = 20) -> Dict:
        """
        Вычисляет Pivot Points для подтверждения разворота
        """
        if len(df) < period:
            return {'resistance': 0, 'support': 0, 'pivot': 0, 'strength': 0}
        
        recent = df.tail(period)
        high = recent['high'].max()
        low = recent['low'].min()
        close = recent['close'].iloc[-1]
        
        pivot = (high + low + close) / 3
        resistance = 2 * pivot - low
        support = 2 * pivot - high
        
        # Сила разворота (0-1)
        price_position = (close - support) / (resistance - support) if resistance != support else 0.5
        strength = abs(price_position - 0.5) * 2  # Чем ближе к краям, тем сильнее
        
        return {
            'resistance': resistance,
            'support': support, 
            'pivot': pivot,
            'strength': strength,
            'price_position': price_position
        }
    
    def calculate_adaptive_short_score_v22(
        self,
        fear_greed_index: int,
        funding_rate: float,
        long_liquidations: float,
        short_liquidations: float,
        rsi: float,
        ema_short: float,
        ema_long: float,
        atr: float,
        atr_mean: float,
        adx: float,
        votes_data: Dict,
        pivot_data: Dict,
        btc_dominance_change: float = 0.0,
        fear_history: List[int] = None
    ) -> Tuple[float, Dict]:
        """
        🔴 АДАПТИВНЫЙ SHORT СКОР v2.2
        
        Улучшения:
        - Адаптивные веса по фазам рынка
        - Market Sentiment Index
        - ADX подтверждение тренда
        - Pivot Points для разворота
        - Динамические пороги
        """
        
        # 1. Market Sentiment Index
        sentiment_index = self.calculate_market_sentiment_index(votes_data)
        
        # 2. Определяем фазу рынка
        market_phase = self.get_market_phase(fear_greed_index, sentiment_index)
        weights = self.phase_weights[market_phase]
        
        # 3. Базовые компоненты скора
        fear_score = self._calculate_fear_score(fear_greed_index, market_phase)
        funding_score = self._calculate_funding_score(funding_rate)
        liquidation_score = self._calculate_liquidation_score(long_liquidations, short_liquidations)
        rsi_score = self._calculate_rsi_score(rsi, market_phase)
        ema_score = self._calculate_ema_score(ema_short, ema_long)
        volatility_score = self._calculate_volatility_score(atr, atr_mean)
        
        # 4. Новые компоненты v2.2
        sentiment_score = self._calculate_sentiment_score(sentiment_index)
        adx_score = self._calculate_adx_score(adx, market_phase)
        pivot_score = self._calculate_pivot_score(pivot_data)
        
        # 5. Бонусы
        btc_dominance_bonus = self._calculate_btc_dominance_bonus(
            btc_dominance_change, fear_greed_index
        )
        inertia_bonus = self._calculate_inertia_bonus(fear_history, fear_greed_index)
        trend_confirmation_bonus = self._calculate_trend_confirmation_bonus(
            adx, sentiment_index, market_phase
        )
        
        # 6. Составной скор с адаптивными весами
        base_score = (
            fear_score * weights['fear'] +
            funding_score * weights['funding'] +
            liquidation_score * weights['liquidation'] +
            rsi_score * weights['rsi'] +
            ema_score * weights['ema'] +
            volatility_score * weights['volatility'] +
            sentiment_score * 0.15 +  # Новый компонент
            adx_score * 0.10 +        # Новый компонент
            pivot_score * 0.05       # Новый компонент
        )
        
        # 7. Применяем бонусы
        final_score = base_score + btc_dominance_bonus + inertia_bonus + trend_confirmation_bonus
        final_score = min(1.0, final_score)  # Ограничиваем максимумом
        
        # 8. Адаптивный порог активации
        min_threshold = self._get_adaptive_threshold(market_phase, sentiment_index)
        
        # 9. Детализация для логирования
        breakdown = {
            'market_phase': market_phase,
            'sentiment_index': sentiment_index,
            'fear_score': fear_score,
            'funding_score': funding_score,
            'liquidation_score': liquidation_score,
            'rsi_score': rsi_score,
            'ema_score': ema_score,
            'volatility_score': volatility_score,
            'sentiment_score': sentiment_score,
            'adx_score': adx_score,
            'pivot_score': pivot_score,
            'btc_dominance_bonus': btc_dominance_bonus,
            'inertia_bonus': inertia_bonus,
            'trend_confirmation_bonus': trend_confirmation_bonus,
            'base_score': base_score,
            'final_score': final_score,
            'min_threshold': min_threshold,
            'weights': weights
        }
        
        return final_score, breakdown
    
    def _calculate_fear_score(self, fear_index: int, market_phase: str) -> float:
        """Адаптивный скор страха по фазам"""
        if market_phase == 'EXTREME_FEAR':
            return 1.0 if fear_index < self.config['FEAR_EXTREME'] else 0.0
        elif market_phase == 'HIGH_FEAR':
            return 1.0 if fear_index < self.config['FEAR_HIGH'] else 0.5
        elif market_phase == 'MODERATE_FEAR':
            return 1.0 if fear_index < self.config['FEAR_MODERATE'] else 0.3
        else:
            return 0.0
    
    def _calculate_funding_score(self, funding_rate: float) -> float:
        """Скор funding rate"""
        if funding_rate < -0.01:  # Очень негативный
            return 1.0
        elif funding_rate < 0:     # Негативный
            return 0.8
        elif funding_rate < 0.005: # Нейтральный
            return 0.3
        else:
            return 0.0
    
    def _calculate_liquidation_score(self, long_liq: float, short_liq: float) -> float:
        """Скор ликвидаций"""
        if short_liq == 0:
            return 0.0
        
        ratio = long_liq / short_liq
        if ratio > 3.0:
            return 1.0
        elif ratio > 2.0:
            return 0.8
        elif ratio > 1.5:
            return 0.6
        else:
            return 0.0
    
    def _calculate_rsi_score(self, rsi: float, market_phase: str) -> float:
        """Адаптивный RSI скор"""
        if market_phase in ['EXTREME_FEAR', 'HIGH_FEAR']:
            # В страхе RSI менее важен
            return 1.0 if rsi > 80 else 0.5 if rsi > 70 else 0.0
        else:
            # В нейтрале RSI более важен
            return 1.0 if rsi > 70 else 0.5 if rsi > 60 else 0.0
    
    def _calculate_ema_score(self, ema_short: float, ema_long: float) -> float:
        """Скор EMA тренда"""
        if ema_short < ema_long:
            slope = (ema_short - ema_long) / ema_long
            if slope < -0.02:  # Сильный медвежий тренд
                return 1.0
            elif slope < -0.01:  # Умеренный медвежий тренд
                return 0.7
            else:
                return 0.3
        return 0.0
    
    def _calculate_volatility_score(self, atr: float, atr_mean: float) -> float:
        """Скор волатильности"""
        if atr_mean == 0:
            return 0.0
        
        ratio = atr / atr_mean
        if ratio > self.config['VOLATILITY_HIGH']:
            return 1.0
        elif ratio > self.config['VOLATILITY_MODERATE']:
            return 0.7
        else:
            return 0.3
    
    def _calculate_sentiment_score(self, sentiment: float) -> float:
        """Новый: Market Sentiment Score"""
        if sentiment < self.config['SENTIMENT_BEARISH']:
            return 1.0
        elif sentiment < self.config['SENTIMENT_NEGATIVE']:
            return 0.8
        elif sentiment < self.config['SENTIMENT_NEUTRAL']:
            return 0.5
        else:
            return 0.0
    
    def _calculate_adx_score(self, adx: float, market_phase: str) -> float:
        """Новый: ADX подтверждение тренда"""
        if market_phase in ['EXTREME_FEAR', 'HIGH_FEAR']:
            # В страхе нужен сильный тренд
            if adx > self.config['ADX_TREND_STRONG']:
                return 1.0
            elif adx > self.config['ADX_TREND_MODERATE']:
                return 0.7
            else:
                return 0.3
        else:
            # В нейтрале достаточно умеренного тренда
            if adx > self.config['ADX_TREND_MODERATE']:
                return 1.0
            elif adx > self.config['ADX_TREND_WEAK']:
                return 0.7
            else:
                return 0.3
    
    def _calculate_pivot_score(self, pivot_data: Dict) -> float:
        """Новый: Pivot Points для разворота"""
        strength = pivot_data.get('strength', 0)
        price_position = pivot_data.get('price_position', 0.5)
        
        # Бонус за близость к resistance (разворот вниз)
        if price_position > 0.8:  # Близко к resistance
            return strength * 0.5
        elif price_position < 0.2:  # Близко к support
            return 0.0  # Не подходит для SHORT
        else:
            return strength * 0.2
    
    def _calculate_btc_dominance_bonus(self, btc_change: float, fear_index: int) -> float:
        """BTC доминирование бонус"""
        if btc_change > 1.0 and fear_index < 40:
            return 0.1
        elif btc_change > 0.5 and fear_index < 35:
            return 0.05
        return 0.0
    
    def _calculate_inertia_bonus(self, fear_history: List[int], current_fear: int) -> float:
        """Инерция страха"""
        if not fear_history or len(fear_history) < 3:
            return 0.0
        
        recent_fears = fear_history[-3:]
        if all(f < 35 for f in recent_fears):
            return 0.1
        elif all(f < 45 for f in recent_fears):
            return 0.05
        return 0.0
    
    def _calculate_trend_confirmation_bonus(self, adx: float, sentiment: float, market_phase: str) -> float:
        """Новый: Подтверждение тренда"""
        if market_phase in ['EXTREME_FEAR', 'HIGH_FEAR'] and sentiment < -2:
            if adx > 25:
                return 0.1  # Сильный тренд + сильный страх
            elif adx > 20:
                return 0.05
        return 0.0
    
    def _get_adaptive_threshold(self, market_phase: str, sentiment: float) -> float:
        """Адаптивный порог активации"""
        if market_phase == 'EXTREME_FEAR' and sentiment < -3:
            return self.config['MIN_SCORE_EXTREME']
        elif market_phase == 'HIGH_FEAR' and sentiment < -1:
            return self.config['MIN_SCORE_STRONG']
        else:
            return self.config['MIN_SCORE_BASIC']
    
    def should_activate_short(self, score: float, threshold: float, 
                            fear_index: int, sentiment: float, 
                            adx: float, market_phase: str) -> Tuple[bool, str]:
        """
        Определяет, следует ли активировать SHORT
        """
        # Базовые условия
        if score < threshold:
            return False, f"Score {score:.3f} < threshold {threshold:.3f}"
        
        if fear_index > 50:
            return False, f"Fear {fear_index} > 50 (too greedy)"
        
        if sentiment > 0:
            return False, f"Sentiment {sentiment} > 0 (bullish)"
        
        if adx < 15:
            return False, f"ADX {adx} < 15 (no trend)"
        
        # Дополнительные условия для разных фаз
        if market_phase == 'NEUTRAL':
            if score < self.config['MIN_SCORE_STRONG']:
                return False, f"Neutral phase requires strong signal"
        
        return True, f"SHORT activated: score {score:.3f}, phase {market_phase}"


def run_mini_backtest():
    """
    Мини-бэктест SHORT v2.2
    """
    print("🧪 МИНИ-БЭКТЕСТ SHORT v2.2")
    print("=" * 50)
    
    # Создаем экземпляр механики
    short_mechanics = AdaptiveShortMechanicsV22()
    
    # Тестовые сценарии
    test_scenarios = [
        {
            'name': 'Экстремальный страх + сильный медвежий тренд',
            'fear_index': 18,
            'funding_rate': -0.015,
            'long_liquidations': 25.0,
            'short_liquidations': 8.0,
            'rsi': 85,
            'ema_short': 100.0,
            'ema_long': 120.0,
            'atr': 5.0,
            'atr_mean': 3.0,
            'adx': 35,
            'votes': {'bullish_votes': 2, 'bearish_votes': 8},
            'pivot': {'strength': 0.8, 'price_position': 0.9},
            'btc_dominance': 1.5,
            'fear_history': [18, 20, 22]
        },
        {
            'name': 'Высокий страх + умеренный тренд',
            'fear_index': 28,
            'funding_rate': -0.008,
            'long_liquidations': 18.0,
            'short_liquidations': 10.0,
            'rsi': 75,
            'ema_short': 105.0,
            'ema_long': 110.0,
            'atr': 4.0,
            'atr_mean': 3.5,
            'adx': 22,
            'votes': {'bullish_votes': 3, 'bearish_votes': 7},
            'pivot': {'strength': 0.6, 'price_position': 0.7},
            'btc_dominance': 0.8,
            'fear_history': [28, 30, 32]
        },
        {
            'name': 'Умеренный страх + слабый тренд',
            'fear_index': 42,
            'funding_rate': -0.003,
            'long_liquidations': 12.0,
            'short_liquidations': 8.0,
            'rsi': 65,
            'ema_short': 108.0,
            'ema_long': 112.0,
            'atr': 3.5,
            'atr_mean': 3.2,
            'adx': 18,
            'votes': {'bullish_votes': 4, 'bearish_votes': 6},
            'pivot': {'strength': 0.4, 'price_position': 0.6},
            'btc_dominance': 0.3,
            'fear_history': [42, 45, 48]
        },
        {
            'name': 'Нейтральный рынок',
            'fear_index': 55,
            'funding_rate': 0.002,
            'long_liquidations': 10.0,
            'short_liquidations': 12.0,
            'rsi': 50,
            'ema_short': 110.0,
            'ema_long': 108.0,
            'atr': 3.0,
            'atr_mean': 3.0,
            'adx': 12,
            'votes': {'bullish_votes': 5, 'bearish_votes': 5},
            'pivot': {'strength': 0.2, 'price_position': 0.5},
            'btc_dominance': -0.2,
            'fear_history': [55, 58, 60]
        }
    ]
    
    results = []
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n📊 Сценарий {i}: {scenario['name']}")
        print("-" * 40)
        
        # Вычисляем скор
        score, breakdown = short_mechanics.calculate_adaptive_short_score_v22(
            fear_greed_index=scenario['fear_index'],
            funding_rate=scenario['funding_rate'],
            long_liquidations=scenario['long_liquidations'],
            short_liquidations=scenario['short_liquidations'],
            rsi=scenario['rsi'],
            ema_short=scenario['ema_short'],
            ema_long=scenario['ema_long'],
            atr=scenario['atr'],
            atr_mean=scenario['atr_mean'],
            adx=scenario['adx'],
            votes_data=scenario['votes'],
            pivot_data=scenario['pivot'],
            btc_dominance_change=scenario['btc_dominance'],
            fear_history=scenario['fear_history']
        )
        
        # Проверяем активацию
        should_activate, reason = short_mechanics.should_activate_short(
            score=score,
            threshold=breakdown['min_threshold'],
            fear_index=scenario['fear_index'],
            sentiment=breakdown['sentiment_index'],
            adx=scenario['adx'],
            market_phase=breakdown['market_phase']
        )
        
        # Результат
        result = {
            'scenario': scenario['name'],
            'score': score,
            'threshold': breakdown['min_threshold'],
            'activated': should_activate,
            'reason': reason,
            'phase': breakdown['market_phase'],
            'sentiment': breakdown['sentiment_index']
        }
        results.append(result)
        
        # Вывод
        print(f"  Фаза рынка: {breakdown['market_phase']}")
        print(f"  Sentiment: {breakdown['sentiment_index']}")
        print(f"  SHORT Score: {score:.3f}")
        print(f"  Порог: {breakdown['min_threshold']:.3f}")
        print(f"  Активация: {'✅ ДА' if should_activate else '❌ НЕТ'}")
        print(f"  Причина: {reason}")
        
        # Детализация скора
        print(f"  Компоненты:")
        print(f"    Fear: {breakdown['fear_score']:.3f}")
        print(f"    Funding: {breakdown['funding_score']:.3f}")
        print(f"    Liquidation: {breakdown['liquidation_score']:.3f}")
        print(f"    RSI: {breakdown['rsi_score']:.3f}")
        print(f"    EMA: {breakdown['ema_score']:.3f}")
        print(f"    Volatility: {breakdown['volatility_score']:.3f}")
        print(f"    Sentiment: {breakdown['sentiment_score']:.3f}")
        print(f"    ADX: {breakdown['adx_score']:.3f}")
        print(f"    Pivot: {breakdown['pivot_score']:.3f}")
    
    # Итоговая статистика
    print(f"\n📈 ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 50)
    
    total_scenarios = len(results)
    activated_count = sum(1 for r in results if r['activated'])
    avg_score = sum(r['score'] for r in results) / total_scenarios
    avg_sentiment = sum(r['sentiment'] for r in results) / total_scenarios
    
    print(f"Всего сценариев: {total_scenarios}")
    print(f"SHORT активирован: {activated_count} ({activated_count/total_scenarios*100:.1f}%)")
    print(f"Средний скор: {avg_score:.3f}")
    print(f"Средний sentiment: {avg_sentiment:.2f}")
    
    # Детали по активированным
    activated_results = [r for r in results if r['activated']]
    if activated_results:
        print(f"\nАктивированные SHORT:")
        for r in activated_results:
            print(f"  - {r['scenario']}: скор {r['score']:.3f}")
    
    return results


if __name__ == "__main__":
    # Запускаем мини-бэктест
    results = run_mini_backtest()
    
    print(f"\n🎯 ЗАКЛЮЧЕНИЕ")
    print("SHORT v2.2 успешно реализован с улучшениями:")
    print("✅ Адаптивные пороги по фазам рынка")
    print("✅ Market Sentiment Index")
    print("✅ ADX подтверждение тренда") 
    print("✅ Pivot Points для разворота")
    print("✅ Динамические веса факторов")
    print("✅ Усиленная фильтрация активации")
