# База данных TradeBot

Система использует SQLite/PostgreSQL для хранения всех данных.

## 🗄️ Структура БД

### Основные таблицы:

1. **paper_trading_state** - Состояние paper trading
	 - Баланс, статистика сделок
	 - Настройки торговли

2. **positions** - Открытые позиции
	 - Все параметры позиции (entry, SL, TP, etc.)
	 - Связь с averaging_entries

3. **averaging_entries** - История докупаний
	 - Цена, объём, режим (AVERAGE_DOWN/PYRAMID_UP)

4. **trades_history** - История всех сделок
	 - BUY, SELL, STOP-LOSS, PARTIAL-TP, etc.
	 - Полная информация о P&L

5. **tracked_symbols** - Отслеживаемые символы
	 - Список активных пар

6. **bot_settings** - Настройки бота
	 - chat_id, poll_interval, volatility настройки

7. **signals** - Логи сигналов
	 - Все сигналы с причинами
	 - RSI, ADX, ATR, market_regime

8. **backtests** - Результаты бэктестов
	 - Метрики (Sharpe, Drawdown, Win Rate)
	 - Связь с trades

9. **backtest_trades** - Сделки в бэктестах
	 - Детальная история

## 🚀 Быстрый старт

### 1. Установить зависимости

```bash
pip install sqlalchemy>=2.0.0
```

### 2. Инициализировать БД

```bash
python init_db.py
```

### 3. Запустить бота

```bash
python bot.py
```

## 📊 Использование

### Конфигурация

По умолчанию используется SQLite: `tradebot.db`

Для PostgreSQL (production):

```bash
# .env
DATABASE_URL=postgresql://user:password@localhost:5432/tradebot
```

### Python API

```python
from database import db

# Paper trading
state = db.get_paper_state()
positions = db.get_all_positions()
trades = db.get_trades_history(limit=100)

# Символы
symbols = db.get_tracked_symbols()
db.add_tracked_symbol("BTCUSDT")

# Сигналы
signals = db.get_signals(symbol="BTCUSDT", limit=50)

# Бэктесты
backtests = db.get_backtests(symbol="ETHUSDT")
backtest = db.get_backtest(backtest_id=1)
```

## 🔧 Обслуживание

### Бэкап БД (SQLite)

```bash
# Создать бэкап
cp tradebot.db tradebot_backup_$(date +%Y%m%d).db

# Автоматический бэкап (cron)
0 2 * * * cd /path/to/TradeBot && cp tradebot.db backups/tradebot_$(date +\%Y\%m\%d).db
```

### Очистка старых данных

```python
from database import db, Signal
from datetime import datetime, timedelta

# Удалить старые сигналы (старше 30 дней)
with db.session_scope() as session:
	cutoff = datetime.now() - timedelta(days=30)
	session.query(Signal).filter(Signal.time < cutoff).delete()
	session.commit()
```

### Vacuum (SQLite)

```bash
sqlite3 tradebot.db "VACUUM;"
```

## 📈 Производительность

### Индексы

Все критичные поля проиндексированы:
- `positions.symbol`
- `trades_history.symbol`, `trades_history.time`
- `signals.symbol`, `signals.time`
- `backtests.symbol`, `backtests.created_at`

### Оптимизация запросов

```python
# Лимит на количество записей
trades = db.get_trades_history(limit=100)

# Фильтрация по символу
signals = db.get_signals(symbol="BTCUSDT", limit=50)
```

## 🔒 Безопасность

### SQLite (development)
- Файл: `tradebot.db`
- Права: `chmod 600 tradebot.db`
- Бэкапы: регулярные копии

### PostgreSQL (production)
- SSL соединение
- Отдельный пользователь с ограниченными правами
- Регулярные pg_dump бэкапы
- Connection pooling

```bash
# Создать пользователя PostgreSQL
sudo -u postgres psql
CREATE USER tradebot WITH PASSWORD 'secure_password';
CREATE DATABASE tradebot OWNER tradebot;
GRANT ALL PRIVILEGES ON DATABASE tradebot TO tradebot;
```

## 🐛 Troubleshooting

### Ошибка "database is locked" (SQLite)

```python
# В database.py уже настроено:
StaticPool + check_same_thread=False
```

### Инициализация не работает

1. Проверить, что БД создана:
	 ```bash
	 ls -lh tradebot.db
	 ```

2. Проверить права:
	 ```bash
	 chmod 644 tradebot.db
	 ```

3. Проверить логи:
	 ```bash
	 tail -f trading_bot.log
	 ```

### Пересоздать БД

```bash
python init_db.py reset
```

## 📝 Команды управления

```bash
# Инициализация
python init_db.py

# Проверка целостности
python init_db.py check

# Сброс БД (ОПАСНО!)
python init_db.py reset

# Тесты
python test_database.py
```

## 🚀 Production Checklist

- [ ] Настроить PostgreSQL (если нужно)
- [ ] Запустить инициализацию
- [ ] Проверить работу бота
- [ ] Настроить автоматические бэкапы
- [ ] Добавить мониторинг БД
- [ ] Настроить логирование ошибок БД
