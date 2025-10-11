#!/bin/bash

# Скрипт для восстановления данных из бэкапа

set -e

echo "🔄 Восстановление данных Trading Bot..."
echo ""

# Проверка наличия бэкапов
if [ ! -d "backups" ]; then
	echo "❌ Директория backups не найдена!"
	exit 1
fi

# Список доступных бэкапов
echo "Доступные бэкапы:"
echo ""

BACKUPS=($(ls -t backups/backup_* 2>/dev/null))

if [ ${#BACKUPS[@]} -eq 0 ]; then
	echo "❌ Бэкапы не найдены!"
	exit 1
fi

# Показать список
for i in "${!BACKUPS[@]}"; do
	SIZE=$(du -sh "${BACKUPS[$i]}" 2>/dev/null | cut -f1)
	DATE=$(basename "${BACKUPS[$i]}" | sed 's/backup_//' | sed 's/_/ /')
	echo "  [$i] $DATE ($SIZE)"
done

echo ""
read -p "Выберите номер бэкапа для восстановления: " CHOICE

# Проверка выбора
if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || [ "$CHOICE" -ge "${#BACKUPS[@]}" ]; then
	echo "❌ Неверный выбор!"
	exit 1
fi

BACKUP_DIR="${BACKUPS[$CHOICE]}"
echo ""
echo "Восстановление из: $BACKUP_DIR"
echo ""

# Проверка что бот остановлен
if docker ps | grep -q tradebot; then
	echo "⚠️  Бот запущен!"
	read -p "Остановить бота? (y/N) " -n 1 -r
	echo
	if [[ $REPLY =~ ^[Yy]$ ]]; then
		if docker compose version &> /dev/null; then
			docker compose down
		else
			docker-compose down
		fi
	else
		echo "❌ Остановите бота перед восстановлением!"
		exit 1
	fi
fi

# Создание бэкапа текущих файлов
echo "💾 Создание бэкапа текущих файлов..."
CURRENT_BACKUP="backups/before_restore_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$CURRENT_BACKUP"
[ -f ".env" ] && cp .env "$CURRENT_BACKUP/"
[ -f "paper_trading_state.json" ] && cp paper_trading_state.json "$CURRENT_BACKUP/"
[ -f "tracked_symbols.json" ] && cp tracked_symbols.json "$CURRENT_BACKUP/"
echo "✅ Текущее состояние сохранено в: $CURRENT_BACKUP"
echo ""

# Восстановление файлов
COUNT=0

if [ -f "$BACKUP_DIR/.env" ]; then
	cp "$BACKUP_DIR/.env" .
	echo "✓ .env восстановлен"
	((COUNT++))
fi

if [ -f "$BACKUP_DIR/paper_trading_state.json" ]; then
	cp "$BACKUP_DIR/paper_trading_state.json" .
	echo "✓ paper_trading_state.json восстановлен"
	((COUNT++))
fi

if [ -f "$BACKUP_DIR/tracked_symbols.json" ]; then
	cp "$BACKUP_DIR/tracked_symbols.json" .
	echo "✓ tracked_symbols.json восстановлен"
	((COUNT++))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Восстановление завершено!"
echo "Файлов восстановлено: $COUNT"
echo ""
echo "Запустите бота:"
if docker compose version &> /dev/null; then
	echo "  docker compose up -d"
else
	echo "  docker-compose up -d"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

