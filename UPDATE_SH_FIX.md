# 🔧 Update.sh Fix - Docker Migration Issue

## Проблема
```
ModuleNotFoundError: No module named 'sqlalchemy'
```

## Причина
`./update.sh` пытался выполнить миграцию базы данных на хосте, где не установлен SQLAlchemy. Миграция должна выполняться только внутри Docker контейнера.

## Решение

### ✅ Исправлено в update.sh
- **Docker deployments**: Миграция пропускается на хосте, выполняется в контейнере
- **Systemd deployments**: Миграция выполняется на хосте (где установлены зависимости)

### 🔄 Логика работы

#### Для Docker:
```bash
# На хосте (update.sh):
ℹ️  Миграция базы данных будет выполнена в Docker контейнере

# В контейнере (docker-entrypoint.sh):
🔄 Проверка миграции БД...
✅ real_trading_state table already exists
✅ real_trades table already exists  
✅ bayesian_pending_signals table already exists
✅ Real Trading tables migration completed
✅ Миграция БД завершена
```

#### Для Systemd:
```bash
# На хосте (update.sh):
🔄 Проверка миграции базы данных...
📊 Выполнение миграции базы данных...
✅ Миграция базы данных завершена
```

## Команды для пользователя

### 1. Теперь `./update.sh` работает правильно:
```bash
./update.sh
```

### 2. Ожидаемый вывод для Docker:
```
🔄 Обновление Trading Bot...

📦 Обнаружен Docker

📥 Получение обновлений из репозитория...
Уже актуально.

ℹ️  Миграция базы данных будет выполнена в Docker контейнере

🐳 Обновление Docker контейнера...
Используется: docker compose
Остановка
Пересборка и запуск
✅ Обновление завершено!
📊 Проверка: docker-compose logs -f
```

### 3. Проверить что миграция выполнилась в контейнере:
```bash
docker-compose logs tradebot | grep -i "migration"
```

Должно показать:
```
🔄 Проверка миграции БД...
✅ real_trading_state table already exists
✅ real_trades table already exists  
✅ bayesian_pending_signals table already exists
✅ Real Trading tables migration completed
✅ Миграция БД завершена
```

## Архитектура миграции

### Docker Flow:
1. **update.sh** - получает обновления, пересобирает контейнер
2. **docker-entrypoint.sh** - выполняет миграцию внутри контейнера
3. **bot.py** - запускается после успешной миграции

### Systemd Flow:
1. **update.sh** - получает обновления, выполняет миграцию на хосте
2. **systemctl start tradebot** - запускает бота

## Проверка после исправления

### 1. Выполнить обновление:
```bash
./update.sh
```

### 2. Проверить логи Docker:
```bash
docker-compose logs -f tradebot
```

### 3. Проверить что бот запустился:
```bash
docker-compose ps
```

## Результат

После исправления:
- ✅ **update.sh работает** - без ошибок SQLAlchemy на хосте
- ✅ **Миграция выполняется** - внутри Docker контейнера
- ✅ **Бот запускается** - после успешной миграции
- ✅ **Real Trading готов** - все таблицы созданы

**Проблема с миграцией на хосте решена! 🚀**
