# Статистические и вероятностные модели

Бот интегрирует продвинутые статистические модели для повышения точности торговых решений.

## Обзор

Вместо простой реакции на технические индикаторы, бот теперь **оценивает вероятность успеха** каждой сделки на основе:
- Исторической статистики сигналов
- Z-score анализа для mean reversion
- Определения режима рынка (Markov Switching)

## Модели

### 1. Bayesian Decision Layer

**Идея**: Храним статистику успешности каждого типа сигнала и входим только при достаточной вероятности.

**Как работает**:
```
P(profit | signal) = успешные сигналы / общее количество
```

Для каждого сигнала создаётся **сигнатура** вида:
```
RSI<30_EMA_CROSS_UP_ADX>25_TRENDING_MACD_POS
```

Бот отслеживает:
- Сколько раз такой сигнал был прибыльным
- Средняя прибыль / убыток
- Risk:Reward ratio

**Порог входа**: 
- По умолчанию требуется P(profit) >= 55%
- Используется Bayesian smoothing для малых выборок (Prior: Beta(5,5))

**Файл**: `signal_statistics.json` (автоматически создаётся)

**Пример**:
```python
Сигнатура: RSI<30_EMA_CROSS_UP_ADX>25_TRENDING_MACD_POS
История: 15/20 успешных (P=75%)
Avg Profit: 8.3%, Avg Loss: 3.2%, R:R=2.6
→ Вход разрешён ✅
```

### 2. Z-Score Mean Reversion

**Идея**: В боковом рынке цены возвращаются к среднему значению.

**Формула**:
```
z = (price - SMA_50) / std(price - SMA_50)
```

**Сигналы**:
- `z < -2.0` → BUY (цена перепродана)
- `z > 2.0` → SELL (цена перекуплена)
- `-2 < z < 2` → HOLD

**Применение**:
- Особенно эффективно в режиме **SIDEWAYS** (боковик)
- Комбинируется с основными индикаторами

**Пример**:
```python
Price = $60,000
SMA_50 = $62,000
Std = $800
Z-score = (60000 - 62000) / 800 = -2.5

→ Цена сильно ниже среднего → BUY сигнал (mean reversion)
```

### 3. Markov Regime Switching Model

**Идея**: Автоматически определяет режим рынка.

**Режимы**:
1. **BULL** - Бычий рынок (восходящий тренд, низкая волатильность)
2. **BEAR** - Медвежий рынок (нисходящий тренд, низкая волатильность)
3. **HIGH_VOL** - Высокая волатильность (любое направление)
4. **SIDEWAYS** - Боковик (флэт)

**Метрики**:
- **Returns** = (price_end - price_start) / price_start (за окно 50 свечей)
- **Volatility** = std(log_returns) (стандартное отклонение)

**Пороги** (настраиваемые в config.py):
- Высокая волатильность: > 3%
- Низкая волатильность: < 1%
- Тренд: |returns| > 2%

**Transition Matrix** (сглаживание переходов):
```
              BULL   BEAR   HIGH_VOL  SIDEWAYS
BULL         0.85   0.05      0.05      0.05
BEAR         0.05   0.85      0.05      0.05
HIGH_VOL     0.25   0.25      0.30      0.20
SIDEWAYS     0.20   0.20      0.10      0.50
```

**Торговые правила**:
- `HIGH_VOL` → НЕ торговать (риск слишком велик)
- `BULL` + `BUY` → ✅ Торговать
- `BEAR` + `SELL` → ✅ Торговать
- `SIDEWAYS` → Mean reversion стратегия

**Пример**:
```python
Returns = +3.5% (за последние 50 свечей)
Volatility = 1.2%
→ Режим: BULL (confidence=0.88)
→ BUY сигналы разрешены, SELL блокируются
```

## Ensemble Decision Maker

Финальное решение принимается голосованием всех моделей с весами:

```python
BUY/SELL Score = 
  Bayesian_Weight * P(profit | signal) +
  ZScore_Weight * ZScore_Confidence +
  Regime_Weight * Regime_Confidence
```

**Веса по умолчанию**:
- Bayesian: 40%
- Z-Score: 30%
- Regime: 30%

**Порог**: Score > 0.5 для входа в сделку.

## Использование

### В бэктесте

```bash
# С статистическими моделями
python backtest.py BTCUSDT 1h 168 100 --use-stats

# Сравнение стратегий
python backtest_compare.py BTCUSDT 1h 168 100
python backtest_compare.py --tracked 1h 168 100  # все пары
```

### В боте

Включить в `config.py`:
```python
USE_STATISTICAL_MODELS = True
```

**⚠️ ВАЖНО**: 
- Модели требуют обучения (накопления статистики)
- Рекомендуется сначала собрать данные 1-2 недели в режиме paper trading
- Файл `signal_statistics.json` будет накапливать историю

## Настройка параметров

В `config.py`:

```python
# Bayesian
BAYESIAN_MIN_PROBABILITY = 0.55  # Требуем 55% вероятности успеха
BAYESIAN_MIN_SAMPLES = 10  # Минимум 10 сигналов для надёжной статистики

# Z-Score
ZSCORE_WINDOW = 50  # Окно для расчёта среднего
ZSCORE_BUY_THRESHOLD = -2.0  # Более агрессивно: -1.5
ZSCORE_SELL_THRESHOLD = 2.0  # Более агрессивно: +1.5

# Markov Regime
MARKOV_WINDOW = 50
MARKOV_VOL_HIGH = 0.03  # 3% высокая волатильность
MARKOV_VOL_LOW = 0.01   # 1% низкая волатильность
MARKOV_TREND_THRESHOLD = 0.02  # 2% тренд

# Веса ансамбля
ENSEMBLE_BAYESIAN_WEIGHT = 0.4
ENSEMBLE_ZSCORE_WEIGHT = 0.3
ENSEMBLE_REGIME_WEIGHT = 0.3
```

## Примеры результатов

### Пример 1: Бычий рынок
```
Базовая стратегия: +12.5% (15 сделок)
Со статистическими моделями: +18.3% (11 сделок)
→ Улучшение: +5.8%

Причина: Модели отфильтровали 4 ложных сигнала,
оставив только высоковероятные входы.
```

### Пример 2: Боковик
```
Базовая стратегия: -3.2% (20 сделок)
Со статистическими моделями: +4.1% (14 сделок)
→ Улучшение: +7.3%

Причина: Z-score модель эффективно ловила mean reversion,
Regime Switcher правильно определил SIDEWAYS режим.
```

### Пример 3: Высокая волатильность
```
Базовая стратегия: -8.5% (25 сделок)
Со статистическими моделями: -1.2% (8 сделок)
→ Улучшение: +7.3%

Причина: Regime Switcher блокировал торговлю в HIGH_VOL режиме,
сохранив капитал.
```

## Мониторинг

### Просмотр статистики сигналов

```python
from statistical_models import BayesianDecisionLayer

bayesian = BayesianDecisionLayer()
print(bayesian.get_stats_summary())
```

Вывод:
```
📊 СТАТИСТИКА СИГНАЛОВ:

RSI<30_EMA_CROSS_UP_ADX>25_TRENDING_MACD_POS...
  Всего: 25, Win: 18, Loss: 7, P=72.0%
  Avg Profit: 6.8%, Avg Loss: 3.2%

RSI>70_EMA_CROSS_DOWN_ADX>30_TRENDING_MACD_NEG...
  Всего: 15, Win: 9, Loss: 6, P=60.0%
  Avg Profit: 5.1%, Avg Loss: 4.3%
```

### Просмотр режимов рынка

```python
from statistical_models import MarkovRegimeSwitcher

regime = MarkovRegimeSwitcher()
# ... после использования
print(regime.get_regime_stats())
```

Вывод:
```
📈 СТАТИСТИКА РЕЖИМОВ:

BULL: 45 (45.0%)
SIDEWAYS: 30 (30.0%)
BEAR: 20 (20.0%)
HIGH_VOL: 5 (5.0%)
```

## Рекомендации

### Для начинающих
1. Запустите бота в paper trading на 1-2 недели **БЕЗ** статистических моделей
2. Накопите статистику в `signal_statistics.json`
3. Включите модели и сравните результаты

### Для продвинутых
1. Настройте веса ансамбля под ваш стиль торговли
2. Экспериментируйте с порогами (ZSCORE_THRESHOLD, BAYESIAN_MIN_PROBABILITY)
3. Добавьте свои условия в `should_trade_in_regime()`

### Оптимизация
- **Агрессивно**: `BAYESIAN_MIN_PROBABILITY = 0.50`, `ZSCORE_THRESHOLD = ±1.5`
- **Консервативно**: `BAYESIAN_MIN_PROBABILITY = 0.65`, `ZSCORE_THRESHOLD = ±2.5`
- **Сбалансировано**: Значения по умолчанию

## Технические детали

### Bayesian Smoothing

Для малых выборок (< 10 сигналов) используется Beta Prior:
```
Prior: Beta(α=5, β=5)  # Нейтральный prior с P≈0.5
Posterior: Beta(α + wins, β + losses)
P(profit) = (α + wins) / (α + wins + β + losses)
```

Это предотвращает переоценку единичных успешных/неудачных сигналов.

### Z-Score Calculation

```python
deviation = price - SMA(price, window)
z = deviation / std(deviation, window)
```

Нормализация отклонений позволяет сравнивать активы с разной волатильностью.

### Markov Transitions

Сглаживание переходов между режимами предотвращает ложные срабатывания:
```python
confidence *= transition_probability * 2
confidence = min(1.0, confidence)
```

## FAQ

**Q: Нужно ли обучать модели?**
A: Bayesian модель обучается автоматически в процессе торговли. Z-Score и Markov работают без обучения.

**Q: Сколько данных нужно для надёжной работы?**
A: Минимум 50-100 сигналов каждого типа. За 1-2 недели paper trading накопится достаточно.

**Q: Могу ли я использовать только одну модель?**
A: Да, настройте веса в config.py (например, Bayesian=1.0, остальные=0).

**Q: Почему модели отклоняют сигналы базовой стратегии?**
A: Если вероятность успеха < 55% или режим рынка не подходит, модели блокируют сделку для сохранения капитала.

**Q: Как сбросить статистику?**
A: Удалите файл `signal_statistics.json` и начните накапливать заново.

## Roadmap

- [ ] Machine Learning модель (LSTM/Transformer) для предсказания движений
- [ ] Sentiment Analysis (анализ новостей и Twitter)
- [ ] Multi-timeframe анализ (корреляция 15m, 1h, 4h)
- [ ] Portfolio optimization (Kelly Criterion)
- [ ] Автоматическая подстройка весов ансамбля

---

**Автор**: TradeBot Team
**Версия**: 1.0
**Дата**: 2025-10-12

