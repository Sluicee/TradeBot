# 🚀 Инструкция по развертыванию на сервере

## Требования

- Ubuntu/Debian Linux (18.04+) или другой дистрибутив с systemd
- Python 3.10+
- Git
- sudo доступ
- Минимум 512MB RAM

## Быстрый старт

### 1. Клонирование репозитория

```bash
cd ~
git clone https://github.com/YOUR_USERNAME/TradeBot.git
cd TradeBot
```

### 2. Настройка окружения

```bash
# Копируем пример конфигурации
cp env.example .env

# Редактируем конфигурацию
nano .env
```

Заполните:
- `TELEGRAM_TOKEN` - токен от @BotFather
- `OWNER_CHAT_ID` - ваш Telegram ID от @userinfobot
- `DEFAULT_SYMBOL` - символ по умолчанию (например, BTCUSDT)
- `DEFAULT_INTERVAL` - интервал по умолчанию (например, 15m)

### 3. Автоматическое развертывание

```bash
chmod +x deploy.sh
./deploy.sh
```

Скрипт автоматически:
- ✅ Создаст виртуальное окружение
- ✅ Установит зависимости
- ✅ Создаст необходимые директории
- ✅ Настроит systemd service
- ✅ Включит автозапуск

### 4. Запуск бота

```bash
sudo systemctl start tradebot
```

## Управление ботом

### Основные команды

```bash
# Запуск
sudo systemctl start tradebot

# Остановка
sudo systemctl stop tradebot

# Перезапуск
sudo systemctl restart tradebot

# Статус
sudo systemctl status tradebot

# Автозапуск при загрузке
sudo systemctl enable tradebot

# Отключить автозапуск
sudo systemctl disable tradebot
```

### Просмотр логов

```bash
# Последние записи
journalctl -u tradebot -n 50

# Следить за логами в реальном времени
journalctl -u tradebot -f

# Логи приложения
tail -f logs/bot_service.log
tail -f logs/bot_service_error.log

# Последний файл логов
tail -f logs/log_*.txt | head -n 100
```

## Обновление бота

### Автоматическое обновление

```bash
chmod +x update.sh
./update.sh
```

### Ручное обновление

```bash
# Остановить бота
sudo systemctl stop tradebot

# Получить обновления
git pull

# Обновить зависимости
source venv/bin/activate
pip install --upgrade -r requirements.txt

# Запустить бота
sudo systemctl start tradebot
```

## Мониторинг

### Проверка работоспособности

```bash
# Статус сервиса
sudo systemctl status tradebot

# Использование ресурсов
top -p $(pgrep -f "python bot.py")

# Использование памяти
ps aux | grep "python bot.py"

# Открытые соединения
netstat -tunap | grep python
```

### Размер логов

```bash
# Проверка размера логов
du -h logs/

# Очистка старых логов (старше 7 дней)
find logs/ -name "*.log" -mtime +7 -delete
find logs/ -name "*.txt" -mtime +7 -delete
```

## Автоматическая очистка логов

Добавьте в crontab для еженедельной очистки:

```bash
crontab -e
```

Добавьте строку:
```
0 0 * * 0 find /home/YOUR_USERNAME/TradeBot/logs/ -name "*.log" -mtime +7 -delete
```

## Безопасность

### Права доступа

```bash
# Проверка прав на .env
chmod 600 .env

# Владелец всех файлов - ваш пользователь
chown -R $USER:$USER ~/TradeBot
```

### Firewall

Бот использует только исходящие соединения (к Telegram и Bybit API), входящие порты не требуются.

```bash
# Проверка firewall (опционально)
sudo ufw status
```

## Устранение проблем

### Бот не запускается

```bash
# Проверить логи systemd
journalctl -u tradebot -n 100

# Проверить конфигурацию
cat .env

# Проверить права
ls -la .env

# Проверить Python и зависимости
source venv/bin/activate
python --version
pip list
```

### Ошибки в логах

```bash
# Детальные логи
tail -f logs/bot_service_error.log

# Полный лог последнего запуска
ls -t logs/log_*.txt | head -n 1 | xargs cat
```

### Переустановка

```bash
# Остановить и отключить сервис
sudo systemctl stop tradebot
sudo systemctl disable tradebot

# Удалить сервис
sudo rm /etc/systemd/system/tradebot.service
sudo systemctl daemon-reload

# Очистить виртуальное окружение
rm -rf venv/

# Запустить deploy.sh заново
./deploy.sh
```

## Резервное копирование

### Что нужно сохранять

```bash
# Конфигурация
.env

# Состояние Paper Trading
paper_trading_state.json

# Отслеживаемые символы
tracked_symbols.json
```

### Создание бэкапа

```bash
# Создать архив
tar -czf tradebot_backup_$(date +%Y%m%d).tar.gz \
	.env \
	paper_trading_state.json \
	tracked_symbols.json \
	logs/

# Скопировать на другой сервер
scp tradebot_backup_*.tar.gz user@backup-server:/backups/
```

## Мультиплексирование (альтернатива systemd)

Если нет доступа к systemd, используйте screen или tmux:

```bash
# Установка screen
sudo apt install screen

# Запуск в screen
screen -S tradebot
source venv/bin/activate
python bot.py

# Отключиться: Ctrl+A, затем D
# Подключиться обратно:
screen -r tradebot
```

## 🐳 Развертывание через Docker

Docker - самый простой способ развертывания, не требует настройки Python и зависимостей.

### Установка Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
# Перелогиньтесь после этого

# Установка docker-compose
sudo apt install docker-compose
```

### Запуск через Docker Compose

```bash
# 1. Настройте .env
cp env.example .env
nano .env

# 2. Соберите и запустите
docker-compose up -d

# 3. Просмотр логов
docker-compose logs -f

# 4. Остановка
docker-compose down

# 5. Перезапуск после обновлений
git pull
docker-compose up -d --build
```

### Управление Docker контейнером

```bash
# Статус
docker-compose ps

# Логи
docker-compose logs -f tradebot

# Рестарт
docker-compose restart

# Остановка
docker-compose stop

# Запуск
docker-compose start

# Полное удаление (с данными)
docker-compose down -v
```

### Преимущества Docker

- ✅ Изолированное окружение
- ✅ Не нужно устанавливать Python и зависимости
- ✅ Легко обновлять и откатывать
- ✅ Работает одинаково на всех системах
- ✅ Автоматический рестарт при сбоях

## Поддержка нескольких ботов

Для запуска нескольких инстансов:

```bash
# Копировать проект
cp -r ~/TradeBot ~/TradeBot2

# Настроить другой .env
cd ~/TradeBot2
nano .env  # другой TELEGRAM_TOKEN

# Создать новый service
sudo cp tradebot.service /etc/systemd/system/tradebot2.service
sudo nano /etc/systemd/system/tradebot2.service  # изменить пути

# Запустить
sudo systemctl enable tradebot2
sudo systemctl start tradebot2
```

## Производительность

### Оптимизация для слабых серверов

В `config.py` можно добавить:

```python
# Для экономии памяти
import gc
gc.set_threshold(700, 10, 10)  # более частая сборка мусора
```

### Мониторинг памяти

```bash
# Установка htop
sudo apt install htop

# Запуск
htop -p $(pgrep -f "python bot.py")
```

## Полезные алиасы

Добавьте в `~/.bashrc`:

```bash
# Алиасы для управления ботом
alias bot-start='sudo systemctl start tradebot'
alias bot-stop='sudo systemctl stop tradebot'
alias bot-restart='sudo systemctl restart tradebot'
alias bot-status='sudo systemctl status tradebot'
alias bot-logs='journalctl -u tradebot -f'
alias bot-cd='cd ~/TradeBot'
```

Затем:
```bash
source ~/.bashrc
```

## Контакты и поддержка

При проблемах проверьте:
1. Логи в `logs/`
2. Системный журнал `journalctl -u tradebot`
3. Конфигурацию `.env`
4. Версию Python `python --version`

