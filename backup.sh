#!/bin/bash

# Скрипт для создания бэкапа критичных данных

set -e

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

# Создание директории для бэкапов
mkdir -p "$BACKUP_DIR"

echo "🗄️  Создание бэкапа TradeBot..."
echo "Дата: $(date)"
echo ""

# Проверка наличия критичных файлов
CRITICAL_FILES=()

if [ -f ".env" ]; then
	CRITICAL_FILES+=(".env")
else
	echo "⚠️  .env не найден"
fi

if [ -f "paper_trading_state.json" ]; then
	CRITICAL_FILES+=("paper_trading_state.json")
fi

if [ -f "tracked_symbols.json" ]; then
	CRITICAL_FILES+=("tracked_symbols.json")
fi

# Добавить директорию backtests если есть файлы
if [ -d "backtests" ] && [ "$(ls -A backtests 2>/dev/null)" ]; then
	CRITICAL_FILES+=("backtests/")
fi

if [ ${#CRITICAL_FILES[@]} -eq 0 ]; then
	echo "❌ Нет файлов для бэкапа!"
	exit 1
fi

# Создание архива
BACKUP_FILE="$BACKUP_DIR/tradebot_backup_$DATE.tar.gz"

echo "📦 Создание архива..."
echo "Файлы:"
for file in "${CRITICAL_FILES[@]}"; do
	echo "  - $file"
done
echo ""

tar -czf "$BACKUP_FILE" "${CRITICAL_FILES[@]}" 2>/dev/null || {
	echo "❌ Ошибка создания архива"
	exit 1
}

# Проверка размера
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "✅ Бэкап создан: $BACKUP_FILE"
echo "📊 Размер: $BACKUP_SIZE"
echo ""

# Очистка старых бэкапов (старше 30 дней)
OLD_BACKUPS=$(find "$BACKUP_DIR" -name "tradebot_backup_*.tar.gz" -mtime +30 2>/dev/null | wc -l)
if [ "$OLD_BACKUPS" -gt 0 ]; then
	echo "🧹 Удаление старых бэкапов (>30 дней)..."
	find "$BACKUP_DIR" -name "tradebot_backup_*.tar.gz" -mtime +30 -delete
	echo "Удалено: $OLD_BACKUPS файлов"
	echo ""
fi

# Список всех бэкапов
TOTAL_BACKUPS=$(ls -1 "$BACKUP_DIR"/tradebot_backup_*.tar.gz 2>/dev/null | wc -l)
if [ "$TOTAL_BACKUPS" -gt 0 ]; then
	echo "📚 Всего бэкапов: $TOTAL_BACKUPS"
	echo "Последние 5:"
	ls -lht "$BACKUP_DIR"/tradebot_backup_*.tar.gz | head -n 5 | awk '{print "  ", $9, "(" $5 ")"}'
else
	echo "📚 Бэкапов: 1 (только что созданный)"
fi

echo ""
echo "✅ Бэкап завершен!"
echo ""
echo "💡 Для восстановления:"
echo "   tar -xzf $BACKUP_FILE"
echo ""

