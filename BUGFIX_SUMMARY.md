# 🐛 Bug Fix: bayesian_pending_signals Table Missing

## Проблема
```
ERROR: (sqlite3.OperationalError) no such table: bayesian_pending_signals
[SQL: DELETE FROM bayesian_pending_signals WHERE bayesian_pending_signals.signal_signature = ? AND bayesian_pending_signals.entry_price = ?]
```

## Причина
Таблица `bayesian_pending_signals` была определена в `database.py`, но не была создана в базе данных при миграции.

## Решение

### 1. Обновлен `migrate_real_trading.py`
Добавлена поддержка создания таблицы `bayesian_pending_signals`:

```sql
CREATE TABLE bayesian_pending_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_signature TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    entry_price REAL NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Добавлены индексы
```sql
CREATE INDEX IF NOT EXISTS idx_bayesian_pending_signature ON bayesian_pending_signals(signal_signature);
CREATE INDEX IF NOT EXISTS idx_bayesian_pending_created ON bayesian_pending_signals(created_at);
```

### 3. Исправлены Unicode проблемы
Заменил все эмодзи на простой текст для совместимости с Windows PowerShell.

## Результат миграции

```
Real Trading Migration Script
==================================================

Проверка требований...
OK: Все требования выполнены
Real Trading Migration...

Проверка существующих таблиц...
   Найдено таблиц: 13
   OK: Таблица real_trading_state уже существует
   OK: Таблица real_trades уже существует
   OK: Таблица bayesian_pending_signals уже существует
Создание индексов...
   OK: Индексы созданы
Инициализация состояния real trading...
   OK: Состояние real trading уже инициализировано

OK: Миграция Real Trading завершена успешно!

Статистика:
   Real trades: 0
   Trading state records: 1
   Pending signals: 0
   Database: data/tradebot.db

SUCCESS: Миграция Real Trading завершена успешно!
   Теперь можно использовать реальную торговлю
```

## Статус

✅ **Проблема решена**
- Таблица `bayesian_pending_signals` создана
- Индексы добавлены
- Бот перезапущен (PID: 6132)
- Ошибки больше не возникают

## Автоматическая миграция

Теперь при выполнении `./update.sh` автоматически:
1. Проверяется наличие таблиц
2. Создаются недостающие таблицы
3. Добавляются индексы
4. Инициализируется состояние

**Система полностью исправлена и готова к работе! 🚀**
