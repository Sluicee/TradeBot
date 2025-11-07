"""
Скрипт для исправления схемы таблицы real_trades
Делает поле order_id nullable для предотвращения ошибок записи
"""

import sqlite3
from logger import logger

def fix_real_trades_table():
	"""Исправляет схему таблицы real_trades"""
	try:
		# Подключаемся к БД
		conn = sqlite3.connect('data/tradebot.db')
		cursor = conn.cursor()
		
		logger.info("Начинаем исправление таблицы real_trades...")
		
		# Проверяем существование таблицы
		cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='real_trades'")
		if not cursor.fetchone():
			logger.warning("Таблица real_trades не существует, пропускаем миграцию")
			conn.close()
			return
		
		# SQLite не поддерживает ALTER COLUMN, поэтому нужно пересоздать таблицу
		logger.info("Создаем временную таблицу...")
		
		# 1. Создаем временную таблицу с правильной схемой
		cursor.execute("""
			CREATE TABLE real_trades_new (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				symbol TEXT NOT NULL,
				side TEXT NOT NULL,
				order_type TEXT NOT NULL,
				quantity REAL NOT NULL,
				price REAL NOT NULL,
				order_id TEXT,
				status TEXT NOT NULL,
				commission REAL DEFAULT 0.0,
				realized_pnl REAL DEFAULT 0.0,
				timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
				reason TEXT,
				created_at DATETIME DEFAULT CURRENT_TIMESTAMP
			)
		""")
		
		# 2. Копируем данные из старой таблицы
		logger.info("Копируем данные...")
		cursor.execute("""
			INSERT INTO real_trades_new 
			(id, symbol, side, order_type, quantity, price, order_id, status, 
			 commission, realized_pnl, timestamp, reason, created_at)
			SELECT id, symbol, side, order_type, quantity, price, order_id, status,
				   commission, realized_pnl, timestamp, reason, created_at
			FROM real_trades
		""")
		
		# 3. Удаляем старую таблицу
		logger.info("Удаляем старую таблицу...")
		cursor.execute("DROP TABLE real_trades")
		
		# 4. Переименовываем новую таблицу
		logger.info("Переименовываем новую таблицу...")
		cursor.execute("ALTER TABLE real_trades_new RENAME TO real_trades")
		
		# 5. Создаем индексы заново
		logger.info("Создаем индексы...")
		cursor.execute("CREATE INDEX IF NOT EXISTS ix_real_trades_symbol ON real_trades (symbol)")
		cursor.execute("CREATE INDEX IF NOT EXISTS ix_real_trades_order_id ON real_trades (order_id)")
		cursor.execute("CREATE INDEX IF NOT EXISTS ix_real_trades_timestamp ON real_trades (timestamp)")
		
		# Коммитим изменения
		conn.commit()
		logger.info("✅ Таблица real_trades успешно исправлена!")
		
		# Выводим количество записей
		cursor.execute("SELECT COUNT(*) FROM real_trades")
		count = cursor.fetchone()[0]
		logger.info(f"Количество записей в таблице: {count}")
		
		conn.close()
		
	except Exception as e:
		logger.error(f"❌ Ошибка исправления таблицы: {e}")
		raise

if __name__ == "__main__":
	fix_real_trades_table()

