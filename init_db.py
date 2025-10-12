"""
Инициализация базы данных
Создаёт все таблицы и проверяет структуру
"""
from database import db
from logger import logger


def init_database():
	"""Создать все таблицы в БД"""
	logger.info("=== ИНИЦИАЛИЗАЦИЯ БД ===")
	
	try:
		# Создаём таблицы
		db.create_tables()
		logger.info("✅ Таблицы созданы успешно")
		
		# Проверка
		state = db.get_paper_state()
		if state:
			logger.info(f"📊 Paper Trading: ${state.balance:.2f}")
		else:
			logger.info("📊 Paper Trading: не инициализирован")
		
		symbols = db.get_tracked_symbols()
		logger.info(f"🎯 Отслеживаемых символов: {len(symbols)}")
		
		positions = db.get_all_positions()
		logger.info(f"💼 Открытых позиций: {len(positions)}")
		
		trades = db.get_trades_history(limit=1000)
		logger.info(f"📝 История сделок: {len(trades)} записей")
		
		signals = db.get_signals(limit=1000)
		logger.info(f"📡 Логов сигналов: {len(signals)} записей")
		
		backtests = db.get_backtests()
		logger.info(f"🧪 Бэктестов: {len(backtests)}")
		
		logger.info("\n✅ База данных готова к использованию!")
		logger.info(f"📍 Файл БД: {db.database_url}")
		
	except Exception as e:
		logger.error(f"❌ Ошибка инициализации БД: {e}")
		raise


def check_database():
	"""Проверить целостность БД"""
	logger.info("=== ПРОВЕРКА БД ===")
	
	try:
		# Проверка основных таблиц
		tables_to_check = [
			("paper_trading_state", db.get_paper_state),
			("tracked_symbols", lambda: db.get_tracked_symbols()),
			("positions", lambda: db.get_all_positions()),
			("trades_history", lambda: db.get_trades_history(limit=1)),
			("signals", lambda: db.get_signals(limit=1)),
			("bot_settings", lambda: db.get_bot_settings()),
			("backtests", lambda: db.get_backtests(limit=1)),
		]
		
		errors = []
		for table_name, check_func in tables_to_check:
			try:
				check_func()
				logger.info(f"✅ {table_name}: OK")
			except Exception as e:
				logger.error(f"❌ {table_name}: {e}")
				errors.append((table_name, e))
		
		if errors:
			logger.error(f"\n❌ Обнаружено ошибок: {len(errors)}")
			for table, error in errors:
				logger.error(f"  - {table}: {error}")
			return False
		else:
			logger.info("\n✅ Все таблицы в порядке!")
			return True
			
	except Exception as e:
		logger.error(f"❌ Критическая ошибка проверки: {e}")
		return False


def reset_database():
	"""ОПАСНО: Удалить все таблицы и пересоздать"""
	logger.warning("⚠️  ВНИМАНИЕ: Все данные будут удалены!")
	
	response = input("Вы уверены? Введите 'YES' для подтверждения: ")
	if response != "YES":
		logger.info("❌ Операция отменена")
		return
	
	try:
		logger.info("Удаление таблиц...")
		db.drop_tables()
		
		logger.info("Создание таблиц...")
		db.create_tables()
		
		logger.info("✅ База данных сброшена")
		
	except Exception as e:
		logger.error(f"❌ Ошибка сброса БД: {e}")
		raise


if __name__ == "__main__":
	import sys
	
	if len(sys.argv) > 1:
		command = sys.argv[1].lower()
		
		if command == "init":
			init_database()
		elif command == "check":
			check_database()
		elif command == "reset":
			reset_database()
		else:
			print("Использование:")
			print("  python init_db.py init   - Инициализировать БД")
			print("  python init_db.py check  - Проверить БД")
			print("  python init_db.py reset  - Сбросить БД (ОПАСНО)")
	else:
		# По умолчанию - инициализация
		init_database()

