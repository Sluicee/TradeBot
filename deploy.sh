#!/bin/bash

# Скрипт для первого развертывания бота на сервере

set -e

echo "🚀 Развертывание Trading Bot на сервере..."

# Проверка Python
if ! command -v python3 &> /dev/null; then
	echo "❌ Python 3 не найден. Установите Python 3.10+"
	exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Python $PYTHON_VERSION найден"

# Создание виртуального окружения
if [ ! -d "venv" ]; then
	echo "📦 Создание виртуального окружения..."
	python3 -m venv venv
fi

# Активация venv
source venv/bin/activate

# Обновление pip
echo "📦 Обновление pip..."
pip install --upgrade pip

# Установка зависимостей
echo "📦 Установка зависимостей..."
pip install -r requirements.txt

# Создание необходимых директорий
echo "📁 Создание директорий для логов..."
mkdir -p logs
mkdir -p signals
mkdir -p backtests

# Проверка .env файла
if [ ! -f ".env" ]; then
	echo "⚠️  Файл .env не найден!"
	echo "📝 Создайте .env файл на основе env.example:"
	echo "   cp env.example .env"
	echo "   nano .env"
	exit 1
fi

# Проверка обязательных переменных
source .env
if [ -z "$TELEGRAM_TOKEN" ] || [ "$TELEGRAM_TOKEN" = "your_telegram_bot_token_here" ]; then
	echo "❌ TELEGRAM_TOKEN не настроен в .env"
	exit 1
fi

if [ -z "$OWNER_CHAT_ID" ] || [ "$OWNER_CHAT_ID" = "your_telegram_id_here" ]; then
	echo "❌ OWNER_CHAT_ID не настроен в .env"
	exit 1
fi

echo "✅ Конфигурация проверена"

# Установка systemd service
echo "🔧 Настройка systemd service..."
CURRENT_USER=$(whoami)
CURRENT_DIR=$(pwd)

# Копируем и настраиваем service файл
sudo cp tradebot.service /etc/systemd/system/
sudo sed -i "s|YOUR_USERNAME|$CURRENT_USER|g" /etc/systemd/system/tradebot.service
sudo sed -i "s|/home/YOUR_USERNAME/TradeBot|$CURRENT_DIR|g" /etc/systemd/system/tradebot.service

# Перезагрузка systemd
sudo systemctl daemon-reload
sudo systemctl enable tradebot.service

echo ""
echo "✅ Развертывание завершено!"
echo ""
echo "📋 Команды для управления ботом:"
echo "   sudo systemctl start tradebot    # Запустить бота"
echo "   sudo systemctl stop tradebot     # Остановить бота"
echo "   sudo systemctl restart tradebot  # Перезапустить бота"
echo "   sudo systemctl status tradebot   # Статус бота"
echo ""
echo "📊 Просмотр логов:"
echo "   tail -f logs/bot_service.log         # Основной лог"
echo "   tail -f logs/bot_service_error.log   # Лог ошибок"
echo "   journalctl -u tradebot -f            # Системный лог"
echo ""
echo "🚀 Запустите бота командой: sudo systemctl start tradebot"

