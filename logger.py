import os
import time
import logging

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

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

formatter = logging.Formatter("%(asctime)s — %(name)s — %(levelname)s — %(message)s")

logger = logging.getLogger("crypto_signal_bot")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = TimedFileHandler()
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
