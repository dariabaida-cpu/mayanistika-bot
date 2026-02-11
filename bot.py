import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# =============================================
# НАСТРОЙКИ — заполни свои данные здесь
# =============================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_ТОКЕН_БОТА")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "ВАШ_TELEGRAM_ID")  # получи у @userinfobot
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "ID_ВАШЕЙ_ТАБЛИЦЫ")

# Данные мастер-класса
MASTERCLASS_NAME = "Мезоамериканская Масленица"
MASTERCLASS_DATE = "21 февраля в 12:00"
PAYMENT_LINK = "https://www.tinkoff.ru/rm/r_bGudilgQdb.LnPDXEEDwC/gFnDK18010"
QR_CODE_IMAGE = "qr_code.jpg"       # положи файл рядом с bot.py
WELCOME_IMAGE = "maya_welcome.jpg"  # приветственная картинка
LOCATION_IMAGE = "location.jpg"     # фото места

PAYMENT_INFO = f"""
💳 Оплатите участие в мастер-классе по ссылке или QR-коду:

{PAYMENT_LINK}

После оплаты нажмите кнопку «Продолжить» ⬇️
"""

LOCATION_INFO = """
📍 Как добраться:

Электродный проезд 16

🚇 Метро Шоссе Энтузиастов (выход 4)

🚪 Вход №2 (со стороны дороги-4, козырек слева)
Код: 2580#

⬆️ Второй этаж, налево и до конца
"""

# =============================================
# Состояния диалога
# =============================================
NAME, PHONE, WAITING_PAYMENT = range(3)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================
# Google Sheets
# =============================================
def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1
    return sheet

def save_to_sheets(name: str, phone: str, telegram_id: int, username: str):
    try:
        sheet = get_sheet()
        # Заголовки если таблица пустая
        if sheet.row_count == 0 or sheet.cell(1, 1).value is None:
            sheet.append_row(["Дата", "ФИО", "Телефон", "Telegram ID", "Username", "Мастер-класс"])
        sheet.append_row([
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            name,
            phone,
            telegram_id,
            f"@{username}" if username else "—",
            MASTERCLASS_NAME
        ])
        logger.info(f"Saved to sheets: {name}, {phone}")
    except Exception as e:
        logger.error(f"Sheets error: {e}")


# =============================================
# Хендлеры
# =============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — всегда запускает бота заново"""
    context.user_data.clear()  # сброс предыдущего состояния

    keyboard = [[InlineKeyboardButton("🎟 Купить билет", callback_data="buy_ticket")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        with open(WELCOME_IMAGE, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption="Привет! Это telegram-бот канала *Майянистика без мистики*.",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    except FileNotFoundError:
        await update.message.reply_text(
            "👋 Привет! Это telegram-бот канала *Майянистика без мистики*.",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    return ConversationHandler.END


async def buy_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Нажата кнопка Купить билет"""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📝 Укажите ваши ФИО:")
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем ФИО"""
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("📱 Укажите ваш номер телефона:")
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем телефон, показываем реквизиты"""
    context.user_data["phone"] = update.message.text.strip()

    keyboard = [[InlineKeyboardButton("✅ Продолжить", callback_data="paid")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(PAYMENT_INFO, reply_markup=reply_markup)

    # Отправляем QR-код
    try:
        with open(QR_CODE_IMAGE, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption="Секачева Дарья Сергеевна\nНомер договора 5053221965"
            )
    except FileNotFoundError:
        pass  # QR-код не обязателен, пропускаем

    return WAITING_PAYMENT


async def payment_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Нажата кнопка Продолжить после оплаты"""
    query = update.callback_query
    await query.answer()

    name = context.user_data.get("name", "Орлол")
    phone = context.user_data.get("phone", "")
    user = query.from_user

    # Сохраняем в Google Sheets
    save_to_sheets(name, phone, user.id, user.username)

    # Уведомление администратору
    admin_msg = (
        f"🎟 *Новая покупка билета!*\n\n"
        f"👤 ФИО: {name}\n"
        f"📱 Телефон: {phone}\n"
        f"🆔 Telegram: @{user.username or '—'} (ID: {user.id})\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    try:
        await query.get_bot().send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_msg,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Admin notification error: {e}")

    # Имя — первое слово из ФИО
    first_name = name.split()[1] if len(name.split()) > 1 else name.split()[0]

    # Благодарность клиенту
    thank_you_msg = (
        f"🙏 Спасибо, {first_name}!\n\n"
        f"Вы оплатили участие в мастер-классе *\"{MASTERCLASS_NAME}\"*.\n\n"
        f"В ближайшее время вы получите чек об оплате.\n\n"
        f"До встречи *{MASTERCLASS_DATE}*! 🎉"
    )

    keyboard = [[InlineKeyboardButton("🎟 Купить ещё билет", callback_data="restart")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(thank_you_msg, parse_mode="Markdown")
    await query.message.reply_text(LOCATION_INFO)

    # Фото места
    try:
        with open(LOCATION_IMAGE, "rb") as photo:
            await query.message.reply_photo(photo=photo)
    except FileNotFoundError:
        pass

    await query.message.reply_text(
        "Хотите купить ещё один билет?",
        reply_markup=reply_markup
    )

    return ConversationHandler.END


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка Купить ещё — возврат к началу"""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    keyboard = [[InlineKeyboardButton("🎟 Купить билет", callback_data="buy_ticket")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        with open(WELCOME_IMAGE, "rb") as photo:
            await query.message.reply_photo(
                photo=photo,
                caption="Привет! Это telegram-бот канала *Майянистика без мистики*.",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    except FileNotFoundError:
        await query.message.reply_text(
            "👋 Готово! Нажми кнопку чтобы купить ещё один билет:",
            reply_markup=reply_markup
        )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено. Напиши /start чтобы начать заново.")
    return ConversationHandler.END


# =============================================
# Запуск
# =============================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(buy_ticket, pattern="^buy_ticket$"),
            CallbackQueryHandler(restart, pattern="^restart$"),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            WAITING_PAYMENT: [CallbackQueryHandler(payment_confirmed, pattern="^paid$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,  # позволяет запускать /start повторно!
        per_message=False,
    )

    app.add_handler(conv_handler)

    # Отдельный хендлер для /start вне ConversationHandler (на всякий случай)
    app.add_handler(CommandHandler("start", start))

    logger.info("Бот запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
