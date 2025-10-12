FROM python:3.10-slim

# Установка рабочей директории
WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
	gcc \
	&& rm -rf /var/lib/apt/lists/*

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir --upgrade pip && \
	pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Создание необходимых директорий
RUN mkdir -p logs signals backtests data

# Копирование entrypoint скрипта
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Переменные окружения
ENV PYTHONUNBUFFERED=1

# Запуск через entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

