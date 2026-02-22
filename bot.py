import os
import logging
import asyncio
import aiofiles
import time
import random
from datetime import datetime
from typing import List, Dict
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException

import requests

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфиг
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS = os.environ.get('ADMIN_IDS', '').split(',')
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS if id.strip()]
ALLOWED_USERS = ADMIN_IDS.copy() if ADMIN_IDS else []

# Статистика
bot_stats = {
    'total': 0,
    'capes_found': 0,
    'start_time': datetime.now()
}

class OptifineParser:
    """Парсер плащей с Optifine.net"""
    
    def __init__(self):
        self.driver = None
        self.found_capes = set()  # для избежания дубликатов
        
    def setup_driver(self):
        """Настройка Chrome для парсинга"""
        chrome_options = Options()
        
        # Режим без головы для сервера
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # Отключаем лишнее для скорости
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--disable-features=VizDisplayCompositor')
        
        # Маскировка под реального пользователя
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Путь к ChromeDriver
        chromedriver_path = '/usr/local/bin/chromedriver'
        if not os.path.exists(chromedriver_path):
            chromedriver_path = '/usr/bin/chromedriver'
        
        try:
            service = Service(chromedriver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return True
        except Exception as e:
            logger.error(f"Ошибка запуска Chrome: {e}")
            return False
    
    async def parse_cape_page(self, page_num: int = 1) -> List[str]:
        """Парсит страницу с плащами"""
        
        if not self.driver:
            if not self.setup_driver():
                return []
        
        try:
            # Загружаем страницу с плащами
            if page_num == 1:
                url = "https://optifine.net/capes"
            else:
                url = f"https://optifine.net/capes?page={page_num}"
            
            logger.info(f"Парсим страницу {page_num}: {url}")
            self.driver.get(url)
            
            # Ждем загрузку
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
            )
            
            # Небольшая задержка для загрузки контента
            time.sleep(2)
            
            # Ищем все ссылки на плащи
            # На Optifine плащи обычно в виде /capes/ник.png
            page_source = self.driver.page_source
            
            # Разные паттерны для поиска ников
            patterns = [
                r'/capes/([a-zA-Z0-9_]+)\.png',
                r'capes/([a-zA-Z0-9_]+)\.png',
                r'optifine\.net/capes/([a-zA-Z0-9_]+)\.png',
                r'src="[^"]*capes/([a-zA-Z0-9_]+)\.png"',
                r'href="[^"]*capes/([a-zA-Z0-9_]+)\.png"'
            ]
            
            usernames = set()
            for pattern in patterns:
                matches = re.findall(pattern, page_source, re.IGNORECASE)
                for match in matches:
                    if 2 < len(match) < 20:  # нормальная длина ника
                        usernames.add(match)
            
            # Также ищем текст, который может быть никами
            text_pattern = r'\b([a-zA-Z0-9_]{3,16})\b'
            text_matches = re.findall(text_pattern, page_source)
            
            # Фильтруем (исключаем common words)
            common_words = {'the', 'and', 'for', 'you', 'are', 'not', 'but', 'has', 'have', 'with', 
                           'this', 'that', 'from', 'your', 'will', 'page', 'next', 'prev', 'cape',
                           'capes', 'optifine', 'minecraft', 'download', 'login', 'register'}
            
            for match in text_matches:
                if (match.lower() not in common_words and 
                    2 < len(match) < 17 and 
                    match.isascii()):
                    usernames.add(match)
            
            # Также ищем в атрибутах data-*
            data_attrs = self.driver.execute_script("""
                const elements = document.querySelectorAll('[data-username], [data-player], [data-nick]');
                return Array.from(elements).map(el => el.getAttribute('data-username') || 
                                                       el.getAttribute('data-player') || 
                                                       el.getAttribute('data-nick')).filter(Boolean);
            """)
            
            for username in data_attrs:
                if 2 < len(username) < 20:
                    usernames.add(username)
            
            logger.info(f"Найдено {len(usernames)} ников на странице {page_num}")
            return list(usernames)
            
        except TimeoutException:
            logger.error(f"Таймаут при загрузке страницы {page_num}")
            return []
        except Exception as e:
            logger.error(f"Ошибка при парсинге страницы {page_num}: {e}")
            return []
    
    async def check_cape_direct(self, username: str) -> bool:
        """Прямая проверка наличия плаща"""
        try:
            # Пробуем разные URL
            urls = [
                f"https://optifine.net/capes/{username}.png",
                f"http://optifine.net/capes/{username}.png",
                f"https://s.optifine.net/capes/{username}.png"
            ]
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://optifine.net/'
            }
            
            for url in urls:
                response = requests.get(url, headers=headers, timeout=3, allow_redirects=True)
                
                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '')
                    size = len(response.content)
                    
                    # Проверяем что это PNG и размер подходящий
                    if 'image' in content_type and size > 500:
                        logger.info(f"🔥 Найден плащ: {username}")
                        return True
                        
                # Небольшая задержка между запросами
                await asyncio.sleep(0.1)
                
            return False
            
        except Exception as e:
            logger.debug(f"Ошибка проверки {username}: {e}")
            return False
    
    async def parse_all_pages(self, max_pages: int = 10) -> List[Dict]:
        """Парсит несколько страниц"""
        
        results = []
        self.found_capes.clear()
        
        if not self.driver:
            if not self.setup_driver():
                return results
        
        try:
            for page in range(1, max_pages + 1):
                # Парсим страницу
                usernames = await self.parse_cape_page(page)
                
                if not usernames:
                    # Если страница пустая, возможно достигли конца
                    break
                
                # Проверяем каждый ник
                for username in usernames:
                    if username in self.found_capes:
                        continue  # уже проверяли
                    
                    has_cape = await self.check_cape_direct(username)
                    
                    if has_cape:
                        results.append({
                            'username': username,
                            'page': page
                        })
                        self.found_capes.add(username)
                    
                    # Маленькая задержка между проверками
                    await asyncio.sleep(0.2)
                
                # Задержка между страницами
                if page < max_pages:
                    await asyncio.sleep(random.uniform(2, 4))
                    
            return results
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге: {e}")
            return results
        finally:
            self.close()
    
    def close(self):
        """Закрытие браузера"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

# Создаем экземпляр
parser = OptifineParser()

async def start_parsing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск парсинга"""
    
    msg = await update.message.reply_text(
        "🔍 **Запускаю парсер плащей Optifine...**\n"
        "⏳ Это займет 1-2 минуты"
    )
    
    try:
        # Парсим страницы
        results = await parser.parse_all_pages(max_pages=10)
        
        if not results:
            await msg.edit_text("❌ **Не найдено плащей**")
            return
        
        # Сохраняем результаты
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"🔥_ПЛАЩИ_OPTIFINE_{len(results)}шт_{timestamp}.txt"
        
        async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
            await f.write("🔥 НАЙДЕННЫЕ ПЛАЩИ OPTIFINE 🔥\n\n")
            await f.write(f"Всего найдено: {len(results)}\n")
            await f.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            await f.write("=" * 40 + "\n\n")
            
            for cape in results:
                await f.write(f"Ник: {cape['username']}\n")
                await f.write(f"Страница: {cape['page']}\n")
                await f.write(f"Ссылка: https://optifine.net/capes/{cape['username']}.png\n")
                await f.write("-" * 30 + "\n")
        
        # Отправляем файл
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"🔥 **Найдено плащей: {len(results)}**"
            )
        
        os.remove(filename)
        
        # Обновляем статистику
        bot_stats['capes_found'] += len(results)
        bot_stats['total'] += 1
        
        await msg.edit_text(
            f"✅ **Парсинг завершен!**\n\n"
            f"📊 **Результат:**\n"
            f"• Найдено плащей: {len(results)}\n"
            f"• Проверено страниц: 10"
        )
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await msg.edit_text(f"❌ **Ошибка:** {str(e)[:100]}")
    finally:
        parser.close()

async def check_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка конкретного ника"""
    
    if not context.args:
        await update.message.reply_text("❌ **Укажи ник:** /check Steve")
        return
    
    username = context.args[0].strip()
    
    msg = await update.message.reply_text(f"🔍 **Проверяю ник:** {username}")
    
    # Проверяем через прямой запрос
    has_cape = await parser.check_cape_direct(username)
    
    if has_cape:
        await msg.edit_text(
            f"✅ **У {username} есть плащ!**\n\n"
            f"🔗 Ссылка: https://optifine.net/capes/{username}.png"
        )
    else:
        await msg.edit_text(f"❌ **У {username} нет плаща**")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт"""
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ **Нет доступа**")
        return
    
    uptime = datetime.now() - bot_stats['start_time']
    hours = int(uptime.seconds // 3600)
    minutes = int((uptime.seconds // 60) % 60)
    
    keyboard = [
        [InlineKeyboardButton("🚀 Запустить парсинг", callback_data='parse')],
        [InlineKeyboardButton("📊 Стата", callback_data='stats')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    
    await update.message.reply_text(
        f"👋 **Optifine Cape Parser**\n\n"
        f"🔍 **Парсит плащи прямо с optifine.net**\n\n"
        f"📊 **Статистика:**\n"
        f"• Найдено плащей: {bot_stats['capes_found']}\n"
        f"• Запусков: {bot_stats['total']}\n\n"
        f"⏱ **Работаю:** {hours}ч {minutes}мин\n\n"
        f"📌 **Команды:**\n"
        f"• /parse - запустить парсинг\n"
        f"• /check ник - проверить конкретный ник",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'parse':
        await query.edit_message_text("🚀 **Запускаю парсинг...**")
        await start_parsing(update, context)
    
    elif query.data == 'stats':
        uptime = datetime.now() - bot_stats['start_time']
        hours = int(uptime.seconds // 3600)
        minutes = int((uptime.seconds // 60) % 60)
        
        await query.edit_message_text(
            f"📊 **СТАТИСТИКА**\n\n"
            f"Найдено плащей: {bot_stats['capes_found']}\n"
            f"Запусков парсинга: {bot_stats['total']}\n\n"
            f"⏱ Аптайм: {hours}ч {minutes}мин"
        )
    
    elif query.data == 'help':
        await query.edit_message_text(
            "❓ **КАК ПОЛЬЗОВАТЬСЯ**\n\n"
            "🔍 **Парсинг плащей:**\n"
            "• Нажми кнопку 'Запустить парсинг'\n"
            "• Или отправь команду /parse\n\n"
            "✅ **Проверка ника:**\n"
            "• Отправь /check ник\n"
            "• Например: /check Notch\n\n"
            "📌 **Как это работает:**\n"
            "• Парсит страницы optifine.net/capes\n"
            "• Ищет все возможные ники\n"
            "• Проверяет наличие плаща\n"
            "• Сохраняет результаты в файл"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        return
    
    text = update.message.text.strip()
    
    # Если просто текст, проверяем как ник
    if len(text) < 20 and re.match(r'^[a-zA-Z0-9_]+$', text):
        await check_username(update, context)

def main():
    """Запуск"""
    if not TOKEN:
        print("❌ НЕТ ТОКЕНА!")
        return
    
    print("=" * 50)
    print("🚀 ЗАПУСК OPTIFINE CAPE PARSER")
    print("=" * 50)
    
    app = Application.builder().token(TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parse", start_parsing))
    app.add_handler(CommandHandler("check", check_username))
    
    # Кнопки
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Текстовые сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ БОТ РАБОТАЕТ!")
    
    try:
        app.run_polling()
    finally:
        parser.close()

if __name__ == '__main__':
    main()