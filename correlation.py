from typing import Dict, Any
from logger import logger

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
