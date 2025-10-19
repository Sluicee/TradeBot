from typing import Dict, Any
from logger import logger
from config import ENABLE_BTC_CORRELATION_CHECK, MAX_BTC_CORRELATED_POSITIONS

# Группы коррелированных активов (упрощенно)
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


def check_correlation_risk(new_symbol: str, existing_positions: Dict[str, Any]) -> bool:
	"""
	Проверяет риск корреляции.
	Возвращает True если можно открывать позицию, False если риск высокий.
	"""
	if not existing_positions:
		return True
	
	# НОВОЕ: Проверка BTC-корреляции для всех альткоинов
	if ENABLE_BTC_CORRELATION_CHECK:
		btc_symbols = ["BTCUSDT", "BTCUSD", "BTCBUSD"]
		has_btc_position = any(pos_symbol in btc_symbols for pos_symbol in existing_positions.keys())
		
		# Если есть позиция в BTC и пытаемся открыть альткоин - проверяем корреляцию
		if has_btc_position and new_symbol not in btc_symbols:
			# Проверяем, не является ли новый символ сильно коррелированным с BTC
			high_btc_correlation_symbols = [
				# Мажорные альткоины с высокой корреляцией с BTC
				"ETHUSDT", "ETHUSD", "ETHBUSD", "ETHBTC",
				"BNBUSDT", "BNBUSD", "BNBBUSD",
				"SOLUSDT", "SOLUSD", "SOLBUSD",
				"XRPUSDT", "XRPUSD", "XRPBUSD",
				"ADAUSDT", "ADAUSD", "ADABUSD",
				# L1 блокчейны
				"AVAXUSDT", "ATOMUSDT", "DOTUSDT", "NEARUSDT", "APTUSDT",
				# DeFi токены
				"UNIUSDT", "AAVEUSDT", "LINKUSDT", "MKRUSDT"
			]
			
			if new_symbol in high_btc_correlation_symbols:
				logger.warning(f"[CORRELATION] ❌ {new_symbol}: высокая корреляция с BTC (уже есть позиция в BTC)")
				return False
	
	# Находим группу нового символа
	new_group = None
	for group_name, symbols in CORRELATION_GROUPS.items():
		if new_symbol in symbols:
			new_group = group_name
			break
	
	# Если символ не в известных группах, разрешаем (неизвестная корреляция)
	if new_group is None:
		return True
	
	# Проверяем открытые позиции
	for pos_symbol in existing_positions.keys():
		for group_name, symbols in CORRELATION_GROUPS.items():
			if pos_symbol in symbols:
				# Нашли группу существующей позиции
				if group_name == new_group:
					# Уже есть позиция из той же группы - запрещаем
					logger.warning(f"[CORRELATION] ❌ {new_symbol}: конфликт с {pos_symbol} (группа '{new_group}')")
					return False
	return True
