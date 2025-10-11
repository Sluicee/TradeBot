import os
import dotenv

dotenv.load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "BTCUSDT")
DEFAULT_INTERVAL = os.getenv("DEFAULT_INTERVAL", "1m")
