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

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ========== DEEPSEEK НЕЙРОСЕТЬ ==========
try:
    # Импортируем только то, что нужно
    from openai import AsyncOpenAI
    DEEPSEEK_AVAILABLE = True
    logger.info("✅ OpenAI/DeepSeek библиотека доступна")
except ImportError as e:
    DEEPSEEK_AVAILABLE = False
    logger.warning(f"❌ OpenAI библиотека не установлена: {e}")

class DeepSeekNeuralNetwork:
    """Настоящая нейросеть DeepSeek для анализа CS2 матчей"""
    
    def __init__(self):
        self.active = False
        
        logger.info("🧠 Проверяю настройки нейросети...")
        
        if not DEEPSEEK_AVAILABLE:
            logger.error("❌ Библиотека openai недоступна")
            return
        
        if not DEEPSEEK_API_KEY:
            logger.error("❌ DEEPSEEK_API_KEY не найден")
            return
        
        logger.info(f"✅ Ключ найден, длина: {len(DEEPSEEK_API_KEY)} символов")
        
        try:
            # МИНИМАЛЬНАЯ ИНИЦИАЛИЗАЦИЯ - только обязательные параметры
            logger.info("🔄 Создаю клиент DeepSeek...")
            
            # Вот это КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ - только 2 параметра!
            self.client = AsyncOpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url="https://api.deepseek.com"
            )
            
            self.active = True
            logger.info("✅ DeepSeek нейросеть успешно активирована")
            
            # Тестируем соединение
            asyncio.create_task(self._test_connection())
            
        except TypeError as e:
            logger.error(f"❌ ОШИБКА ТИПА ПАРАМЕТРА: {e}")
            logger.error("Проверьте, что не передаются лишние параметры в AsyncOpenAI")
        except Exception as e:
            logger.error(f"❌ Ошибка при создании клиента: {e}")
            self.active = False
    
    async def _test_connection(self):
        """Тестируем соединение с API"""
        try:
            # Простой тестовый запрос
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": "Привет! Ответь 'Готов к работе!'"}],
                max_tokens=10
            )
            logger.info(f"✅ Тест API: {response.choices[0].message.content}")
        except Exception as e:
            logger.error(f"❌ Ошибка теста API: {e}")
            self.active = False
    
    async def analyze_match(self, team1: str, team2: str, tournament: str = "", 
                          match_time: str = "") -> Dict:
        """Анализ матча настоящей нейросетью DeepSeek"""
        
        if not self.active:
            raise Exception("🍻 Бармен отдыхает! Добавьте DEEPSEEK_API_KEY в настройки.")
        
        try:
            # Промпт в стиле бара
            prompt = f"""
Ты - бармен и эксперт по CS2 в баре "HeadShot". Проанализируй матч между {team1} и {team2}.

Турнир: {tournament if tournament else 'Не указан'}
Время: {match_time if match_time else 'Скоро'}

Дай прогноз в формате JSON:
{{
  "bar_intro": "веселое вступление",
  "team1_analysis": {{
    "strength": число от 1 до 100,
    "current_form": "описание",
    "key_strengths": ["сила1", "сила2"],
    "weaknesses": ["слабость1", "слабость2"],
    "bar_nickname": "прозвище в баре"
  }},
  "team2_analysis": {{ ... }},
  "match_prediction": {{
    "likely_winner": "{team1} или {team2}",
    "probability": число,
    "score_prediction": "2:0 или 2:1",
    "confidence": число,
    "risk_level": "LOW/MEDIUM/HIGH",
    "bar_metaphor": "сравнение с напитком"
  }},
  "key_factors": ["фактор1", "фактор2"],
  "recommended_bets": [
    {{
      "type": "ставка",
      "reason": "обоснование",
      "confidence": "LOW/MEDIUM/HIGH",
      "bar_drink": "рекомендуемый напиток"
    }}
  ],
  "detailed_analysis": "развернутый анализ",
  "bar_tip": "совет бармена",
  "funny_comment": "шутка про матч"
}}

Будь креативным и забавным!
"""
            
            logger.info(f"🍺 Бармен анализирует: {team1} vs {team2}")
            
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "Ты бармен-аналитик CS2. Отвечай в JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            result["source"] = "Бармен DeepSeek"
            result["analysis_time"] = datetime.now().strftime("%d.%m.%Y %H:%M")
            
            return result
            
        except Exception as e:
            logger.error(f"🍻 Ошибка анализа: {e}")
            raise Exception(f"Бармен перебрал: {str(e)}")

# ========== ПАРСИНГ МАТЧЕЙ ==========
class PandaScoreAPI:
    """API клиент для CS2"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def get_today_matches(self):
        """Получить матчи на сегодня"""
        try:
            session = await self.get_session()
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{today.isoformat()},{tomorrow.isoformat()}",
                "per_page": 20,
                "sort": "scheduled_at"
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                return []
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return []
    
    async def close(self):
        if self.session:
            await self.session.close()

# ========== ИНИЦИАЛИЗАЦИЯ ==========
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)
neural_network = DeepSeekNeuralNetwork()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_drink_emoji(drink: str) -> str:
    """Эмодзи напитков"""
    emojis = {
        "пиво": "🍺", "вино": "🍷", "виски": "🥃", 
        "коктейль": "🍸", "шампанское": "🍾", "водка": "🥂",
        "кофе": "☕", "чай": "🫖", "сок": "🧃"
    }
    return emojis.get(drink, "🍹")

def create_main_keyboard():
    """Главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍺 Матчи сегодня", callback_data="today")],
        [InlineKeyboardButton(text="🎯 Анализ от бармена", callback_data="analyze")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
    ])

# ========== ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    status = "✅ БАРМЕН ГОТОВ" if neural_network.active else "❌ БАРМЕН ОТДЫХАЕТ"
    
    await message.answer(
        f"{get_drink_emoji('пиво')} <b>CS2 БАР «HEADSHOT»</b>\n\n"
        f"Бармен-аналитик: {status}\n\n"
        f"<i>Анализируем CS2 с кружкой пенного!</i>",
        reply_markup=create_main_keyboard()
    )

@dp.callback_query(F.data == "analyze")
async def handle_analyze(callback: types.CallbackQuery):
    """Анализ матча"""
    await callback.answer("🎯 Бармен готовится...")
    
    if not neural_network.active:
        await callback.message.edit_text(
            f"{get_drink_emoji('пиво')} <b>БАРМЕН ОТДЫХАЕТ</b>\n\n"
            f"Добавьте DEEPSEEK_API_KEY в настройки!",
            reply_markup=create_main_keyboard()
        )
        return
    
    # Тестовый анализ
    try:
        analysis = await neural_network.analyze_match(
            "NAVI", "Vitality", "ESL Pro League", "20:00"
        )
        
        pred = analysis["match_prediction"]
        
        await callback.message.edit_text(
            f"{get_drink_emoji('шампанское')} <b>АНАЛИЗ ОТ БАРМЕНА</b>\n\n"
            f"🎯 NAVI 🆚 Vitality\n"
            f"🏆 ESL Pro League\n\n"
            f"🍺 Победитель: <b>{pred['likely_winner']}</b>\n"
            f"📊 Вероятность: <b>{pred['probability']}%</b>\n"
            f"⚡ Счет: <b>{pred['score_prediction']}</b>\n"
            f"🎲 Риск: <b>{pred['risk_level']}</b>\n\n"
            f"<i>{pred.get('bar_metaphor', 'Интересный матч!')}</i>",
            reply_markup=create_main_keyboard()
        )
        
    except Exception as e:
        await callback.message.edit_text(
            f"{get_drink_emoji('пиво')} <b>ОШИБКА</b>\n\n{str(e)}",
            reply_markup=create_main_keyboard()
        )

@dp.callback_query(F.data == "today")
async def handle_today(callback: types.CallbackQuery):
    """Матчи сегодня"""
    await callback.answer("🍺 Загружаю...")
    
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await callback.message.edit_text(
            "🍻 Сегодня тихо в баре...",
            reply_markup=create_main_keyboard()
        )
        return
    
    text = f"{get_drink_emoji('пиво')} <b>МАТЧИ СЕГОДНЯ</b>\n\n"
    for match in matches[:5]:
        teams = match.get("opponents", [])
        if len(teams) >= 2:
            t1 = teams[0].get("opponent", {}).get("name", "?")
            t2 = teams[1].get("opponent", {}).get("name", "?")
            text += f"• {t1} 🆚 {t2}\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=create_main_keyboard()
    )

@dp.callback_query(F.data == "settings")
async def handle_settings(callback: types.CallbackQuery):
    """Настройки"""
    status = "✅ АКТИВЕН" if neural_network.active else "❌ НЕ АКТИВЕН"
    
    await callback.message.edit_text(
        f"{get_drink_emoji('коктейль')} <b>НАСТРОЙКИ БАРА</b>\n\n"
        f"Бармен: {status}\n"
        f"API ключ: {'✅' if DEEPSEEK_API_KEY else '❌'}\n\n"
        f"<i>Для активации бармена добавьте DEEPSEEK_API_KEY в Railway Variables</i>",
        reply_markup=create_main_keyboard()
    )

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Тест нейросети"""
    try:
        if neural_network.active:
            await message.answer("✅ Нейросеть активна!")
        else:
            await message.answer("❌ Нейросеть не активна")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("analyze"))
async def cmd_analyze(message: types.Message):
    """Анализ команды"""
    args = message.text.split()
    if len(args) < 3:
        await message.answer("Используйте: /analyze Team1 Team2")
        return
    
    team1, team2 = args[1], args[2]
    
    try:
        analysis = await neural_network.analyze_match(team1, team2)
        pred = analysis["match_prediction"]
        
        await message.answer(
            f"🎯 {team1} 🆚 {team2}\n"
            f"Победитель: {pred['likely_winner']}\n"
            f"Вероятность: {pred['probability']}%\n"
            f"Счет: {pred['score_prediction']}"
        )
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")

# ========== ЗАПУСК ==========
async def main():
    """Запуск бота"""
    logger.info("=" * 50)
    logger.info("🍺 ЗАПУСК CS2 БАРА")
    logger.info("=" * 50)
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Нет TELEGRAM_BOT_TOKEN")
        return
    
    if not PANDASCORE_TOKEN:
        logger.warning("⚠️ Нет PANDASCORE_TOKEN")
    
    logger.info(f"🤖 Бармен: {'✅ ГОТОВ' if neural_network.active else '❌ НЕ АКТИВЕН'}")
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await panda_api.close()

if __name__ == "__main__":
    asyncio.run(main())