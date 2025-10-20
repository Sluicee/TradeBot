# 🐳 Docker Force Rebuild - Решение проблемы SQLAlchemy

## Проблема
```
ModuleNotFoundError: No module named 'sqlalchemy'
```

## Причина
Docker контейнер использует старый образ без новых зависимостей из `requirements.txt`.

## Решение

### 1. Принудительная пересборка (рекомендуется)

```bash
# Остановить все контейнеры
docker-compose down

# Удалить старые образы и контейнеры
docker-compose down --rmi all --volumes

# Пересобрать с нуля
docker-compose up -d --build --force-recreate

# Проверить логи
docker-compose logs -f tradebot
```

### 2. Альтернативный способ

```bash
# Полная очистка Docker
docker system prune -a --volumes

# Пересборка
docker-compose up -d --build
```

### 3. Проверка установленных пакетов

```bash
# Войти в контейнер
docker-compose exec tradebot bash

# Проверить SQLAlchemy
python -c "import sqlalchemy; print('SQLAlchemy OK')"

# Проверить pybit
python -c "import pybit; print('pybit OK')"

# Проверить все зависимости
pip list | grep -E "(sqlalchemy|pybit)"
```

## Обновленные зависимости

### requirements.txt теперь включает:
```txt
python-telegram-bot>=20.0
python-dotenv>=1.0.0
pandas>=2.0.0
numpy>=1.24.0
aiohttp>=3.9.0
ta>=0.11.0
ccxt>=4.0.0
pybit>=5.0.0          # ← НОВОЕ для Real Trading
sqlalchemy>=2.0.0     # ← Уже было, но не установился
```

## Проверка после пересборки

### 1. Проверить что миграция работает:
```bash
docker-compose logs tradebot | grep -i "migration"
```

Должно показать:
```
✅ real_trading_state table already exists
✅ real_trades table already exists  
✅ bayesian_pending_signals table already exists
✅ Real Trading tables migration completed
```

### 2. Проверить что бот запустился:
```bash
docker-compose ps
```

### 3. Проверить логи бота:
```bash
docker-compose logs tradebot | tail -20
```

## Если проблема остается

### 1. Ручная установка в контейнере:
```bash
docker-compose exec tradebot pip install sqlalchemy pybit
```

### 2. Проверить Dockerfile:
```dockerfile
# Должно быть:
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

### 3. Проверить docker-compose.yml:
```yaml
# Должно быть:
build: .
# или
image: tradebot:latest
```

## Результат

После успешной пересборки:
- ✅ SQLAlchemy установлен
- ✅ pybit установлен  
- ✅ Миграция базы данных работает
- ✅ Real Trading инициализируется
- ✅ `./update.sh` работает без ошибок

## Команды для выполнения

```bash
# 1. Остановить контейнеры
docker-compose down

# 2. Удалить старые образы
docker-compose down --rmi all

# 3. Пересобрать с новыми зависимостями
docker-compose up -d --build

# 4. Проверить логи
docker-compose logs -f tradebot
```

**После этого `./update.sh` должен работать! 🚀**
