import os
import dotenv
import sys

dotenv.load_dotenv()

# ====================================================================
# TELEGRAM BOT
# ====================================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")  # ID владельца бота

# Настройки по умолчанию (захардкожены в конфиге)
DEFAULT_SYMBOL = "BNBUSDT"  # Лучший результат в тестах: +11.5% за 41.7 дней
DEFAULT_INTERVAL = "1h"  # 1h для Hybrid Strategy (оптимально)

# Настройки фонового мониторинга
POLL_INTERVAL = 60  # Базовый интервал проверки сигналов (секунды)
POLL_INTERVAL_MIN = 60  # Минимальный интервал при низкой волатильности
POLL_INTERVAL_MAX = 300  # Максимальный интервал при высокой волатильности (5 минут)
VOLATILITY_WINDOW = 10  # Окно для детекции волатильности (свечей)
VOLATILITY_THRESHOLD = 0.05  # Порог волатильности для алерта (5%)
POLL_VOLATILITY_HIGH_THRESHOLD = 0.08  # Порог высокой волатильности (8%) - увеличиваем интервал
POLL_VOLATILITY_LOW_THRESHOLD = 0.02  # Порог низкой волатильности (2%) - можно проверять чаще
VOLATILITY_ALERT_COOLDOWN = 600  # Cooldown для повторных уведомлений о волатильности (10 минут)

# ====================================================================
# ИНДИКАТОРЫ (SignalGenerator)
# ====================================================================

# Параметры скользящих средних
SMA_PERIODS = [20, 50, 200]  # Периоды для SMA
EMA_PERIODS = [20, 50, 200]  # Периоды для EMA

# Основные EMA для пересечений
EMA_SHORT_WINDOW = 12
EMA_LONG_WINDOW = 26

# RSI
RSI_WINDOW = 14
RSI_OVERSOLD = 30  # Порог перепроданности
RSI_OVERSOLD_NEAR = 40  # Близко к перепроданности
RSI_OVERBOUGHT = 70  # Порог перекупленности
RSI_OVERBOUGHT_NEAR = 60  # Близко к перекупленности
RSI_BUY_RANGE = (30, 70)  # Диапазон для входа в BUY
RSI_SELL_RANGE = (30, 70)  # Диапазон для входа в SELL

# MACD
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# ADX (сила тренда)
ADX_WINDOW = 14
ADX_TRENDING = 30  # Порог сильного тренда
ADX_RANGING = 20  # Порог флэта (ADX < 20)
ADX_STRONG = 25  # Порог для фильтра сильного тренда (ADX >= 25)
ADX_MODERATE = 20  # Минимальный порог тренда (ADX >= 20) - отличается от RANGING по направлению

# Stochastic
STOCH_WINDOW = 14
STOCH_SMOOTH_WINDOW = 3
STOCH_OVERSOLD = 20
STOCH_OVERBOUGHT = 80

# ATR (волатильность)
ATR_WINDOW = 14

# Volume
VOLUME_MA_WINDOW = 20
VOLUME_HIGH_RATIO = 1.5  # Высокий объем (150% от среднего)
VOLUME_MODERATE_RATIO = 1.2  # Умеренно высокий объем (120%)
VOLUME_LOW_RATIO = 0.7  # Низкий объем (70%)

# ====================================================================
# ВЕСА И ПОРОГИ ГОЛОСОВАНИЯ
# ====================================================================

# Веса индикаторов в зависимости от режима рынка
TRENDING_TREND_WEIGHT = 3  # Вес трендовых индикаторов в тренде
TRENDING_OSCILLATOR_WEIGHT = 1  # Вес осцилляторов в тренде

RANGING_TREND_WEIGHT = 1  # Вес трендовых индикаторов во флэте
RANGING_OSCILLATOR_WEIGHT = 2  # Вес осцилляторов во флэте

TRANSITIONING_TREND_WEIGHT = 2  # Вес трендовых индикаторов при переходе
TRANSITIONING_OSCILLATOR_WEIGHT = 2  # Вес осцилляторов при переходе

# Пороги голосования для генерации сигнала
VOTE_THRESHOLD_TRENDING = 2  # Порог в трендовом рынке
VOTE_THRESHOLD_RANGING = 4  # Порог во флэте
VOTE_THRESHOLD_TRANSITIONING = 3  # Порог при переходе

# Минимальное количество пройденных фильтров для сигнала
MIN_FILTERS = 3  # Из 5 возможных фильтров

# ====================================================================
# PAPER TRADING & BACKTEST
# ====================================================================

# Комиссия биржи
COMMISSION_RATE = 0.0018  # 0.18%

# Управление позициями
MAX_POSITIONS = 3  # Базовое максимальное количество одновременных позиций (используется как fallback)
INITIAL_BALANCE = 100.0  # Начальный баланс для paper trading

# Динамическое изменение MAX_POSITIONS на основе баланса
USE_DYNAMIC_MAX_POSITIONS = True  # Включить динамический расчет максимального количества позиций
DYNAMIC_POSITIONS_THRESHOLDS = {
	# баланс: макс_позиций
	0: 2,        # <$100: 2 позиции (консервативно)
	100: 3,      # $100-$500: 3 позиции (базовый режим)
	500: 4,      # $500-$1000: 4 позиции
	1000: 5,     # $1000-$2000: 5 позиций
	2000: 6,     # $2000+: 6 позиций (максимум)
}
MAX_DYNAMIC_POSITIONS_LIMIT = 6  # Абсолютный максимум позиций независимо от баланса

# ====================================================================
# KELLY CRITERION
# ====================================================================

# Использовать Kelly Criterion для оптимального размера позиции
USE_KELLY_CRITERION = True
KELLY_FRACTION = 0.2  # Четверть Kelly для консервативности (0.25 = 25%)
MIN_TRADES_FOR_KELLY = 15  # Минимум сделок для расчёта Kelly
KELLY_LOOKBACK_WINDOW = 50  # Скользящее окно последних N сделок

# ====================================================================
# УМНОЕ ДОКУПАНИЕ (AVERAGING)
# ====================================================================

# Включить умное докупание/пирамидинг
ENABLE_AVERAGING = True
MAX_AVERAGING_ATTEMPTS = 2  # Максимум 2-3 докупания на позицию
AVERAGING_PRICE_DROP_PERCENT = 0.05  # Докупаем при падении на 5%
AVERAGING_TIME_THRESHOLD_HOURS = 24  # Время для триггера докупания (24 часа)
MAX_TOTAL_RISK_MULTIPLIER = 1.5  # Общий риск не более 1.5× базового

# Пирамидинг вверх при сильном тренде
ENABLE_PYRAMID_UP = True
PYRAMID_ADX_THRESHOLD = 25  # Порог ADX для пирамидинга вверх
AVERAGING_SIZE_PERCENT = 0.5  # Размер докупания (50% от исходного)

# Стоп-лосс и тейк-профит
STOP_LOSS_PERCENT = 0.05  # 5% стоп-лосс (базовый)
TAKE_PROFIT_PERCENT = 0.10  # 10% тейк-профит
PARTIAL_CLOSE_PERCENT = 0.50  # Закрываем 50% позиции на TP
TRAILING_STOP_PERCENT = 0.02  # 2% trailing stop после частичного закрытия

# Динамический стоп-лосс на основе ATR
DYNAMIC_SL_ATR_MULTIPLIER = 2.5  # 2.5x ATR для расчета SL (увеличено для 15m)
DYNAMIC_SL_MIN = 0.02  # Минимум 2% (снижено)
DYNAMIC_SL_MAX = 0.08  # Максимум 8%

# Размеры позиций по силе сигнала
POSITION_SIZE_STRONG = 0.70  # 70% для сильного сигнала (>= 9 голосов)
POSITION_SIZE_MEDIUM = 0.50  # 50% для среднего сигнала (>= 6 голосов)
POSITION_SIZE_WEAK = 0.30  # 30% для слабого сигнала
SIGNAL_STRENGTH_STRONG = 9  # Порог для сильного сигнала
SIGNAL_STRENGTH_MEDIUM = 6  # Порог для среднего сигнала

# Корректировка размера позиции на волатильность
VOLATILITY_HIGH_THRESHOLD = 3.0  # ATR > 3% - высокая волатильность
VOLATILITY_LOW_THRESHOLD = 1.0  # ATR < 1% - низкая волатильность
VOLATILITY_ADJUSTMENT_MAX = 1.2  # Максимальное увеличение размера

# Время удержания позиции
MAX_HOLDING_HOURS = 72  # Максимум 72 часа (3 дня) для Trend Following
# MR_MAX_HOLDING_HOURS задан ниже в секции Mean Reversion (строка 222)

# Partial Take Profit (v5.1 улучшение)
USE_PARTIAL_TP = True  # Включить частичное закрытие позиции
PARTIAL_TP_PERCENT = 0.5  # Закрывать 50% позиции
PARTIAL_TP_TRIGGER = 0.015  # На +2% прибыли
PARTIAL_TP_REMAINING_TP = 0.03  # TP для оставшихся 50%: +4%

# ====================================================================
# СТАТИСТИЧЕСКИЕ МОДЕЛИ
# ====================================================================

# Включить статистические модели (Bayesian, Z-score, Markov)
USE_STATISTICAL_MODELS = False  # По умолчанию выключено (требует обучения)

# Bayesian Decision Layer
BAYESIAN_MIN_PROBABILITY = 0.55  # Минимальная вероятность успеха для входа (55%)
BAYESIAN_MIN_SAMPLES = 10  # Минимальное количество сигналов для надёжной статистики

# Z-Score Mean Reversion (для статистических моделей, если USE_STATISTICAL_MODELS = True)
ZSCORE_WINDOW = 50  # Окно для расчёта среднего
ZSCORE_BUY_THRESHOLD = -2.0  # Порог покупки (цена сильно ниже среднего)
ZSCORE_SELL_THRESHOLD = 2.0  # Порог продажи (цена сильно выше среднего)
# Для основной MR стратегии используются MR_ZSCORE_* параметры (строка 208+)

# Markov Regime Switching
MARKOV_WINDOW = 50  # Окно для анализа режима
MARKOV_VOL_HIGH = 0.03  # Порог высокой волатильности (3%)
MARKOV_VOL_LOW = 0.01  # Порог низкой волатильности (1%)
MARKOV_TREND_THRESHOLD = 0.02  # Порог тренда (2%)

# Ensemble Decision Maker (веса моделей)
ENSEMBLE_BAYESIAN_WEIGHT = 0.4  # Вес Bayesian модели (40%)
ENSEMBLE_ZSCORE_WEIGHT = 0.3  # Вес Z-score модели (30%)
ENSEMBLE_REGIME_WEIGHT = 0.3  # Вес Regime модели (30%)

# ====================================================================
# MEAN REVERSION STRATEGY
# ====================================================================

# Режим работы стратегии
STRATEGY_MODE = "HYBRID"  # "TREND_FOLLOWING", "MEAN_REVERSION", или "HYBRID"

# Параметры Mean Reversion v5.2 (РЕАЛИСТИЧНЫЕ ДЛЯ 1h - ПРОТЕСТИРОВАНЫ)
MR_RSI_OVERSOLD = 40  # Порог перепроданности (вернули v4 - оптимально!)
MR_RSI_EXIT = 52  # Порог выхода (небольшой momentum)
MR_ZSCORE_BUY_THRESHOLD = -1.8  # Z-score порог покупки (вернули v4)
MR_ZSCORE_SELL_THRESHOLD = 0.4  # Z-score порог выхода
MR_ZSCORE_STRONG_BUY = -2.3  # Сильная перепроданность для 70% позиции
MR_ADX_MAX = 32  # Максимальный ADX (компромисс 30-35)
MR_EMA_DIVERGENCE_MAX = 0.02  # Максимальная дивергенция EMA (2%) - флэт

# Размеры позиций для Mean Reversion v4
MR_POSITION_SIZE_STRONG = 0.70  # 70% для сильной перепроданности (RSI<25, Z<-2.3)
MR_POSITION_SIZE_MEDIUM = 0.50  # 50% для умеренной перепроданности (RSI<35, Z<-2.0)
MR_POSITION_SIZE_WEAK = 0.35  # 35% для слабой перепроданности (было 30%, увеличено)

# TP/SL для Mean Reversion v5 (улучшенный R:R)
MR_TAKE_PROFIT_PERCENT = 0.035  # 3.5% тейк-профит (улучшен R:R)
MR_STOP_LOSS_PERCENT = 0.028  # 2.8% стоп-лосс (оптимизирован)
MR_MAX_HOLDING_HOURS = 24  # Максимум 24 часа удержания (было 48h, уменьшено для быстрого выхода)

# Z-score параметры для MR
MR_ZSCORE_WINDOW = 50  # Окно для расчёта среднего

# Фильтры "падающего ножа" v5.3 (СМЯГЧЕНЫ для больше трейдов)
NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT = 0.10  # v5.3: Не входить только если цена < min(24h) * 0.90 (было 0.07)
NO_BUY_IF_EMA200_SLOPE_NEG = False  # v5.2: ОТКЛЮЧЕН! (блокировал 100% сигналов)
EMA200_NEG_SLOPE_THRESHOLD = -0.005  # -0.5% наклон EMA200 (смягчено, не используется)
USE_RED_CANDLES_FILTER = False  # v5: ОТКЛЮЧЕН (позволяет ловить ранние bounces)

# Фильтр объёма v5.3 (смягчён)
USE_VOLUME_FILTER = True  # v5: Блокировать входы при всплесках объёма
VOLUME_SPIKE_THRESHOLD = 3.0  # v5.3: Не входить если volume > 3.0x средний за 24h (было 2.2, смягчили)

# Динамический SL на основе ATR v5
USE_DYNAMIC_SL_FOR_MR = True  # Использовать ATR-based SL вместо фиксированного
MR_ATR_SL_MULTIPLIER = 2.0  # Множитель ATR для SL (2.0x ATR, консервативнее)
MR_ATR_SL_MIN = 0.02  # Минимальный SL 2%
MR_ATR_SL_MAX = 0.04  # Максимальный SL 4%

# Адаптивный SL v5 (ОТКЛЮЧЕН - не работал в v4)
ADAPTIVE_SL_ON_RISK = False  # v5: ОТКЛЮЧЕН (не эффективен, лучше блокировать вход)
ADAPTIVE_SL_MULTIPLIER = 1.5  # Увеличить SL на 50% при риске (не используется)

# Динамический TP v5
USE_DYNAMIC_TP_FOR_MR = True  # Использовать динамический TP на основе ATR
MR_ATR_TP_MULTIPLIER = 2.8  # 2.8x ATR для TP (реалистичнее для 1h)
MR_ATR_TP_MIN = 0.025  # Минимум 2.5%
MR_ATR_TP_MAX = 0.045  # Максимум 4.5%

# Трейлинг стоп для MR v5 (менее агрессивный для 1h)
USE_TRAILING_STOP_MR = True  # Включить трейлинг стоп после прибыли
MR_TRAILING_ACTIVATION = 0.015  # v5: Активация после +1.5% (устойчивее к шуму)
MR_TRAILING_DISTANCE = 0.010  # v5: 1.0% от максимума (баланс)

# Агрессивный трейлинг v5 (после сильной прибыли)
MR_TRAILING_AGGRESSIVE_ACTIVATION = 0.03  # После +3% прибыли
MR_TRAILING_AGGRESSIVE_DISTANCE = 0.008  # 0.8% от максимума

# ====================================================================
# ГИБРИДНАЯ СТРАТЕГИЯ (MR + TF с переключением по ADX)
# ====================================================================

STRATEGY_HYBRID_MODE = "AUTO"  # "AUTO" (переключение по ADX), "MR_ONLY", "TF_ONLY"

# Пороги ADX для переключения режимов (v5.7: агрессивные пороги для низкой волатильности)
HYBRID_ADX_MR_THRESHOLD = 15  # ADX < 15 → Mean Reversion (боковик)
HYBRID_ADX_MR_EXIT = 20  # ADX > 20 → Выход из MR в TF (гистерезис)
HYBRID_ADX_TF_THRESHOLD = 18  # ADX > 18 → Trend Following (тренд)
HYBRID_ADX_TF_EXIT = 15  # ADX < 15 → Выход из TF в MR (гистерезис)
# 15 <= ADX <= 18 → переходная зона 3 пункта (агрессивно)

HYBRID_TRANSITION_MODE = "HOLD"  # "HOLD" (не входить) или "LAST" (использовать последний режим)

# Минимальное время в режиме (защита от частого переключения)
HYBRID_MIN_TIME_IN_MODE = 0.1  # v5.6: 6 минут минимум (быстрое переключение)

# ====================================================================
# MULTI-TIMEFRAME ANALYSIS
# ====================================================================

# Использовать multi-timeframe анализ (1h, 4h, 1d) - оптимизировано для 1h
USE_MULTI_TIMEFRAME = True

# Таймфреймы для анализа (от меньшего к большему) - v5
MTF_TIMEFRAMES = ['1h', '4h', '1d']

# Веса для weighted voting (сумма должна быть 1.0) - v5
MTF_WEIGHTS = {
	'1h': 0.50,   # Основной таймфрейм (главный сигнал)
	'4h': 0.35,   # Среднесрочный тренд (подтверждение)
	'1d': 0.15    # Долгосрочный фильтр (защита от противотренда)
}

# Минимальное количество согласованных таймфреймов для входа - v5.1
MTF_MIN_AGREEMENT = 1  # Минимум 1 из 3 TF (используем weighted voting)

# Бонус за полное согласие всех таймфреймов
MTF_FULL_ALIGNMENT_BONUS = 1.5  # Увеличить силу сигнала на 50% если все 3 TF согласны

# ====================================================================
# API
# ====================================================================

# Таймаут для API запросов
API_TIMEOUT = 30  # секунд

# ====================================================================
# SHORT-МЕХАНИКА v2.1 - ADAPTIVE FEAR SHORT
# ====================================================================

# Включить расширенную SHORT-механику v2.1
USE_ADVANCED_SHORT = True
SHORT_VERSION = "2.1"  # Версия для логирования

# Адаптивные размеры позиций на основе уровня страха (v2.1)
SHORT_POSITION_SIZE_EXTREME_FEAR = 0.8    # < 20 (экстремальный страх)
SHORT_POSITION_SIZE_HIGH_FEAR = 0.5       # 20-35 (высокий страх)
SHORT_POSITION_SIZE_MODERATE_FEAR = 0.25  # 35-45 (умеренный страх) - увеличено
SHORT_POSITION_SIZE_NEUTRAL = 0.1         # > 45 (нейтрально) - увеличено

# Пороги для определения уровня страха (v2.1 - более чувствительные)
SHORT_FEAR_EXTREME_THRESHOLD = 20
SHORT_FEAR_HIGH_THRESHOLD = 35
SHORT_FEAR_MODERATE_THRESHOLD = 45  # Увеличено с 40 до 45

# Inertia buffer для последовательного страха
SHORT_FEAR_INERTIA_THRESHOLD = 30  # Если страх < 30
SHORT_FEAR_INERTIA_CANDLES = 3     # В течение 3 свечей подряд
SHORT_FEAR_INERTIA_BONUS = 0.1     # Бонус к скору

# Веса для составного скора SHORT v2.1 (сумма должна быть 1.0)
SHORT_FEAR_WEIGHT = 0.25         # Индекс страха (уменьшено с 0.3)
SHORT_FUNDING_WEIGHT = 0.15      # Funding Rate (уменьшено с 0.2)
SHORT_LIQUIDATION_WEIGHT = 0.2   # Ликвидации (без изменений)
SHORT_RSI_WEIGHT = 0.2           # RSI перекупленность (без изменений)
SHORT_EMA_WEIGHT = 0.1           # EMA тренд (без изменений)
SHORT_VOLATILITY_WEIGHT = 0.1    # Волатильность (новое)

# Минимальный скор для активации SHORT (v2.1 - более чувствительный)
SHORT_MIN_SCORE = 0.55  # Уменьшено с 0.6 до 0.55

# Волатильность как фильтр
SHORT_VOLATILITY_MULTIPLIER = 1.2  # ATR > 1.2x среднего
SHORT_VOLATILITY_BONUS = 0.1       # Бонус за высокую волатильность

# BTC Dominance фильтр
SHORT_BTC_DOMINANCE_THRESHOLD = 1.0  # Рост доминирования BTC в %
SHORT_BTC_DOMINANCE_FEAR_THRESHOLD = 30  # При страхе < 30
SHORT_BTC_DOMINANCE_BONUS = 0.1         # Бонус за рост доминирования

# API настройки для внешних данных
SHORT_API_TIMEOUT = 5  # Таймаут для API запросов (секунды)
SHORT_FUNDING_RATE_THRESHOLD = 0.0  # Отрицательный funding rate усиливает SHORT
SHORT_LIQUIDATION_RATIO_THRESHOLD = 1.5  # Long/Short ликвидации > 1.5x

# Fallback значения при недоступности API
SHORT_FALLBACK_FUNDING_RATE = 0.0
SHORT_FALLBACK_LONG_LIQUIDATIONS = 0.0
SHORT_FALLBACK_SHORT_LIQUIDATIONS = 0.0
SHORT_FALLBACK_BTC_DOMINANCE = 0.0

# ====================================================================
# ДИНАМИЧЕСКИЙ РАСЧЕТ MAX_POSITIONS
# ====================================================================

def get_dynamic_max_positions(total_balance: float) -> int:
	"""
	Рассчитывает максимальное количество одновременных позиций на основе баланса.
	
	Args:
		total_balance: Общий баланс (свободный + в позициях)
	
	Returns:
		Максимальное количество позиций для данного баланса
	"""
	if not USE_DYNAMIC_MAX_POSITIONS:
		return MAX_POSITIONS
	
	# Сортируем пороги по возрастанию
	sorted_thresholds = sorted(DYNAMIC_POSITIONS_THRESHOLDS.items())
	
	# Находим подходящий порог
	max_positions = sorted_thresholds[0][1]  # По умолчанию самый низкий уровень
	
	for threshold, positions in sorted_thresholds:
		if total_balance >= threshold:
			max_positions = positions
		else:
			break
	
	# Ограничиваем абсолютным максимумом
	return min(max_positions, MAX_DYNAMIC_POSITIONS_LIMIT)
