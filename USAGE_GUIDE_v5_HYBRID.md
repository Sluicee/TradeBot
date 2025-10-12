# 📚 ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ v5 и HYBRID

## 🎯 Быстрый выбор стратегии

| Если нужно | Используй |
|------------|-----------|
| **Максимальная доходность** | 🏆 **HYBRID** |
| **Только боковой рынок** | v5 MR |
| **Только трендовый рынок** | TF (baseline) |
| **Безопасность (low DD)** | 🏆 **HYBRID** (1.56% DD) |
| **Высокий Win Rate** | v5 MR или HYBRID (71.4%) |

**Рекомендация**: 🏆 **HYBRID** — лучший выбор для всех условий.

---

## 🚀 ГИБРИДНАЯ СТРАТЕГИЯ

### Запуск бэктеста
```bash
python backtest_hybrid.py
```

**Выход**:
- CSV: `hybrid_trades.csv`
- График: `equity_curve_hybrid.png`
- Консоль: метрики + переключения режимов

### Конфигурация (config.py)

```python
# ====================================================================
# ГИБРИДНАЯ СТРАТЕГИЯ (MR + TF с переключением по ADX)
# ====================================================================

STRATEGY_HYBRID_MODE = "AUTO"  # "AUTO", "MR_ONLY", "TF_ONLY"

# Пороги ADX для переключения
HYBRID_ADX_MR_THRESHOLD = 20  # ADX < 20 → Mean Reversion
HYBRID_ADX_TF_THRESHOLD = 25  # ADX > 25 → Trend Following

# Режим переходной зоны (20 <= ADX <= 25)
HYBRID_TRANSITION_MODE = "HOLD"  # "HOLD" (не входить) или "LAST" (последний режим)

# Минимальное время в режиме (защита от частых переключений)
HYBRID_MIN_TIME_IN_MODE = 4  # часов
```

### Как работает

1. **Расчёт ADX** на каждой свече
2. **Определение режима**:
   - ADX < 20 → **Mean Reversion** (боковик)
   - ADX > 25 → **Trend Following** (тренд)
   - 20-25 → переходная зона (HOLD или последний режим)
3. **Генерация сигнала** в выбранном режиме
4. **Защита от частых переключений**: минимум 4 часа в одном режиме

### Пример логов

```
[2025-09-04 16:00] ADX=18.5 < 20 → MEAN REVERSION режим
[2025-09-04 16:00] BUY $109,424 (MR: RSI=28, Z=-2.6)
[2025-09-04 21:00] SELL $110,488 (+0.97%, SIGNAL_EXIT)

[2025-09-30 21:00] ADX=32.1 > 25 → TREND FOLLOWING режим
[2025-09-30 21:00] BUY $114,165 (TF: EMA crossover)
[2025-10-02 15:00] SELL $119,950 (+5.07%, TAKE_PROFIT) 🚀

Mode Switches: 24
```

### Анализ сделок

`hybrid_trades.csv`:
```
symbol,entry_time,entry_price,entry_mode,exit_time,exit_price,pnl_percent,pnl_usd,reason,hours_held
BTCUSDT,2025-09-14 15:00,115216.7,MEAN_REVERSION,2025-09-14 20:00,115793.3,0.50,0.11,SIGNAL_EXIT,5.0
BTCUSDT,2025-09-30 21:00,114165.5,TREND_FOLLOWING,2025-10-02 15:00,119950.0,5.07,2.42,TAKE_PROFIT,42.0
```

**Колонка `entry_mode`**:
- `MEAN_REVERSION` — вход был в MR режиме
- `TREND_FOLLOWING` — вход был в TF режиме

---

## 📊 MEAN REVERSION v5

### Запуск бэктеста
```bash
python backtest_mean_reversion.py
```

**Выход**:
- CSV: `mean_reversion_trades.csv`, `trend_following_trades.csv`
- Графики: `equity_curve_comparison.png`, `zscore_vs_pnl.png`
- Консоль: сравнительная таблица MR vs TF

### Конфигурация v5 (config.py)

```python
# Параметры Mean Reversion v5 (ОПТИМИЗИРОВАННЫЕ ДЛЯ 10-15 СДЕЛОК)
MR_RSI_OVERSOLD = 40  # Порог перепроданности
MR_ZSCORE_BUY_THRESHOLD = -1.8  # Z-score порог покупки
MR_ADX_MAX = 35  # Максимальный ADX (умеренный тренд разрешён)
MR_EMA_DIVERGENCE_MAX = 0.02  # 2% дивергенция EMA (флэт)

# Фильтры v5 (УСИЛЕННЫЕ)
NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT = 0.04  # Не входить если цена < min(24h) * 0.96
NO_BUY_IF_EMA200_SLOPE_NEG = True  # Блокировать при падающем EMA200
EMA200_NEG_SLOPE_THRESHOLD = -0.003  # -0.3% наклон
USE_RED_CANDLES_FILTER = True  # ✅ ВКЛЮЧЕН (защита от падающих ножей)
USE_VOLUME_FILTER = True  # ✅ ВКЛЮЧЕН (блокировать всплески объёма)
VOLUME_SPIKE_THRESHOLD = 1.5  # Не входить если volume > 1.5x средний

# Адаптивный SL v5 (ОТКЛЮЧЕН)
ADAPTIVE_SL_ON_RISK = False  # НЕ работал в v4, лучше блокировать вход
```

### Изменения от v4 к v5

| Параметр | v4 | v5 | Почему |
|----------|----|----|--------|
| `USE_RED_CANDLES_FILTER` | False | **True** | Защита от падающих ножей |
| `NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT` | 0.05 | **0.04** | Усилили фильтр |
| `ADAPTIVE_SL_ON_RISK` | True | **False** | Не работал, лучше блокировать |
| `USE_VOLUME_FILTER` | — | **True** | Новый фильтр всплесков объёма |

---

## ⚙️ Переключение между стратегиями

### В bot.py / paper_trader.py

```python
# В функции generate_signal()

# Вариант 1: Гибридная стратегия (рекомендуется)
signal = signal_generator.generate_signal_hybrid(
	last_mode=self.last_mode,
	last_mode_time=self.last_mode_time
)

# Вариант 2: Mean Reversion v5 only
signal = signal_generator.generate_signal_mean_reversion()

# Вариант 3: Trend Following only (baseline)
signal = signal_generator.generate_signal()
```

### Для бэктеста

```python
# backtest_hybrid.py
res = gen.generate_signal_hybrid(
	last_mode=self.last_mode,
	last_mode_time=self.last_mode_time if self.last_mode_time else 0
)

# backtest_mean_reversion.py (в run_backtest)
if strategy == "mean_reversion":
	res = gen.generate_signal_mean_reversion()
else:
	res = gen.generate_signal()
```

---

## 🔧 Оптимизация параметров

### Если нужно БОЛЬШЕ сделок в Hybrid:

```python
# Снизить порог MR (больше MR входов)
HYBRID_ADX_MR_THRESHOLD = 22  # было 20

# Уменьшить защиту от переключений
HYBRID_MIN_TIME_IN_MODE = 2  # было 4
```

### Если нужно МЕНЬШЕ сделок:

```python
# Повысить порог MR (меньше MR входов)
HYBRID_ADX_MR_THRESHOLD = 18  # было 20

# Ужесточить MR фильтры
MR_RSI_OVERSOLD = 35  # было 40
MR_ZSCORE_BUY_THRESHOLD = -2.0  # было -1.8
```

### Если низкий Win Rate:

```python
# Ужесточить фильтры падающего ножа
NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT = 0.03  # было 0.04
VOLUME_SPIKE_THRESHOLD = 1.3  # было 1.5

# Увеличить SL для MR
MR_STOP_LOSS_PERCENT = 0.035  # было 0.03
MR_ATR_SL_MULTIPLIER = 3.0  # было 2.5
```

### Если большой Drawdown:

```python
# Уменьшить размеры позиций
MR_POSITION_SIZE_STRONG = 0.50  # было 0.70
MR_POSITION_SIZE_MEDIUM = 0.35  # было 0.50
MR_POSITION_SIZE_WEAK = 0.25  # было 0.35

# Раньше активировать трейлинг
MR_TRAILING_ACTIVATION = 0.005  # было 0.008 (активация после +0.5%)
```

---

## 📈 Понимание результатов

### Ключевые метрики

- **Total Return** — общая доходность (цель: >0%)
- **Win Rate** — процент прибыльных сделок (цель: >65%)
- **Max Drawdown** — максимальная просадка (цель: <10%)
- **Sharpe Ratio** — доходность с учётом риска (цель: >0.5)
- **Avg Win / Avg Loss** — средний выигрыш/проигрыш (R:R цель: >1)

### Для Hybrid

- **MR Trades / TF Trades** — сколько сделок в каждом режиме
- **Mode Switches** — количество переключений режимов
  - Слишком много (>50) → увеличить `HYBRID_MIN_TIME_IN_MODE`
  - Слишком мало (<10) → уменьшить защиту от переключений

### Хорошие паттерны

✅ **Hybrid**: 
- Равномерное распределение MR/TF
- Mode Switches: 15-30 за месяц
- TF ловит большие движения (+3-5%)
- MR защищает на боковике (+0.5-1%)

✅ **v5 MR**:
- Win Rate > 70%
- Avg Loss < 2%
- Быстрое удержание (<12h)
- Нет больших лоссов

---

## 🐛 Troubleshooting

### Проблема: "AttributeError: 'SignalGenerator' object has no attribute 'indicators'"

**Решение**: Убедитесь что вызываете `compute_indicators()` ПЕРЕД `generate_signal_hybrid()`:
```python
gen = SignalGenerator(sub_df)
gen.compute_indicators()  # ← ОБЯЗАТЕЛЬНО
res = gen.generate_signal_hybrid()
```

### Проблема: Слишком много переключений режимов

**Решение**: Увеличить `HYBRID_MIN_TIME_IN_MODE`:
```python
HYBRID_MIN_TIME_IN_MODE = 6  # было 4
```

### Проблема: Hybrid не входит в сделки (0 trades)

**Решение**: Проверить пороги ADX:
```python
# Возможно ADX всегда в переходной зоне 20-25
# Попробуйте расширить диапазоны:
HYBRID_ADX_MR_THRESHOLD = 22  # было 20
HYBRID_ADX_TF_THRESHOLD = 23  # было 25
```

### Проблема: v5 MR слишком мало сделок (<5)

**Решение**: Смягчить фильтры:
```python
MR_RSI_OVERSOLD = 42  # было 40
MR_ZSCORE_BUY_THRESHOLD = -1.6  # было -1.8
USE_VOLUME_FILTER = False  # отключить фильтр объёма
```

---

## 🧪 Тестирование

### 1. Разные периоды

```bash
# В backtest_hybrid.py или backtest_mean_reversion.py
period_days = 30   # Последний месяц
period_days = 90   # Последние 3 месяца
period_days = 180  # Последние полгода
```

### 2. Разные интервалы

```bash
interval = "15m"  # Скальпинг
interval = "1h"   # Интрадей (рекомендуется)
interval = "4h"   # Свинг
```

### 3. Разные монеты

```bash
symbol = "BTCUSDT"
symbol = "ETHUSDT"
symbol = "SOLUSDT"
symbol = "BNBUSDT"
```

### 4. Grid Search

```python
for adx_mr in [18, 20, 22]:
	for adx_tf in [23, 25, 27]:
		HYBRID_ADX_MR_THRESHOLD = adx_mr
		HYBRID_ADX_TF_THRESHOLD = adx_tf
		# ... запустить бэктест
		# сохранить результаты
```

---

## 🚀 Production Deployment

### 1. Paper Trading

```bash
# Запустить paper trader с hybrid стратегией
python paper_trader.py

# В paper_trader.py изменить:
signal = self.signal_generator.generate_signal_hybrid(
	last_mode=self.last_mode,
	last_mode_time=self.last_mode_time
)
```

### 2. Мониторинг

**Что отслеживать**:
- Число сделок в день (цель: 1-3)
- Win Rate в реальном времени (цель: >65%)
- Drawdown (цель: <10%)
- Распределение MR/TF сделок
- Количество переключений режимов

**Логи**:
```bash
tail -f logs/paper_trading.log
# Смотреть на:
# - "ADX=XX → режим YY"
# - "BUY/SELL" сигналы
# - "Mode switch: MR → TF"
```

### 3. Живая торговля

**После 2-4 недель успешного paper trading**:

```bash
# В bot.py
INITIAL_BALANCE = 100  # Начать с малого баланса
USE_PAPER_TRADING = False  # Переключить на реальную торговлю

python bot.py
```

**Важно**:
- Начинать с малого баланса ($100-$500)
- Постепенно увеличивать после подтверждения
- Следить за комиссиями (Binance: 0.1%)
- Проверять исполнение ордеров

---

## 📊 Сравнение всех версий

| Версия | Return | Win Rate | DD | Sharpe | Trades | Рекомендация |
|--------|--------|----------|-----|--------|--------|--------------|
| **v1 MR** | -1.86% | 50.0% | 4.85% | -0.52 | 2 | ❌ Слишком мало сделок |
| **v2 MR** | -0.93% | 71.4% | 4.02% | -0.10 | 7 | ⚠️ Лучшая MR до v5 |
| **v3 MR** | -1.38% | 60.0% | 5.39% | -0.34 | 5 | ❌ Слишком мало сделок |
| **v4 MR** | -3.84% | 63.6% | 4.97% | -0.30 | 11 | ❌ Большие потери |
| **v5 MR** | -1.20% | 71.4% | 1.99% | -0.13 | 7 | ⚠️ Хорошие фильтры, но убыток |
| **TF** | -1.09% | 42.1% | 4.24% | 0.21 | 19 | ⚠️ Baseline |
| 🏆 **HYBRID** | **+1.29%** | **71.4%** | **1.56%** | **1.08** | 7 | ✅ **ЛУЧШАЯ** |

---

## ✅ Чек-лист перед запуском

- [ ] Выбрана стратегия (рекомендуется HYBRID)
- [ ] Настроены параметры в `config.py`
- [ ] Запущен бэктест (проверены результаты)
- [ ] Win Rate > 65%
- [ ] Sharpe Ratio > 0.5
- [ ] Max Drawdown < 10%
- [ ] Запущен paper trading (2-4 недели)
- [ ] Paper trading показывает стабильную прибыль
- [ ] Логи проверены на ошибки
- [ ] Готов к запуску на малом балансе

---

## 📁 Файлы проекта

```
TradeBot/
├── config.py                  # ← Параметры v5 + Hybrid
├── signal_generator.py        # ← generate_signal_hybrid()
├── backtest_mean_reversion.py # ← Бэктест v5 MR
├── backtest_hybrid.py         # ← Бэктест Hybrid
├── bot.py                     # ← Для live trading
├── paper_trader.py            # ← Для paper trading
├── mean_reversion_trades.csv  # ← Результаты v5 MR
├── hybrid_trades.csv          # ← Результаты Hybrid
├── equity_curve_comparison.png
├── equity_curve_hybrid.png
├── FINAL_COMPARISON_v5_vs_HYBRID.md  # ← Анализ
└── USAGE_GUIDE_v5_HYBRID.md   # ← Эта инструкция
```

---

**Дата**: 2025-10-12  
**Версия**: v5 + Hybrid v1  
**Автор**: AI Trading Bot Assistant  
**Статус**: ✅ Ready for Production

