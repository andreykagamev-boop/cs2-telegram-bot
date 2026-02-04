import os
import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
PANDASCORE_TOKEN = os.getenv("PANDASCORE_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Проверяем переменные
logger.info(f"TELEGRAM_BOT_TOKEN: {'✅' if TELEGRAM_BOT_TOKEN else '❌'}")
logger.info(f"PANDASCORE_TOKEN: {'✅' if PANDASCORE_TOKEN else '❌'}")
logger.info(f"DEEPSEEK_API_KEY: {'✅' if DEEPSEEK_API_KEY else '❌'}")

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ========== DEEPSEEK НЕЙРОСЕТЬ ==========
try:
    from openai import AsyncOpenAI
    DEEPSEEK_AVAILABLE = True
    logger.info("✅ OpenAI/DeepSeek библиотека доступна")
except ImportError as e:
    DEEPSEEK_AVAILABLE = False
    logger.error(f"❌ Ошибка импорта OpenAI: {e}")

class DeepSeekNeuralNetwork:
    """Нейросеть DeepSeek для анализа CS2 матчей"""
    
    def __init__(self):
        self.active = False
        self.client = None
        
        logger.info("🧠 Инициализация нейросети DeepSeek...")
        
        if not DEEPSEEK_AVAILABLE:
            logger.error("❌ Библиотека OpenAI недоступна")
            return
        
        if not DEEPSEEK_API_KEY:
            logger.error("❌ Отсутствует DEEPSEEK_API_KEY")
            return
        
        try:
            # Проверяем формат ключа
            if not DEEPSEEK_API_KEY.startswith('sk-'):
                logger.warning(f"⚠️ Ключ может быть неверного формата")
            
            logger.info("🔄 Создаю клиент DeepSeek...")
            
            # ПРАВИЛЬНАЯ ИНИЦИАЛИЗАЦИЯ для openai>=1.0.0
            self.client = AsyncOpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url="https://api.deepseek.com"
            )
            
            self.active = True
            logger.info("✅ Нейросеть DeepSeek активирована")
            
        except TypeError as e:
            logger.error(f"❌ Ошибка параметров AsyncOpenAI: {e}")
            logger.error("Проверьте совместимость версии библиотеки openai")
            self.active = False
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации DeepSeek: {str(e)}")
            self.active = False
    
    async def test_connection(self):
        """Тест подключения к API"""
        if not self.active or not self.client:
            return False
        
        try:
            logger.info("🔄 Тестирую подключение к DeepSeek API...")
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": "Привет! Ответь 'Готов к работе'"}],
                max_tokens=10,
                temperature=0.1
            )
            
            result = response.choices[0].message.content
            logger.info(f"✅ Тест API успешен: {result}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка теста API: {str(e)}")
            self.active = False
            return False
    
    async def analyze_match(self, team1: str, team2: str, tournament: str = "", 
                          match_time: str = "") -> Dict:
        """Анализ матча нейросетью"""
        if not self.active:
            raise Exception("🍻 Бармен отдыхает! Нейросеть не активирована.")
        
        try:
            # Промпт в стиле бара
            prompt = f"""
Ты - опытный бармен и эксперт по киберспорту в баре "HeadShot". 
Проанализируй матч CS2 между командами {team1} и {team2}.

Турнир: {tournament if tournament else 'Не указан'}
Время матча: {match_time if match_time else 'Скоро'}

Дай прогноз в следующем JSON формате:
{{
  "bar_intro": "забавное вступление о матче",
  "team1_analysis": {{
    "strength": число от 0 до 100,
    "current_form": "описание текущей формы",
    "key_strengths": ["сильная сторона 1", "сильная сторона 2"],
    "weaknesses": ["слабая сторона 1", "слабая сторона 2"],
    "bar_nickname": "забавное прозвище в баре"
  }},
  "team2_analysis": {{ ... }},
  "match_prediction": {{
    "likely_winner": "{team1} или {team2}",
    "probability": число от 0 до 100,
    "score_prediction": "2:0, 2:1, 1:2 или 0:2",
    "confidence": число от 0 до 100,
    "risk_level": "LOW, MEDIUM или HIGH",
    "bar_metaphor": "сравнение матча с напитком"
  }},
  "key_factors": ["ключевой фактор 1", "ключевой фактор 2"],
  "recommended_bets": [
    {{
      "type": "тип ставки (П1, Тотал и т.д.)",
      "reason": "обоснование в стиле бара",
      "confidence": "LOW, MEDIUM или HIGH",
      "bar_drink": "рекомендуемый напиток"
    }}
  ],
  "detailed_analysis": "развернутый анализ на 2-3 предложения",
  "bar_tip": "совет бармена на матч",
  "funny_comment": "шутка или забавный комментарий"
}}

Будь креативным и забавным! Добавь барного юмора!
"""
            
            logger.info(f"🍺 Бармен анализирует матч: {team1} vs {team2}")
            
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system", 
                        "content": "Ты бармен-аналитик CS2 в баре 'HeadShot'. Отвечай всегда в JSON формате с юмором и креативом."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Добавляем метаданные
            result["source"] = "Бармен DeepSeek"
            result["analysis_time"] = datetime.now().strftime("%d.%m.%Y %H:%M")
            result["bar_name"] = "CS2 Бар 'HeadShot'"
            
            logger.info(f"✅ Анализ завершен для {team1} vs {team2}")
            return result
            
        except Exception as e:
            logger.error(f"🍻 Ошибка анализа матча: {str(e)}")
            raise Exception(f"Бармен перебрал с аналитикой: {str(e)[:100]}")

# ========== ИНИЦИАЛИЗАЦИЯ СЕРВИСОВ ==========
neural_network = DeepSeekNeuralNetwork()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_drink_emoji():
    """Случайный эмодзи напитка"""
    drinks = ["🍺", "🍷", "🥃", "🍸", "🍾", "🥂", "☕", "🍹"]
    import random
    return random.choice(drinks)

def create_main_keyboard():
    """Главное меню бара"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🍺 О БАРЕ", callback_data="about"),
            InlineKeyboardButton(text="🎯 АНАЛИЗ", callback_data="analyze")
        ],
        [
            InlineKeyboardButton(text="⚙️ НАСТРОЙКИ", callback_data="settings"),
            InlineKeyboardButton(text="ℹ️ ПОМОЩЬ", callback_data="help")
        ]
    ])
    return keyboard

# ========== ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт - вход в бар"""
    status = "✅ БАРМЕН ГОТОВ" if neural_network.active else "❌ БАРМЕН ОТДЫХАЕТ"
    
    welcome = f"""
{get_drink_emoji()} <b>ДОБРО ПОЖАЛОВАТЬ В CS2 БАР «HEADSHOT»</b>

<i>Место, где киберспорт встречается с хорошими напитками!</i>

🤖 <b>Ваш бармен-аналитик:</b> {status}
🕐 <b>Время:</b> {datetime.now().strftime('%H:%M MSK')}

🎯 <b>Что умеет бармен:</b>
• Анализирует матчи с помощью AI
• Дает прогнозы с юмором
• Рекомендует напитки
• Создает атмосферу настоящего бара

{get_drink_emoji()} <b>Спецпредложение:</b>
Закажи анализ матча и получи рекомендацию по напитку!

👇 <b>Выберите действие:</b>
"""
    
    await message.answer(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "analyze")
async def handle_analyze(callback: types.CallbackQuery):
    """Анализ матча"""
    await callback.answer("🎯 Бармен готовится...")
    
    if not neural_network.active:
        await callback.message.edit_text(
            f"{get_drink_emoji()} <b>БАРМЕН ОТДЫХАЕТ</b>\n\n"
            f"К сожалению, наш бармен сейчас не доступен.\n\n"
            f"<i>Для активации бармена добавьте DEEPSEEK_API_KEY в Railway Variables</i>\n\n"
            f"<b>Где получить ключ:</b>\n"
            f"1. Зарегистрируйтесь на platform.deepseek.com\n"
            f"2. Создайте API ключ\n"
            f"3. Добавьте его в настройки проекта",
            reply_markup=create_main_keyboard()
        )
        return
    
    try:
        # Тестируем соединение
        connection_ok = await neural_network.test_connection()
        if not connection_ok:
            raise Exception("Нет связи с барменом")
        
        # Делаем тестовый анализ
        await callback.message.edit_text(
            f"{get_drink_emoji()} <b>БАРМЕН АНАЛИЗИРУЕТ...</b>\n\n"
            f"Пробую матч: NAVI vs Vitality\n"
            f"Это займет несколько секунд...",
            disable_web_page_preview=True
        )
        
        analysis = await neural_network.analyze_match(
            "NAVI", "Vitality", "ESL Pro League", "20:00"
        )
        
        prediction = analysis.get("match_prediction", {})
        
        result_text = f"""
{get_drink_emoji()} <b>АНАЛИЗ ОТ БАРМЕНА</b>
{analysis.get('bar_intro', '🎯 Интересный матч в нашем баре!')}

🏆 <b>NAVI vs Vitality</b>
⏰ 20:00 MSK | 🏆 ESL Pro League

📊 <b>ПРОГНОЗ:</b>
• Победитель: <b>{prediction.get('likely_winner', 'Сложно сказать')}</b>
• Вероятность: <b>{prediction.get('probability', 0):.1f}%</b>
• Счет: <b>{prediction.get('score_prediction', '?')}</b>
• Риск: <b>{prediction.get('risk_level', 'MEDIUM')}</b>

🍸 <b>СОВЕТ БАРМЕНА:</b>
{analysis.get('bar_tip', 'Наслаждайтесь игрой!')}

😄 <b>КОММЕНТАРИЙ:</b>
{analysis.get('funny_comment', 'Будет жарко!')}

<i>Анализ от AI-бармена DeepSeek</i>
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🍺 ЗАКАЗАТЬ СВОЙ АНАЛИЗ", callback_data="custom")],
            [InlineKeyboardButton(text="🏠 В БАР", callback_data="back")]
        ])
        
        await callback.message.edit_text(
            result_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        error_msg = str(e)
        await callback.message.edit_text(
            f"{get_drink_emoji()} <b>ОШИБКА В БАРЕ</b>\n\n"
            f"Бармен не справился:\n"
            f"<code>{error_msg[:200]}</code>\n\n"
            f"<i>Попробуйте позже или проверьте настройки API ключа</i>",
            reply_markup=create_main_keyboard()
        )

@dp.callback_query(F.data == "custom")
async def handle_custom(callback: types.CallbackQuery):
    """Заказ анализа"""
    await callback.answer("📝 Готовлю бланк заказа...")
    
    await callback.message.edit_text(
        f"{get_drink_emoji()} <b>ЗАКАЗ АНАЛИЗА</b>\n\n"
        f"Чтобы бармен проанализировал конкретный матч,\n"
        f"используйте команду:\n\n"
        f"<code>/analyze NAVI Vitality</code>\n\n"
        f"Или с турниром:\n"
        f"<code>/analyze FaZe G2 ESL Pro League</code>\n\n"
        f"<i>Бармен приготовит для вас особый анализ!</i>",
        reply_markup=create_main_keyboard()
    )

@dp.callback_query(F.data == "about")
async def handle_about(callback: types.CallbackQuery):
    """О баре"""
    await callback.answer("🍺 Рассказываю о баре...")
    
    about_text = f"""
{get_drink_emoji()} <b>О БАРЕ «HEADSHOT»</b>

<i>Где страсть к киберспорту встречается с искусством бара!</i>

🎯 <b>НАША МИССИЯ:</b>
Делаем анализ CS2 матчей интересным, креативным и доступным для всех!

🍸 <b>ЧТО ПРЕДЛАГАЕМ:</b>
• AI-анализ матчей от бармена
• Прогнозы с юмором и креативом
• Рекомендации по напиткам
• Атмосферу настоящего киберспорт-бара

🤖 <b>НАШ БАРМЕН:</b>
Умная нейросеть DeepSeek, обученная на тысячах матчей CS2.
Знает все о командах, тактиках и турнирах!

⚡ <b>ПОЧЕМУ МЫ:</b>
• Уникальный барный стиль
• Объективные прогнозы
• Быстрые и точные анализы
• Настоящая атмосфера бара

<i>Заходите чаще - у нас всегда есть что предложить!</i>
"""
    
    await callback.message.edit_text(
        about_text,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "settings")
async def handle_settings(callback: types.CallbackQuery):
    """Настройки бара"""
    status = "✅ АКТИВЕН" if neural_network.active else "❌ НЕ АКТИВЕН"
    
    await callback.answer("⚙️ Проверяю настройки...")
    
    settings_text = f"""
{get_drink_emoji()} <b>НАСТРОЙКИ БАРА</b>

🤖 <b>Бармен-аналитик:</b> {status}
🔑 <b>API ключ:</b> {'✅ Установлен' if DEEPSEEK_API_KEY else '❌ Отсутствует'}

⚙️ <b>Как активировать бармена:</b>
1. Получите API ключ на platform.deepseek.com
2. Добавьте в Railway Variables: DEEPSEEK_API_KEY
3. Перезапустите приложение

💡 <b>Требования к ключу:</b>
• Должен начинаться с <code>sk-</code>
• Должен быть действительным
• Должен иметь доступ к DeepSeek Chat API

🔄 <b>Текущий статус:</b>
{'🍸 Бармен готов к работе! Заказывайте анализы!' if neural_network.active else '🍺 Бармен отдыхает. Активируйте для полного функционала.'}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ПРОВЕРИТЬ ПОДКЛЮЧЕНИЕ", callback_data="test_connection")],
        [InlineKeyboardButton(text="🍺 В БАР", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        settings_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "test_connection")
async def handle_test_connection(callback: types.CallbackQuery):
    """Тест подключения"""
    await callback.answer("🔄 Тестирую...")
    
    if not neural_network.active:
        await callback.message.edit_text(
            "❌ Бармен не активирован",
            reply_markup=create_main_keyboard()
        )
        return
    
    try:
        await callback.message.edit_text(
            f"{get_drink_emoji()} <b>ТЕСТ ПОДКЛЮЧЕНИЯ</b>\n\n"
            f"Проверяю связь с барменом...",
            disable_web_page_preview=True
        )
        
        success = await neural_network.test_connection()
        
        if success:
            result = f"""
✅ <b>ПОДКЛЮЧЕНИЕ УСПЕШНО</b>

🤖 Бармен отвечает и готов к работе!
🕐 Время: {datetime.now().strftime('%H:%M:%S')}

🎯 Теперь можете заказывать анализы матчей!

<i>Бар «HeadShot» к вашим услугам!</i>
"""
        else:
            result = """
❌ <b>ПРОБЛЕМА С ПОДКЛЮЧЕНИЕМ</b>

Бармен не отвечает. Возможные причины:
1. Неверный API ключ
2. Проблемы с сетью
3. Ограничения API

Проверьте DEEPSEEK_API_KEY и попробуйте снова.
"""
        
        await callback.message.edit_text(
            result,
            reply_markup=create_main_keyboard(),
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка теста: {str(e)}",
            reply_markup=create_main_keyboard()
        )

@dp.callback_query(F.data == "help")
async def handle_help(callback: types.CallbackQuery):
    """Помощь"""
    await callback.answer("ℹ️ Рассказываю как пользоваться...")
    
    help_text = f"""
{get_drink_emoji()} <b>ПОМОЩЬ ПО БАРУ</b>

🎯 <b>ОСНОВНЫЕ КОМАНДЫ:</b>
• /start - Вход в бар
• /analyze Team1 Team2 - Анализ матча
• /status - Статус бара
• /help - Эта справка

🍸 <b>КАК ЗАКАЗАТЬ АНАЛИЗ:</b>
1. Нажмите "АНАЛИЗ" в меню
2. Или используйте команду /analyze
3. Укажите две команды
4. Получите экспертный прогноз

🤖 <b>КАК РАБОТАЕТ БАРМЕН:</b>
1. Получает данные о командах
2. Анализирует с помощью нейросети
3. Добавляет барный юмор и стиль
4. Дает прогноз и рекомендации

⚡ <b>ПРИМЕРЫ:</b>
<code>/analyze NAVI Vitality</code>
<code>/analyze FaZe G2 BLAST Premier</code>

<i>Наслаждайтесь анализом и хорошей игрой!</i>
"""
    
    await callback.message.edit_text(
        help_text,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "back")
async def handle_back(callback: types.CallbackQuery):
    """Назад в главное меню"""
    await cmd_start(callback.message)
    await callback.answer()

@dp.message(Command("analyze"))
async def cmd_analyze(message: types.Message):
    """Анализ матча через команду"""
    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            f"{get_drink_emoji()} <b>ИСПОЛЬЗУЙТЕ:</b>\n"
            f"<code>/analyze NAVI Vitality</code>\n"
            f"Или: <code>/analyze Team1 Team2 Турнир</code>"
        )
        return
    
    team1 = args[1]
    team2 = args[2]
    tournament = " ".join(args[3:]) if len(args) > 3 else ""
    
    if not neural_network.active:
        await message.answer(
            f"{get_drink_emoji()} <b>БАРМЕН ОТДЫХАЕТ</b>\n\n"
            f"Активируйте нейросеть для анализа матчей."
        )
        return
    
    try:
        status_msg = await message.answer(
            f"{get_drink_emoji()} <b>БАРМЕН АНАЛИЗИРУЕТ...</b>\n\n"
            f"🎯 {team1} vs {team2}\n"
            f"🏆 {tournament if tournament else 'Матч'}\n\n"
            f"<i>Готовлю особый анализ...</i>"
        )
        
        analysis = await neural_network.analyze_match(team1, team2, tournament)
        prediction = analysis.get("match_prediction", {})
        
        result = f"""
{get_drink_emoji()} <b>АНАЛИЗ ОТ БАРМЕНА</b>

{analysis.get('bar_intro', '🎯 Интересный матч!')}

🏆 <b>{team1} 🆚 {team2}</b>
{f'🏆 {tournament}' if tournament else ''}

📊 <b>ПРОГНОЗ:</b>
• Победитель: <b>{prediction.get('likely_winner', '?')}</b>
• Вероятность: <b>{prediction.get('probability', 0):.1f}%</b>
• Счет: <b>{prediction.get('score_prediction', '?')}</b>
• Уверенность: <b>{prediction.get('confidence', 0):.1f}%</b>
• Риск: <b>{prediction.get('risk_level', 'MEDIUM')}</b>

🍸 <b>РЕКОМЕНДАЦИЯ:</b>
"""
        
        # Добавляем рекомендации по ставкам
        bets = analysis.get("recommended_bets", [])
        if bets:
            for bet in bets[:2]:
                result += f"• {bet.get('type', '?')} - {bet.get('reason', '')}\n"
        else:
            result += "• Наслаждайтесь игрой как зритель!\n"
        
        result += f"""
🎯 <b>КЛЮЧЕВОЙ ФАКТОР:</b>
{analysis.get('key_factors', ['Сложно сказать'])[0]}

💡 <b>СОВЕТ БАРМЕНА:</b>
{analysis.get('bar_tip', 'Наслаждайтесь игрой!')}

<i>Анализ от AI-бармена DeepSeek</i>
"""
        
        await status_msg.edit_text(result, disable_web_page_preview=True)
        
    except Exception as e:
        await message.answer(
            f"{get_drink_emoji()} <b>ОШИБКА АНАЛИЗА</b>\n\n"
            f"Бармен не справился:\n"
            f"<code>{str(e)[:150]}</code>"
        )

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    """Статус системы"""
    status_text = f"""
{get_drink_emoji()} <b>СТАТУС БАРА «HEADSHOT»</b>

🤖 <b>Бармен-аналитик:</b> {'✅ АКТИВЕН' if neural_network.active else '❌ НЕ АКТИВЕН'}
🔑 <b>API ключ:</b> {'✅ УСТАНОВЛЕН' if DEEPSEEK_API_KEY else '❌ ОТСУТСТВУЕТ'}
🤖 <b>Библиотека OpenAI:</b> {'✅' if DEEPSEEK_AVAILABLE else '❌'}
🕐 <b>Время сервера:</b> {datetime.now().strftime('%d.%m.%Y %H:%M MSK')}

{f'🍸 Бармен готов к работе! Используйте /analyze для заказа анализа.' if neural_network.active else '🍺 Для активации бармена добавьте DEEPSEEK_API_KEY в Railway Variables.'}

<i>Бар всегда к вашим услугам!</i>
"""
    
    await message.answer(status_text, disable_web_page_preview=True)

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Тест системы"""
    await message.answer(
        f"{get_drink_emoji()} <b>ТЕСТ СИСТЕМЫ</b>\n\n"
        f"• Бот работает: ✅\n"
        f"• Нейросеть: {'✅' if neural_network.active else '❌'}\n"
        f"• Время: {datetime.now().strftime('%H:%M:%S')}\n"
        f"• Версия: CS2 Бар v1.0"
    )

# ========== ЗАПУСК БАРА ==========
async def main():
    """Запуск бота"""
    logger.info("=" * 50)
    logger.info("🍺 ЗАПУСК CS2 БАРА «HEADSHOT»")
    logger.info("=" * 50)
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Ошибка: TELEGRAM_BOT_TOKEN не найден")
        return
    
    logger.info(f"🤖 Состояние бармена: {'✅ АКТИВЕН' if neural_network.active else '❌ НЕ АКТИВЕН'}")
    
    if not neural_network.active:
        logger.warning("⚠️ Бармен не активирован. Для работы добавьте DEEPSEEK_API_KEY")
    
    try:
        logger.info("🚀 Открываю бар...")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")

if __name__ == "__main__":
    asyncio.run(main())