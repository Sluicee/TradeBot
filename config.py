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
MAX_HOLDING_HOURS = 72  # Максимум 72 часа (3 дня)

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
# API
# ====================================================================

# Таймаут для API запросов
API_TIMEOUT = 30  # секунд
