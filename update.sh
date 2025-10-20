#!/bin/bash

# Универсальный скрипт обновления бота (Docker и Systemd)

set -e

echo "🔄 Обновление Trading Bot..."
echo ""

# Определение метода запуска
if [ -f "docker-compose.yml" ] && command -v docker-compose &> /dev/null; then
	METHOD="docker"
	echo "📦 Обнаружен Docker"
	
	# Проверка доступа к Docker
	if ! docker ps &> /dev/null; then
		echo ""
		echo "❌ Нет доступа к Docker!"
		echo ""
		echo "Решения:"
		echo "  1. Добавить пользователя в группу docker:"
		echo "     sudo usermod -aG docker \$USER"
		echo "     exit  # И перелогиниться"
		echo ""
		echo "  2. Или запустить с sudo:"
		echo "     sudo docker-compose down"
		echo "     sudo docker-compose up -d --build"
		echo ""
		echo "  3. Проверить что Docker запущен:"
		echo "     sudo systemctl status docker"
		exit 1
	fi
	
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

# Миграция Real Trading
echo "🔄 Проверка миграции Real Trading..."
if [ -f "migrate_real_trading.py" ]; then
	echo "📊 Выполнение миграции Real Trading..."
	python3 migrate_real_trading.py
	
	if [ $? -eq 0 ]; then
		echo "✅ Миграция Real Trading завершена"
	else
		echo "⚠️  Миграция Real Trading завершилась с предупреждениями"
	fi
else
	echo "ℹ️  Миграция Real Trading не найдена, пропускаем"
fi

echo ""

# Обновление в зависимости от метода
if [ "$METHOD" = "docker" ]; then
	echo "🐳 Обновление Docker контейнера..."
	
	
	# Определение версии docker-compose
	if docker compose version &> /dev/null; then
		DC_CMD="docker compose"
	elif command -v docker-compose &> /dev/null; then
		DC_CMD="docker-compose"
	else
		echo "❌ docker-compose не найден!"
		exit 1
	fi
	
	echo "Используется: $DC_CMD"
	
	# Остановка
	$DC_CMD down
	
	# Пересборка и запуск
	$DC_CMD up -d --build
	
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

