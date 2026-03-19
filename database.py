"""
database.py — Работа с базой данных SQLite.

Хранит историю диалогов: сообщения пользователей и ответы оператора.
sqlite3 — встроенный модуль Python, устанавливать отдельно не нужно.
"""

import sqlite3
import logging
from config import DB_NAME

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Создаёт таблицу dialog, если она ещё не существует."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dialog (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER   NOT NULL,
                username TEXT,
                fullname TEXT,
                role     TEXT      NOT NULL,        -- 'user' или 'admin'
                message  TEXT,
                photo    TEXT,                      -- file_id фотографии
                status   TEXT      DEFAULT 'ожидание',
                time     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    logger.info("База данных инициализирована.")


def save_message(
    user_id: int,
    username: str,
    fullname: str,
    role: str,
    message: str,
    photo: str | None = None,
) -> None:
    """
    Сохраняет одно сообщение диалога в БД.

    Args:
        user_id:  Telegram ID пользователя (для сообщений админа — ID собеседника).
        username: @username пользователя.
        fullname: Полное имя пользователя.
        role:     'user' — от пользователя, 'admin' — от оператора.
        message:  Текст сообщения (может быть пустой строкой, если только фото).
        photo:    file_id фотографии или None.
    """
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(
            """
            INSERT INTO dialog (user_id, username, fullname, role, message, photo, status)
            VALUES (?, ?, ?, ?, ?, ?, 'ожидание')
            """,
            (user_id, username, fullname, role, message, photo),
        )
        conn.commit()


def get_dialog(user_id: int) -> list[tuple]:
    """
    Возвращает все сообщения диалога с пользователем, отсортированные по времени.

    Returns:
        Список кортежей (role, message, photo).
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.execute(
            """
            SELECT role, message, photo
            FROM dialog
            WHERE user_id = ?
            ORDER BY time ASC
            """,
            (user_id,),
        )
        return cursor.fetchall()


def update_status(user_id: int, new_status: str) -> None:
    """
    Обновляет статус всех записей диалога с пользователем.

    Args:
        user_id:    Telegram ID пользователя.
        new_status: Новый статус, например 'решено'.
    """
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(
            "UPDATE dialog SET status = ? WHERE user_id = ?",
            (new_status, user_id),
        )
        conn.commit()
