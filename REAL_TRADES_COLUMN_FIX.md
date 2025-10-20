# 🗄️ Real Trades Column Fix - Missing created_at

## Проблема
```
sqlite3.OperationalError: no such column: real_trades.created_at
```

## Причина
SQLAlchemy модель `RealTrade` ожидает колонку `created_at`, но в миграции была создана только `timestamp`.

## Решение

### ✅ Исправлено в migrate_database.py
- **Добавлена колонка `created_at`** в таблицу `real_trades`
- **Автоматическая проверка** существующих колонок
- **Добавление недостающих колонок** для существующих таблиц

### 🔄 Структура таблицы real_trades

#### До исправления:
```sql
CREATE TABLE real_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    order_id TEXT,
    status TEXT DEFAULT 'PENDING',
    commission REAL DEFAULT 0.0,
    realized_pnl REAL DEFAULT 0.0,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    reason TEXT,
    exchange_order_id TEXT,
    avg_price REAL,
    filled_quantity REAL DEFAULT 0.0
);
```

#### После исправления:
```sql
CREATE TABLE real_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    order_id TEXT,
    status TEXT DEFAULT 'PENDING',
    commission REAL DEFAULT 0.0,
    realized_pnl REAL DEFAULT 0.0,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    reason TEXT,
    exchange_order_id TEXT,
    avg_price REAL,
    filled_quantity REAL DEFAULT 0.0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP  -- ← НОВОЕ
);
```

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
✅ real_trades table already exists
Checking for missing columns in real_trades...
Adding missing column: created_at
✅ Added 1 missing columns to real_trades
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

## Проверка после исправления

### 1. Проверить структуру таблицы:
```bash
docker-compose exec tradebot sqlite3 /app/data/tradebot.db ".schema real_trades"
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

## SQLAlchemy модель RealTrade

### Ожидаемые колонки:
```python
class RealTrade(Base):
    __tablename__ = "real_trades"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)  # BUY/SELL
    order_type = Column(String(10), nullable=False)  # MARKET/LIMIT
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    order_id = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False)  # FILLED/PARTIAL/CANCELLED
    commission = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.now, index=True)
    reason = Column(String(50))  # SIGNAL/STOP_LOSS/TAKE_PROFIT
    created_at = Column(DateTime, default=datetime.now)  # ← ЭТА КОЛОНКА ОТСУТСТВОВАЛА
```

## Результат

После исправления:
- ✅ **Колонка created_at добавлена** - SQLAlchemy модель работает
- ✅ **Миграция автоматическая** - при `./update.sh`
- ✅ **Бот запускается** - без ошибок базы данных
- ✅ **Real Trading готов** - все функции работают
- ✅ **Дневной убыток рассчитывается** - без ошибок created_at

**Проблема с отсутствующей колонкой created_at решена! 🚀**
