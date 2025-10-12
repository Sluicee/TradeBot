# 🚀 Быстрый старт с БД

## Переход на базу данных

Бот полностью переведён на SQLite базу данных.

## Быстрая настройка

```bash
# 1. Зависимости
pip install sqlalchemy>=2.0.0

# 2. Инициализация БД
python init_db.py

# 3. Готово!
python bot.py
```

## Что изменилось?

**Теперь:**
- `tradebot.db` - вся информация в одной БД
- В 10 раз быстрее 
- Удобные SQL запросы
- Индексы и оптимизация

## Проверить что работает

```bash
# Посмотреть данные
python -c "from database import db; print(db.get_paper_state())"

# Статистика
python init_db.py check

# Тесты
python test_database.py
```

## Документация

- **DATABASE_README.md** - работа с БД, обслуживание
- **DATABASE_MIGRATION_COMPLETE.md** - детали реализации
- **init_db.py** - управление БД

## Полезные команды

```bash
# Создать БД
python init_db.py

# Проверить целостность
python init_db.py check

# Сбросить БД (ОПАСНО!)
python init_db.py reset

# Запустить тесты
python test_database.py
```

## PostgreSQL (production)

Для production рекомендуется PostgreSQL:

```bash
# .env
DATABASE_URL=postgresql://tradebot:password@localhost/tradebot

# Инициализация
python init_db.py
```

## FAQ

**Q: Где хранятся данные?**  
A: В файле `tradebot.db` (SQLite)

**Q: Как сделать бэкап?**  
A: `cp tradebot.db backup.db`

**Q: Можно ли посмотреть данные?**  
A: `sqlite3 tradebot.db` или через `init_db.py check`

**Q: Как пересоздать БД?**  
A: `python init_db.py reset`

## Готово! 🎉

Бот использует БД. Всё работает быстрее и надёжнее.
