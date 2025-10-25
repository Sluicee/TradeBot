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

# ====================================================================
# ЛОГИРОВАНИЕ
# ====================================================================
# Компактный режим логирования (уменьшает размер логов)
COMPACT_LOGGING = True  # True = компактные логи, False = подробные логи
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
SIGNAL_DIAG_COMPACT = True  # Компактный режим для диагностики сигналов

# Продакшен режим (максимально компактные логи)
PRODUCTION_LOGGING = False  # True = продакшен режим (только критичные события)
PRODUCTION_LOG_LEVEL = "WARNING"  # Уровень для продакшена

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
RSI_BUY_RANGE = (30, 70)  # Диапазон для входа в BUY (перепроданность)
RSI_SELL_RANGE = (70, 100)  # Диапазон для входа в SELL (перекупленность)

# MACD
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# ADX (сила тренда)
ADX_WINDOW = 14
ADX_TRENDING = 25
ADX_RANGING = 15
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
TRENDING_TREND_WEIGHT = 2  # Вес трендовых индикаторов в тренде
TRENDING_OSCILLATOR_WEIGHT = 2  # Вес осцилляторов в тренде

RANGING_TREND_WEIGHT = 1  # Вес трендовых индикаторов во флэте
RANGING_OSCILLATOR_WEIGHT = 2  # Вес осцилляторов во флэте

TRANSITIONING_TREND_WEIGHT = 2  # Вес трендовых индикаторов при переходе
TRANSITIONING_OSCILLATOR_WEIGHT = 2  # Вес осцилляторов при переходе

# Пороги голосования для генерации сигнала (ОПТИМИЗИРОВАНО: снижение с 423 до ~75 сигналов/час)
VOTE_THRESHOLD_TRENDING = 2      # Было 1, стало 2 (снижение с 423 до ~75 сигналов/час)
VOTE_THRESHOLD_RANGING = 4       # Было 3, стало 4 (снижение с 423 до ~75 сигналов/час)
VOTE_THRESHOLD_TRANSITIONING = 5 # Было 4, стало 5 (снижение с 423 до ~75 сигналов/час)

# Минимальное количество пройденных фильтров для сигнала
MIN_FILTERS = 2  # Из 5 возможных фильтров

# ====================================================================
# PAPER TRADING & BACKTEST
# ====================================================================

# Комиссия биржи
COMMISSION_RATE = 0.0018  # 0.18%

# Управление позициями
MAX_POSITIONS = 3  # Базовое максимальное количество одновременных позиций (используется как fallback)
INITIAL_BALANCE = 100.0  # Начальный баланс для paper trading

# BTC-корреляция (ВНИМАНИЕ: может блокировать 90% сделок в крипторынке)
#ENABLE_BTC_CORRELATION_CHECK = True  # Проверять корреляцию с BTC
#MAX_BTC_CORRELATED_POSITIONS = 1  # Максимум 1 позиция из высоко коррелированных с BTC

# АЛЬТЕРНАТИВНЫЕ НАСТРОЙКИ ДЛЯ БОЛЕЕ ГИБКОЙ ТОРГОВЛИ:
ENABLE_BTC_CORRELATION_CHECK = False  # Отключить BTC-корреляцию полностью
MAX_BTC_CORRELATED_POSITIONS = 3     # Разрешить больше BTC-коррелированных позиций

# Динамическое изменение MAX_POSITIONS на основе баланса
USE_DYNAMIC_MAX_POSITIONS = True  # Включить динамический расчет максимального количества позиций
DYNAMIC_POSITIONS_THRESHOLDS = {
	# баланс: макс_позиций
	0: 3,        # <$100: 3 позиции (консервативно)
	100: 4,      # $100-$500: 4 позиции (базовый режим)
	500: 5,      # $500-$1000: 5 позиции
	1000: 6,     # $1000-$2000: 6 позиций
	2000: 7,     # $2000+: 7 позиций (максимум)
}
MAX_DYNAMIC_POSITIONS_LIMIT = 7  # Абсолютный максимум позиций независимо от баланса

# ====================================================================
# KELLY CRITERION
# ====================================================================

# Использовать Kelly Criterion для оптимального размера позиции (ИСПРАВЛЕНО)
USE_KELLY_CRITERION = True
KELLY_FRACTION = 0.15  # ИСПРАВЛЕНО: 15% Kelly для консервативности (было 20%)
MIN_TRADES_FOR_KELLY = 15  # Минимум сделок для расчёта Kelly
KELLY_LOOKBACK_WINDOW = 50  # Скользящее окно последних N сделок
KELLY_NEGATIVE_MULTIPLIER = 0.3  # Множитель при отрицательном Kelly (30% от базового)

# ====================================================================
# УМНОЕ ДОКУПАНИЕ (AVERAGING)
# ====================================================================

# Включить умное докупание/пирамидинг
ENABLE_AVERAGING = True
MAX_AVERAGING_ATTEMPTS = 2  # Максимум 2-3 докупания на позицию
AVERAGING_PRICE_DROP_PERCENT = 0.05  # Докупаем при падении на 5%
AVERAGING_TIME_THRESHOLD_HOURS = 24  # Время для триггера докупания (24 часа)
MAX_TOTAL_RISK_MULTIPLIER = 1.5  # Общий риск не более 1.5× базового

# Защита от переинвестирования при больших убытках
MAX_POSITION_DRAWDOWN_PERCENT = 0.15  # Максимальный drawdown позиции для докупания (15%)
MAX_AVERAGING_DRAWDOWN_PERCENT = 0.25  # Максимальный drawdown для докупания (25%)

# Пирамидинг вверх при сильном тренде
ENABLE_PYRAMID_UP = True
PYRAMID_ADX_THRESHOLD = 25  # Порог ADX для пирамидинга вверх
AVERAGING_SIZE_PERCENT = 0.5  # Размер докупания (50% от исходного)

# Стоп-лосс и тейк-профит
STOP_LOSS_PERCENT = 0.05  # 5% стоп-лосс (базовый)
TAKE_PROFIT_PERCENT = 0.07  # 7% тейк-профит (ИСПРАВЛЕНО - было 10%)
PARTIAL_CLOSE_PERCENT = 0.50  # Закрываем 50% позиции на TP
TRAILING_STOP_PERCENT = 0.02  # 2% trailing stop после частичного закрытия

# Динамический стоп-лосс на основе ATR (КРИТИЧЕСКИ УВЕЛИЧЕНО)
DYNAMIC_SL_ATR_MULTIPLIER = 4.0  # 4.0x ATR для расчета SL (было 3.0 - мало!)
DYNAMIC_SL_MIN = 0.05  # Минимум 5% (было 3% - мало для крипты!)
DYNAMIC_SL_MAX = 0.15  # Максимум 15% (было 10% - увеличиваем диапазон)

# Размеры позиций по силе сигнала
POSITION_SIZE_STRONG = 0.70  # 70% для сильного сигнала (>= 9 голосов)
POSITION_SIZE_MEDIUM = 0.50  # 50% для среднего сигнала (>= 6 голосов)
POSITION_SIZE_WEAK = 0.30  # 30% для слабого сигнала

# Break-even Stop Loss (защита прибыли)
BREAKEVEN_PROFIT_THRESHOLD = 0.02  # При +2% прибыли
BREAKEVEN_ENABLED = True
SIGNAL_STRENGTH_STRONG = 9  # Порог для сильного сигнала
SIGNAL_STRENGTH_MEDIUM = 6  # Порог для среднего сигнала

# Корректировка размера позиции на волатильность
VOLATILITY_HIGH_THRESHOLD = 3.0  # ATR > 3% - высокая волатильность
VOLATILITY_LOW_THRESHOLD = 1.0  # ATR < 1% - низкая волатильность
VOLATILITY_ADJUSTMENT_MAX = 1.2  # Максимальное увеличение размера

# Время удержания позиции
MAX_HOLDING_HOURS = 72  # Максимум 72 часа (3 дня) для Trend Following
# MR_MAX_HOLDING_HOURS задан ниже в секции Mean Reversion (строка 231)

# Partial Take Profit (ИСПРАВЛЕНО - более агрессивно)
USE_PARTIAL_TP = True  # Включить частичное закрытие позиции
PARTIAL_TP_PERCENT = 0.5  # Закрывать 50% позиции
PARTIAL_TP_TRIGGER = 0.01  # На +1% прибыли (было 1.5%)
PARTIAL_TP_REMAINING_TP = 0.02  # TP для оставшихся 50%: +2% (было 3%)

# ====================================================================
# СТАТИСТИЧЕСКИЕ МОДЕЛИ
# ====================================================================

# Включить статистические модели (Bayesian, Z-score, Markov)
USE_STATISTICAL_MODELS = True  # По умолчанию выключено (требует обучения)

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

# Параметры Mean Reversion v5.2 (ИСПРАВЛЕНО: приведено в соответствие с общими RSI порогами)
MR_RSI_OVERSOLD = 35  # Порог перепроданности (смягчено с 40 до 35 для большего количества сигналов)
MR_RSI_EXIT = 52  # Порог выхода (небольшой momentum)
MR_ZSCORE_BUY_THRESHOLD = -1.5  # Z-score порог покупки (смягчено с -1.8 для большего количества сигналов)
MR_ZSCORE_SELL_THRESHOLD = 0.4  # Z-score порог выхода
MR_ZSCORE_STRONG_BUY = -2.0  # Сильная перепроданность для 70% позиции (смягчено с -2.3)
MR_ADX_MAX = 30  # Максимальный ADX (смягчено с 32 для большего количества сигналов)
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

# Фильтры "падающего ножа" v5.4 (ИСПРАВЛЕНО: отключен блокирующий EMA200 фильтр)
# ⚠️ РИСК: Отключение этих фильтров может привести к входу в "падающий нож"
# в сильном медвежьем тренде, что исторически приводит к крупным убыткам
NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT = 0.10  # Не входить если цена < min(24h) * 0.90
NO_BUY_IF_EMA200_SLOPE_NEG = False  # ИСПРАВЛЕНО: ОТКЛЮЧЕН (блокировал 100% сигналов!)
EMA200_NEG_SLOPE_THRESHOLD = -0.010  # -1.0% наклон EMA200 (не используется)
USE_RED_CANDLES_FILTER = True  # ВКЛЮЧЕН: блокировать при серии красных свечей

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

# Минимальный R:R контроль (ИСПРАВЛЕНО: предотвращает деградацию R:R)
MIN_RR_RATIO = 1.25  # Минимальный Risk:Reward ratio (1:1.25)
ENFORCE_MIN_RR = True  # Принудительно обеспечивать минимальный R:R

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

# Пороги ADX для переключения режимов (ИСПРАВЛЕНО: оптимальные пороги)
HYBRID_ADX_MR_THRESHOLD = 20  # ADX < 20 → Mean Reversion (боковик)
HYBRID_ADX_MR_EXIT = 25  # ADX > 25 → Выход из MR в TF (гистерезис)
HYBRID_ADX_TF_THRESHOLD = 25  # ADX > 25 → Trend Following (тренд)
HYBRID_ADX_TF_EXIT = 20  # ADX < 20 → Выход из TF в MR (гистерезис)
# 20 <= ADX <= 25 → переходная зона 5 пунктов (оптимальная зона)

HYBRID_TRANSITION_MODE = "HOLD"  # КРИТИЧЕСКИ: только HOLD (запрет входов в переходной зоне)

# Минимальное время в режиме (защита от частого переключения)
HYBRID_MIN_TIME_IN_MODE = 0.5  # v5.6: 30 минут минимум (стабильное переключение)

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
# РЕЖИМЫ СТРАТЕГИЙ (константы для избежания хардкода)
# ====================================================================
MODE_MEAN_REVERSION = "MEAN_REVERSION"
MODE_TREND_FOLLOWING = "TREND_FOLLOWING"
MODE_TRANSITION = "TRANSITION"

# Константы типов стратегий для time exit
STRATEGY_TYPE_MR = "MR"
STRATEGY_TYPE_TF = "TF"
STRATEGY_TYPE_HYBRID = "HYBRID"

# Основной таймфрейм для MTF анализа (используется как fallback)
MTF_PRIMARY_TIMEFRAME = "1h"

# ====================================================================
# REAL TRADING CONFIGURATION
# ====================================================================

# Trading Mode Flags
ENABLE_PAPER_TRADING = True   # Включить paper trading
ENABLE_REAL_TRADING = True   # Включить реальную торговлю

# Bybit API (загружаются из .env)
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"  # True для testnet

# Отладочная информация для API ключей
import logging
logger = logging.getLogger(__name__)
logger.info(f"Config: BYBIT_API_KEY loaded = {BYBIT_API_KEY is not None}")
logger.info(f"Config: BYBIT_API_SECRET loaded = {BYBIT_API_SECRET is not None}")

# Real Trading Safety Limits
REAL_MAX_DAILY_LOSS = 50.0  # Макс убыток в день (USD)
REAL_MAX_POSITION_SIZE = 100.0  # Макс размер позиции (USD)
REAL_MIN_ORDER_VALUE = 1.0  # Минимальная сумма ордера (USD) для spot торговли (fallback, реальные лимиты получаются динамически)
REAL_ORDER_TYPE = "MARKET"  # "MARKET" или "LIMIT"
REAL_LIMIT_ORDER_OFFSET_PERCENT = 0.001  # 0.1% оффсет для лимитных ордеров

# ====================================================================
# МАЛЫЕ БАЛАНСЫ - АДАПТИВНЫЙ РАСЧЕТ РАЗМЕРА ПОЗИЦИЙ
# ====================================================================

# Пороги для малых балансов
SMALL_BALANCE_THRESHOLD = 50.0  # Порог малого баланса (USD)
SMALL_BALANCE_MIN_ORDER = 5.0  # Минимум для малых балансов (USD) - соответствует Bybit лимиту
SMALL_BALANCE_POSITION_MULTIPLIER = 1.2  # Увеличенный процент для малых балансов

# Динамические минимумы для торговых пар
USE_DYNAMIC_MIN_ORDER = True  # Использовать минимумы из БД для каждой пары
SYMBOL_INFO_UPDATE_HOURS = 24  # Обновлять информацию о парах раз в сутки

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

