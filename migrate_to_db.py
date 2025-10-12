"""
Инициализация базы данных
Создаёт структуру БД с пустыми таблицами
"""
from database import db
from logger import logger


def initialize_database():
	"""Создать БД с пустыми таблицами"""
	logger.info("=== ИНИЦИАЛИЗАЦИЯ БД ===")
	
	try:
		# Создаём таблицы
		logger.info("Создание таблиц БД...")
		db.create_tables()
		
		logger.info("✅ База данных создана успешно!")
		logger.info(f"📍 Файл БД: {db.database_url}")
		
		# Статистика
		logger.info("\n📊 Статистика БД:")
		
		state = db.get_paper_state()
		if state:
			logger.info(f"  Paper Trading: ${state.balance:.2f} / {state.total_trades} сделок")
		else:
			logger.info("  Paper Trading: не инициализирован")
		
		symbols = db.get_tracked_symbols()
		logger.info(f"  Отслеживаемых символов: {len(symbols)}")
		
		positions = db.get_all_positions()
		logger.info(f"  Открытых позиций: {len(positions)}")
		
		trades = db.get_trades_history(limit=1000)
		logger.info(f"  История сделок: {len(trades)} записей")
		
		signals = db.get_signals(limit=1000)
		logger.info(f"  Логи сигналов: {len(signals)} записей")
		
		backtests = db.get_backtests()
		logger.info(f"  Бэктестов: {len(backtests)}")
		
		logger.info("\n✅ База данных готова к использованию!")
		
	except Exception as e:
		logger.error(f"❌ Ошибка инициализации БД: {e}")
		raise


if __name__ == "__main__":
	initialize_database()
