#!/bin/bash

# Скрипт для быстрого тестового запуска бота

set -e

echo "🧪 Тестовый запуск бота..."

# Проверка .env файла
if [ ! -f ".env" ]; then
	echo "❌ Файл .env не найден!"
	echo "Создайте его на основе env.example"
	exit 1
fi

# Активация venv если есть
if [ -d "venv" ]; then
	source venv/bin/activate
	echo "✅ Виртуальное окружение активировано"
else
	echo "⚠️  Виртуальное окружение не найдено"
	echo "Используется системный Python"
fi

# Проверка зависимостей
echo "📦 Проверка зависимостей..."
pip show python-telegram-bot > /dev/null 2>&1 || {
	echo "❌ Зависимости не установлены!"
	echo "Запустите: pip install -r requirements.txt"
	exit 1
}

echo "✅ Зависимости установлены"

# Проверка конфигурации
echo "🔧 Проверка конфигурации..."
source .env

if [ -z "$TELEGRAM_TOKEN" ] || [ "$TELEGRAM_TOKEN" = "your_telegram_bot_token_here" ]; then
	echo "❌ TELEGRAM_TOKEN не настроен в .env"
	exit 1
fi

if [ -z "$OWNER_CHAT_ID" ] || [ "$OWNER_CHAT_ID" = "your_telegram_id_here" ]; then
	echo "⚠️  OWNER_CHAT_ID не настроен - бот будет доступен всем!"
fi

echo "✅ Конфигурация в порядке"
echo ""
echo "▶️  Запуск бота..."
echo "Нажмите Ctrl+C для остановки"
echo ""

# Запуск
python bot.py

