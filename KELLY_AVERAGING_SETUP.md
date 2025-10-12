# Kelly Criterion + Averaging + Dashboard - Руководство по запуску

## 🎯 Что реализовано

### 1. Kelly Criterion
✅ Расчёт оптимального размера позиции на основе статистики
✅ Скользящее окно последних 50 сделок
✅ Нормализация по волатильности (ATR)
✅ Консервативная дробь Kelly (25%)
✅ Интеграция в `get_position_size_percent()`

**Файлы:**
- `config.py` - параметры Kelly
- `paper_trader.py` - метод `calculate_kelly_fraction()`

### 2. Умное докупание (Averaging)
✅ AVERAGE_DOWN - усреднение при падении цены
✅ PYRAMID_UP - пирамидинг при сильном тренде (ADX > 25)
✅ Ограничение по количеству докупаний (MAX_AVERAGING_ATTEMPTS)
✅ Контроль общего риска (MAX_TOTAL_RISK_MULTIPLIER)
✅ Умное обновление SL/TP (не сужаем SL)
✅ История докупаний

**Файлы:**
- `config.py` - параметры Averaging
- `paper_trader.py` - методы `can_average_down()`, `average_position()`

### 3. Streamlit Dashboard
✅ Страница "Обзор" - KPI и equity curve
✅ Страница "Текущие позиции" - таблица с докупаниями
✅ Страница "История сделок" - фильтры и экспорт
✅ Страница "Метрики" - Sharpe, Sortino, Drawdown, Kelly
✅ Страница "Бэктесты" - загрузка и сравнение
✅ Страница "Настройки" - управление параметрами
✅ Автообновление данных (60 сек)
✅ Кэширование для производительности

**Файлы:**
- `dashboard.py` - основной файл dashboard
- `DASHBOARD_README.md` - документация

### 4. Telegram Bot интеграция
✅ Команда `/kelly_info` - информация о Kelly Criterion
✅ Команда `/averaging_status` - статус докупаний по позициям

**Файлы:**
- `telegram_bot.py` - новые команды

### 5. Зависимости
✅ `requirements.txt` обновлен:
- streamlit>=1.32.0
- plotly>=5.18.0
- scipy>=1.11.0

## 🚀 Быстрый старт

### Шаг 1: Установка зависимостей
```bash
pip install -r requirements.txt
```

### Шаг 2: Настройка config.py
Все параметры уже добавлены в `config.py`:

```python
# Kelly Criterion (включен по умолчанию)
USE_KELLY_CRITERION = True
KELLY_FRACTION = 0.25
MIN_TRADES_FOR_KELLY = 10
KELLY_LOOKBACK_WINDOW = 50

# Averaging (включен по умолчанию)
ENABLE_AVERAGING = True
MAX_AVERAGING_ATTEMPTS = 2
AVERAGING_PRICE_DROP_PERCENT = 0.05
AVERAGING_TIME_THRESHOLD_HOURS = 24
MAX_TOTAL_RISK_MULTIPLIER = 1.5

# Pyramid Mode (включен по умолчанию)
ENABLE_PYRAMID_UP = True
PYRAMID_ADX_THRESHOLD = 25
```

### Шаг 3: Запуск бота
```bash
python bot.py
```

### Шаг 4: Запуск Dashboard
В отдельном терминале:
```bash
streamlit run dashboard.py
```

Dashboard откроется по адресу: http://localhost:8501

### Шаг 5: Telegram команды
```
/paper_start - Запустить paper trading
/kelly_info - Информация о Kelly Criterion
/averaging_status - Статус докупаний
```

## 🧪 Тестирование

### Тест 1: Kelly Criterion (изолированно)

1. Отключите averaging в `config.py`:
```python
ENABLE_AVERAGING = False
```

2. Запустите бэктест:
```bash
python backtest.py BTCUSDT 1h 2024-01-01 2024-06-01
```

3. Сравните результаты:
   - ROI должен быть стабильнее
   - Max Drawdown должен быть меньше
   - Win Rate может остаться прежним, но размер позиций оптимизируется

4. Проверьте через Dashboard:
   - Страница "Метрики" → Kelly рекомендация
   - Equity curve должна быть более гладкой

### Тест 2: Averaging (изолированно)

1. Отключите Kelly в `config.py`:
```python
USE_KELLY_CRITERION = False
ENABLE_AVERAGING = True
```

2. Запустите paper trading:
```bash
python bot.py
# В Telegram: /paper_start
```

3. Ждите докупания (24 часа + падение 5%)

4. Проверьте:
   - `/averaging_status` - статус докупаний
   - Dashboard → "Текущие позиции" - количество докупаний
   - Средняя цена должна обновиться

### Тест 3: Полная интеграция

1. Включите оба модуля:
```python
USE_KELLY_CRITERION = True
ENABLE_AVERAGING = True
```

2. Запустите walkforward анализ:
```bash
python backtest_walkforward.py BTCUSDT 1h 2024-01-01 2024-06-01
```

3. Проверьте результаты:
   - ROI должен улучшиться
   - Sharpe Ratio должен вырасти
   - Max Drawdown должен снизиться

4. Dashboard:
   - Страница "Бэктесты" → сравните с baseline
   - Проверьте метрики

### Тест 4: Dashboard

1. Откройте Dashboard:
```bash
streamlit run dashboard.py
```

2. Проверьте все страницы:
   - ✅ Обзор - KPI карточки работают
   - ✅ Текущие позиции - таблица отображается
   - ✅ История сделок - фильтры работают
   - ✅ Метрики - графики загружаются
   - ✅ Бэктесты - файлы из `backtests/` отображаются
   - ✅ Настройки - сохранение работает

3. Тест автообновления:
   - Включите "Автообновление (60с)"
   - Совершите сделку в боте
   - Проверьте, что данные обновились

4. Тест экспорта:
   - Страница "История сделок" → Экспорт в CSV
   - Проверьте файл

## 📊 Мониторинг эффективности

### До и После

**Baseline (без Kelly и Averaging):**
```bash
python backtest.py BTCUSDT 1h 2024-01-01 2024-06-01
```
Запишите: ROI, Sharpe, Max DD, Win Rate

**С Kelly (без Averaging):**
```python
USE_KELLY_CRITERION = True
ENABLE_AVERAGING = False
```
```bash
python backtest.py BTCUSDT 1h 2024-01-01 2024-06-01
```
Ожидаемо: ROI ~same, Sharpe +10-15%, Max DD -10-20%

**С Averaging (без Kelly):**
```python
USE_KELLY_CRITERION = False
ENABLE_AVERAGING = True
```
```bash
python backtest.py BTCUSDT 1h 2024-01-01 2024-06-01
```
Ожидаемо: ROI +5-10%, Win Rate +5-10%, Max DD может вырасти

**Полная интеграция:**
```python
USE_KELLY_CRITERION = True
ENABLE_AVERAGING = True
```
```bash
python backtest.py BTCUSDT 1h 2024-01-01 2024-06-01
```
Ожидаемо: ROI +10-20%, Sharpe +15-25%, Max DD -15-25%

### Метрики успеха

✅ **Kelly работает хорошо если:**
- Sharpe Ratio вырос на >10%
- Max Drawdown снизился на >10%
- Размеры позиций адаптируются (проверьте в `paper_trading_state.json`)

✅ **Averaging работает хорошо если:**
- Win Rate вырос на >5%
- Количество успешных докупаний > 50%
- Средняя цена после докупания лучше исходной

✅ **Dashboard работает если:**
- Все страницы загружаются без ошибок
- Графики интерактивные
- Данные актуальные (проверьте время обновления)
- Настройки сохраняются

## 🐛 Решение проблем

### Проблема: Kelly не применяется

**Диагностика:**
```bash
python -c "from paper_trader import PaperTrader; pt = PaperTrader(); pt.load_state(); print(pt.calculate_kelly_fraction('BTCUSDT', 1.5))"
```

**Возможные причины:**
1. Недостаточно сделок (<10)
2. USE_KELLY_CRITERION = False
3. Ошибка в расчётах (проверьте логи)

**Решение:**
- Запустите больше сделок
- Проверьте config.py
- Включите DEBUG логирование

### Проблема: Averaging не срабатывает

**Диагностика:**
```bash
# В Telegram
/averaging_status
```

**Возможные причины:**
1. ENABLE_AVERAGING = False
2. Не выполнены условия (время + цена)
3. Превышен лимит докупаний

**Решение:**
- Проверьте параметры в config.py
- Уменьшите AVERAGING_TIME_THRESHOLD_HOURS для теста
- Проверьте логи: `grep "AVERAGE" logs/tradebot.log`

### Проблема: Dashboard не показывает данные

**Диагностика:**
```bash
# Проверьте наличие файла
ls -lh paper_trading_state.json

# Проверьте содержимое
python -c "import json; print(json.load(open('paper_trading_state.json'))['balance'])"
```

**Решение:**
1. Запустите paper trading: `/paper_start`
2. Совершите хотя бы одну сделку
3. Очистите кэш Streamlit: `streamlit cache clear`
4. Перезапустите Dashboard

### Проблема: Высокая просадка при Averaging

**Симптомы:**
- Max Drawdown увеличился >20%
- Много последовательных убыточных докупаний

**Решение:**
1. Уменьшите MAX_AVERAGING_ATTEMPTS (с 2 до 1)
2. Увеличьте AVERAGING_PRICE_DROP_PERCENT (с 5% до 7%)
3. Увеличьте AVERAGING_TIME_THRESHOLD_HOURS (с 24 до 48)
4. Отключите ENABLE_PYRAMID_UP на флэтовых рынках

## 📈 Оптимизация параметров

### Kelly Fraction
```python
# Консервативный (рекомендуется)
KELLY_FRACTION = 0.25  # 25% от полного Kelly

# Умеренный
KELLY_FRACTION = 0.40  # 40%

# Агрессивный (не рекомендуется)
KELLY_FRACTION = 0.50  # 50%
```

### Averaging параметры
```python
# Консервативный (для флэта)
MAX_AVERAGING_ATTEMPTS = 1
AVERAGING_PRICE_DROP_PERCENT = 0.07  # 7%
AVERAGING_TIME_THRESHOLD_HOURS = 48

# Умеренный (базовый)
MAX_AVERAGING_ATTEMPTS = 2
AVERAGING_PRICE_DROP_PERCENT = 0.05  # 5%
AVERAGING_TIME_THRESHOLD_HOURS = 24

# Агрессивный (для тренда)
MAX_AVERAGING_ATTEMPTS = 3
AVERAGING_PRICE_DROP_PERCENT = 0.03  # 3%
AVERAGING_TIME_THRESHOLD_HOURS = 12
```

### Pyramid параметры
```python
# Только сильный тренд
PYRAMID_ADX_THRESHOLD = 30

# Базовый
PYRAMID_ADX_THRESHOLD = 25

# Умеренный тренд (рискованнее)
PYRAMID_ADX_THRESHOLD = 20
```

## 🎓 Дополнительные ресурсы

- **Kelly Criterion**: https://en.wikipedia.org/wiki/Kelly_criterion
- **Position Sizing**: https://www.investopedia.com/terms/k/kellycriterion.asp
- **Averaging Strategies**: https://www.investopedia.com/terms/a/averagedown.asp
- **Pyramiding**: https://www.investopedia.com/terms/p/pyramiding.asp
- **Sharpe Ratio**: https://www.investopedia.com/terms/s/sharperatio.asp

## ✅ Checklist для деплоя

- [ ] Протестировали Kelly изолированно
- [ ] Протестировали Averaging изолированно
- [ ] Протестировали полную интеграцию
- [ ] Запустили walkforward анализ (6+ месяцев)
- [ ] Проверили Dashboard на всех страницах
- [ ] Проверили Telegram команды `/kelly_info` и `/averaging_status`
- [ ] Настроили параметры под свой риск-профиль
- [ ] Бэкап `paper_trading_state.json`
- [ ] Мониторинг логов (`tail -f logs/tradebot.log`)
- [ ] Установили алерты на критические события

## 🚨 Важные замечания

1. **Kelly Criterion** - это рекомендация, не гарантия. Всегда используйте консервативную дробь.
2. **Averaging** может увеличить просадку. Контролируйте MAX_TOTAL_RISK_MULTIPLIER.
3. **Pyramid Mode** работает только на трендовых рынках (ADX > 25).
4. **Dashboard** - это инструмент анализа, не торговая платформа.
5. Всегда тестируйте на paper trading перед реальными деньгами.

Удачи! 🚀

