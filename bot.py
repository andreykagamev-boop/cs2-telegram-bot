import os
import sys
import logging
import asyncio
import aiofiles
import time
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

def get_public_ip():
    try:
        result = subprocess.run(['curl', '-s', 'ifconfig.me'], capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except:
        return "IP-АДРЕС"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    ip = get_public_ip()
    await update.message.reply_text(
        f"👋 **Optifine Checker**\n\n"
        f"📱 **Доступ к браузеру:**\n"
        f"http://{ip}:8080/vnc.html\n\n"
        f"📥 Отправь .txt файл с аккаунтами"
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
    
    await update.message.reply_text(
        f"✅ Файл получен\n\n"
        f"1️⃣ Открой браузер по ссылке выше\n"
        f"2️⃣ Нажми галочку\n"
        f"3️⃣ Напиши /check чтобы начать проверку"
    )
    
    context.user_data['file_path'] = path

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_path = context.user_data.get('file_path')
    if not file_path:
        await update.message.reply_text("❌ Сначала отправь файл")
        return
    
    await update.message.reply_text("🚀 Начинаю проверку...")
    # Тут будет логика проверки

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ БОТ ЗАПУЩЕН!")
    app.run_polling()

if __name__ == '__main__':
    main()