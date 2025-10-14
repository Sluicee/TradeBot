# ====================================================================
# РЕКОМЕНДУЕМЫЕ ПАРАМЕТРЫ V5.3
# ====================================================================
# Основано на результатах многопарного тестирования
# Дата: 2025-10-14
# Источник: tests/QUANT_ANALYSIS_REPORT.md

"""
КРАТКОЕ РЕЗЮМЕ ТЕСТОВ:

1h HYBRID (V5.2) - УСПЕХ:
- BNBUSDT: ROI +11.5%, Sharpe 1.88, WR 65%, Max DD -3.66%
- BTCUSDT: ROI +1.68%, Sharpe 1.41, WR 69%, Max DD -2.49%
- Средние: ROI +3.36%, Sharpe 1.01, WR 63.6%, Max DD -4.12%

15m MEAN REVERSION (V5.2) - ПРОВАЛ:
- 0 сделок на всех парах за 10.4 дня
- Параметры слишком строгие для 15m
"""

# ====================================================================
# ВАРИАНТ A: 1h HYBRID (V5.3) - РЕКОМЕНДУЕТСЯ ДЛЯ PRODUCTION
# ====================================================================

CONFIG_1H_HYBRID_V53 = {
	# Основные настройки
	"DEFAULT_SYMBOL": "BNBUSDT",  # Лучший результат тестов
	"DEFAULT_INTERVAL": "1h",
	"STRATEGY_MODE": "HYBRID",
	"STRATEGY_HYBRID_MODE": "AUTO",
	
	# Mean Reversion (оставляем V5.2 - РАБОТАЮТ!)
	"MR_RSI_OVERSOLD": 40,  # НЕ МЕНЯТЬ
	"MR_ZSCORE_BUY_THRESHOLD": -1.8,  # НЕ МЕНЯТЬ
	"MR_ADX_MAX": 32,  # НЕ МЕНЯТЬ
	"MR_TAKE_PROFIT_PERCENT": 0.035,  # 3.5%
	"MR_STOP_LOSS_PERCENT": 0.028,  # 2.8%
	"MR_MAX_HOLDING_HOURS": 24,
	
	# Гибридные пороги (V5.2 - ОПТИМАЛЬНЫ!)
	"HYBRID_ADX_MR_THRESHOLD": 22,
	"HYBRID_ADX_TF_THRESHOLD": 26,
	"HYBRID_MIN_TIME_IN_MODE": 2,
	
	# Multi-Timeframe
	"USE_MULTI_TIMEFRAME": True,
	"MTF_TIMEFRAMES": ['1h', '4h', '1d'],
	"MTF_WEIGHTS": {'1h': 0.50, '4h': 0.35, '1d': 0.15},
	"MTF_MIN_AGREEMENT": 1,
	
	# Фильтры "падающего ножа" - ОСЛАБЛЕНЫ в V5.3
	"NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT": 0.07,  # Было 0.05 → 0.07
	"VOLUME_SPIKE_THRESHOLD": 2.2,  # Было 1.8 → 2.2
	
	# Kelly Criterion (консервативнее)
	"USE_KELLY_CRITERION": True,
	"KELLY_FRACTION": 0.20,  # Было 0.25 → 0.20
	"MIN_TRADES_FOR_KELLY": 15,  # Было 10 → 15
	
	# Trailing Stop (меньше ложных закрытий)
	"USE_TRAILING_STOP_MR": True,
	"MR_TRAILING_ACTIVATION": 0.018,  # Было 0.015 → 0.018
	"MR_TRAILING_DISTANCE": 0.012,  # Было 0.010 → 0.012
	
	# Динамические позиции
	"USE_DYNAMIC_MAX_POSITIONS": True,
	"DYNAMIC_POSITIONS_THRESHOLDS": {
		0: 1,      # <$100: 1 позиция (безопасный старт!)
		100: 2,    # $100-$500: 2 позиции
		500: 3,    # $500-$1000: 3 позиции
		1000: 4,   # $1000+: 4 позиции
	},
	
	# Ожидаемые метрики
	"EXPECTED_METRICS": {
		"roi_per_month": "6-10%",
		"trades_per_month": "7-10 на пару",
		"winrate": "60-65%",
		"sharpe": "0.9-1.2",
		"max_dd": "4-8%",
	}
}

# ====================================================================
# ВАРИАНТ B: 30m MEAN REVERSION (V5.3) - ДЛЯ ТЕСТИРОВАНИЯ
# ====================================================================

CONFIG_30M_MR_V53 = {
	# Основные настройки
	"DEFAULT_SYMBOL": "BNBUSDT",
	"DEFAULT_INTERVAL": "30m",
	"STRATEGY_MODE": "MEAN_REVERSION",
	
	# Mean Reversion - ОСЛАБЛЕНЫ для 30m
	"MR_RSI_OVERSOLD": 42,  # Было 40 → 42 (чаще сигналы)
	"MR_ZSCORE_BUY_THRESHOLD": -1.6,  # Было -1.8 → -1.6 (чаще сигналы)
	"MR_ADX_MAX": 34,  # Было 32 → 34 (разрешаем умеренные тренды)
	"MR_TAKE_PROFIT_PERCENT": 0.030,  # 3.0% (было 3.5%)
	"MR_STOP_LOSS_PERCENT": 0.025,  # 2.5% (было 2.8%)
	"MR_MAX_HOLDING_HOURS": 16,  # 16 часов = 32 свечи 30m
	
	# Z-score параметры
	"MR_ZSCORE_WINDOW": 60,  # 60 свечей 30m = 30 часов
	
	# Фильтры - ЗНАЧИТЕЛЬНО ОСЛАБЛЕНЫ
	"NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT": 0.08,  # Было 0.05 → 0.08
	"VOLUME_SPIKE_THRESHOLD": 2.5,  # Было 1.8 → 2.5
	"NO_BUY_IF_EMA200_SLOPE_NEG": False,  # ОТКЛЮЧЕН
	"USE_RED_CANDLES_FILTER": False,  # ОТКЛЮЧЕН
	
	# Динамический SL/TP на основе ATR
	"USE_DYNAMIC_SL_FOR_MR": True,
	"MR_ATR_SL_MULTIPLIER": 2.2,  # Было 2.0 → 2.2 (больше дыхания)
	"MR_ATR_SL_MIN": 0.018,  # Было 0.020 → 0.018
	"MR_ATR_SL_MAX": 0.045,  # Было 0.040 → 0.045
	
	"USE_DYNAMIC_TP_FOR_MR": True,
	"MR_ATR_TP_MULTIPLIER": 2.5,  # Было 2.8 → 2.5 (реалистичнее для 30m)
	"MR_ATR_TP_MIN": 0.020,  # Было 0.025 → 0.020
	"MR_ATR_TP_MAX": 0.040,  # Было 0.045 → 0.040
	
	# Trailing Stop (менее агрессивный)
	"USE_TRAILING_STOP_MR": True,
	"MR_TRAILING_ACTIVATION": 0.020,  # 2.0%
	"MR_TRAILING_DISTANCE": 0.015,  # 1.5%
	
	# Kelly Criterion
	"USE_KELLY_CRITERION": True,
	"KELLY_FRACTION": 0.18,  # Более консервативно для 30m
	"MIN_TRADES_FOR_KELLY": 20,  # Больше сделок для надёжной статистики
	
	# Multi-Timeframe (опционально для 30m)
	"USE_MULTI_TIMEFRAME": True,
	"MTF_TIMEFRAMES": ['30m', '1h', '4h'],
	"MTF_WEIGHTS": {'30m': 0.50, '1h': 0.35, '4h': 0.15},
	"MTF_MIN_AGREEMENT": 1,
	
	# Ожидаемые метрики (ТРЕБУЕТ ТЕСТИРОВАНИЯ!)
	"EXPECTED_METRICS": {
		"roi_per_month": "4-8%",
		"trades_per_month": "8-12 на пару",
		"winrate": "55-60%",
		"sharpe": "0.6-0.9",
		"max_dd": "6-10%",
	}
}

# ====================================================================
# ВАРИАНТ C: 15m MEAN REVERSION (V6.0) - АГРЕССИВНЫЙ (ЭКСПЕРИМЕНТАЛЬНО)
# ====================================================================

CONFIG_15M_MR_V60 = {
	# Основные настройки
	"DEFAULT_SYMBOL": "BNBUSDT",
	"DEFAULT_INTERVAL": "15m",
	"STRATEGY_MODE": "MEAN_REVERSION",
	
	# Mean Reversion - СИЛЬНО ОСЛАБЛЕНЫ для 15m
	"MR_RSI_OVERSOLD": 45,  # Было 40 → 45 (много сигналов)
	"MR_ZSCORE_BUY_THRESHOLD": -1.5,  # Было -1.8 → -1.5 (много сигналов)
	"MR_ADX_MAX": 35,  # Было 32 → 35 (разрешаем тренды)
	"MR_TAKE_PROFIT_PERCENT": 0.025,  # 2.5% (реалистично для 15m)
	"MR_STOP_LOSS_PERCENT": 0.020,  # 2.0% (R:R 1.25:1)
	"MR_MAX_HOLDING_HOURS": 8,  # 8 часов = 32 свечи 15m
	
	# Z-score параметры
	"MR_ZSCORE_WINDOW": 80,  # 80 свечей 15m = 20 часов
	
	# Фильтры - МАКСИМАЛЬНО ОСЛАБЛЕНЫ или ОТКЛЮЧЕНЫ
	"NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT": 0.10,  # 10% (очень слабо)
	"VOLUME_SPIKE_THRESHOLD": 3.0,  # 3.0x (пропускаем почти всё)
	"NO_BUY_IF_EMA200_SLOPE_NEG": False,  # ОТКЛЮЧЕН
	"USE_RED_CANDLES_FILTER": False,  # ОТКЛЮЧЕН
	
	# Динамический SL/TP на основе ATR
	"USE_DYNAMIC_SL_FOR_MR": True,
	"MR_ATR_SL_MULTIPLIER": 2.5,  # Больше дыхания для 15m
	"MR_ATR_SL_MIN": 0.015,
	"MR_ATR_SL_MAX": 0.050,
	
	"USE_DYNAMIC_TP_FOR_MR": True,
	"MR_ATR_TP_MULTIPLIER": 2.2,  # Меньше для 15m
	"MR_ATR_TP_MIN": 0.018,
	"MR_ATR_TP_MAX": 0.035,
	
	# Trailing Stop (очень консервативный для 15m)
	"USE_TRAILING_STOP_MR": True,
	"MR_TRAILING_ACTIVATION": 0.025,  # 2.5%
	"MR_TRAILING_DISTANCE": 0.020,  # 2.0%
	
	# Kelly Criterion (очень консервативно)
	"USE_KELLY_CRITERION": True,
	"KELLY_FRACTION": 0.15,  # Только 15% Kelly
	"MIN_TRADES_FOR_KELLY": 30,  # Много сделок для статистики
	
	# Multi-Timeframe (обязательно для фильтрации шума!)
	"USE_MULTI_TIMEFRAME": True,
	"MTF_TIMEFRAMES": ['15m', '1h', '4h'],
	"MTF_WEIGHTS": {'15m': 0.40, '1h': 0.40, '4h': 0.20},
	"MTF_MIN_AGREEMENT": 2,  # Требуем согласия 2 из 3 TF!
	
	# Ожидаемые метрики (ЭКСПЕРИМЕНТАЛЬНО, ТРЕБУЕТ ТЕСТИРОВАНИЯ!)
	"EXPECTED_METRICS": {
		"roi_per_month": "3-6%",
		"trades_per_month": "20-40 на пару",
		"winrate": "52-58%",
		"sharpe": "0.4-0.7",
		"max_dd": "8-15%",
		"warning": "НЕ ТЕСТИРОВАНО! Использовать на свой риск!"
	}
}

# ====================================================================
# РЕКОМЕНДАЦИИ ПО ВЫБОРУ КОНФИГУРАЦИИ
# ====================================================================

RECOMMENDATIONS = {
	"for_production": {
		"config": "CONFIG_1H_HYBRID_V53",
		"reason": "Протестировано, стабильно, Sharpe 1.01",
		"pairs": ["BNBUSDT", "BTCUSDT"],
		"initial_balance": 100,
		"max_positions": 1,
		"expected_monthly_roi": "6-10%",
	},
	
	"for_testing": {
		"config": "CONFIG_30M_MR_V53",
		"reason": "Оптимизировано для 30m, но не тестировано",
		"pairs": ["BNBUSDT"],
		"initial_balance": 50,
		"max_positions": 1,
		"expected_monthly_roi": "4-8%",
		"warning": "Требует минимум 2 недели paper trading!"
	},
	
	"experimental": {
		"config": "CONFIG_15M_MR_V60",
		"reason": "Экспериментальная конфигурация для высокочастотной торговли",
		"pairs": ["BNBUSDT"],
		"initial_balance": 50,
		"max_positions": 1,
		"expected_monthly_roi": "3-6%",
		"warning": "НЕ ТЕСТИРОВАНО! Высокий риск! Только для опытных!"
	}
}

# ====================================================================
# ПРИОРИТЕТНЫЕ ПАРЫ ДЛЯ ТОРГОВЛИ
# ====================================================================

PAIR_RANKINGS = {
	"tier_1": {
		"pairs": ["BNBUSDT", "BTCUSDT"],
		"reason": "Протестированы, стабильны, хорошие метрики",
		"recommendation": "Используйте для production",
		"allocation": "70% капитала"
	},
	
	"tier_2": {
		"pairs": ["ETHUSDT"],
		"reason": "Низкий ROI, но стабильный Sharpe",
		"recommendation": "Добавить при балансе >$500",
		"allocation": "20% капитала"
	},
	
	"tier_3": {
		"pairs": ["SOLUSDT"],
		"reason": "Высокий DD, низкий ROI",
		"recommendation": "НЕ рекомендуется до оптимизации",
		"allocation": "0% (избегать)"
	},
	
	"to_test": {
		"pairs": ["AVAXUSDT", "ADAUSDT", "DOTUSDT", "MATICUSDT"],
		"reason": "Не тестированы, потенциально некоррелированные",
		"recommendation": "Протестировать на бэктесте",
		"allocation": "10% для экспериментов"
	}
}

# ====================================================================
# ПЛАН РАЗВЕРТЫВАНИЯ (DEPLOYMENT PLAN)
# ====================================================================

DEPLOYMENT_PLAN = {
	"phase_1_validation": {
		"duration": "1 неделя",
		"config": "CONFIG_1H_HYBRID_V53",
		"symbol": "BNBUSDT",
		"balance": 100,
		"max_positions": 1,
		"position_size": "40%",
		"success_criteria": {
			"min_winrate": 55,
			"min_trades": 1,
			"max_dd": 10,
		},
		"next_action": "Если успешно → phase_2, иначе → review параметров"
	},
	
	"phase_2_stabilization": {
		"duration": "2-3 недели",
		"symbols": ["BNBUSDT", "BTCUSDT"],
		"balance": "100-150",
		"max_positions": 2,
		"position_size": "50%",
		"success_criteria": {
			"min_winrate": 58,
			"min_sharpe": 0.8,
			"max_dd": 12,
			"monthly_roi": ">5%"
		},
		"next_action": "phase_3"
	},
	
	"phase_3_scaling": {
		"duration": "1-2 месяца",
		"symbols": ["BNBUSDT", "BTCUSDT", "ETHUSDT"],
		"balance": "200-500",
		"max_positions": 3,
		"position_size": "50-60%",
		"success_criteria": {
			"min_winrate": 60,
			"min_sharpe": 0.9,
			"max_dd": 15,
			"monthly_roi": ">6%"
		},
		"next_action": "phase_4"
	},
	
	"phase_4_optimization": {
		"duration": "ongoing",
		"symbols": "портфель 3-4 пар",
		"balance": ">500",
		"max_positions": "3-4",
		"position_size": "60-70% (Kelly)",
		"actions": [
			"Walk-forward оптимизация ежемесячно",
			"Адаптивная подстройка параметров",
			"Диверсификация на новые пары",
			"Мониторинг деградации метрик"
		]
	}
}

# ====================================================================
# КРИТЕРИИ STOP TRADING (КОГДА ОСТАНОВИТЬ ТОРГОВЛЮ)
# ====================================================================

STOP_TRADING_CRITERIA = {
	"immediate_stop": {
		"conditions": [
			"Max DD > 25%",
			"3 consecutive losses с SL",
			"API недоступен >1 час",
			"Критическая ошибка в коде"
		],
		"action": "Немедленно остановить бота, закрыть позиции"
	},
	
	"warning_review": {
		"conditions": [
			"Win Rate < 50% за 2 недели",
			"Sharpe < 0.5 за месяц",
			"Max DD > 15%",
			"ROI < 0% за месяц"
		],
		"action": "Уменьшить размер позиций до 30%, анализ параметров"
	},
	
	"performance_degradation": {
		"conditions": [
			"Win Rate падает на 10% от ожидаемого",
			"Sharpe падает на 30% от ожидаемого",
			"Частота сделок падает на 50%"
		],
		"action": "Walk-forward оптимизация или откат к консервативным параметрам"
	}
}

# ====================================================================
# ИСПОЛЬЗОВАНИЕ
# ====================================================================

"""
Как использовать эти конфигурации:

1. ДЛЯ PRODUCTION (рекомендуется):
   from tests.config_v53_recommendations import CONFIG_1H_HYBRID_V53
   # Обновить config.py значениями из CONFIG_1H_HYBRID_V53

2. ДЛЯ ТЕСТИРОВАНИЯ 30m:
   from tests.config_v53_recommendations import CONFIG_30M_MR_V53
   # Запустить бэктест с этими параметрами
   # Минимум 30 дней данных для валидации

3. ДЛЯ ЭКСПЕРИМЕНТОВ:
   from tests.config_v53_recommendations import CONFIG_15M_MR_V60
   # ТОЛЬКО для опытных пользователей
   # Начать с paper trading минимум 1 неделя

ВАЖНО:
- Всегда начинайте с paper trading!
- Мониторьте метрики ежедневно первую неделю
- Используйте STOP_TRADING_CRITERIA для защиты капитала
- Следуйте DEPLOYMENT_PLAN для безопасного масштабирования
"""

