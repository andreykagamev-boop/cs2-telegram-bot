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

def check_chrome():
    """Проверка наличия Chrome и ChromeDriver"""
    logger.info("🔍 Проверка Chrome...")
    
    # Проверяем Chrome
    try:
        result = subprocess.run(['google-chrome', '--version'], 
                              capture_output=True, text=True)
        logger.info(f"✅ Chrome: {result.stdout.strip()}")
    except Exception as e:
        logger.error(f"❌ Chrome не найден: {e}")
    
    # Проверяем ChromeDriver
    try:
        result = subprocess.run(['chromedriver', '--version'], 
                              capture_output=True, text=True)
        logger.info(f"✅ ChromeDriver: {result.stdout.strip()}")
    except Exception as e:
        logger.error(f"❌ ChromeDriver не найден: {e}")
    
    # Проверяем пути
    common_paths = [
        '/usr/bin/google-chrome',
        '/usr/bin/chromedriver',
        '/usr/local/bin/chromedriver',
        '/app/chromedriver'
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            logger.info(f"✅ Найден: {path}")
        else:
            logger.info(f"❌ Не найден: {path}")

class OptifineChecker:
    """Проверка аккаунтов на Optifine.net с selenium-stealth"""
    
    def __init__(self):
        self.driver = None
        logger.info("🚀 Инициализация OptifineChecker...")
        check_chrome()
        self.init_driver()
    
    def init_driver(self):
        """Инициализация драйвера с stealth режимом"""
        try:
            chrome_options = Options()
            
            # Основные настройки для скрытности
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
            
            # Скрываем автоматизацию
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Пробуем разные пути к ChromeDriver
            driver_paths = [
                '/usr/bin/chromedriver',
                '/usr/local/bin/chromedriver',
                '/app/chromedriver'
            ]
            
            driver = None
            for path in driver_paths:
                if os.path.exists(path):
                    logger.info(f"✅ Найден ChromeDriver по пути: {path}")
                    try:
                        service = Service(path)
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                        break
                    except Exception as e:
                        logger.error(f"❌ Ошибка при запуске с {path}: {e}")
            
            if not driver:
                # Пробуем без указания пути
                logger.info("🔄 Пробую запустить без указания пути...")
                driver = webdriver.Chrome(options=chrome_options)
            
            self.driver = driver
            
            # Применяем stealth
            stealth(self.driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )
            
            logger.info("✅ Драйвер успешно инициализирован с selenium-stealth")
            
            # Проверяем работу
            self.driver.get("about:blank")
            logger.info("✅ Драйвер работает")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации драйвера: {e}")
            logger.exception("Детали ошибки:")
            self.driver = None
    
    def human_like_delay(self, min_sec=1, max_sec=3):
        """Человекоподобная задержка"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def human_like_typing(self, element, text):
        """Имитация печати человека"""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))
    
    async def check_account(self, login: str, password: str) -> Dict:
        """Проверка одного аккаунта через Selenium"""
        
        logger.info(f"🔍 Начинаю проверку: {login[:20]}...")
        
        if not self.driver:
            logger.error("❌ Драйвер не инициализирован, пробую переинициализировать")
            self.init_driver()
            if not self.driver:
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Драйвер не инициализирован'
                }
        
        try:
            # Пробуем загрузить страницу
            logger.info(f"🌐 Загружаю страницу для {login[:20]}...")
            self.driver.get("https://optifine.net")
            self.human_like_delay(3, 5)
            
            # Проверяем, что страница загрузилась
            if "optifine" not in self.driver.title.lower():
                logger.warning(f"⚠️ Странный заголовок: {self.driver.title}")
            
            # Сохраняем скриншот
            self.driver.save_screenshot(f"/app/debug/main_{login[:10]}.png")
            
            # Остальной код проверки...
            # (вставьте сюда остальной код из предыдущей версии)
            
            return {
                'login': login,
                'status': 'invalid',
                'error': 'Метод не реализован'
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке {login[:20]}: {e}")
            logger.exception("Детали:")
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
    print(f"🐍 Python версия: {sys.version}")
    print("=" * 50)
    
    # Проверяем Chrome перед запуском
    check_chrome()
    
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