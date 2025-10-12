#!/bin/bash
set -e

echo "🚀 Запуск TradeBot..."

# Проверка и инициализация БД
if [ ! -f "data/tradebot.db" ] || [ ! -s "data/tradebot.db" ]; then
	echo "📊 База данных не найдена или пуста. Инициализация..."
	python init_db.py init
	
	if [ $? -eq 0 ]; then
		echo "✅ База данных инициализирована успешно"
	else
		echo "❌ Ошибка инициализации БД!"
		exit 1
	fi
else
	echo "✅ База данных найдена"
	# Быстрая проверка целостности
	python -c "from database import db; db.get_paper_state()" 2>/dev/null
	if [ $? -ne 0 ]; then
		echo "⚠️  БД повреждена, переинициализация..."
		python init_db.py init
	fi
fi

# Запуск бота
echo "▶️  Запуск бота..."
exec python bot.py

