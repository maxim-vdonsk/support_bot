"""
config.py — Настройки бота.

Токен и ID администратора читаются из файла .env,
чтобы не хранить секреты прямо в коде.
"""

import os
import logging
from dotenv import load_dotenv

# Загружаем переменные из файла .env (если он существует)
load_dotenv()

# Токен бота — получить у @BotFather в Telegram
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# Telegram ID администратора — узнать через @userinfobot
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))

# Имя файла базы данных SQLite
DB_NAME: str = "support.db"

# Настройка логгирования: уровень INFO, формат с временем и уровнем
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# Проверка при запуске — если переменные не заданы, бот не запустится корректно
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не задан! Добавьте его в файл .env")

if not ADMIN_ID:
    logger.error("ADMIN_ID не задан! Добавьте его в файл .env")
