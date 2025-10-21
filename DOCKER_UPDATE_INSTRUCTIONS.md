# 🐳 Docker Update Instructions

## Проблема
```
ModuleNotFoundError: No module named 'sqlalchemy'
```

## Причина
Docker контейнер не пересобирается с новыми зависимостями из `requirements.txt`.

## Решение

### 1. Принудительная пересборка Docker контейнера

```bash
# Остановить контейнеры
docker-compose down

# Удалить старые образы (опционально)
docker-compose down --rmi all

# Пересобрать с новыми зависимостями
docker-compose up -d --build

# Проверить логи
docker-compose logs -f
```

### 2. Альтернативный способ (если первый не работает)

```bash
# Полная очистка Docker
docker-compose down --volumes --rmi all

# Пересборка с нуля
docker-compose up -d --build --force-recreate

# Проверить что контейнер запустился
docker-compose ps
```

### 3. Проверка установленных пакетов

```bash
# Войти в контейнер
docker-compose exec tradebot bash

# Проверить установленные пакеты
pip list | grep -E "(sqlalchemy|pybit)"

# Должно показать:
# pybit                   5.0.0
# SQLAlchemy              2.0.44
```

## Обновленные зависимости

### Добавлено в requirements.txt:
- `pybit>=5.0.0` - для Bybit API интеграции
- `sqlalchemy>=2.0.0` - уже был, но мог не установиться

### Все зависимости Real Trading:
```txt
python-telegram-bot>=20.0
python-dotenv>=1.0.0
pandas>=2.0.0
numpy>=1.24.0
aiohttp>=3.9.0
ta>=0.11.0
ccxt>=4.0.0
pybit>=5.0.0          # ← НОВОЕ для Real Trading
sqlalchemy>=2.0.0    # ← Уже было
```

## Проверка после обновления

### 1. Проверить что миграция работает:
```bash
docker-compose logs tradebot | grep -i "migration\|sqlalchemy"
```

### 2. Проверить что Real Trading инициализируется:
```bash
docker-compose logs tradebot | grep -i "real trading\|bybit"
```

### 3. Проверить статус контейнера:
```bash
docker-compose ps
```

## Если проблема остается

### 1. Проверить Dockerfile:
```dockerfile
# Должно быть:
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

### 2. Проверить docker-compose.yml:
```yaml
# Должно быть:
build: .
# или
image: tradebot:latest
```

### 3. Ручная установка в контейнере:
```bash
docker-compose exec tradebot pip install sqlalchemy pybit
```

## Результат

После успешного обновления:
- ✅ SQLAlchemy установлен
- ✅ pybit установлен  
- ✅ Миграция базы данных работает
- ✅ Real Trading инициализируется
- ✅ Все зависимости доступны

**Docker контейнер готов к Real Trading! 🚀**

