import os
import logging
import datetime

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
def log_signal(symbol: str, interval: str, signal: str, reasons: list, price: float):
    reasons_text = "; ".join(reasons)
    msg = f"{symbol} ({interval}) | {signal} | Цена: {price} | Причины: {reasons_text}"
    signal_logger.info(msg)
