from typing import Dict, Any, List, Set
from logger import logger
from config import ENABLE_BTC_CORRELATION_CHECK, MAX_BTC_CORRELATED_POSITIONS

# Группы коррелированных активов
CORRELATION_GROUPS = {
	"BTC": ["BTCUSDT", "BTCUSD", "BTCBUSD"],
	"ETH": ["ETHUSDT", "ETHUSD", "ETHBUSD", "ETHBTC"],
	"BNB": ["BNBUSDT", "BNBUSD", "BNBBUSD"],
	"SOL": ["SOLUSDT", "SOLUSD", "SOLBUSD"],
	"XRP": ["XRPUSDT", "XRPUSD", "XRPBUSD"],
	"ADA": ["ADAUSDT", "ADAUSD", "ADABUSD"],
	# L1 блокчейны часто коррелируют
	"L1": ["AVAXUSDT", "ATOMUSDT", "DOTUSDT", "NEARUSDT", "APTUSDT"],
	# DeFi токены
	"DEFI": ["UNIUSDT", "AAVEUSDT", "LINKUSDT", "MKRUSDT"],
	# Мемы
	"MEME": ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT"]
}

# Символы с высокой корреляцией с BTC (включая альткоины)
# ВНИМАНИЕ: В крипторынке ВСЕ альткоины коррелируют с BTC (0.7-0.9)
# Слишком строгие ограничения блокируют 90% сделок
# Рекомендуется отключить BTC-корреляцию или увеличить лимит
HIGH_BTC_CORRELATION_GROUPS = ["ETH", "BNB", "SOL", "XRP", "ADA", "L1", "DEFI"]


def get_symbol_group(symbol: str) -> str:
	"""Возвращает группу корреляции для символа"""
	for group_name, symbols in CORRELATION_GROUPS.items():
		if symbol in symbols:
			return group_name
	return None


def get_btc_correlation_symbols() -> Set[str]:
	"""Возвращает все символы с высокой корреляцией с BTC"""
	btc_correlation_symbols = set()
	for group in HIGH_BTC_CORRELATION_GROUPS:
		if group in CORRELATION_GROUPS:
			btc_correlation_symbols.update(CORRELATION_GROUPS[group])
	return btc_correlation_symbols


def count_btc_correlated_positions(existing_positions: Dict[str, Any]) -> int:
	"""Подсчитывает количество позиций с высокой корреляцией с BTC"""
	btc_correlation_symbols = get_btc_correlation_symbols()
	count = 0
	for pos_symbol in existing_positions.keys():
		if pos_symbol in btc_correlation_symbols:
			count += 1
	return count


def check_correlation_risk(new_symbol: str, existing_positions: Dict[str, Any]) -> bool:
	"""
	Проверяет риск корреляции.
	Возвращает True если можно открывать позицию, False если риск высокий.
	
	ВНИМАНИЕ: BTC-корреляция может блокировать 90% сделок в крипторынке.
	Рекомендуется отключить ENABLE_BTC_CORRELATION_CHECK или увеличить MAX_BTC_CORRELATED_POSITIONS.
	"""
	if not existing_positions:
		return True
	
	# Получаем группу нового символа
	new_group = get_symbol_group(new_symbol)
	
	# Если символ не в известных группах, разрешаем (неизвестная корреляция)
	if new_group is None:
		logger.info(f"[CORRELATION] ✅ {new_symbol}: неизвестная корреляция, разрешаем")
		return True
	
	# Проверка BTC-корреляции (может быть слишком строгой для крипторынка)
	if ENABLE_BTC_CORRELATION_CHECK:
		btc_symbols = CORRELATION_GROUPS["BTC"]
		has_btc_position = any(pos_symbol in btc_symbols for pos_symbol in existing_positions.keys())
		
		# Если есть позиция в BTC и пытаемся открыть альткоин с высокой корреляцией
		if has_btc_position and new_group in HIGH_BTC_CORRELATION_GROUPS:
			logger.warning(f"[CORRELATION] ❌ {new_symbol}: высокая корреляция с BTC (уже есть позиция в BTC)")
			logger.warning(f"[CORRELATION] 💡 Совет: отключите ENABLE_BTC_CORRELATION_CHECK для более гибкой торговли")
			return False
		
		# Проверяем лимит BTC-коррелированных позиций
		if new_group in HIGH_BTC_CORRELATION_GROUPS:
			btc_correlated_count = count_btc_correlated_positions(existing_positions)
			if btc_correlated_count >= MAX_BTC_CORRELATED_POSITIONS:
				logger.warning(f"[CORRELATION] ❌ {new_symbol}: превышен лимит BTC-коррелированных позиций ({btc_correlated_count}/{MAX_BTC_CORRELATED_POSITIONS})")
				logger.warning(f"[CORRELATION] 💡 Совет: увеличьте MAX_BTC_CORRELATED_POSITIONS для большего разнообразия")
				return False
	
	# Проверяем конфликты внутри групп корреляции (это разумно)
	for pos_symbol in existing_positions.keys():
		pos_group = get_symbol_group(pos_symbol)
		if pos_group == new_group:
			logger.warning(f"[CORRELATION] ❌ {new_symbol}: конфликт с {pos_symbol} (группа '{new_group}')")
			return False
	
	logger.info(f"[CORRELATION] ✅ {new_symbol}: корреляционная проверка пройдена")
	return True
