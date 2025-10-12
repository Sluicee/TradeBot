#!/bin/bash
set -e

echo "🚀 Запуск TradeBot..."

# Инициализация БД если её нет
if [ ! -f "tradebot.db" ]; then
	echo "📊 База данных не найдена. Инициализация..."
	python init_db.py
else
	echo "✅ База данных найдена"
fi

# Запуск бота
echo "▶️  Запуск бота..."
exec python bot.py

