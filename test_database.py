"""
Простые тесты для проверки работы БД
"""
import os
import sys
from datetime import datetime
from database import db
from logger import logger


def test_paper_trading_state():
	"""Тест сохранения/загрузки состояния paper trading"""
	logger.info("Тест: Paper Trading State")
	
	# Сохраняем тестовые данные
	db.save_paper_state(
		initial_balance=100.0,
		balance=95.5,
		is_running=True,
		start_time=datetime.now(),
		stats={
			"total_trades": 5,
			"winning_trades": 3,
			"losing_trades": 2,
			"total_commission": 0.5,
			"stop_loss_triggers": 1,
			"take_profit_triggers": 2,
			"trailing_stop_triggers": 0
		}
	)
	
	# Загружаем
	state = db.get_paper_state()
	assert state is not None, "Состояние не загружено"
	assert state.balance == 95.5, f"Неверный баланс: {state.balance}"
	assert state.total_trades == 5, f"Неверное количество сделок: {state.total_trades}"
	
	logger.info("✅ Paper Trading State: OK")


def test_tracked_symbols():
	"""Тест отслеживаемых символов"""
	logger.info("Тест: Tracked Symbols")
	
	# Добавляем символы
	test_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
	for symbol in test_symbols:
		db.add_tracked_symbol(symbol)
	
	# Загружаем
	symbols = db.get_tracked_symbols()
	assert len(symbols) >= len(test_symbols), "Символы не сохранены"
	for symbol in test_symbols:
		assert symbol in symbols, f"Символ {symbol} не найден"
	
	# Удаляем
	db.remove_tracked_symbol("BNBUSDT")
	symbols = db.get_tracked_symbols()
	assert "BNBUSDT" not in symbols, "Символ не удалён"
	
	logger.info("✅ Tracked Symbols: OK")


def test_positions():
	"""Тест позиций"""
	logger.info("Тест: Positions")
	
	# Создаём позицию
	position_data = {
		"symbol": "TEST_USDT",
		"entry_price": 100.0,
		"amount": 1.0,
		"entry_time": datetime.now(),
		"signal_strength": 8,
		"invest_amount": 100.0,
		"entry_commission": 0.18,
		"atr": 0.5,
		"stop_loss_price": 95.0,
		"stop_loss_percent": 0.05,
		"take_profit_price": 110.0,
		"partial_closed": False,
		"max_price": 100.0,
		"partial_close_profit": 0.0,
		"original_amount": 1.0,
		"averaging_count": 0,
		"average_entry_price": 100.0,
		"pyramid_mode": False,
		"total_invested": 100.0
	}
	
	# Сохраняем
	db.save_position(position_data)
	
	# Загружаем
	position = db.get_position("TEST_USDT")
	assert position is not None, "Позиция не сохранена"
	assert position.entry_price == 100.0, f"Неверная цена входа: {position.entry_price}"
	assert position.symbol == "TEST_USDT", f"Неверный символ: {position.symbol}"
	
	# Удаляем
	db.delete_position("TEST_USDT")
	position = db.get_position("TEST_USDT")
	assert position is None, "Позиция не удалена"
	
	logger.info("✅ Positions: OK")


def test_trades_history():
	"""Тест истории сделок"""
	logger.info("Тест: Trades History")
	
	# Добавляем сделку
	trade_data = {
		"type": "BUY",
		"symbol": "TEST_USDT",
		"price": 100.0,
		"amount": 1.0,
		"time": datetime.now(),
		"invest_amount": 100.0,
		"commission": 0.18,
		"signal_strength": 8,
		"balance_after": 900.0
	}
	
	db.add_trade(trade_data)
	
	# Загружаем
	trades = db.get_trades_history(symbol="TEST_USDT", limit=10)
	assert len(trades) > 0, "Сделки не сохранены"
	assert trades[0]["symbol"] == "TEST_USDT", "Неверный символ"
	
	logger.info("✅ Trades History: OK")


def test_signals():
	"""Тест логов сигналов"""
	logger.info("Тест: Signals")
	
	# Добавляем сигнал
	db.add_signal(
		symbol="TEST_USDT",
		interval="1h",
		signal="BUY",
		price=100.0,
		reasons=["RSI oversold", "MACD bullish"],
		signal_strength=8,
		market_regime="TRENDING",
		adx=35.0,
		rsi=28.0,
		atr=0.5
	)
	
	# Загружаем
	signals = db.get_signals(symbol="TEST_USDT", limit=10)
	assert len(signals) > 0, "Сигналы не сохранены"
	assert signals[0]["symbol"] == "TEST_USDT", "Неверный символ"
	assert signals[0]["signal"] == "BUY", "Неверный тип сигнала"
	
	logger.info("✅ Signals: OK")


def test_bot_settings():
	"""Тест настроек бота"""
	logger.info("Тест: Bot Settings")
	
	# Сохраняем настройки
	db.save_bot_settings(
		chat_id=123456789,
		poll_interval=60,
		volatility_window=10,
		volatility_threshold=0.05
	)
	
	# Загружаем
	settings = db.get_bot_settings()
	assert settings is not None, "Настройки не сохранены"
	assert settings.chat_id == 123456789, f"Неверный chat_id: {settings.chat_id}"
	assert settings.poll_interval == 60, f"Неверный интервал: {settings.poll_interval}"
	
	logger.info("✅ Bot Settings: OK")


def test_backtests():
	"""Тест бэктестов"""
	logger.info("Тест: Backtests")
	
	# Добавляем бэктест
	backtest_data = {
		"symbol": "TEST_USDT",
		"interval": "1h",
		"start_date": datetime(2025, 1, 1),
		"end_date": datetime(2025, 10, 1),
		"initial_balance": 100.0,
		"final_balance": 120.0,
		"total_return": 20.0,
		"total_return_percent": 20.0,
		"total_trades": 50,
		"winning_trades": 30,
		"losing_trades": 20,
		"win_rate": 60.0,
		"max_drawdown": -5.0,
		"sharpe_ratio": 1.5,
		"profit_factor": 1.8,
		"avg_trade_duration": "2ч 30м",
		"stats": {"test": "data"},
		"config": {"kelly": True},
		"trades": [
			{
				"type": "BUY",
				"symbol": "TEST_USDT",
				"price": 100.0,
				"amount": 1.0,
				"time": datetime.now(),
				"profit": 0.0,
				"profit_percent": 0.0,
				"balance_after": 100.0
			}
		]
	}
	
	backtest_id = db.add_backtest(backtest_data)
	assert backtest_id > 0, "Бэктест не сохранён"
	
	# Загружаем
	backtest = db.get_backtest(backtest_id)
	assert backtest is not None, "Бэктест не загружен"
	assert backtest["symbol"] == "TEST_USDT", "Неверный символ"
	assert len(backtest["trades"]) > 0, "Сделки не сохранены"
	
	# Список бэктестов
	backtests = db.get_backtests(symbol="TEST_USDT")
	assert len(backtests) > 0, "Список бэктестов пуст"
	
	logger.info("✅ Backtests: OK")


def run_all_tests():
	"""Запуск всех тестов"""
	logger.info("=== ТЕСТИРОВАНИЕ БД ===\n")
	
	# Создаём тестовую БД
	test_db_file = "test_tradebot.db"
	if os.path.exists(test_db_file):
		os.remove(test_db_file)
	
	# Переключаем на тестовую БД
	import database
	database.db = database.DatabaseManager(f"sqlite:///{test_db_file}")
	database.db.create_tables()
	
	# Глобально обновляем db
	globals()['db'] = database.db
	
	tests = [
		test_paper_trading_state,
		test_tracked_symbols,
		test_positions,
		test_trades_history,
		test_signals,
		test_bot_settings,
		test_backtests
	]
	
	failed = []
	
	for test_func in tests:
		try:
			test_func()
		except Exception as e:
			logger.error(f"❌ {test_func.__name__}: {e}")
			failed.append((test_func.__name__, e))
	
	# Удаляем тестовую БД
	if os.path.exists(test_db_file):
		os.remove(test_db_file)
	
	logger.info("\n" + "="*50)
	if failed:
		logger.error(f"❌ Провалено тестов: {len(failed)}/{len(tests)}")
		for name, error in failed:
			logger.error(f"  - {name}: {error}")
		return False
	else:
		logger.info(f"✅ Все тесты пройдены: {len(tests)}/{len(tests)}")
		return True


if __name__ == "__main__":
	success = run_all_tests()
	sys.exit(0 if success else 1)

