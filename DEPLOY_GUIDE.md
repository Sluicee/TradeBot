# Руководство по Деплою TradeBot

## Быстрый старт

### Вариант 1: Docker (Рекомендуется)

```bash
# 1. Клонировать репозиторий
git clone <your-repo-url> TradeBot
cd TradeBot

# 2. Создать .env файл
cp env.example .env
nano .env  # Заполнить TELEGRAM_TOKEN и OWNER_CHAT_ID

# 3. Запустить
docker compose up -d --build

# 4. Проверить логи
docker compose logs -f
```

### Вариант 2: Systemd Service

```bash
# 1. Клонировать репозиторий
git clone <your-repo-url> TradeBot
cd TradeBot

# 2. Создать .env файл
cp env.example .env
nano .env  # Заполнить TELEGRAM_TOKEN и OWNER_CHAT_ID

# 3. Запустить скрипт деплоя
chmod +x deploy.sh
./deploy.sh

# 4. Запустить бота
sudo systemctl start tradebot
```

---

## Предварительные требования

### Системные требования
- **OS**: Linux (Ubuntu 20.04+ / Debian 10+ / CentOS 7+)
- **RAM**: минимум 512MB, рекомендуется 1GB+
- **Disk**: минимум 2GB свободного места
- **Network**: стабильное подключение к интернету

### Программное обеспечение

#### Для Docker:
```bash
# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Добавить пользователя в группу docker
sudo usermod -aG docker $USER

# Установка Docker Compose (если нет)
sudo apt-get install docker-compose-plugin
```

#### Для Systemd:
```bash
# Python 3.10+
sudo apt update
sudo apt install python3 python3-pip python3-venv git -y
```

---

## Получение токенов

### 1. Telegram Bot Token
1. Открыть [@BotFather](https://t.me/BotFather) в Telegram
2. Отправить `/newbot`
3. Следовать инструкциям
4. Скопировать токен (формат: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Owner Chat ID
1. Открыть [@userinfobot](https://t.me/userinfobot) в Telegram
2. Отправить любое сообщение
3. Скопировать ваш ID (число, например: `123456789`)

---

## Детальная настройка

### Конфигурация .env

```bash
# Обязательные параметры
TELEGRAM_TOKEN=your_telegram_bot_token_here
OWNER_CHAT_ID=your_telegram_id_here

# Опциональные параметры
DEFAULT_SYMBOL=BTCUSDT
DEFAULT_INTERVAL=15m

# База данных (опционально)
# SQLite (по умолчанию): sqlite:///tradebot.db
# PostgreSQL: postgresql://user:password@localhost:5432/tradebot
# DATABASE_URL=sqlite:///tradebot.db
```

### База данных

Бот использует **SQLAlchemy ORM** с поддержкой:
- **SQLite** (по умолчанию) - лёгкая встроенная БД
- **PostgreSQL** (опционально) - для production с высокой нагрузкой

**SQLite (по умолчанию):**
- Не требует настройки
- БД сохраняется в файл `tradebot.db`
- Подходит для большинства случаев

**PostgreSQL (опционально):**
```bash
# Установка PostgreSQL
sudo apt install postgresql postgresql-contrib

# Создание БД и пользователя
sudo -u postgres psql
CREATE DATABASE tradebot;
CREATE USER tradebot_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE tradebot TO tradebot_user;
\q

# В .env добавить:
# DATABASE_URL=postgresql://tradebot_user:your_password@localhost:5432/tradebot
```

**Инициализация БД:**
```bash
# Автоматически при первом запуске Docker
# Или вручную:
python init_db.py
```

### Структура директорий

После первого запуска будут созданы:
```
TradeBot/
├── logs/                    # Логи работы бота
├── signals/                 # История сигналов
├── backtests/              # Результаты бэктестов
└── tradebot.db             # База данных SQLite (все данные)
```

**База данных содержит:**
- Состояние paper trading (баланс, статистика)
- Открытые позиции
- История сделок
- Отслеживаемые символы
- История сигналов

---

## Управление ботом

### Docker

```bash
# Запуск
docker compose up -d

# Остановка
docker compose down

# Перезапуск
docker compose restart

# Логи (реального времени)
docker compose logs -f

# Логи (последние 100 строк)
docker compose logs --tail=100

# Обновление
./update.sh
```

### Systemd

```bash
# Запуск
sudo systemctl start tradebot

# Остановка
sudo systemctl stop tradebot

# Перезапуск
sudo systemctl restart tradebot

# Статус
sudo systemctl status tradebot

# Логи (реального времени)
journalctl -u tradebot -f

# Логи (последние 100 строк)
journalctl -u tradebot -n 100

# Обновление
./update.sh
```

---

## Обновление бота

Универсальный скрипт работает для Docker и Systemd:

```bash
./update.sh
```

Скрипт автоматически:
- Определяет метод запуска
- Получает обновления из git
- Перестраивает/обновляет зависимости
- Перезапускает бота

---

## Мониторинг и проверка

### Healthcheck скрипт

```bash
# Запуск проверки здоровья
chmod +x healthcheck.sh
./healthcheck.sh
```

Скрипт проверяет:
- ✅ Наличие .env и правильность конфигурации
- ✅ Статус работы бота
- ✅ Ошибки в логах
- ✅ Размер логов
- ✅ Использование ресурсов
- ✅ Файлы состояния

### Автоматический мониторинг (cron)

Добавить в crontab для ежечасной проверки:

```bash
crontab -e
```

Добавить строку:
```
0 * * * * /home/username/TradeBot/healthcheck.sh >> /home/username/TradeBot/logs/healthcheck.log 2>&1
```

---

## Очистка логов

### Ручная очистка

```bash
# Удалить логи старше 7 дней
find logs/ -name '*.log' -mtime +7 -delete
find logs/ -name '*.txt' -mtime +7 -delete
find signals/ -name '*.log' -mtime +7 -delete

# Удалить все логи (осторожно!)
rm -rf logs/*.log logs/*.txt signals/*.log
```

### Автоматическая очистка (cron)

```bash
crontab -e
```

Добавить строку для еженедельной очистки:
```
0 3 * * 0 find /home/username/TradeBot/logs/ -name '*.log' -mtime +7 -delete
0 3 * * 0 find /home/username/TradeBot/signals/ -name '*.log' -mtime +7 -delete
```

---

## Troubleshooting

### Бот не запускается

**Docker:**
```bash
# Проверить логи
docker compose logs

# Проверить статус контейнера
docker ps -a

# Пересоздать контейнер
docker compose down
docker compose up -d --build --force-recreate
```

**Systemd:**
```bash
# Проверить статус
sudo systemctl status tradebot

# Проверить логи
journalctl -u tradebot -n 50

# Проверить права
ls -la /home/username/TradeBot/
```

### Ошибка "Permission denied"

```bash
# Для Docker
sudo usermod -aG docker $USER
# Перелогиниться после этого

# Для скриптов
chmod +x deploy.sh update.sh healthcheck.sh
```

### Бот не отвечает в Telegram

1. Проверить TELEGRAM_TOKEN в .env
2. Проверить OWNER_CHAT_ID в .env
3. Проверить логи на ошибки API
4. Проверить интернет-соединение сервера
5. Проверить, что токен активен в @BotFather

### Высокое использование памяти

```bash
# Ограничить память для Docker
# В docker-compose.yml добавить:
deploy:
  resources:
    limits:
      memory: 512M
```

### Логи занимают много места

```bash
# Проверить размер
du -sh logs/

# Очистить старые логи
find logs/ -name '*.log' -mtime +7 -delete

# Настроить ротацию логов в docker-compose.yml (уже настроено)
```

---

## Безопасность

### ✅ Чеклист безопасности

- [ ] .env файл НЕ в git (проверить .gitignore)
- [ ] OWNER_CHAT_ID настроен (только вы можете управлять ботом)
- [ ] Используется docker/systemd (изоляция процесса)
- [ ] Логи не содержат токены (проверить logger.py)
- [ ] Регулярные обновления системы
- [ ] Firewall настроен (если нужен внешний доступ)

### Рекомендации

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Настройка firewall (если нужен)
sudo ufw allow 22/tcp  # SSH
sudo ufw enable

# Регулярные бэкапы .env и БД
cp .env .env.backup
cp tradebot.db tradebot.db.backup
```

---

## Backup и Восстановление

### Создание бэкапа

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups"
mkdir -p $BACKUP_DIR

# Бэкап критичных файлов
tar -czf "$BACKUP_DIR/tradebot_backup_$DATE.tar.gz" \
	.env \
	tradebot.db \
	backtests/ \
	--exclude='backtests/*.json'

echo "Backup created: $BACKUP_DIR/tradebot_backup_$DATE.tar.gz"
# Или используйте готовый скрипт:
# ./backup.sh
```

### Восстановление

```bash
# Распаковать бэкап
tar -xzf backups/tradebot_backup_YYYYMMDD_HHMMSS.tar.gz

# Перезапустить бота
docker compose restart
# или
sudo systemctl restart tradebot
```

---

## Полезные команды

### Просмотр активных сделок

```bash
# Проверить paper_trading_state.json
cat paper_trading_state.json | python -m json.tool
```

### Просмотр отслеживаемых символов

```bash
# Проверить tracked_symbols.json
cat tracked_symbols.json | python -m json.tool
```

### Тестирование стратегии

```bash
# Запустить бэктест
python backtest.py BTCUSDT 1h

# Сравнение стратегий
python test_strategy_comparison.py
```

---

## Производительность

### Оптимизация Docker

```bash
# Очистка старых образов
docker image prune -a

# Очистка volumes
docker volume prune
```

### Оптимизация системы

```bash
# Проверить использование ресурсов
htop

# Проверить дисковое пространство
df -h

# Проверить загрузку сети
iftop
```

---

## FAQ

**Q: Можно ли запустить несколько ботов одновременно?**
A: Да, но нужно изменить `container_name` в docker-compose.yml и использовать разные директории.

**Q: Как часто бот проверяет сигналы?**
A: Зависит от интервала. Для 15m - каждые 15 минут после закрытия свечи.

**Q: Можно ли использовать на Windows?**
A: Да, через Docker Desktop или WSL2.

**Q: Нужен ли VPS?**
A: Рекомендуется для 24/7 работы. Подойдет любой VPS с 512MB+ RAM.

**Q: Сколько трафика использует бот?**
A: ~100-500 MB/месяц в зависимости от количества отслеживаемых символов.

---

## Поддержка

При возникновении проблем:
1. Запустить `./healthcheck.sh`
2. Проверить логи
3. Проверить .env конфигурацию
4. Создать issue с подробным описанием проблемы

---

## Лицензия и Дисклеймер

⚠️ **Важно**: Этот бот предназначен только для образовательных целей. 
Не используйте его для реальной торговли без тщательного тестирования. 
Автор не несет ответственности за финансовые потери.

---

**Успешного деплоя! 🚀**

