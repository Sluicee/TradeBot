# TradeBot Dashboard

Панель визуализации и управления для TradeBot на основе Streamlit.

## 📊 Возможности

### 1. Обзор
- KPI-карточки: баланс, P&L, win rate, количество позиций
- Equity curve (график капитала)
- Последние 5 сделок

### 2. Текущие позиции
- Таблица открытых позиций с детальной информацией
- Количество докупаний и средняя цена входа
- История докупаний для каждой позиции
- Режим (PYRAMID/AVERAGE)

### 3. История сделок
- Фильтры по символу, типу сделки, прибыльности
- Детальная таблица всех сделок
- Распределение P&L (гистограмма)
- Экспорт в CSV

### 4. Метрики
**Основные:**
- Total Trades, Win Rate, Profit Factor
- Winning/Losing Trades
- Average Win/Loss
- Max Consecutive Wins/Losses

**Продвинутые:**
- Sharpe Ratio
- Sortino Ratio
- Maximum Drawdown
- Kelly Criterion рекомендация

**Графики:**
- Equity Drawdown Chart
- Box plot распределения P&L

### 5. Бэктесты
- Загрузка результатов из `backtests/`
- Отображение метрик для каждого бэктеста
- Сравнение нескольких бэктестов
- Overlay equity curves

### 6. Настройки
- Включение/выключение Kelly Criterion
- Включение/выключение Averaging
- Включение/выключение Pyramid Mode
- Параметры (Kelly Fraction, Max Averaging Attempts, Averaging Drop %)
- Экспорт данных
- Сброс paper trading

## 🚀 Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Убедитесь, что bot запущен и создан файл `paper_trading_state.json`

3. Запустите dashboard:
```bash
streamlit run dashboard.py
```

4. Откройте браузер по адресу: http://localhost:8501

## ⚙️ Конфигурация

Dashboard автоматически загружает данные из:
- `paper_trading_state.json` - текущее состояние paper trading
- `backtests/` - результаты бэктестов
- `dashboard_settings.json` - настройки dashboard (создается автоматически)

## 📝 Настройки в config.py

### Kelly Criterion
```python
USE_KELLY_CRITERION = True  # Включить Kelly
KELLY_FRACTION = 0.25  # 25% от полного Kelly
MIN_TRADES_FOR_KELLY = 10  # Минимум сделок
KELLY_LOOKBACK_WINDOW = 50  # Скользящее окно
```

### Averaging
```python
ENABLE_AVERAGING = True  # Включить докупание
MAX_AVERAGING_ATTEMPTS = 2  # Максимум докупаний
AVERAGING_PRICE_DROP_PERCENT = 0.05  # Падение 5%
AVERAGING_TIME_THRESHOLD_HOURS = 24  # Порог времени
MAX_TOTAL_RISK_MULTIPLIER = 1.5  # Максимальный риск 1.5x
```

### Pyramid Mode
```python
ENABLE_PYRAMID_UP = True  # Пирамидинг вверх
PYRAMID_ADX_THRESHOLD = 25  # Порог ADX для пирамидинга
```

## 🔄 Автообновление

Dashboard поддерживает автообновление данных каждые 60 секунд:
1. Включите чекбокс "Автообновление (60с)" в боковой панели
2. Или нажмите кнопку "🔄 Обновить сейчас" для ручного обновления

## 📱 Telegram команды

### Kelly Criterion
```
/kelly_info - Информация о Kelly Criterion и текущая рекомендация
```

### Averaging
```
/averaging_status - Статус докупаний по позициям и общая статистика
```

## 📈 Как это работает

### Kelly Criterion
1. Рассчитывается на основе последних 50 сделок (скользящее окно)
2. Использует win rate, avg win, avg loss
3. Применяется консервативная дробь (25% от полного Kelly)
4. Нормализуется по волатильности (ATR)
5. Результат: множитель 0.5-1.5 для размера позиции

### Умное докупание
**AVERAGE_DOWN (усреднение вниз):**
- Триггер: цена упала на 5% от средней И позиция висит >24 часа
- Размер: 50% от исходного
- Пересчёт средней цены и SL/TP

**PYRAMID_UP (пирамидинг вверх):**
- Триггер: ADX > 25 (сильный тренд) И новый BUY сигнал
- Размер: 30% от исходного (зависит от силы сигнала)
- Докупаем при росте цены на 2%

**Ограничения:**
- Максимум 2-3 докупания на позицию
- Общий риск не более 1.5x от базового
- SL не сужается при усреднении (берётся max)

## 🎯 Метрики

### Sharpe Ratio
Годовой Sharpe = (средняя доходность / стандартное отклонение) × √252

### Sortino Ratio
Как Sharpe, но учитывает только downside volatility

### Kelly Criterion
Kelly = (win_rate × avg_win - (1 - win_rate) × avg_loss) / avg_win

### Maximum Drawdown
Максимальная просадка от пика баланса в процентах

## 💡 Советы

1. **Kelly Criterion**: Начните с 25% (KELLY_FRACTION = 0.25), это консервативно и безопасно
2. **Averaging**: Используйте MAX_AVERAGING_ATTEMPTS = 2, больше может превратиться в мартингейл
3. **Pyramid**: Включайте только при высоком ADX (>25), иначе высокий риск
4. **Dashboard**: Используйте страницу Метрики для анализа эффективности стратегии
5. **Бэктесты**: Сравнивайте разные конфигурации через страницу Бэктестов

## 🐛 Troubleshooting

### Dashboard не запускается
```bash
# Проверьте версию Python (требуется 3.10+)
python --version

# Переустановите зависимости
pip install -r requirements.txt --upgrade
```

### Нет данных в Dashboard
1. Убедитесь, что paper trading запущен: `/paper_start`
2. Проверьте наличие файла `paper_trading_state.json`
3. Совершите хотя бы одну сделку

### Ошибка кэширования
```bash
# Очистите кэш Streamlit
streamlit cache clear
```

## 📚 Дополнительно

- Все графики интерактивные (Plotly)
- Данные кэшируются для быстрой загрузки
- Настройки сохраняются в `dashboard_settings.json`
- Экспорт данных в CSV доступен на странице "История сделок"

## 🔗 Ссылки

- Документация Streamlit: https://docs.streamlit.io/
- Plotly Documentation: https://plotly.com/python/
- Kelly Criterion: https://en.wikipedia.org/wiki/Kelly_criterion

