import os
import logging
import datetime
from typing import Optional, Dict, Any
from database import db
from logger import logger as main_logger

# ----------------------------
# Логгер сигналов
# ----------------------------
SIGNALS_DIR = "signals"
os.makedirs(SIGNALS_DIR, exist_ok=True)

signal_logger = logging.getLogger("signals_logger")
signal_logger.setLevel(logging.INFO)

# Новый файл сигналов на каждый запуск бота
now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
signal_file = os.path.join(SIGNALS_DIR, f"signals_{now_str}.log")

signal_file_handler = logging.FileHandler(signal_file, encoding="utf-8")
signal_file_handler.setFormatter(logging.Formatter("%(asctime)s — %(message)s"))
signal_logger.addHandler(signal_file_handler)

# ----------------------------
# Функция для логирования сигналов
# ----------------------------
def log_signal(
	symbol: str,
	interval: str,
	signal: str,
	reasons: list,
	price: float,
	signal_strength: Optional[int] = None,
	market_regime: Optional[str] = None,
	adx: Optional[float] = None,
	rsi: Optional[float] = None,
	atr: Optional[float] = None,
	extra_data: Optional[Dict[str, Any]] = None
):
	"""
	Логирует сигнал в файл и БД
	"""
	# Логируем в файл
	reasons_text = "; ".join(reasons)
	msg = f"{symbol} ({interval}) | {signal} | Цена: {price} | Причины: {reasons_text}"
	signal_logger.info(msg)
	
	# Сохраняем в БД
	try:
		db.add_signal(
			symbol=symbol,
			interval=interval,
			signal=signal,
			price=price,
			reasons=reasons,
			signal_strength=signal_strength,
			market_regime=market_regime,
			adx=adx,
			rsi=rsi,
			atr=atr,
			extra_data=extra_data
		)
	except Exception as e:
		main_logger.error(f"Ошибка сохранения сигнала в БД: {e}")
