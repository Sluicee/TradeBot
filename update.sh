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

# Обновление в зависимости от метода
if [ "$METHOD" = "docker" ]; then
	echo "🐳 Обновление Docker контейнера..."
	
	# Создание бэкапа данных
	echo "💾 Создание бэкапа данных..."
	BACKUP_DIR="backups/backup_$(date +%Y%m%d_%H%M%S)"
	mkdir -p "$BACKUP_DIR"
	
	# Бэкап важных файлов
	[ -f "paper_trading_state.json" ] && cp paper_trading_state.json "$BACKUP_DIR/"
	[ -f "tracked_symbols.json" ] && cp tracked_symbols.json "$BACKUP_DIR/"
	[ -f ".env" ] && cp .env "$BACKUP_DIR/"
	
	echo "✅ Бэкап создан в: $BACKUP_DIR"
	
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

