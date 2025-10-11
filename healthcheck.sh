#!/bin/bash

# Скрипт для проверки здоровья бота
# Можно запускать вручную или через cron для мониторинга

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🏥 Проверка здоровья Trading Bot..."
echo ""

# Цветные выводы
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверка метода запуска
if command -v docker-compose &> /dev/null && [ -f "docker-compose.yml" ]; then
	METHOD="docker"
	echo "📦 Метод запуска: Docker"
elif systemctl is-active --quiet tradebot 2>/dev/null; then
	METHOD="systemd"
	echo "⚙️  Метод запуска: Systemd"
else
	METHOD="unknown"
	echo -e "${YELLOW}⚠️  Не удалось определить метод запуска${NC}"
fi

echo ""

# Проверка .env
echo -n "📝 Конфигурация (.env): "
if [ -f ".env" ]; then
	echo -e "${GREEN}✓${NC}"
	
	# Проверка важных переменных
	source .env
	
	echo -n "   TELEGRAM_TOKEN: "
	if [ -n "$TELEGRAM_TOKEN" ] && [ "$TELEGRAM_TOKEN" != "your_telegram_bot_token_here" ]; then
		echo -e "${GREEN}✓${NC}"
	else
		echo -e "${RED}✗ Не настроен${NC}"
	fi
	
	echo -n "   OWNER_CHAT_ID: "
	if [ -n "$OWNER_CHAT_ID" ] && [ "$OWNER_CHAT_ID" != "your_telegram_id_here" ]; then
		echo -e "${GREEN}✓${NC}"
	else
		echo -e "${YELLOW}⚠ Не настроен (небезопасно)${NC}"
	fi
else
	echo -e "${RED}✗ Файл не найден${NC}"
fi

echo ""

# Проверка статуса
echo -n "🔄 Статус бота: "
if [ "$METHOD" = "docker" ]; then
	if docker-compose ps | grep -q "Up"; then
		echo -e "${GREEN}✓ Работает${NC}"
	else
		echo -e "${RED}✗ Не работает${NC}"
	fi
elif [ "$METHOD" = "systemd" ]; then
	if systemctl is-active --quiet tradebot; then
		echo -e "${GREEN}✓ Работает${NC}"
	else
		echo -e "${RED}✗ Не работает${NC}"
	fi
else
	echo -e "${YELLOW}? Неизвестно${NC}"
fi

echo ""

# Проверка логов на ошибки
echo "📊 Последние ошибки в логах:"
if [ -d "logs" ]; then
	LATEST_LOG=$(ls -t logs/log_*.txt 2>/dev/null | head -n 1)
	if [ -n "$LATEST_LOG" ]; then
		ERROR_COUNT=$(grep -i "error\|exception\|failed" "$LATEST_LOG" 2>/dev/null | wc -l || echo 0)
		if [ "$ERROR_COUNT" -eq 0 ]; then
			echo -e "   ${GREEN}✓ Ошибок не обнаружено${NC}"
		else
			echo -e "   ${YELLOW}⚠ Найдено ошибок: $ERROR_COUNT${NC}"
			echo "   Последние 3 ошибки:"
			grep -i "error\|exception\|failed" "$LATEST_LOG" | tail -n 3 | sed 's/^/   /'
		fi
	else
		echo -e "   ${YELLOW}⚠ Логи не найдены${NC}"
	fi
else
	echo -e "   ${YELLOW}⚠ Директория logs не найдена${NC}"
fi

echo ""

# Проверка размера логов
echo -n "💾 Размер логов: "
if [ -d "logs" ]; then
	LOG_SIZE=$(du -sh logs/ 2>/dev/null | cut -f1)
	echo "$LOG_SIZE"
	
	# Предупреждение если больше 100MB
	LOG_SIZE_MB=$(du -sm logs/ 2>/dev/null | cut -f1)
	if [ "$LOG_SIZE_MB" -gt 100 ]; then
		echo -e "   ${YELLOW}⚠ Логи занимают много места. Рекомендуется очистка.${NC}"
		echo "   Команда: find logs/ -name '*.log' -mtime +7 -delete"
	fi
else
	echo -e "${YELLOW}Директория не найдена${NC}"
fi

echo ""

# Проверка использования ресурсов
if [ "$METHOD" = "docker" ]; then
	echo "🖥️  Использование ресурсов (Docker):"
	docker stats --no-stream --format "   CPU: {{.CPUPerc}}, Memory: {{.MemUsage}}" tradebot 2>/dev/null || echo -e "   ${YELLOW}Недоступно${NC}"
elif [ "$METHOD" = "systemd" ]; then
	echo "🖥️  Использование ресурсов:"
	PID=$(pgrep -f "python.*bot.py" | head -n 1)
	if [ -n "$PID" ]; then
		ps -p "$PID" -o %cpu,%mem,rss,vsz | tail -n 1 | awk '{printf "   CPU: %s%%, Memory: %s%% (RSS: %d KB, VSZ: %d KB)\n", $1, $2, $3, $4}'
	else
		echo -e "   ${YELLOW}Процесс не найден${NC}"
	fi
fi

echo ""

# Проверка файлов состояния
echo "📁 Файлы состояния:"
echo -n "   paper_trading_state.json: "
if [ -f "paper_trading_state.json" ]; then
	echo -e "${GREEN}✓${NC} ($(stat -c%s paper_trading_state.json) bytes)"
else
	echo -e "${YELLOW}Не найден (норма для нового запуска)${NC}"
fi

echo -n "   tracked_symbols.json: "
if [ -f "tracked_symbols.json" ]; then
	SYMBOL_COUNT=$(jq '. | length' tracked_symbols.json 2>/dev/null || echo "?")
	echo -e "${GREEN}✓${NC} ($SYMBOL_COUNT символов)"
else
	echo -e "${YELLOW}Не найден (норма для нового запуска)${NC}"
fi

echo ""

# Итоговая оценка
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Итоговая оценка здоровья:"

HEALTH_SCORE=0
MAX_SCORE=5

# Проверки для счета
[ -f ".env" ] && ((HEALTH_SCORE++))
[ -n "$TELEGRAM_TOKEN" ] && [ "$TELEGRAM_TOKEN" != "your_telegram_bot_token_here" ] && ((HEALTH_SCORE++))
[ "$METHOD" != "unknown" ] && ((HEALTH_SCORE++))

if [ "$METHOD" = "docker" ]; then
	docker-compose ps | grep -q "Up" && ((HEALTH_SCORE++))
elif [ "$METHOD" = "systemd" ]; then
	systemctl is-active --quiet tradebot && ((HEALTH_SCORE++))
fi

[ "${ERROR_COUNT:-0}" -eq 0 ] && ((HEALTH_SCORE++))

if [ "$HEALTH_SCORE" -eq "$MAX_SCORE" ]; then
	echo -e "${GREEN}✅ Отлично! Все системы работают нормально.${NC}"
elif [ "$HEALTH_SCORE" -ge 3 ]; then
	echo -e "${YELLOW}⚠️  Хорошо, но есть небольшие проблемы.${NC}"
else
	echo -e "${RED}❌ Обнаружены серьезные проблемы!${NC}"
fi

echo "Счет здоровья: $HEALTH_SCORE/$MAX_SCORE"
echo ""

# Команды для управления
echo "💡 Полезные команды:"
if [ "$METHOD" = "docker" ]; then
	echo "   Логи:        docker-compose logs -f"
	echo "   Рестарт:     docker-compose restart"
	echo "   Остановка:   docker-compose stop"
elif [ "$METHOD" = "systemd" ]; then
	echo "   Логи:        journalctl -u tradebot -f"
	echo "   Рестарт:     sudo systemctl restart tradebot"
	echo "   Остановка:   sudo systemctl stop tradebot"
fi
echo "   Очистка логов: find logs/ -name '*.log' -mtime +7 -delete"
echo ""

