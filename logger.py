import os
import time
import logging
from typing import Optional

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Компактные форматы логов
COMPACT_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
VERBOSE_FORMAT = "%(asctime)s — %(name)s — %(levelname)s — %(message)s"

def get_log_filename():
    return os.path.join(LOG_DIR, time.strftime("log_%Y%m%d_%H%M%S.txt"))

class TimedFileHandler(logging.FileHandler):
    def __init__(self, interval=8*60*60, *args, **kwargs):
        self.interval = interval
        self.start_time = time.time()
        self.baseFilename = get_log_filename()
        super().__init__(self.baseFilename, encoding="utf-8", *args, **kwargs)

    def emit(self, record):
        if time.time() - self.start_time > self.interval:
            self.start_time = time.time()
            self.baseFilename = get_log_filename()
            self.stream.close()
            self.stream = self._open()
        super().emit(record)

class CompactFormatter(logging.Formatter):
    """Компактный форматтер для сокращения логов"""
    
    def format(self, record):
        # Сокращаем длинные сообщения
        message = record.getMessage()
        
        # Сокращаем диагностические сообщения
        if "[SIGNAL_DIAG]" in message:
            if "📊" in message and "@" in message:
                # Извлекаем только основную информацию
                parts = message.split("|")
                if len(parts) >= 2:
                    symbol_part = parts[0].split("📊")[-1].strip()
                    signal_part = parts[1].strip() if len(parts) > 1 else ""
                    message = f"SIGNAL: {symbol_part} | {signal_part}"
            elif "Голоса:" in message:
                # Сокращаем информацию о голосах
                message = message.replace("Голоса: ", "Votes: ").replace("Bullish=", "B=").replace("Bearish=", "S=").replace("Delta=", "D=")
            elif "Топ-3 причины:" in message:
                message = "REASONS: " + message.split("Топ-3 причины:")[-1].strip()[:50] + "..."
            elif "=" * 80 in message:
                message = "---"
        
        # Сокращаем другие длинные сообщения
        if len(message) > 100:
            message = message[:97] + "..."
            
        record.msg = message
        return super().format(record)

# Настройка логгера
logger = logging.getLogger("crypto_signal_bot")

# Удаляем существующие хендлеры
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Инициализация с настройками из config
try:
    import config
    # Проверяем продакшен режим
    if getattr(config, 'PRODUCTION_LOGGING', False):
        logger.setLevel(getattr(logging, config.PRODUCTION_LOG_LEVEL.upper(), logging.WARNING))
        use_compact = True
    else:
        logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
        use_compact = getattr(config, 'COMPACT_LOGGING', True)
except ImportError:
    logger.setLevel(logging.INFO)
    use_compact = True

# Компактный или подробный консольный вывод
console_handler = logging.StreamHandler()
if use_compact:
    console_handler.setFormatter(CompactFormatter(COMPACT_FORMAT))
else:
    console_handler.setFormatter(logging.Formatter(VERBOSE_FORMAT))
logger.addHandler(console_handler)

# Подробный файловый вывод (всегда подробный для файлов)
file_handler = TimedFileHandler()
file_handler.setFormatter(logging.Formatter(VERBOSE_FORMAT))
logger.addHandler(file_handler)

# Функция для переключения режимов логирования
def set_log_level(level: str, compact: bool = True):
    """Устанавливает уровень логирования и режим"""
    levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR
    }
    
    logger.setLevel(levels.get(level.upper(), logging.INFO))
    
    if compact:
        # Компактный режим для консоли
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.setFormatter(CompactFormatter(COMPACT_FORMAT))
    else:
        # Подробный режим
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.setFormatter(logging.Formatter(VERBOSE_FORMAT))

# Функция для логирования только важных событий
def log_important(message: str, level: str = "INFO"):
    """Логирует только важные события в компактном формате"""
    getattr(logger, level.lower())(f"🔔 {message}")

# Функция для логирования сигналов в компактном формате
def log_signal_compact(symbol: str, signal: str, price: float, votes: int = None):
    """Компактное логирование сигналов"""
    votes_str = f" (v{votes})" if votes else ""
    logger.info(f"📊 {symbol}: {signal} @ {price:.4f}{votes_str}")

# Функция для логирования ошибок
def log_error(message: str, error: Exception = None):
    """Логирует ошибки"""
    if error:
        logger.error(f"❌ {message}: {error}")
    else:
        logger.error(f"❌ {message}")

# Функция для переключения в продакшен режим
def enable_production_mode():
    """Включает продакшен режим - только критичные события"""
    try:
        import config
        config.PRODUCTION_LOGGING = True
        logger.setLevel(logging.WARNING)
        logger.info("🔧 Продакшен режим включен - только WARNING и ERROR")
    except ImportError:
        logger.warning("Не удалось включить продакшен режим")

# Функция для переключения в режим разработки
def enable_development_mode():
    """Включает режим разработки - подробные логи"""
    try:
        import config
        config.PRODUCTION_LOGGING = False
        config.COMPACT_LOGGING = False
        logger.setLevel(logging.DEBUG)
        logger.info("🔧 Режим разработки включен - подробные логи")
    except ImportError:
        logger.warning("Не удалось включить режим разработки")

# Функция для компактного режима
def enable_compact_mode():
    """Включает компактный режим - сжатые логи"""
    try:
        import config
        config.COMPACT_LOGGING = True
        config.SIGNAL_DIAG_COMPACT = True
        logger.info("🔧 Компактный режим включен")
    except ImportError:
        logger.warning("Не удалось включить компактный режим")
