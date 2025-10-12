# Чеклист перед деплоем

## ✅ Подготовка файлов

- [x] `.gitignore` настроен (исключает .env, логи, venv)
- [x] `requirements.txt` актуален (убран asyncio, добавлен python-dotenv)
- [x] `env.example` содержит все необходимые переменные
- [x] `Dockerfile` настроен и оптимизирован
- [x] `docker-compose.yml` настроен с healthcheck и log rotation
- [x] Скрипты деплоя готовы: `deploy.sh`, `update.sh`, `healthcheck.sh`
- [ ] Создан файл `.env` (на сервере после клонирования)

## 🔐 Безопасность

- [x] `.env` в .gitignore
- [x] Логи не содержат токены/секреты
- [x] OWNER_CHAT_ID используется для ограничения доступа
- [ ] .env файл НЕ закоммичен в git
- [ ] Проверить: `git log --all --full-history -- .env`

## 📦 Зависимости

- [x] `requirements.txt` содержит все нужные пакеты
- [x] Версии зависимостей указаны (>=)
- [x] Нет конфликтующих зависимостей
- [x] Убран asyncio (встроенный модуль)

## 🐳 Docker

- [x] `Dockerfile` создает нужные директории
- [x] `docker-compose.yml` настроен с volumes для персистентности
- [x] Healthcheck настроен
- [x] Log rotation настроен (10MB x 3 файла)
- [x] Restart policy: unless-stopped

## 🖥️ Systemd (альтернатива Docker)

- [x] `tradebot.service` файл готов
- [x] `deploy.sh` настраивает systemd service
- [x] Пути в service файле используют переменные

## 📝 Документация

- [x] `README.md` содержит основную информацию
- [x] `DEPLOY_GUIDE.md` с подробными инструкциями по деплою
- [x] `DOCKER_COMMANDS.md` с полезными командами
- [x] Все комментарии в коде актуальны

## 🧪 Тестирование

- [ ] Протестировать локально через Docker
- [ ] Проверить все основные команды бота
- [ ] Проверить бэктест
- [ ] Проверить paper trading
- [ ] Проверить логирование

## 🚀 Перед отправкой на сервер

### Локальная проверка

```bash
# 1. Проверить, что .env не в git
git status
git ls-files | grep .env  # Должно быть пусто!

# 2. Проверить Docker сборку
docker compose build

# 3. Запустить локально
cp env.example .env
# Отредактировать .env
docker compose up

# 4. Проверить работу бота
# Отправить команду /start в Telegram

# 5. Остановить
docker compose down
```

### На сервере

```bash
# 1. Клонировать репозиторий
git clone <your-repo-url> TradeBot
cd TradeBot

# 2. Создать .env
cp env.example .env
nano .env
# Заполнить TELEGRAM_TOKEN и OWNER_CHAT_ID

# 3. Выбрать метод запуска

## Вариант A: Docker
chmod +x update.sh healthcheck.sh
docker compose up -d --build
docker compose logs -f

## Вариант B: Systemd
chmod +x deploy.sh update.sh healthcheck.sh
./deploy.sh
sudo systemctl start tradebot
journalctl -u tradebot -f

# 4. Проверить работу
./healthcheck.sh

# 5. Отправить /start боту в Telegram
```

## 🔍 Финальная проверка

После запуска на сервере:

```bash
# Healthcheck
./healthcheck.sh

# Проверить логи (первые 5 минут)
# Docker:
docker compose logs --tail=50

# Systemd:
journalctl -u tradebot -n 50

# Проверить что бот отвечает в Telegram
# /start
# /help
# /status

# Проверить автозапуск
# Docker: restart: unless-stopped (уже настроено)
# Systemd: sudo systemctl enable tradebot (делает deploy.sh)

# Проверить использование ресурсов
htop
docker stats  # для Docker
```

## 📊 Мониторинг после деплоя

Первые 24 часа следить за:

- [ ] Логи на наличие ошибок
- [ ] Использование памяти (должно быть < 200MB)
- [ ] Использование CPU (должно быть < 10%)
- [ ] Размер логов (rotation работает?)
- [ ] Ответы бота в Telegram
- [ ] Paper trading работает корректно

## 🔧 Возможные проблемы и решения

### Проблема: Docker не запускается
```bash
# Проверить
docker compose config
docker compose logs

# Решение
docker compose down
docker compose up -d --build --force-recreate
```

### Проблема: Permission denied для Docker
```bash
# Решение
sudo usermod -aG docker $USER
# Перелогиниться
```

### Проблема: Бот не отвечает
```bash
# Проверить
1. TELEGRAM_TOKEN в .env корректный?
2. OWNER_CHAT_ID совпадает с вашим ID?
3. Интернет соединение работает?
4. Логи показывают ошибки?
```

### Проблема: Высокое использование памяти
```bash
# Ограничить память Docker (добавить в docker-compose.yml)
deploy:
  resources:
    limits:
      memory: 512M
```

## 📞 Контакты и поддержка

При возникновении проблем:
1. Запустить `./healthcheck.sh`
2. Проверить логи
3. Создать issue на GitHub
4. Приложить вывод healthcheck и последние строки логов

## ✅ Финальный чеклист

Перед тем как считать деплой завершенным:

- [ ] Бот запущен и работает
- [ ] Отвечает на команды в Telegram
- [ ] Логи чистые (нет критических ошибок)
- [ ] Healthcheck показывает 5/5
- [ ] Автозапуск настроен
- [ ] Мониторинг настроен (опционально)
- [ ] Backup скрипт создан (опционально)
- [ ] Документация прочитана

---

**Готово? Время деплоить! 🚀**

