"""
handlers.py — Обработчики команд, сообщений и нажатий inline-кнопок.

Каждая async-функция — это один обработчик, который вызывается
библиотекой python-telegram-bot при наступлении нужного события.
"""

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import ContextTypes

from config import ADMIN_ID
from database import save_message, get_dialog, update_status

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Вспомогательная функция
# ---------------------------------------------------------------------------

def _format_dialog_text(user_id: int, rows: list[tuple]) -> tuple[str, list]:
    """
    Форматирует историю диалога в текст и список медиа.

    Returns:
        (text, media_group) — текстовое представление и список InputMediaPhoto.
    """
    text = f"Диалог с пользователем ID {user_id}:\n\n"
    media_group = []

    for role, msg, photo in rows:
        prefix = "[Пользователь]" if role == "user" else "[Оператор]"
        if msg:
            text += f"{prefix}:\n{msg}\n\n"
        if photo:
            media_group.append(InputMediaPhoto(media=photo, caption=f"{prefix} (фото)"))

    return text, media_group


# ---------------------------------------------------------------------------
# Обработчики для пользователей
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ответ на команду /start — приветственное сообщение."""
    user = update.effective_user
    logger.info(f"/start от {user.full_name} (ID {user.id})")
    await update.message.reply_text(
        "Привет! Напишите свой вопрос, и оператор скоро ответит."
    )


async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Принимает текстовое сообщение или фото от пользователя,
    сохраняет в БД и пересылает администратору с кнопкой «Открыть диалог».
    """
    user = update.effective_user
    uid = user.id
    username = user.username or "без username"
    fullname = user.full_name or "без имени"
    text = update.message.text or ""
    photo = update.message.photo[-1].file_id if update.message.photo else None

    # Сохраняем сообщение в базу
    save_message(uid, username, fullname, "user", text, photo)

    # Отправляем уведомление администратору
    notification = f"[Пользователь @{username} | ID {uid}]:\n{text}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Открыть диалог", callback_data=f"dialog:{uid}")]
    ])
    await context.bot.send_message(ADMIN_ID, notification, reply_markup=keyboard)

    # Если есть фото — отправляем отдельно
    if photo:
        await context.bot.send_photo(ADMIN_ID, photo=photo)

    await update.message.reply_text("Ваше сообщение передано в поддержку.")


# ---------------------------------------------------------------------------
# Обработчики для администратора
# ---------------------------------------------------------------------------

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Принимает ответ администратора и пересылает его пользователю.

    Чтобы выбрать собеседника, нужно сначала открыть диалог кнопкой
    или командой /dialog <user_id>.

    Баг (исправлен): фильтр теперь включает и PHOTO, поэтому фото от админа
    не уходят в обработчик user_message.
    """
    if "reply_to" not in context.user_data:
        await update.message.reply_text(
            "Не выбран пользователь. Откройте диалог через кнопку или /dialog <user_id>."
        )
        return

    uid: int = context.user_data["reply_to"]
    text = update.message.text or ""
    photo = update.message.photo[-1].file_id if update.message.photo else None

    # Сохраняем ответ оператора в БД под user_id собеседника
    save_message(uid, "admin", "Оператор", "admin", text, photo)

    # Отправляем ответ пользователю
    if text:
        await context.bot.send_message(uid, f"[Оператор]:\n{text}")
    if photo:
        await context.bot.send_photo(uid, photo=photo)

    await update.message.reply_text("Ответ отправлен пользователю.")


async def admin_dialog_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /dialog <user_id> — открывает историю диалога с пользователем
    и устанавливает его как получателя следующих ответов администратора.
    """
    if not context.args:
        await update.message.reply_text("Используйте: /dialog <user_id>")
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Некорректный ID. Укажите числовой Telegram ID.")
        return

    # Запоминаем, кому отвечаем
    context.user_data["reply_to"] = uid

    rows = get_dialog(uid)
    if not rows:
        await update.message.reply_text("Диалог не найден.")
        return

    text, _ = _format_dialog_text(uid, rows)

    # Отправляем фотографии из диалога
    for role, msg, photo in rows:
        if photo:
            prefix = "[Пользователь]" if role == "user" else "[Оператор]"
            await update.message.reply_photo(photo=photo, caption=f"{prefix} (фото)")

    await update.message.reply_text(text[:4096])


# ---------------------------------------------------------------------------
# Обработчики inline-кнопок (CallbackQuery)
# ---------------------------------------------------------------------------

async def open_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback «dialog:<user_id>» — показывает историю диалога администратору
    и устанавливает выбранного пользователя как получателя ответов.
    """
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    if len(parts) < 2 or not parts[1].isdigit():
        await query.edit_message_text("Некорректные данные кнопки.")
        return

    uid = int(parts[1])
    context.user_data["reply_to"] = uid

    rows = get_dialog(uid)
    if not rows:
        await query.edit_message_text("Диалог пуст.")
        return

    text, media_group = _format_dialog_text(uid, rows)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Решено", callback_data=f"status:решено:{uid}"),
            InlineKeyboardButton("Назад", callback_data="cancel"),
        ]
    ])

    # Сначала редактируем текущее сообщение с кнопками
    await query.edit_message_text(text[:4096], reply_markup=keyboard)

    # Если в диалоге есть фото — отправляем их отдельными сообщениями
    for media in media_group:
        await query.message.chat.send_media_group([media])


async def change_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback «status:<новый_статус>:<user_id>» — меняет статус диалога
    и уведомляет пользователя о завершении.
    """
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    if len(parts) < 3:
        await query.edit_message_text("Некорректные данные кнопки.")
        return

    _, status, uid_str = parts
    uid = int(uid_str)

    update_status(uid, status)

    # Уведомляем пользователя, если диалог помечен как решённый
    if status == "решено":
        try:
            await context.bot.send_message(
                uid,
                "Ваш диалог с поддержкой завершён. Спасибо за обращение!",
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {uid}: {e}")

    await query.edit_message_text(f"Статус диалога с ID {uid} обновлён на '{status}'.")


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback «cancel» — возврат в меню (скрывает текущее сообщение)."""
    await update.callback_query.answer()
    await update.callback_query.message.edit_text("Выберите действие.")
