# 🐳 Шпаргалка по Docker командам

## Основные операции

### Запуск и остановка

```bash
# Запустить в фоне
docker-compose up -d

# Остановить
docker-compose down

# Перезапустить
docker-compose restart

# Остановить без удаления контейнера
docker-compose stop

# Запустить остановленный контейнер
docker-compose start
```

### Обновление

```bash
# Простое обновление (автоматически)
./update.sh

# Или вручную:
git pull
docker-compose up -d --build

# Обновление с полной пересборкой
git pull
docker-compose build --no-cache
docker-compose up -d
```

### Логи и мониторинг

```bash
# Следить за логами в реальном времени
docker-compose logs -f

# Последние 50 строк
docker-compose logs --tail 50

# Логи конкретного сервиса
docker-compose logs -f tradebot

# Статус контейнера
docker-compose ps

# Использование ресурсов
docker stats tradebot
```

### Отладка

```bash
# Войти в контейнер
docker-compose exec tradebot /bin/bash

# Или sh если bash недоступен
docker-compose exec tradebot /bin/sh

# Запустить команду в контейнере
docker-compose exec tradebot python --version

# Проверить переменные окружения
docker-compose exec tradebot env

# Просмотр файлов
docker-compose exec tradebot ls -la
docker-compose exec tradebot cat paper_trading_state.json
```

### Очистка

```bash
# Остановить и удалить контейнер
docker-compose down

# Остановить и удалить включая volumes (УДАЛИТ ДАННЫЕ!)
docker-compose down -v

# Очистка неиспользуемых образов
docker image prune

# Очистка всего неиспользуемого
docker system prune

# Агрессивная очистка (удалит ВСЕ неиспользуемые образы)
docker system prune -a
```

## Работа с данными

### Бэкап

```bash
# Создать бэкап состояния
cp paper_trading_state.json paper_trading_state.json.backup

# Бэкап всех важных файлов
tar -czf backup_$(date +%Y%m%d).tar.gz \
	.env \
	paper_trading_state.json \
	tracked_symbols.json

# Скопировать с сервера на локальную машину
scp user@server:/path/to/TradeBot/backup_*.tar.gz ./
```

### Восстановление

```bash
# Восстановить из бэкапа
cp paper_trading_state.json.backup paper_trading_state.json

# Перезапустить бота
docker-compose restart

# Или полная остановка/запуск
docker-compose down
docker-compose up -d
```

## Проблемы и решения

### Ошибка "permission denied" или "http+docker"

Нет прав доступа к Docker:

```bash
# Добавить себя в группу docker
sudo usermod -aG docker $USER

# Перелогиниться
exit
ssh user@server

# Проверить
docker ps
groups  # Должна быть группа docker
```

### Docker daemon не запущен

```bash
# Запустить Docker
sudo systemctl start docker
sudo systemctl enable docker

# Проверить статус
sudo systemctl status docker
```

### Бот не запускается

```bash
# Проверить логи
docker-compose logs --tail 100

# Проверить статус
docker-compose ps

# Пересоздать контейнер
docker-compose down
docker-compose up -d --build

# Проверить healthcheck
./healthcheck.sh
```

### Ошибки при сборке

```bash
# Пересобрать без кэша
docker-compose build --no-cache

# Удалить старый образ и пересобрать
docker-compose down
docker rmi tradebot_tradebot
docker-compose up -d --build
```

### Контейнер постоянно перезапускается

```bash
# Посмотреть последние логи
docker-compose logs --tail 50

# Запустить без автоматического перезапуска
docker-compose up

# Проверить конфигурацию
cat .env
docker-compose config
```

### Проблемы с памятью

```bash
# Проверить использование ресурсов
docker stats tradebot

# Ограничить память в docker-compose.yml
# Добавить в сервис:
# deploy:
#   resources:
#     limits:
#       memory: 512M
```

### Порты заняты

```bash
# Docker не требует входящих портов для этого бота
# Если нужно проверить:
netstat -tulpn | grep docker
```

## Полезные alias'ы

Добавьте в `~/.bashrc`:

```bash
alias dc='docker-compose'
alias dcup='docker-compose up -d'
alias dcdown='docker-compose down'
alias dclogs='docker-compose logs -f'
alias dcps='docker-compose ps'
alias dcrestart='docker-compose restart'
alias dcbuild='docker-compose up -d --build'

# Специфичные для бота
alias bot-update='cd ~/TradeBot && ./update.sh'
alias bot-logs='docker-compose logs -f tradebot'
alias bot-status='docker-compose ps tradebot'
alias bot-restart='docker-compose restart tradebot'
alias bot-health='cd ~/TradeBot && ./healthcheck.sh'
```

Затем: `source ~/.bashrc`

## Docker Compose файл

Основные параметры в `docker-compose.yml`:

```yaml
version: '3.8'

services:
  tradebot:
    build: .                    # Собрать из Dockerfile в текущей директории
    container_name: tradebot    # Имя контейнера
    restart: unless-stopped     # Автоматический перезапуск при сбое
    env_file: .env              # Переменные окружения из .env
    volumes:                    # Монтирование директорий
      - ./logs:/app/logs
      - ./paper_trading_state.json:/app/paper_trading_state.json
```

## Мониторинг в продакшене

### Автоматическая проверка

Добавьте в crontab:

```bash
crontab -e
```

```cron
# Проверка каждый час
0 * * * * cd /path/to/TradeBot && ./healthcheck.sh >> logs/healthcheck.log 2>&1

# Автоматический рестарт если упал
*/5 * * * * docker-compose -f /path/to/TradeBot/docker-compose.yml up -d
```

### Логирование

```bash
# Следить за размером логов
du -h logs/

# Очистка старых логов
find logs/ -name "*.log" -mtime +7 -delete
find logs/ -name "*.txt" -mtime +7 -delete
```

## Обновление Docker и Docker Compose

```bash
# Обновить Docker
sudo apt update
sudo apt upgrade docker-ce docker-ce-cli containerd.io

# Обновить Docker Compose (v2)
sudo apt update
sudo apt upgrade docker-compose-plugin

# Проверить версии
docker --version
docker-compose --version
```

## Безопасность

```bash
# Проверить права на .env
ls -la .env
# Должно быть: -rw------- (600)

# Исправить если нужно
chmod 600 .env

# Проверить что .env не в git
git check-ignore .env
# Должен вывести: .env

# Запустить без root (уже настроено в docker-compose.yml)
# Docker автоматически использует указанного пользователя
```

## Дополнительные команды

```bash
# Проверить конфигурацию docker-compose.yml
docker-compose config

# Пересоздать контейнер с нуля
docker-compose up -d --force-recreate

# Показать процессы в контейнере
docker-compose top

# Экспортировать образ
docker save tradebot_tradebot > tradebot_image.tar

# Импортировать образ
docker load < tradebot_image.tar
```

---

**💡 Совет:** Используйте `./update.sh` для обновлений - он автоматически определит Docker и выполнит все правильно!

