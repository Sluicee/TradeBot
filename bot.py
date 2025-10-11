from telegram_bot import TelegramBot
from logger import logger
from config import TELEGRAM_TOKEN, DEFAULT_SYMBOL, DEFAULT_INTERVAL

if __name__ == "__main__":
    try:
        bot = TelegramBot(token=TELEGRAM_TOKEN, default_symbol=DEFAULT_SYMBOL, default_interval=DEFAULT_INTERVAL)
        bot.run()
    except Exception as exc:
        logger.exception("Не удалось запустить бота: %s", exc)
        raise
