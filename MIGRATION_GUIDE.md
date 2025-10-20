# 🚀 Real Trading Migration Guide

## Обзор

Этот гайд описывает процесс миграции для добавления поддержки реального трейдинга на Bybit.

## Автоматическая миграция

### Через update.sh (рекомендуется)

```bash
# Выполните обновление - миграция произойдет автоматически
./update.sh
```

Скрипт автоматически:
1. Получит обновления из репозитория
2. Выполнит миграцию Real Trading
3. Перезапустит бота

### Ручная миграция

```bash
# Выполните миграцию вручную
python3 migrate_real_trading.py
```

## Что создается при миграции

### 1. Таблица `real_trading_state`
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

### 2. Таблица `real_trades`
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

### 3. Индексы для оптимизации
- `idx_real_trades_symbol` - по символу
- `idx_real_trades_timestamp` - по времени
- `idx_real_trades_status` - по статусу

## Настройка после миграции

### 1. Настройка API ключей

Добавьте в `.env`:
```env
# Bybit API (обязательно для реальной торговли)
BYBIT_API_KEY=your_api_key_here
BYBIT_API_SECRET=your_api_secret_here
BYBIT_TESTNET=true  # true для testnet, false для mainnet

# Режимы торговли
ENABLE_PAPER_TRADING=false
ENABLE_REAL_TRADING=true
```

### 2. Получение API ключей

#### Testnet (рекомендуется для тестирования):
1. Перейдите на [Bybit Testnet](https://testnet.bybit.com/)
2. Зарегистрируйтесь или войдите
3. Перейдите в API Management
4. Создайте новый API ключ с правами:
   - Spot Trading
   - Read Account Info

#### Mainnet (для реальной торговли):
1. Перейдите на [Bybit](https://www.bybit.com/)
2. Войдите в аккаунт
3. Перейдите в API Management
4. Создайте новый API ключ с правами:
   - Spot Trading
   - Read Account Info

### 3. Настройка лимитов безопасности

В `config.py` настройте лимиты:
```python
# Real Trading Safety Limits
REAL_MAX_DAILY_LOSS = 50.0      # Макс убыток в день (USD)
REAL_MAX_POSITION_SIZE = 100.0  # Макс размер позиции (USD)
REAL_MAX_POSITIONS = 2          # Макс количество позиций
REAL_ORDER_TYPE = "MARKET"      # "MARKET" или "LIMIT"
```

## Команды для управления

### Telegram команды:
```bash
/real_status     # Статус реальной торговли
/real_balance    # Баланс с биржи
/real_start      # Запуск реальной торговли
/real_stop       # Остановка реальной торговли
/real_trades     # История сделок
/real_limits     # Просмотр лимитов
/real_emergency_stop  # Экстренная остановка
```

## Проверка работы

### 1. Проверка миграции
```bash
# Проверьте что таблицы созданы
sqlite3 data/tradebot.db ".tables"
```

### 2. Проверка API подключения
```bash
# Запустите бота и проверьте логи
python bot.py
```

### 3. Тестирование команд
Отправьте в Telegram боту:
```
/real_status
/real_balance
```

## Безопасность

### ⚠️ Важные предупреждения:

1. **Начните с testnet** - используйте тестовые ключи для проверки
2. **Установите лимиты** - настройте максимальные убытки
3. **Мониторинг** - следите за логами и уведомлениями
4. **Экстренная остановка** - команда `/real_emergency_stop` всегда доступна

### Лимиты по умолчанию:
- **Дневной убыток**: $50
- **Размер позиции**: $100
- **Количество позиций**: 2

## Откат миграции

Если нужно отключить реальную торговлю:

```bash
# В config.py установите:
ENABLE_REAL_TRADING = False
ENABLE_PAPER_TRADING = True

# Перезапустите бота
./update.sh
```

## Поддержка

При проблемах с миграцией:

1. Проверьте логи: `tail -f logs/crypto_signal_bot.log`
2. Проверьте базу данных: `sqlite3 data/tradebot.db ".schema"`
3. Запустите миграцию вручную: `python3 migrate_real_trading.py`

## Статус миграции

После успешной миграции вы увидите:
```
✅ Миграция Real Trading завершена успешно!
📊 Статистика:
   Real trades: 0
   Trading state records: 1
   Database: data/tradebot.db
```

**Real Trading готов к использованию! 🚀**
