# filepath: support_bot/tech_bot.py
import sqlite3
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# === НАСТРОЙКА ЛОГГИРОВАНИЯ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "YOUR_BOT_TOKEN"  # Замените на свой токен
ADMIN_ID = YOUR_ADMIN_ID  # Замените на свой ID

# === ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ===

def init_db():
    conn = sqlite3.connect("support.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dialog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            fullname TEXT,
            role TEXT,
            message TEXT,
            photo TEXT,
            status TEXT DEFAULT 'ожидание',
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована.")

def save_dialog(user_id, username, fullname, role, message, photo=None):
    conn = sqlite3.connect("support.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO dialog (user_id, username, fullname, role, message, photo, status)
        VALUES (?, ?, ?, ?, ?, ?, 'ожидание')
    """, (user_id, username, fullname, role, message, photo))
    conn.commit()
    conn.close()

def get_dialog(user_id):
    conn = sqlite3.connect("support.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, message, photo FROM dialog
        WHERE user_id = ?
        ORDER BY time ASC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_status(user_id, new_status):
    conn = sqlite3.connect("support.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE dialog SET status = ? WHERE user_id = ?", (new_status, user_id))
    conn.commit()
    conn.close()

# === ОБРАБОТЧИКИ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"/start от {user.full_name} ({user.id})")
    await update.message.reply_text("Привет! Напишите свой вопрос, и оператор скоро ответит.")

async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    username = user.username or "без username"
    fullname = user.full_name or "без имени"
    text = update.message.text or ""
    photo = update.message.photo[-1].file_id if update.message.photo else None

    save_dialog(uid, username, fullname, "user", text, photo)

    msg = f"[Пользователь @{username} | ID {uid}]:\n{text}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Открыть диалог", callback_data=f"dialog:{uid}")]
    ])
    await context.bot.send_message(ADMIN_ID, msg, reply_markup=keyboard)
    if photo:
        await context.bot.send_photo(ADMIN_ID, photo=photo)

    await update.message.reply_text("Ваше сообщение передано в поддержку.")

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if "reply_to" not in context.user_data:
        return

    uid = context.user_data["reply_to"]
    text = update.message.text or ""
    photo = update.message.photo[-1].file_id if update.message.photo else None

    save_dialog(uid, "admin", "Оператор", "admin", text, photo)

    await context.bot.send_message(uid, f"[Оператор]:\n{text}")
    if photo:
        await context.bot.send_photo(uid, photo)

    await update.message.reply_text("Ответ отправлен оператором.")

async def open_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")
    if len(data) < 2:
        return

    uid = int(data[1])
    context.user_data["reply_to"] = uid
    dialog = get_dialog(uid)

    if not dialog:
        await query.edit_message_text("Диалог пуст.")
        return

    text = f"💬 Диалог с пользователем ID {uid}:\n\n"
    media_group = []

    for role, msg, photo in dialog:
        prefix = "[Пользователь]" if role == "user" else "[Оператор]"
        if msg:
            text += f"{prefix}:\n{msg}\n\n"
        if photo:
            media_group.append(InputMediaPhoto(media=photo, caption=f"{prefix} (фото)"))

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Решено", callback_data=f"status:решено:{uid}"),
            InlineKeyboardButton("Назад", callback_data="cancel")
        ]
    ])

    if media_group:
        await query.message.edit_text(text[:4096], reply_markup=keyboard)
        for media in media_group:
            await query.message.chat.send_media_group([media])
    else:
        await query.edit_message_text(text[:4096], reply_markup=keyboard)

async def change_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, status, uid = query.data.split(":")
    uid = int(uid)

    update_status(uid, status)

    # Оповещение пользователя
    if status == "решено":
        try:
            await context.bot.send_message(uid, "✅ Ваш диалог с поддержкой был завершён. Спасибо за обращение!")
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {uid}: {e}")

    await query.edit_message_text(f"Статус диалога с ID {uid} обновлён на '{status}' ✅")

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.edit_text("Возврат в меню.")

# === КОМАНДЫ ДЛЯ АДМИНА ===

async def admin_dialog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Используйте: /dialog user_id")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Некорректный ID.")
        return

    context.user_data["reply_to"] = uid
    dialog = get_dialog(uid)
    if not dialog:
        await update.message.reply_text("Диалог не найден.")
        return

    text = f"💬 Диалог с пользователем ID {uid}:\n\n"
    for role, msg, photo in dialog:
        prefix = "[Пользователь]" if role == "user" else "[Оператор]"
        if msg:
            text += f"{prefix}:\n{msg}\n\n"
        if photo:
            await update.message.reply_photo(photo=photo, caption=f"{prefix} (фото)")

    await update.message.reply_text(text[:4096])

# === ЗАПУСК ===

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dialog", admin_dialog_command))

    app.add_handler(CallbackQueryHandler(open_dialog, pattern="^dialog:"))
    app.add_handler(CallbackQueryHandler(change_status, pattern="^status:"))
    app.add_handler(CallbackQueryHandler(cancel_callback, pattern="^cancel"))

    app.add_handler(MessageHandler(filters.TEXT & filters.User(ADMIN_ID), admin_reply))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, user_message))

    logger.info("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()