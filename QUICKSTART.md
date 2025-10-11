# ⚡ Быстрый старт - Развертывание за 5 минут

## Что нужно заранее

1. ✅ Сервер с Ubuntu/Debian (512MB RAM минимум)
2. ✅ Telegram бот токен от [@BotFather](https://t.me/BotFather)
3. ✅ Ваш Telegram ID от [@userinfobot](https://t.me/userinfobot)
4. ✅ SSH доступ к серверу

---

## 🐳 Вариант 1: Docker (РЕКОМЕНДУЕТСЯ)

Самый простой способ - работает везде одинаково.

```bash
# Подключитесь к серверу
ssh user@your-server

# Установите Docker (если еще не установлен)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
sudo apt install docker-compose

# Перелогиньтесь
exit
ssh user@your-server

# Клонируйте проект
git clone https://github.com/YOUR_USERNAME/TradeBot.git
cd TradeBot

# Настройте конфигурацию
cp env.example .env
nano .env
# Заполните TELEGRAM_TOKEN и OWNER_CHAT_ID

# Запустите!
docker-compose up -d

# Проверьте логи
docker-compose logs -f
```

**Готово!** Бот запущен и работает в фоне.

---

## 🚀 Вариант 2: Systemd (традиционный)

Если не хотите использовать Docker.

```bash
# Подключитесь к серверу
ssh user@your-server

# Клонируйте проект
git clone https://github.com/YOUR_USERNAME/TradeBot.git
cd TradeBot

# Настройте конфигурацию
cp env.example .env
nano .env
# Заполните TELEGRAM_TOKEN и OWNER_CHAT_ID

# Запустите автоматическую установку
chmod +x deploy.sh
./deploy.sh

# Запустите бота
sudo systemctl start tradebot

# Проверьте статус
sudo systemctl status tradebot
```

**Готово!** Бот запущен как системный сервис.

---

## 📱 Проверка работы

Откройте Telegram и напишите вашему боту:

```
/start - Приветствие
/add BTCUSDT - Добавить Bitcoin для отслеживания
/paper_start 100 - Запустить виртуальную торговлю с $100
/paper_status - Проверить статус
```

Если получили ответ - всё работает! 🎉

---

## 🔧 Основные команды

### Docker

```bash
# Логи
docker-compose logs -f

# Перезапуск
docker-compose restart

# Остановка
docker-compose stop

# Обновление (автоматически)
./update.sh

# Или вручную:
git pull && docker-compose up -d --build
```

📖 **Полная шпаргалка:** [DOCKER_COMMANDS.md](DOCKER_COMMANDS.md)

### Systemd

```bash
# Логи
journalctl -u tradebot -f

# Перезапуск
sudo systemctl restart tradebot

# Остановка
sudo systemctl stop tradebot

# Обновление
./update.sh
```

---

## ❓ Проблемы?

### Бот не отвечает

```bash
# Docker
docker-compose logs --tail 50

# Systemd
journalctl -u tradebot -n 50
```

### Ошибка "Unauthorized"

Проверьте `TELEGRAM_TOKEN` в `.env` файле.

### Ошибка "Access denied"

Проверьте `OWNER_CHAT_ID` в `.env` файле - должен совпадать с вашим ID.

### Бот постоянно перезапускается

```bash
# Посмотрите логи ошибок
tail -f logs/bot_service_error.log
```

---

## 📖 Дальше

- Полная инструкция: [DEPLOYMENT.md](DEPLOYMENT.md)
- Основной README: [README.md](README.md)
- Команды бота: `/start` в Telegram

---

## 💡 Советы

1. **Используйте Docker** - проще в управлении
2. **Настройте автоочистку логов** - см. DEPLOYMENT.md
3. **Добавьте мониторинг** - настройте уведомления в Telegram
4. **Делайте бэкапы** `.env` и `paper_trading_state.json`
5. **Обновляйтесь регулярно** - `git pull` раз в неделю

---

**Успешного тестирования! 🚀**

