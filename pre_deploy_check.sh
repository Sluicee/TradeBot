#!/bin/bash

# Скрипт для проверки готовности проекта к деплою

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0
WARNINGS=0

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  📋 Проверка готовности к деплою"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Функция для проверки
check() {
	local name="$1"
	local condition="$2"
	
	echo -n "  $name... "
	
	if eval "$condition"; then
		echo -e "${GREEN}✓${NC}"
		((PASSED++))
		return 0
	else
		echo -e "${RED}✗${NC}"
		((FAILED++))
		return 1
	fi
}

# Функция для предупреждения
warn() {
	local name="$1"
	local condition="$2"
	
	echo -n "  $name... "
	
	if eval "$condition"; then
		echo -e "${GREEN}✓${NC}"
		((PASSED++))
		return 0
	else
		echo -e "${YELLOW}⚠${NC}"
		((WARNINGS++))
		return 1
	fi
}

echo "🔍 Проверка файлов конфигурации:"
check ".gitignore существует" "[ -f '.gitignore' ]"
check "requirements.txt существует" "[ -f 'requirements.txt' ]"
check "env.example существует" "[ -f 'env.example' ]"
check "Dockerfile существует" "[ -f 'Dockerfile' ]"
check "docker-compose.yml существует" "[ -f 'docker-compose.yml' ]"
echo ""

echo "🔐 Проверка безопасности:"
check ".env в .gitignore" "grep -q '^\.env$' .gitignore"
check ".env НЕ в git" "! git ls-files | grep -q '^\.env$'"
check ".env НЕ в истории git" "[ -z \"\$(git log --all --full-history -- .env 2>/dev/null)\" ]"
check "venv в .gitignore" "grep -q '^venv/' .gitignore"
check "logs в .gitignore" "grep -q '^logs/' .gitignore || grep -q '^logs$' .gitignore"
echo ""

echo "📦 Проверка зависимостей:"
check "requirements.txt не пустой" "[ -s 'requirements.txt' ]"
check "python-telegram-bot в requirements.txt" "grep -q 'python-telegram-bot' requirements.txt"
check "pandas в requirements.txt" "grep -q 'pandas' requirements.txt"
check "ta в requirements.txt" "grep -q 'ta' requirements.txt"
check "НЕТ asyncio в requirements.txt" "! grep -q '^asyncio$' requirements.txt"
check "python-dotenv в requirements.txt" "grep -q 'python-dotenv' requirements.txt"
echo ""

echo "🐳 Проверка Docker конфигурации:"
check "Dockerfile содержит WORKDIR" "grep -q 'WORKDIR' Dockerfile"
check "Dockerfile создает директории" "grep -q 'mkdir.*logs' Dockerfile"
check "docker-compose.yml содержит volumes" "grep -q 'volumes:' docker-compose.yml"
check "docker-compose.yml содержит restart policy" "grep -q 'restart:' docker-compose.yml"
check "docker-compose.yml содержит env_file" "grep -q 'env_file:' docker-compose.yml"
check "docker-compose.yml содержит healthcheck" "grep -q 'healthcheck:' docker-compose.yml"
check "docker-compose.yml содержит logging" "grep -q 'logging:' docker-compose.yml"
echo ""

echo "📝 Проверка скриптов:"
check "deploy.sh существует" "[ -f 'deploy.sh' ]"
check "update.sh существует" "[ -f 'update.sh' ]"
check "healthcheck.sh существует" "[ -f 'healthcheck.sh' ]"
check "backup.sh существует" "[ -f 'backup.sh' ]"
warn "deploy.sh исполняемый" "[ -x 'deploy.sh' ]" && echo "     Выполните: chmod +x deploy.sh"
warn "update.sh исполняемый" "[ -x 'update.sh' ]" && echo "     Выполните: chmod +x update.sh"
warn "healthcheck.sh исполняемый" "[ -x 'healthcheck.sh' ]" && echo "     Выполните: chmod +x healthcheck.sh"
warn "backup.sh исполняемый" "[ -x 'backup.sh' ]" && echo "     Выполните: chmod +x backup.sh"
echo ""

echo "📚 Проверка документации:"
check "README.md существует" "[ -f 'README.md' ]"
check "DEPLOY_GUIDE.md существует" "[ -f 'DEPLOY_GUIDE.md' ]"
check "PRE_DEPLOY_CHECKLIST.md существует" "[ -f 'PRE_DEPLOY_CHECKLIST.md' ]"
echo ""

echo "🧪 Проверка основных файлов проекта:"
check "bot.py существует" "[ -f 'bot.py' ]"
check "config.py существует" "[ -f 'config.py' ]"
check "signal_generator.py существует" "[ -f 'signal_generator.py' ]"
check "data_provider.py существует" "[ -f 'data_provider.py' ]"
echo ""

echo "⚙️  Проверка git репозитория:"
check "git репозиторий инициализирован" "[ -d '.git' ]"
warn "Нет uncommitted изменений" "[ -z \"\$(git status --porcelain 2>/dev/null)\" ]" && \
	echo "     Есть неcохраненные изменения. Выполните: git add . && git commit -m 'Prepare for deployment'"
warn "Есть удаленный репозиторий" "git remote -v | grep -q origin" && \
	echo "     Добавьте удаленный репозиторий: git remote add origin <url>"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Результаты проверки:"
echo ""
echo -e "  ${GREEN}✓ Пройдено:${NC} $PASSED"
echo -e "  ${YELLOW}⚠ Предупреждений:${NC} $WARNINGS"
echo -e "  ${RED}✗ Ошибок:${NC} $FAILED"
echo ""

TOTAL=$((PASSED + WARNINGS + FAILED))
SCORE=$((PASSED * 100 / TOTAL))

if [ $FAILED -eq 0 ] && [ $WARNINGS -eq 0 ]; then
	echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
	echo -e "${GREEN}✅ ОТЛИЧНО! Проект готов к деплою!${NC}"
	echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
	echo ""
	echo "📋 Следующие шаги:"
	echo "  1. Закоммитить изменения: git add . && git commit -m 'Ready for deployment'"
	echo "  2. Запушить на сервер: git push origin master"
	echo "  3. На сервере: git clone <repo> && cd TradeBot"
	echo "  4. Создать .env: cp env.example .env && nano .env"
	echo "  5. Запустить: docker compose up -d --build"
	echo ""
elif [ $FAILED -eq 0 ]; then
	echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
	echo -e "${YELLOW}⚠️  ХОРОШО! Есть небольшие замечания${NC}"
	echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
	echo ""
	echo "Устраните предупреждения выше и можно деплоить"
	echo ""
else
	echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
	echo -e "${RED}❌ ВНИМАНИЕ! Обнаружены ошибки!${NC}"
	echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
	echo ""
	echo "Устраните ошибки перед деплоем!"
	echo ""
	exit 1
fi

echo "💡 Полезные команды:"
echo "  Локальный тест:    docker compose up --build"
echo "  Проверка здоровья: ./healthcheck.sh"
echo "  Создать бэкап:     ./backup.sh"
echo ""

