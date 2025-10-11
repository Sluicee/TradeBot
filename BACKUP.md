# 💾 Резервное копирование и восстановление данных

## 🔐 Что сохраняется автоматически

### При обновлении через `./update.sh`:

Автоматически создается бэкап перед обновлением:
- ✅ `paper_trading_state.json` - состояние торговли (позиции, баланс, история)
- ✅ `tracked_symbols.json` - отслеживаемые пары
- ✅ `.env` - конфигурация бота

Бэкапы сохраняются в `backups/backup_YYYYMMDD_HHMMSS/`

### Git не затрагивает данные:

Эти файлы в `.gitignore` и не перезаписываются при `git pull`:
- `paper_trading_state.json`
- `tracked_symbols.json`
- `logs/`
- `signals/`
- `.env`

### Docker хранит данные на хосте:

Volumes в `docker-compose.yml` монтируют файлы с хоста:
```yaml
volumes:
  - ./paper_trading_state.json:/app/paper_trading_state.json
  - ./tracked_symbols.json:/app/tracked_symbols.json
  - ./logs:/app/logs
```

**Данные не в контейнере, они на хосте - обновление контейнера их не затронет!**

---

## 💾 Ручное создание бэкапа

### Быстрый бэкап:

```bash
./backup.sh
```

Скрипт создаст бэкап всех важных файлов и предложит заархивировать.

### Ручной бэкап:

```bash
# Создать директорию
mkdir -p backups/manual_$(date +%Y%m%d)

# Скопировать важные файлы
cp .env backups/manual_$(date +%Y%m%d)/
cp paper_trading_state.json backups/manual_$(date +%Y%m%d)/
cp tracked_symbols.json backups/manual_$(date +%Y%m%d)/

# Создать архив
tar -czf backups/manual_$(date +%Y%m%d).tar.gz \
	.env \
	paper_trading_state.json \
	tracked_symbols.json
```

---

## 🔄 Восстановление из бэкапа

### Автоматическое восстановление:

```bash
# Остановить бота
docker compose down

# Запустить интерактивное восстановление
./restore.sh

# Выбрать бэкап из списка
# Скрипт автоматически создаст бэкап текущего состояния перед восстановлением

# Запустить бота
docker compose up -d
```

### Ручное восстановление:

```bash
# Остановить бота
docker compose down

# Восстановить файлы
cp backups/backup_YYYYMMDD_HHMMSS/.env .
cp backups/backup_YYYYMMDD_HHMMSS/paper_trading_state.json .
cp backups/backup_YYYYMMDD_HHMMSS/tracked_symbols.json .

# Проверить права
chmod 600 .env

# Запустить бота
docker compose up -d
```

---

## 📋 Процесс обновления БЕЗ потери данных

```bash
# 1. Обновление (автоматически создаст бэкап)
./update.sh

# Скрипт автоматически:
# - Создаст бэкап в backups/backup_YYYYMMDD_HHMMSS/
# - Получит обновления из git
# - Остановит контейнер
# - Пересоберет образ
# - Запустит обновленный контейнер
# - Все данные останутся на месте!

# 2. Проверить что данные на месте
docker compose logs -f

# 3. Проверить в Telegram
# /paper_status - должны быть ваши позиции
# /list - должны быть ваши пары
```

---

## 🗂️ Структура бэкапов

```
backups/
├── backup_20241011_120000/
│   ├── .env
│   ├── paper_trading_state.json
│   ├── tracked_symbols.json
│   └── logs/
├── backup_20241012_150000/
│   ├── .env
│   ├── paper_trading_state.json
│   └── tracked_symbols.json
└── manual_20241013.tar.gz
```

---

## 🧹 Очистка старых бэкапов

```bash
# Удалить бэкапы старше 30 дней
find backups/ -type d -name "backup_*" -mtime +30 -exec rm -rf {} +

# Оставить только последние 10 бэкапов
ls -t backups/backup_* | tail -n +11 | xargs rm -rf

# Проверить размер всех бэкапов
du -sh backups/
```

---

## 📤 Перенос на другой сервер

### Экспорт данных:

```bash
# На старом сервере
cd ~/TradeBot

# Создать полный бэкап
./backup.sh
# Выбрать создание архива (y)

# Скачать архив на локальную машину
# scp user@old-server:~/TradeBot/backups/backup_*.tar.gz ./
```

### Импорт данных:

```bash
# На новом сервере
cd ~/TradeBot

# Загрузить архив
# scp backup_*.tar.gz user@new-server:~/TradeBot/backups/

# Распаковать
mkdir -p backups/imported
tar -xzf backups/backup_*.tar.gz -C backups/imported/

# Восстановить
./restore.sh
# Выбрать imported бэкап

# Запустить
docker compose up -d
```

---

## 🔐 Безопасность бэкапов

### Защита .env файла:

```bash
# .env содержит чувствительные данные (токены)
# Убедитесь что права правильные
chmod 600 .env
chmod 600 backups/*/.env

# НЕ загружайте .env в публичные места!
```

### Шифрование бэкапов (опционально):

```bash
# Зашифровать архив
gpg -c backups/backup_20241011.tar.gz

# Расшифровать
gpg backups/backup_20241011.tar.gz.gpg
```

---

## ✅ Чек-лист безопасности данных

Перед важными изменениями:

- [ ] Создан свежий бэкап: `./backup.sh`
- [ ] Бэкап проверен: `ls -lh backups/`
- [ ] Бот остановлен: `docker compose down`
- [ ] Изменения применены
- [ ] Бот запущен: `docker compose up -d`
- [ ] Данные на месте: проверка в Telegram

---

## 🆘 Экстренное восстановление

### Если что-то пошло не так:

```bash
# 1. Остановить бота
docker compose down

# 2. Найти последний бэкап
ls -lt backups/

# 3. Восстановить
./restore.sh

# 4. Или вручную
cp backups/backup_ПОСЛЕДНИЙ/.env .
cp backups/backup_ПОСЛЕДНИЙ/paper_trading_state.json .
cp backups/backup_ПОСЛЕДНИЙ/tracked_symbols.json .

# 5. Перезапустить
docker compose up -d
```

### Если бэкапов нет:

К сожалению, без бэкапов данные восстановить невозможно. Поэтому:

**Рекомендуется делать регулярные бэкапы!**

```bash
# Добавить в crontab для ежедневного бэкапа
crontab -e

# Добавить строку (бэкап каждый день в 3:00)
0 3 * * * cd /path/to/TradeBot && ./backup.sh
```

---

## 💡 Лучшие практики

1. **Делайте бэкап перед обновлениями** - `./update.sh` делает это автоматически
2. **Храните несколько бэкапов** - не удаляйте сразу старые
3. **Тестируйте восстановление** - проверьте что умеете восстанавливать
4. **Храните .env отдельно** - это самый важный файл
5. **Копируйте критичные бэкапы** - на другой сервер или локально
6. **Автоматизируйте** - используйте cron для регулярных бэкапов

---

**Помните: `./update.sh` автоматически создает бэкап перед обновлением - ваши данные в безопасности!** 🛡️

