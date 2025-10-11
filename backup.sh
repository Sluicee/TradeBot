#!/bin/bash

# Скрипт для создания полного бэкапа данных бота

set -e

echo "💾 Создание бэкапа Trading Bot..."
echo ""

# Директория для бэкапов
BACKUP_ROOT="backups"
BACKUP_DIR="$BACKUP_ROOT/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Счетчик файлов
COUNT=0

# Бэкап конфигурации
if [ -f ".env" ]; then
	cp .env "$BACKUP_DIR/"
	echo "✓ .env"
	((COUNT++))
fi

# Бэкап состояния Paper Trading
if [ -f "paper_trading_state.json" ]; then
	cp paper_trading_state.json "$BACKUP_DIR/"
	echo "✓ paper_trading_state.json"
	((COUNT++))
fi

# Бэкап отслеживаемых символов
if [ -f "tracked_symbols.json" ]; then
	cp tracked_symbols.json "$BACKUP_DIR/"
	echo "✓ tracked_symbols.json"
	((COUNT++))
fi

# Бэкап последних логов (последние 10 файлов)
if [ -d "logs" ]; then
	mkdir -p "$BACKUP_DIR/logs"
	ls -t logs/log_*.txt 2>/dev/null | head -n 10 | xargs -I {} cp {} "$BACKUP_DIR/logs/" 2>/dev/null || true
	LOG_COUNT=$(ls "$BACKUP_DIR/logs/" 2>/dev/null | wc -l)
	if [ "$LOG_COUNT" -gt 0 ]; then
		echo "✓ logs/ (последние $LOG_COUNT файлов)"
		((COUNT++))
	fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Бэкап создан: $BACKUP_DIR"
echo "Файлов сохранено: $COUNT"
echo ""

# Размер бэкапа
SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
echo "Размер: $SIZE"
echo ""

# Создание архива (опционально)
read -p "Создать архив? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
	ARCHIVE="$BACKUP_ROOT/backup_$(date +%Y%m%d_%H%M%S).tar.gz"
	tar -czf "$ARCHIVE" -C "$BACKUP_DIR" .
	echo "✅ Архив создан: $ARCHIVE"
	
	# Удалить директорию после архивирования
	rm -rf "$BACKUP_DIR"
	echo "Размер архива: $(du -sh "$ARCHIVE" | cut -f1)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Восстановление из бэкапа:"
echo "  cp $BACKUP_DIR/.env ."
echo "  cp $BACKUP_DIR/paper_trading_state.json ."
echo "  cp $BACKUP_DIR/tracked_symbols.json ."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

