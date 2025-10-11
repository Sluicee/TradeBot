#!/bin/bash

# Скрипт обновления бота в Docker

set -e

echo "🔄 Обновление Trading Bot (Docker)..."
echo ""

# Проверка наличия docker-compose
if ! command -v docker-compose &> /dev/null; then
	echo "❌ docker-compose не найден!"
	exit 1
fi

# Проверка что мы в правильной директории
if [ ! -f "docker-compose.yml" ]; then
	echo "❌ docker-compose.yml не найден!"
	echo "Запустите скрипт из директории проекта"
	exit 1
fi

# Сохранение текущего коммита для возможности отката
CURRENT_COMMIT=$(git rev-parse --short HEAD)
echo "📌 Текущий коммит: $CURRENT_COMMIT"
echo ""

# Проверка статуса git
if [ -n "$(git status --porcelain)" ]; then
	echo "⚠️  Есть несохраненные изменения!"
	echo "Сохраните или отмените их перед обновлением"
	git status --short
	echo ""
	read -p "Продолжить? (y/N) " -n 1 -r
	echo
	if [[ ! $REPLY =~ ^[Yy]$ ]]; then
		exit 1
	fi
fi

# Получение обновлений
echo "📥 Получение обновлений из репозитория..."
if ! git pull; then
	echo "❌ Ошибка при получении обновлений!"
	exit 1
fi

NEW_COMMIT=$(git rev-parse --short HEAD)

if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then
	echo "✅ Уже на последней версии"
	echo ""
	read -p "Пересобрать контейнер? (y/N) " -n 1 -r
	echo
	if [[ ! $REPLY =~ ^[Yy]$ ]]; then
		echo "Обновление отменено"
		exit 0
	fi
else
	echo "📦 Новый коммит: $NEW_COMMIT"
fi

echo ""

# Создание бэкапа состояния
if [ -f "paper_trading_state.json" ]; then
	echo "💾 Создание бэкапа состояния..."
	cp paper_trading_state.json "paper_trading_state.json.backup_$(date +%Y%m%d_%H%M%S)"
fi

# Остановка контейнера
echo "⏸️  Остановка контейнера..."
docker-compose down

# Пересборка образа
echo "🔨 Пересборка образа..."
if ! docker-compose build; then
	echo ""
	echo "❌ Ошибка при сборке образа!"
	echo "Откатываем к предыдущей версии..."
	git reset --hard $CURRENT_COMMIT
	echo "Запускаем старую версию..."
	docker-compose up -d
	exit 1
fi

# Запуск контейнера
echo "▶️  Запуск обновленного контейнера..."
if ! docker-compose up -d; then
	echo ""
	echo "❌ Ошибка при запуске контейнера!"
	echo "Откатываем к предыдущей версии..."
	git reset --hard $CURRENT_COMMIT
	docker-compose build
	docker-compose up -d
	exit 1
fi

echo ""
echo "✅ Обновление завершено успешно!"
echo ""
echo "Изменения: $CURRENT_COMMIT → $NEW_COMMIT"
echo ""
echo "📊 Проверка логов..."
sleep 3
docker-compose logs --tail 30

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Бот успешно обновлен и запущен!"
echo ""
echo "Команды для мониторинга:"
echo "  docker-compose logs -f       # Следить за логами"
echo "  docker-compose ps            # Статус контейнера"
echo "  ./healthcheck.sh             # Проверка здоровья"
echo ""
echo "Для отката к предыдущей версии:"
echo "  git reset --hard $CURRENT_COMMIT"
echo "  docker-compose up -d --build"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

