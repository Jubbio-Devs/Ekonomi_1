import logging
import sys

from ekonomi import config, create_bot

if __name__ == "__main__":
    if not config.TOKEN:
        sys.exit("BOT_TOKEN ortam değişkeni ayarlanmamış.")
    create_bot().client.run(config.TOKEN, log_level=logging.INFO)
