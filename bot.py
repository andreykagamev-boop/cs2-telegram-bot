import os
import sys
import logging
import asyncio
import aiofiles
import subprocess
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ НЕТ ТОКЕНА!")
    sys.exit(1)

ADMIN_IDS = [int(id.strip()) for id in os.environ.get('ADMIN_IDS', '').split(',') if id.strip()]
ALLOWED_USERS = ADMIN_IDS.copy()

bot_stats = {'total': 0, 'valid': 0, 'invalid': 0, 'start_time': datetime.now()}
active_sessions = {}

def get_railway_url():
    """Получает URL для доступа к VNC"""
    try:
        result = subprocess.run(['curl', '-s', 'http://metadata.railway.internal/'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            hostname = data.get('hostname')
            if hostname:
                return f"https://{hostname}.railway.app"
    except:
        pass
    return "https://cs2-telegram-bot-production.up.railway.app"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    railway_url = get_railway_url()
    await update.message.reply_text(
        f"👋 **Optifine Checker**\n\n"
        f"📱 **Доступ к браузеру:**\n"
        f"{railway_url}/vnc.html\n\n"
        f"📥 Отправь .txt файл с аккаунтами\n\n"
        f"После подключения к VNC нажми галочку в Chrome"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    doc = update.message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Нужен .txt файл")
        return
    
    file = await context.bot.get_file(doc.file_id)
    path = f"temp_{update.effective_user.id}_{doc.file_name}"
    await file.download_to_drive(path)
    
    railway_url = get_railway_url()
    keyboard = [[InlineKeyboardButton("✅ Я нажал галочку", callback_data="done")]]
    
    await update.message.reply_text(
        f"✅ Файл получен\n\n"
        f"1️⃣ Открой браузер:\n"
        f"{railway_url}/vnc.html\n"
        f"2️⃣ Нажми **Connect**\n"
        f"3️⃣ Нажми галочку в Chrome\n"
        f"4️⃣ Вернись и нажми кнопку",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['file_path'] = path

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "done":
        await query.edit_message_text("🚀 Начинаю проверку...")
        # Здесь будет логика проверки

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ БОТ ЗАПУЩЕН!")
    app.run_polling()

if __name__ == '__main__':
    main()