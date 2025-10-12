import os
import dotenv
import sys

dotenv.load_dotenv()

# ====================================================================
# TELEGRAM BOT
# ====================================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")  # ID владельца бота
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "BTCUSDT")
DEFAULT_INTERVAL = os.getenv("DEFAULT_INTERVAL", "1m")

# Настройки фонового мониторинга
POLL_INTERVAL = 60  # Базовый интервал проверки сигналов (секунды)
POLL_INTERVAL_MIN = 60  # Минимальный интервал при низкой волатильности
POLL_INTERVAL_MAX = 300  # Максимальный интервал при высокой волатильности (5 минут)
VOLATILITY_WINDOW = 10  # Окно для детекции волатильности (свечей)
VOLATILITY_THRESHOLD = 0.05  # Порог волатильности для алерта (5%)
VOLATILITY_HIGH_THRESHOLD = 0.08  # Порог высокой волатильности (8%) - увеличиваем интервал
VOLATILITY_LOW_THRESHOLD = 0.02  # Порог низкой волатильности (2%) - можно проверять чаще
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
ADX_RANGING = 20  # Порог флэта
ADX_STRONG = 25  # Порог для фильтра сильного тренда
ADX_MODERATE = 20  # Порог умеренного тренда

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
MAX_POSITIONS = 3  # Максимальное количество одновременных позиций
INITIAL_BALANCE = 100.0  # Начальный баланс для paper trading

# ====================================================================
# KELLY CRITERION
# ====================================================================

# Использовать Kelly Criterion для оптимального размера позиции
USE_KELLY_CRITERION = True
KELLY_FRACTION = 0.25  # Четверть Kelly для консервативности (0.25 = 25%)
MIN_TRADES_FOR_KELLY = 10  # Минимум сделок для расчёта Kelly
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
MR_MAX_HOLDING_HOURS_V4 = 16  # v4: 16 часов для Mean Reversion (было 12)

# ====================================================================
# СТАТИСТИЧЕСКИЕ МОДЕЛИ
# ====================================================================

# Включить статистические модели (Bayesian, Z-score, Markov)
USE_STATISTICAL_MODELS = False  # По умолчанию выключено (требует обучения)

# Bayesian Decision Layer
BAYESIAN_MIN_PROBABILITY = 0.55  # Минимальная вероятность успеха для входа (55%)
BAYESIAN_MIN_SAMPLES = 10  # Минимальное количество сигналов для надёжной статистики

# Z-Score Mean Reversion
ZSCORE_WINDOW = 50  # Окно для расчёта среднего
ZSCORE_BUY_THRESHOLD = -2.0  # Порог покупки (цена сильно ниже среднего)
ZSCORE_SELL_THRESHOLD = 2.0  # Порог продажи (цена сильно выше среднего)

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

# Параметры Mean Reversion v4 (ОПТИМИЗИРОВАННЫЕ ДЛЯ 10-15 СДЕЛОК)
MR_RSI_OVERSOLD = 40  # Порог перепроданности (было 35 → 40 для большего числа сделок)
MR_RSI_EXIT = 50  # Порог выхода (RSI вернулся к норме)
MR_ZSCORE_BUY_THRESHOLD = -1.8  # Z-score порог покупки (было -2.0 → -1.8 для больше входов)
MR_ZSCORE_SELL_THRESHOLD = 0.3  # Z-score порог выхода (возврат к среднему)
MR_ZSCORE_STRONG_BUY = -2.3  # Сильная перепроданность для 70% позиции (было -2.5)
MR_ADX_MAX = 35  # Максимальный ADX (было 30 → 35, разрешаем умеренный тренд)
MR_EMA_DIVERGENCE_MAX = 0.02  # Максимальная дивергенция EMA (2%) - флэт

# Размеры позиций для Mean Reversion v4
MR_POSITION_SIZE_STRONG = 0.70  # 70% для сильной перепроданности (RSI<25, Z<-2.3)
MR_POSITION_SIZE_MEDIUM = 0.50  # 50% для умеренной перепроданности (RSI<35, Z<-2.0)
MR_POSITION_SIZE_WEAK = 0.35  # 35% для слабой перепроданности (было 30%, увеличено)

# TP/SL для Mean Reversion (короткие тейки) - ОПТИМИЗИРОВАННЫЕ
MR_TAKE_PROFIT_PERCENT = 0.025  # 2.5% быстрый тейк-профит (было 3%)
MR_STOP_LOSS_PERCENT = 0.03  # 3% стоп-лосс (было 2%, расширили)
MR_MAX_HOLDING_HOURS = 12  # Максимум 12 часов удержания (было 24)

# Z-score параметры для MR
MR_ZSCORE_WINDOW = 50  # Окно для расчёта среднего

# Фильтры "падающего ножа" v5 (УСИЛЕННЫЕ - вернули красные свечи)
NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT = 0.04  # v5: Не входить если цена < min(24h) * 0.96 (УСИЛИЛИ с 0.05)
NO_BUY_IF_EMA200_SLOPE_NEG = True  # Блокировать если slope(EMA200, 24h) < -0.3%
EMA200_NEG_SLOPE_THRESHOLD = -0.003  # -0.3% наклон EMA200
USE_RED_CANDLES_FILTER = True  # v5: ВКЛЮЧЕН ОБРАТНО (защита от падающих ножей)

# Фильтр объёма v5 (НОВОЕ)
USE_VOLUME_FILTER = True  # v5: Блокировать входы при всплесках объёма
VOLUME_SPIKE_THRESHOLD = 1.5  # Не входить если volume > 1.5x средний за 24h

# Динамический SL на основе ATR v4
USE_DYNAMIC_SL_FOR_MR = True  # Использовать ATR-based SL вместо фиксированного
MR_ATR_SL_MULTIPLIER = 2.5  # Множитель ATR для SL (2.5x ATR)
MR_ATR_SL_MIN = 0.025  # Минимальный SL 2.5%
MR_ATR_SL_MAX = 0.05  # Максимальный SL 5%

# Адаптивный SL v5 (ОТКЛЮЧЕН - не работал в v4)
ADAPTIVE_SL_ON_RISK = False  # v5: ОТКЛЮЧЕН (не эффективен, лучше блокировать вход)
ADAPTIVE_SL_MULTIPLIER = 1.5  # Увеличить SL на 50% при риске (не используется)

# Динамический TP v4 (НОВОЕ)
USE_DYNAMIC_TP_FOR_MR = True  # Использовать динамический TP на основе ATR
MR_ATR_TP_MULTIPLIER = 3.5  # 3.5x ATR для TP (больше чем SL для R:R > 1)
MR_ATR_TP_MIN = 0.02  # Минимум 2%
MR_ATR_TP_MAX = 0.04  # Максимум 4%

# Трейлинг стоп для MR v4 (улучшенный - двухуровневый)
USE_TRAILING_STOP_MR = True  # Включить трейлинг стоп после прибыли
MR_TRAILING_ACTIVATION = 0.008  # v4: Активировать раньше - после +0.8% (было 1%)
MR_TRAILING_DISTANCE = 0.012  # v4: Ближе к цене - 1.2% от максимума (было 1.5%)

# Агрессивный трейлинг v4 (после сильной прибыли)
MR_TRAILING_AGGRESSIVE_ACTIVATION = 0.02  # После +2% прибыли
MR_TRAILING_AGGRESSIVE_DISTANCE = 0.008  # Очень близко - 0.8% от максимума

# ====================================================================
# ГИБРИДНАЯ СТРАТЕГИЯ (MR + TF с переключением по ADX)
# ====================================================================

STRATEGY_HYBRID_MODE = "AUTO"  # "AUTO" (переключение по ADX), "MR_ONLY", "TF_ONLY"

# Пороги ADX для переключения режимов
HYBRID_ADX_MR_THRESHOLD = 20  # ADX < 20 → Mean Reversion (боковик)
HYBRID_ADX_TF_THRESHOLD = 25  # ADX > 25 → Trend Following (тренд)
# 20 <= ADX <= 25 → переходная зона (HOLD или используем последний режим)

HYBRID_TRANSITION_MODE = "HOLD"  # "HOLD" (не входить) или "LAST" (использовать последний режим)

# Минимальное время в режиме (защита от частого переключения)
HYBRID_MIN_TIME_IN_MODE = 0  # Минимум 4 часа в одном режиме

# ====================================================================
# MULTI-TIMEFRAME ANALYSIS
# ====================================================================

# Использовать multi-timeframe анализ (15m, 1h, 4h)
USE_MULTI_TIMEFRAME = True

# Таймфреймы для анализа (от меньшего к большему)
MTF_TIMEFRAMES = ['15m', '1h', '4h']

# Веса для weighted voting (сумма должна быть 1.0)
MTF_WEIGHTS = {
	'15m': 0.30,  # Краткосрочный тренд (шум, но быстрая реакция)
	'1h': 0.40,   # Основной таймфрейм (баланс)
	'4h': 0.30    # Долгосрочный тренд (медленный, но надёжный)
}

# Минимальное количество согласованных таймфреймов для входа
MTF_MIN_AGREEMENT = 1  # Минимум 1 из 3 TF (используем weighted voting)

# Бонус за полное согласие всех таймфреймов
MTF_FULL_ALIGNMENT_BONUS = 1.5  # Увеличить силу сигнала на 50% если все 3 TF согласны

# ====================================================================
# API
# ====================================================================

# Таймаут для API запросов
API_TIMEOUT = 30  # секунд
