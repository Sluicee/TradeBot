# 📈 Crypto Trading Bot - Продвинутая система алгоритмической торговли

## О проекте

**Продвинутый торговый бот** с гибридной стратегией, статистическими моделями и интерактивным дашбордом. Использует публичный REST API биржи **Bybit (Unified Trading API v5)** для получения рыночных данных и Telegram для управления.

## ✨ Ключевые возможности

### 🎯 Торговые стратегии
- **Hybrid Strategy** (🏆 рекомендуется) - автоматическое переключение между Mean Reversion и Trend Following
- **Mean Reversion v5** - торговля откатов с фильтрами "падающего ножа"
- **Trend Following** - классическая трендовая стратегия

### 🧠 Статистические модели
- **Bayesian Decision Layer** - оценка вероятности успеха сигналов
- **Z-Score Analysis** - детекция перекупленности/перепроданности
- **Markov Regime Switcher** - определение режима рынка (BULL/BEAR/SIDEWAYS/HIGH_VOL)

### 📊 Аналитика и мониторинг
- **Streamlit Dashboard** - интерактивная панель с KPI, графиками и метриками
- **SQLite/PostgreSQL** - надежное хранение всех данных
- **Signal Logger** - детальная история всех сигналов

### 💎 Продвинутые техники
- **Kelly Criterion** - оптимальный размер позиций
- **Smart Averaging** - умное докупание (Average Down + Pyramid Up)
- **Dynamic Stop-Loss/Take-Profit** - адаптивные уровни на основе ATR
- **Trailing Stop** - двухуровневый трейлинг для защиты прибыли

### 🔧 Инструменты
- **Paper Trading** - безрисковое тестирование на реальных данных
- **Walk-forward Backtesting** - честная оценка стратегий
- **Telegram Bot** - полное управление и мониторинг
- **Docker Support** - быстрое развертывание в один клик

> 📖 **Полная документация:** [USAGE_GUIDE_v5_HYBRID.md](USAGE_GUIDE_v5_HYBRID.md)

---

## 🚀 Технологический стек

* **Python 3.10+** - основной язык
* **aiohttp** - асинхронные HTTP-запросы к Bybit API
* **pandas** - обработка временных рядов
* **numpy/scipy** - статистический анализ
* **Streamlit** - интерактивный дашборд
* **Plotly** - визуализация данных
* **SQLAlchemy** - ORM для работы с БД
* **python-telegram-bot** - интеграция с Telegram
* **Docker** - контейнеризация

---

## ⚙️ Установка и запуск

### 🐳 Docker (самый простой способ)

```bash
# 1. Клонируйте репозиторий
git clone <URL вашего репозитория>
cd TradeBot

# 2. Настройте .env файл
cp env.example .env
nano .env

# 3. Запустите через Docker Compose
docker-compose up -d

# 4. Проверьте статус
docker-compose ps
docker-compose logs -f
```

**Dashboard:** http://localhost:8501

### 🖥️ Локальная установка (Windows/Mac/Linux)

```bash
# 1. Клонируйте репозиторий
git clone <URL вашего репозитория>
cd TradeBot

# 2. Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# 3. Установите зависимости
pip install -r requirements.txt

# 4. Инициализируйте БД
python init_db.py

# 5. Настройте конфигурацию
cp env.example .env
nano .env

# 6. Запустите бота
python bot.py

# 7. (опционально) Запустите dashboard
streamlit run dashboard.py
```

### 🚀 Развертывание на сервере (Linux)

```bash
# 1. Клонируйте репозиторий
git clone <URL вашего репозитория>
cd TradeBot

# 2. Настройте .env файл
cp env.example .env
nano .env

# 3. Запустите автоматическое развертывание
chmod +x deploy.sh
./deploy.sh

# 4. Запустите бота как сервис
sudo systemctl start tradebot
sudo systemctl status tradebot

# 5. Логи
sudo journalctl -u tradebot -f
```

**📖 Подробнее:** [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md) | [PRE_DEPLOY_CHECKLIST.md](PRE_DEPLOY_CHECKLIST.md)

### Настройка .env файла

Получите:
- **TELEGRAM_TOKEN** у [@BotFather](https://t.me/BotFather)
- **OWNER_CHAT_ID** у [@userinfobot](https://t.me/userinfobot)

```env
TELEGRAM_TOKEN=your_bot_token_here
OWNER_CHAT_ID=your_telegram_id_here
DEFAULT_SYMBOL=BTCUSDT
DEFAULT_INTERVAL=15m
```

### 🔒 Безопасность

**Важно!** Бот теперь защищен от несанкционированного доступа:

- ✅ Только владелец (указанный в `OWNER_CHAT_ID`) может управлять ботом
- ✅ Другие пользователи получат сообщение с отказом в доступе
- ✅ При отказе бот покажет ID пользователя для диагностики
- ⚠️ Если `OWNER_CHAT_ID` не установлен, бот будет доступен всем (небезопасно!)

**Как получить свой Telegram ID:**
1. Напишите боту [@userinfobot](https://t.me/userinfobot)
2. Скопируйте ваш ID
3. Добавьте в `.env`: `OWNER_CHAT_ID=123456789`

**Что защищено:**
- Все команды управления (start, add, remove, settings)
- Все команды Paper Trading (paper_start, paper_stop, и т.д.)
- Анализ и отладка (analyze, paper_debug)
- Фоновые уведомления (отправляются только владельцу)

---

## 💬 Telegram Bot - Команды

### 📊 Основные команды
```
/start              - Приветствие и краткая информация
/help               - Полный список команд
/status             - Статус бота и отслеживаемые пары
/add SYMBOL         - Добавить пару для отслеживания (например: /add BTCUSDT)
/remove SYMBOL      - Удалить пару из отслеживания
/list               - Список отслеживаемых пар
/analyze [SYMBOL]   - Технический анализ пары
```

### 💰 Paper Trading

**Управление:**
```
/paper_start [баланс]   - Запустить виртуальную торговлю (по умолчанию $100)
/paper_stop             - Остановить и закрыть все позиции
/paper_reset            - Сбросить баланс и историю
```

**Мониторинг:**
```
/paper_status           - Текущие позиции и статистика
/paper_balance          - Детали баланса и распределения капитала
/paper_trades [N]       - История последних N сделок (по умолчанию 10)
```

**Продвинутые возможности:**
```
/kelly_info             - Информация о Kelly Criterion и рекомендации
/averaging_status       - Статус докупаний по позициям
```

**Тестирование и отладка:**
```
/paper_backtest [часы]      - Быстрая симуляция на исторических данных (1-168 часов)
/paper_debug [SYMBOL]       - Детальная отладка сигналов и фильтров
/paper_candidates           - Показать пары близкие к генерации сигнала
/paper_force_buy [SYMBOL]   - Принудительная покупка для тестирования
```

### 🎯 Текущая стратегия (Hybrid)

**Режимы работы:**
- **Mean Reversion** (ADX < 20) - торговля откатов в боковом рынке
	- Быстрые тейки 2.5-4%
	- Узкий стоп-лосс 2.5-5%
	- Фильтры "падающего ножа"
- **Trend Following** (ADX > 25) - торговля трендов
	- Тейк-профит 10%
	- Стоп-лосс 5-8%
	- Частичное закрытие + trailing stop

**Параметры риска:**
- 🛑 **Stop-loss**: 2.5-8% (адаптивный на основе ATR)
- 💎 **Take-profit**: 2.5-10% (зависит от режима)
- 🔻 **Trailing stop**: 0.8-2% от максимума
- 💰 **Размер позиции**: 30-70% (Kelly Criterion + сила сигнала)
- 📊 **Макс. позиций**: 3 одновременно
- 💸 **Комиссия**: 0.18% на каждую сделку
- 🔄 **Докупание**: до 2-3 раз (Average Down + Pyramid Up)

**Фильтры Mean Reversion:**
- ✅ RSI < 40 (перепроданность)
- ✅ Z-score < -1.8 (отклонение от среднего)
- ✅ ADX < 35 (нет сильного тренда)
- ✅ Не ниже 24h минимума на 4%
- ✅ EMA200 не падает сильно
- ✅ Нет красных свечей подряд (3+)
- ✅ Нет всплесков объёма (>1.5x)

**Фильтры Trend Following:**
- ✅ ADX > 25 (сильный тренд)
- ✅ EMA пересечение + подтверждение
- ✅ MACD подтверждает направление
- ✅ Минимум 5 "голосов" за направление

### 💡 Пример использования

```bash
# 1. Запустите Paper Trading
/paper_start 100

# 2. Добавьте пары для отслеживания
/add BTCUSDT
/add ETHUSDT
/add SOLUSDT

# 3. Проверьте статус
/paper_status

# 4. Быстрая симуляция за 7 дней (168 часов)
/paper_backtest 168

# 5. Детальная отладка (почему нет сигналов?)
/paper_debug BTCUSDT

# 6. Посмотрите кандидатов на сделку
/paper_candidates

# 7. Информация о Kelly Criterion
/kelly_info

# 8. Статус докупаний
/averaging_status

# 9. История последних 20 сделок
/paper_trades 20

# 10. Для теста можно принудительно открыть позицию
/paper_force_buy BTCUSDT
```

---

## 📊 Dashboard (Streamlit)

Интерактивная панель для визуализации и управления ботом.

### Запуск

```bash
streamlit run dashboard.py
```

**URL:** http://localhost:8501

### Возможности

#### 1. Обзор (Overview)
- KPI-карточки: баланс, P&L, win rate, количество позиций
- Equity curve (график капитала)
- Последние 5 сделок
- Активные позиции с докупаниями

#### 2. История сделок (Trade History)
- Фильтры по символу, типу сделки, прибыльности
- Детальная таблица всех сделок
- Распределение P&L (гистограмма)
- Экспорт в CSV

#### 3. Метрики (Metrics)
**Основные:**
- Total Trades, Win Rate, Profit Factor
- Winning/Losing Trades
- Average Win/Loss
- Max Consecutive Wins/Losses

**Продвинутые:**
- Sharpe Ratio (доходность с учётом риска)
- Sortino Ratio (учитывает только downside volatility)
- Maximum Drawdown
- Kelly Criterion рекомендация

**Графики:**
- Equity Drawdown Chart
- Box plot распределения P&L

#### 4. Бэктесты (Backtests)
- Загрузка результатов из `backtests/`
- Отображение метрик для каждого бэктеста
- Сравнение нескольких бэктестов
- Overlay equity curves

#### 5. Настройки (Settings)
- Включение/выключение Kelly Criterion
- Включение/выключение Averaging
- Включение/выключение Pyramid Mode
- Параметры (Kelly Fraction, Max Averaging Attempts, Averaging Drop %)
- Экспорт данных
- Сброс paper trading

**📖 Подробнее:** [DASHBOARD_README.md](DASHBOARD_README.md)

---

## 🗄️ База данных

SQLite (dev) / PostgreSQL (prod) для надежного хранения данных.

### Структура

**Основные таблицы:**
- `paper_trading_state` - состояние paper trading
- `positions` - открытые позиции
- `averaging_entries` - история докупаний
- `trades_history` - история всех сделок
- `tracked_symbols` - отслеживаемые пары
- `bot_settings` - настройки бота
- `signals` - логи сигналов
- `backtests` - результаты бэктестов
- `backtest_trades` - сделки в бэктестах

### Управление

```bash
# Инициализация БД
python init_db.py

# Проверка целостности
python init_db.py check

# Сброс БД (ОПАСНО!)
python init_db.py reset

# Тесты
python test_database.py

# Бэкап (SQLite)
cp tradebot.db tradebot_backup_$(date +%Y%m%d).db
```

**📖 Подробнее:** [DATABASE_README.md](DATABASE_README.md)

---

## 🧠 Статистические модели

Продвинутые модели для повышения точности торговых решений.

### 1. Bayesian Decision Layer

**Идея:** Храним статистику успешности каждого типа сигнала.

```python
P(profit | signal) = успешные сигналы / общее количество
```

Для каждого сигнала создаётся **сигнатура**:
```
RSI<30_EMA_CROSS_UP_ADX>25_TRENDING_MACD_POS
```

**Порог входа:** P(profit) >= 55%

### 2. Z-Score Mean Reversion

**Формула:**
```
z = (price - SMA_50) / std(price - SMA_50)
```

**Сигналы:**
- `z < -2.0` → BUY (цена перепродана)
- `z > 2.0` → SELL (цена перекуплена)

### 3. Markov Regime Switching

**Режимы рынка:**
- **BULL** - бычий рынок
- **BEAR** - медвежий рынок
- **HIGH_VOL** - высокая волатильность (НЕ торговать)
- **SIDEWAYS** - боковик (mean reversion)

**Торговые правила:**
- `HIGH_VOL` → блокировать торговлю
- `BULL` + `BUY` → торговать
- `BEAR` + `SELL` → торговать
- `SIDEWAYS` → mean reversion стратегия

### Ensemble Decision Maker

Финальное решение принимается голосованием с весами:

```python
Score = Bayesian_Weight × P(profit) +
				ZScore_Weight × ZScore_Confidence +
				Regime_Weight × Regime_Confidence

# Веса по умолчанию: 40% / 30% / 30%
# Порог: Score > 0.5 для входа
```

### Настройка (config.py)

```python
USE_STATISTICAL_MODELS = True  # Включить модели

# Bayesian
BAYESIAN_MIN_PROBABILITY = 0.55  # Требуем 55% вероятности успеха

# Z-Score
ZSCORE_BUY_THRESHOLD = -2.0
ZSCORE_SELL_THRESHOLD = 2.0

# Markov Regime
MARKOV_VOL_HIGH = 0.03  # 3% высокая волатильность
```

**📖 Подробнее:** [STATISTICAL_MODELS.md](STATISTICAL_MODELS.md) | [MODELS_README_RU.md](MODELS_README_RU.md)

---

## 📈 Бэктестинг

### Доступные скрипты

```bash
# Базовый бэктест Trend Following
python backtest.py

# Mean Reversion v5
python backtest_mean_reversion.py

# Hybrid Strategy (рекомендуется)
python backtest_hybrid.py

# Walk-forward тест (честная оценка)
python backtest_walkforward.py

# Сравнение стратегий
python backtest_compare.py
python test_strategy_comparison.py
```

### Пример использования

```bash
# Hybrid стратегия на BTCUSDT за последние 30 дней
python backtest_hybrid.py
# Результат: hybrid_trades.csv, equity_curve_hybrid.png

# Mean Reversion на ETHUSDT
python backtest_mean_reversion.py
# Результат: mean_reversion_trades.csv, trend_following_trades.csv

# Сравнение всех стратегий
python test_strategy_comparison.py
```

### Метрики бэктеста

- **Total Return** - общая доходность
- **Win Rate** - процент прибыльных сделок
- **Max Drawdown** - максимальная просадка
- **Sharpe Ratio** - доходность с учётом риска
- **Sortino Ratio** - учитывает только downside volatility
- **Profit Factor** - общая прибыль / общий убыток
- **Average Win/Loss** - средний выигрыш/проигрыш
- **Max Consecutive Wins/Losses** - максимальная серия

---

## 🏆 Результаты (Hybrid Strategy)

Тест на BTCUSDT, 30 дней, интервал 1h, баланс $100:

| Метрика | Значение |
|---------|----------|
| **Total Return** | +1.29% |
| **Win Rate** | 71.4% |
| **Max Drawdown** | 1.56% |
| **Sharpe Ratio** | 1.08 |
| **Total Trades** | 7 |
| **Mode Switches** | 24 |
| **MR Trades** | 5 (71.4% WR) |
| **TF Trades** | 2 (100% WR) |

**Почему Hybrid лучше:**
- ✅ Положительная доходность (+1.29% vs -1.09% TF, -1.20% MR)
- ✅ Высокий Win Rate (71.4%)
- ✅ Низкий Drawdown (1.56%)
- ✅ Отличный Sharpe Ratio (1.08)
- ✅ Адаптируется к рынку (переключение режимов)

**📖 Подробнее:** [FINAL_COMPARISON_v5_vs_HYBRID.md](FINAL_COMPARISON_v5_vs_HYBRID.md)

---

## 🔧 Настройка стратегии (config.py)

### Выбор режима

```python
STRATEGY_MODE = "HYBRID"  # "TREND_FOLLOWING", "MEAN_REVERSION", или "HYBRID"
```

### Hybrid параметры

```python
HYBRID_ADX_MR_THRESHOLD = 20   # ADX < 20 → Mean Reversion
HYBRID_ADX_TF_THRESHOLD = 25   # ADX > 25 → Trend Following
HYBRID_MIN_TIME_IN_MODE = 4    # Минимум 4 часа в одном режиме
```

### Mean Reversion параметры

```python
MR_RSI_OVERSOLD = 40              # Порог перепроданности
MR_ZSCORE_BUY_THRESHOLD = -1.8   # Z-score порог покупки
MR_ADX_MAX = 35                   # Максимальный ADX
MR_TAKE_PROFIT_PERCENT = 0.025   # 2.5% тейк-профит
MR_STOP_LOSS_PERCENT = 0.03      # 3% стоп-лосс
```

### Trend Following параметры

```python
ADX_STRONG = 25                   # Порог сильного тренда
STOP_LOSS_PERCENT = 0.05         # 5% стоп-лосс
TAKE_PROFIT_PERCENT = 0.10       # 10% тейк-профит
PARTIAL_CLOSE_PERCENT = 0.50     # Закрываем 50% на TP
TRAILING_STOP_PERCENT = 0.02     # 2% trailing stop
```

### Kelly Criterion

```python
USE_KELLY_CRITERION = True
KELLY_FRACTION = 0.25            # 25% от полного Kelly
MIN_TRADES_FOR_KELLY = 10        # Минимум сделок для расчёта
```

### Smart Averaging

```python
ENABLE_AVERAGING = True
MAX_AVERAGING_ATTEMPTS = 2       # Максимум 2 докупания
AVERAGING_PRICE_DROP_PERCENT = 0.05  # Докупаем при падении на 5%
ENABLE_PYRAMID_UP = True         # Пирамидинг вверх при сильном тренде
```

---

## 📚 Документация

- [USAGE_GUIDE_v5_HYBRID.md](USAGE_GUIDE_v5_HYBRID.md) - полное руководство по использованию
- [DASHBOARD_README.md](DASHBOARD_README.md) - документация по dashboard
- [DATABASE_README.md](DATABASE_README.md) - работа с БД
- [STATISTICAL_MODELS.md](STATISTICAL_MODELS.md) - статистические модели
- [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md) - развертывание на сервере
- [PRE_DEPLOY_CHECKLIST.md](PRE_DEPLOY_CHECKLIST.md) - чеклист перед запуском
- [DOCKER_COMMANDS.md](DOCKER_COMMANDS.md) - команды Docker
- [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) - миграция данных
- [FINAL_COMPARISON_v5_vs_HYBRID.md](FINAL_COMPARISON_v5_vs_HYBRID.md) - сравнение стратегий

---

## ❓ FAQ

### Какую стратегию выбрать?

**Hybrid** - лучший выбор для большинства случаев. Автоматически переключается между режимами в зависимости от рынка.

### Как включить статистические модели?

```python
# config.py
USE_STATISTICAL_MODELS = True
```

**Важно:** Модели требуют обучения. Запустите paper trading на 1-2 недели для накопления статистики.

### Как увеличить количество сделок?

```python
# Для Hybrid - снизить порог MR
HYBRID_ADX_MR_THRESHOLD = 22  # было 20

# Для MR - смягчить фильтры
MR_RSI_OVERSOLD = 42  # было 40
MR_ZSCORE_BUY_THRESHOLD = -1.6  # было -1.8
```

### Как уменьшить риск?

```python
# Уменьшить размеры позиций
POSITION_SIZE_STRONG = 0.50  # было 0.70
POSITION_SIZE_MEDIUM = 0.35  # было 0.50

# Уменьшить макс. позиций
MAX_POSITIONS = 2  # было 3

# Консервативный Kelly
KELLY_FRACTION = 0.15  # было 0.25
```

### Почему нет сигналов?

1. Проверьте фильтры: `/paper_debug BTCUSDT`
2. Посмотрите кандидатов: `/paper_candidates`
3. Проверьте режим рынка (ADX): `/analyze BTCUSDT`
4. Возможно рынок в HIGH_VOL режиме (бот не торгует)

### Как перейти на реальную торговлю?

1. ✅ Протестируйте paper trading 2-4 недели
2. ✅ Убедитесь в стабильной прибыли
3. ✅ Win Rate > 65%, Sharpe > 0.5
4. ✅ Начните с малого баланса ($100-$500)
5. ✅ Постепенно увеличивайте после подтверждения

**Важно:** Проект предназначен для тестирования и обучения. Реальная торговля на ваш страх и риск.

---

## 🐛 Troubleshooting

### Dashboard не запускается

```bash
# Проверьте версию Python (требуется 3.10+)
python --version

# Переустановите зависимости
pip install -r requirements.txt --upgrade

# Очистите кэш Streamlit
streamlit cache clear
```

### Бот не отвечает

```bash
# Проверьте логи
tail -f trading_bot.log

# Проверьте процесс
ps aux | grep bot.py

# Перезапустите
python bot.py
```

### Ошибка БД "database is locked"

Уже исправлено в `database.py` (StaticPool + check_same_thread=False).

Если проблема осталась:
```bash
# Закройте все процессы
pkill -f bot.py
pkill -f dashboard.py

# Перезапустите
python bot.py
```

### Нет данных в Dashboard

1. Убедитесь, что paper trading запущен: `/paper_start`
2. Проверьте файл `paper_trading_state.json` или БД `tradebot.db`
3. Совершите хотя бы одну сделку

---

## 📝 TODO / Roadmap

- [ ] Machine Learning модель (LSTM/Transformer) для предсказания
- [ ] Sentiment Analysis (анализ новостей и Twitter)
- [ ] Multi-timeframe анализ (корреляция 15m, 1h, 4h)
- [ ] Portfolio optimization (Markowitz)
- [ ] Автоматическая подстройка параметров
- [ ] REST API для управления
- [ ] Web UI (альтернатива Telegram)
- [ ] Поддержка других бирж (Binance, Coinbase)
- [ ] Алертинг (Discord, Email, SMS)

---

## 📄 Лицензия

Этот проект является **личным тестовым проектом** для образовательных целей. 

**Дисклеймер:** Использование бота для реальной торговли на ваш страх и риск. Автор не несет ответственности за возможные потери.

---

## 🙏 Благодарности

- **Bybit API** - надежный источник данных
- **python-telegram-bot** - отличная библиотека
- **Streamlit** - простой способ создания дашбордов
- **Plotly** - красивые интерактивные графики

---

**Версия:** v5 + Hybrid v1  
**Дата:** 2025-10-12  
**Статус:** ✅ Ready for Production (Paper Trading)

---

<div align="center">
	
**Сделано с ❤️ и Python**

[📖 Документация](USAGE_GUIDE_v5_HYBRID.md) • [🐛 Issues](../../issues) • [⭐ Star](../../stargazers)

</div>