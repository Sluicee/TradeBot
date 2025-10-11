#!/bin/bash

# Универсальный скрипт обновления бота (Docker и Systemd)

set -e

echo "🔄 Обновление Trading Bot..."
echo ""

# Определение метода запуска
if [ -f "docker-compose.yml" ] && command -v docker-compose &> /dev/null; then
	METHOD="docker"
	echo "📦 Обнаружен Docker"
elif systemctl is-active --quiet tradebot 2>/dev/null; then
	METHOD="systemd"
	echo "⚙️  Обнаружен Systemd"
else
	echo "❌ Не удалось определить метод запуска!"
	echo "Установите Docker или настройте Systemd сервис"
	exit 1
fi

echo ""

# Получение обновлений
echo "📥 Получение обновлений из репозитория..."
git pull

echo ""

# Обновление в зависимости от метода
if [ "$METHOD" = "docker" ]; then
	echo "🐳 Обновление Docker контейнера..."
	
	# Создание бэкапа состояния
	if [ -f "paper_trading_state.json" ]; then
		echo "💾 Бэкап состояния..."
		cp paper_trading_state.json "paper_trading_state.json.backup"
	fi
	
	# Остановка
	docker-compose down
	
	# Пересборка и запуск
	docker-compose up -d --build
	
	echo ""
	echo "✅ Обновление завершено!"
	echo "📊 Проверка: docker-compose logs -f"
	
elif [ "$METHOD" = "systemd" ]; then
	echo "⚙️  Обновление Systemd сервиса..."
	
	# Остановка бота
	echo "⏸️  Остановка бота..."
	sudo systemctl stop tradebot
	
	# Активация venv
	if [ -d "venv" ]; then
		source venv/bin/activate
		
		# Обновление зависимостей
		echo "📦 Обновление зависимостей..."
		pip install --upgrade -r requirements.txt
	fi
	
	# Запуск бота
	echo "▶️  Запуск бота..."
	sudo systemctl start tradebot
	
	echo ""
	echo "✅ Обновление завершено!"
	echo "📊 Проверка: sudo systemctl status tradebot"
fi

