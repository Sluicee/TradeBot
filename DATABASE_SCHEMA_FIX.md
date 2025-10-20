# 🗄️ Database Schema Fix - Missing Columns

## Проблема
```
sqlite3.OperationalError: no such column: real_trading_state.start_time
```

## Причина
Таблица `real_trading_state` была создана с базовыми колонками, но SQLAlchemy модель ожидает дополнительные колонки.

## Решение

### 1. Обновленная миграция
Добавлены недостающие колонки в `migrate_database.py`:

```sql
-- Новые колонки для real_trading_state:
start_time DATETIME
winning_trades INTEGER DEFAULT 0
losing_trades INTEGER DEFAULT 0
total_commission REAL DEFAULT 0.0
stop_loss_triggers INTEGER DEFAULT 0
take_profit_triggers INTEGER DEFAULT 0
trailing_stop_triggers INTEGER DEFAULT 0
```

### 2. Автоматическое добавление колонок
Миграция теперь:
- ✅ Проверяет существующие колонки
- ✅ Добавляет недостающие колонки автоматически
- ✅ Совместима с уже существующими таблицами

## Команды для исправления

### 1. Обновить код и пересобрать Docker:
```bash
# Получить обновления
git pull

# Пересобрать контейнер
docker-compose down
docker-compose up -d --build

# Проверить логи
docker-compose logs -f tradebot
```

### 2. Проверить что миграция работает:
```bash
# Должно показать:
✅ real_trading_state table already exists
Checking for missing columns in real_trading_state...
Adding missing column: start_time
Adding missing column: winning_trades
Adding missing column: losing_trades
Adding missing column: total_commission
Adding missing column: stop_loss_triggers
Adding missing column: take_profit_triggers
Adding missing column: trailing_stop_triggers
✅ Added 7 missing columns to real_trading_state
```

### 3. Проверить что бот запускается:
```bash
# Должно показать:
🚀 Запуск TradeBot...
✅ База данных найдена
🔄 Проверка миграции БД...
✅ Миграция БД завершена
▶️  Запуск бота...
✅ Бот запущен успешно
```

## Структура таблицы real_trading_state

### До исправления:
```sql
CREATE TABLE real_trading_state (
    id INTEGER PRIMARY KEY,
    is_running BOOLEAN DEFAULT FALSE,
    daily_pnl REAL DEFAULT 0.0,
    total_trades INTEGER DEFAULT 0,
    last_reset_date DATE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### После исправления:
```sql
CREATE TABLE real_trading_state (
    id INTEGER PRIMARY KEY,
    is_running BOOLEAN DEFAULT FALSE,
    start_time DATETIME,                    -- ← НОВОЕ
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,       -- ← НОВОЕ
    losing_trades INTEGER DEFAULT 0,       -- ← НОВОЕ
    total_commission REAL DEFAULT 0.0,      -- ← НОВОЕ
    stop_loss_triggers INTEGER DEFAULT 0,  -- ← НОВОЕ
    take_profit_triggers INTEGER DEFAULT 0, -- ← НОВОЕ
    trailing_stop_triggers INTEGER DEFAULT 0, -- ← НОВОЕ
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## Проверка после исправления

### 1. Проверить структуру таблицы:
```bash
docker-compose exec tradebot sqlite3 /app/data/tradebot.db ".schema real_trading_state"
```

### 2. Проверить что бот запускается:
```bash
docker-compose logs tradebot | grep -E "(ERROR|SUCCESS|✅|❌)"
```

### 3. Проверить Real Trading:
```bash
# В Telegram боту:
/real_status
```

## Результат

После исправления:
- ✅ **Все колонки добавлены** - SQLAlchemy модель работает
- ✅ **Миграция автоматическая** - при `./update.sh`
- ✅ **Бот запускается** - без ошибок базы данных
- ✅ **Real Trading готов** - все функции работают

**Проблема с отсутствующими колонками решена! 🚀**
