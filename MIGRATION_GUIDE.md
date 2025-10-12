# 🚀 Руководство по настройке БД

## Быстрый старт

```bash
# 1. Установить зависимости
pip install sqlalchemy>=2.0.0

# 2. Инициализировать БД
python init_db.py

# 3. Запустить бота
python bot.py
```

## Детальная инструкция

### Шаг 1: Установка зависимостей

```bash
pip install sqlalchemy>=2.0.0
```

### Шаг 2: Инициализация БД

```bash
# Создаёт структуру таблиц
python init_db.py
```

Ожидаемый вывод:
```
=== ИНИЦИАЛИЗАЦИЯ БД ===
✅ Таблицы созданы успешно
📊 Paper Trading: не инициализирован
🎯 Отслеживаемых символов: 0
💼 Открытых позиций: 0
📝 История сделок: 0 записей
📡 Логов сигналов: 0 записей
🧪 Бэктестов: 0
✅ База данных готова к использованию!
📍 Файл БД: sqlite:///tradebot.db
```

### Шаг 3: Проверка

```bash
# Запускает тесты БД
python test_database.py
```

Ожидаемый вывод:
```
=== ТЕСТИРОВАНИЕ БД ===

Тест: Paper Trading State
✅ Paper Trading State: OK
Тест: Tracked Symbols
✅ Tracked Symbols: OK
...
✅ Все тесты пройдены: 7/7
```

```bash
# Проверка целостности
python init_db.py check
```

### Шаг 4: Запуск бота

```bash
python bot.py
```

В логах должно быть:
```
База данных инициализирована: sqlite:///tradebot.db
Paper Trading: состояние не найдено, используем начальные значения
Загружено 0 пар из БД
```

## Работа с БД

### Python API

```python
from database import db

# Получить состояние paper trading
state = db.get_paper_state()
print(f"Balance: ${state.balance:.2f}" if state else "Not initialized")

# Получить все позиции
positions = db.get_all_positions()
for pos in positions:
    print(f"{pos.symbol}: {pos.amount} @ ${pos.entry_price}")

# История сделок
trades = db.get_trades_history(symbol="BTCUSDT", limit=10)

# Сигналы
signals = db.get_signals(symbol="ETHUSDT", signal_type="BUY")

# Бэктесты
backtests = db.get_backtests(symbol="SOLUSDT", limit=5)
```

### SQL запросы (для продвинутых)

```bash
sqlite3 tradebot.db

# Статистика по символам
SELECT symbol, COUNT(*) as trades, AVG(profit_percent) as avg_profit
FROM trades_history
WHERE type IN ('SELL', 'STOP-LOSS')
GROUP BY symbol
ORDER BY avg_profit DESC;

# Лучшие сигналы
SELECT symbol, signal, COUNT(*) as count
FROM signals
WHERE time > datetime('now', '-7 days')
GROUP BY symbol, signal
ORDER BY count DESC;

# Win rate по дням
SELECT DATE(time) as date,
       COUNT(*) as trades,
       SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
FROM trades_history
WHERE type IN ('SELL', 'STOP-LOSS', 'TRAILING-STOP')
GROUP BY DATE(time)
ORDER BY date DESC
LIMIT 30;
```

## Обслуживание

### Регулярные бэкапы

```bash
# Добавить в crontab (ежедневно в 2:00)
0 2 * * * cd /path/to/TradeBot && cp tradebot.db backups/tradebot_$(date +\%Y\%m\%d).db

# Еженедельная очистка старых бэкапов (старше 30 дней)
0 3 * * 0 find /path/to/TradeBot/backups -name "tradebot_*.db" -mtime +30 -delete
```

### Очистка старых данных

```python
# Удалить старые сигналы (старше 60 дней)
from database import db, Signal
from datetime import datetime, timedelta

with db.session_scope() as session:
    cutoff = datetime.now() - timedelta(days=60)
    deleted = session.query(Signal).filter(Signal.time < cutoff).delete()
    session.commit()
    print(f"Удалено старых сигналов: {deleted}")
```

### Vacuum (сжатие БД)

```bash
# Раз в месяц
sqlite3 tradebot.db "VACUUM;"
```

## PostgreSQL (production)

Для production рекомендуется PostgreSQL:

```bash
# 1. Установить PostgreSQL
sudo apt-get install postgresql postgresql-contrib

# 2. Создать БД и пользователя
sudo -u postgres psql
CREATE USER tradebot WITH PASSWORD 'secure_password';
CREATE DATABASE tradebot OWNER tradebot;
GRANT ALL PRIVILEGES ON DATABASE tradebot TO tradebot;
\q

# 3. Настроить .env
echo "DATABASE_URL=postgresql://tradebot:secure_password@localhost/tradebot" >> .env

# 4. Запустить инициализацию
python init_db.py
```

## Troubleshooting

### Ошибка "database is locked"

SQLite уже настроен для многопоточности. Если всё равно возникает:

```python
# Проверить в database.py:
connect_args={"check_same_thread": False}
poolclass=StaticPool
```

### Файл БД не создаётся

```bash
# Проверить права
ls -lh tradebot.db
chmod 644 tradebot.db

# Проверить DATABASE_URL в .env
echo $DATABASE_URL
```

### Нужно пересоздать БД

```bash
python init_db.py reset
```

## FAQ

**Q: Где хранятся данные?**  
A: В файле `tradebot.db` (SQLite) или на сервере PostgreSQL

**Q: Как сделать бэкап?**  
A: `cp tradebot.db backup.db` (SQLite) или `pg_dump` (PostgreSQL)

**Q: Сколько места занимает БД?**  
A: ~1-5 MB для обычного использования. Сигналы растут ~100 KB/день.

**Q: БД совместима между платформами?**  
A: Да, SQLite файл можно копировать между Windows/Linux/Mac.

**Q: Как экспортировать данные?**  
A: 
```bash
sqlite3 tradebot.db .dump > backup.sql
```

**Q: Нужно ли что-то менять в Docker?**  
A: Нет, просто обновите образ и перезапустите контейнер.

## Команды

```bash
# Инициализация
python init_db.py

# Проверка
python init_db.py check

# Сброс (ОПАСНО!)
python init_db.py reset

# Тесты
python test_database.py
```

---

**Готово к использованию! 🚀**
