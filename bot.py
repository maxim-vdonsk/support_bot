"""
bot.py — Точка входа. Собирает приложение и запускает бота.

Запуск:
    python bot.py
"""

import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import BOT_TOKEN, ADMIN_ID
from database import init_db
from handlers import (
    start,
    user_message,
    admin_reply,
    admin_dialog_command,
    open_dialog,
    change_status,
    cancel_callback,
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Инициализирует БД, регистрирует все обработчики и запускает бота."""

    # Создаём таблицы в SQLite (если их ещё нет)
    init_db()

    # Строим приложение с токеном бота
    app = Application.builder().token(BOT_TOKEN).build()

    # --- Команды ---
    app.add_handler(CommandHandler("start", start))
    # /dialog доступна только для администратора (проверка внутри обработчика)
    app.add_handler(CommandHandler("dialog", admin_dialog_command))

    # --- Inline-кнопки ---
    app.add_handler(CallbackQueryHandler(open_dialog,    pattern=r"^dialog:\d+$"))
    app.add_handler(CallbackQueryHandler(change_status,  pattern=r"^status:.+:\d+$"))
    app.add_handler(CallbackQueryHandler(cancel_callback, pattern=r"^cancel$"))

    # --- Сообщения ---
    # ВАЖНО: обработчик администратора должен стоять ПЕРЕД общим обработчиком,
    # иначе сообщения админа попадут в user_message.
    # Исправленный баг: фильтр включает PHOTO, а не только TEXT,
    # поэтому фото от администратора тоже попадают в admin_reply.
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO) & ~filters.COMMAND & filters.User(ADMIN_ID),
            admin_reply,
        )
    )
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
            user_message,
        )
    )

    logger.info("Бот запущен. Нажмите Ctrl+C для остановки.")
    app.run_polling()


if __name__ == "__main__":
    main()
