#!/bin/bash

# Скрипт для обновления бота на сервере

set -e

echo "🔄 Обновление Trading Bot..."

# Остановка бота
echo "⏸️  Остановка бота..."
sudo systemctl stop tradebot || true

# Обновление из git
echo "📥 Получение обновлений из репозитория..."
git pull

# Активация venv
source venv/bin/activate

# Обновление зависимостей
echo "📦 Обновление зависимостей..."
pip install --upgrade -r requirements.txt

# Запуск бота
echo "▶️  Запуск бота..."
sudo systemctl start tradebot

echo "✅ Обновление завершено!"
echo "📊 Проверьте статус: sudo systemctl status tradebot"

