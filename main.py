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

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Конфигурация
PANDASCORE_TOKEN = os.getenv("PANDASCORE_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # Новый ключ

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ========== AI АНАЛИЗ ЧЕРЕЗ OPENROUTER ==========
try:
    from openai import AsyncOpenAI
    AI_AVAILABLE = True
    logger.info("✅ OpenAI библиотека доступна")
except ImportError:
    AI_AVAILABLE = False
    logger.warning("❌ OpenAI библиотека не установлена")

class BarAnalystAI:
    """AI-аналитик для бара через OpenRouter"""
    
    def __init__(self):
        self.active = False
        self.client = None
        
        logger.info("🧠 Инициализация AI-бармена...")
        
        if not AI_AVAILABLE:
            logger.error("❌ Библиотека OpenAI недоступна")
            return
        
        if not OPENROUTER_API_KEY:
            logger.error("❌ OPENROUTER_API_KEY не найден")
            logger.info("💡 Получите бесплатный ключ на openrouter.ai")
            return
        
        try:
            # OpenRouter клиент
            self.client = AsyncOpenAI(
                api_key=OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://cs2-bar-bot.com",  # Ваш сайт
                    "X-Title": "CS2 Bar Bot"  # Название приложения
                }
            )
            
            self.active = True
            logger.info("✅ AI-бармен активирован через OpenRouter")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            self.active = False
    
    async def analyze_match(self, team1: str, team2: str, tournament: str = "", 
                          match_time: str = "") -> Dict:
        """Анализ матча через AI"""
        if not self.active:
            # Fallback на локальный анализ
            return await self._local_analysis(team1, team2, tournament)
        
        try:
            prompt = self._create_bar_prompt(team1, team2, tournament, match_time)
            
            logger.info(f"🍺 Бармен анализирует: {team1} vs {team2}")
            
            # Пробуем разные бесплатные модели
            models_to_try = [
                "google/gemini-2.0-flash-exp:free",  # Бесплатный Gemini
                "meta-llama/llama-3.2-3b-instruct:free",  # Бесплатный Llama
                "microsoft/phi-3-medium-128k-instruct:free",  # Бесплатный Phi-3
                "qwen/qwen-2.5-32b-instruct:free",  # Бесплатный Qwen
            ]
            
            response = None
            last_error = None
            
            for model in models_to_try:
                try:
                    response = await self.client.chat.completions.create(
                        model=model,
                        messages=[
                            {
                                "role": "system",
                                "content": "Ты бармен-аналитик CS2. Отвечай в JSON с юмором."
                            },
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        max_tokens=1000,
                        response_format={"type": "json_object"}
                    )
                    logger.info(f"✅ Использована модель: {model}")
                    break
                except Exception as e:
                    last_error = e
                    continue
            
            if not response:
                logger.warning("⚠️ Все модели недоступны, использую локальный анализ")
                return await self._local_analysis(team1, team2, tournament)
            
            result = json.loads(response.choices[0].message.content)
            
            # Обогащаем результат
            result["source"] = "AI-бармен (OpenRouter)"
            result["analysis_time"] = datetime.now().strftime("%d.%m.%Y %H:%M")
            result["bar_name"] = "CS2 Бар 'HeadShot'"
            
            return result
            
        except Exception as e:
            logger.error(f"🍻 Ошибка AI анализа: {e}")
            return await self._local_analysis(team1, team2, tournament)
    
    def _create_bar_prompt(self, team1: str, team2: str, tournament: str, match_time: str) -> str:
        """Создание промпта в стиле бара"""
        return f"""
Ты - бармен в киберспортивном баре "HeadShot". Проанализируй матч CS2:

Команда 1: {team1}
Команда 2: {team2}
Турнир: {tournament if tournament else 'Не указан'}
Время: {match_time if match_time else 'Скоро'}

Дай прогноз в JSON формате:
{{
  "bar_intro": "веселое приветствие",
  "team1_analysis": {{
    "strength": число от 1 до 100,
    "nickname": "прозвище в баре",
    "form": "текущая форма",
    "strengths": ["сила1", "сила2"],
    "weaknesses": ["слабость1", "слабость2"]
  }},
  "team2_analysis": {{ ... }},
  "match_prediction": {{
    "winner": "имя команды",
    "probability": число,
    "score": "например 2:1",
    "confidence": число,
    "risk": "LOW/MEDIUM/HIGH",
    "metaphor": "сравнение с напитком"
  }},
  "key_factors": ["фактор1", "фактор2"],
  "recommendations": [
    {{
      "bet": "тип ставки",
      "reason": "обоснование",
      "drink": "рекомендуемый напиток"
    }}
  ],
  "analysis": "краткий анализ",
  "bar_tip": "совет бармена",
  "joke": "шутка про матч"
}}

Будь креативным и забавным!
"""
    
    async def _local_analysis(self, team1: str, team2: str, tournament: str) -> Dict:
        """Локальный fallback анализ"""
        import random
        
        drinks = ["🍺 Пиво", "🍷 Вино", "🥃 Виски", "🍸 Коктейль", "🍾 Шампанское"]
        drink = random.choice(drinks)
        
        # Простая логика для демонстрации
        winner = random.choice([team1, team2])
        prob = random.randint(55, 85)
        
        return {
            "bar_intro": f"🍻 Добро пожаловать в бар 'HeadShot'!",
            "team1_analysis": {
                "strength": random.randint(70, 95),
                "nickname": f"Команда '{team1[:3]}'",
                "form": "Хорошая форма",
                "strengths": ["Опытные игроки", "Хорошая тактика"],
                "weaknesses": ["Иногда нестабильны"]
            },
            "team2_analysis": {
                "strength": random.randint(70, 95),
                "nickname": f"Команда '{team2[:3]}'",
                "form": "Стабильная игра",
                "strengths": ["Молодая энергия", "Агрессивный стиль"],
                "weaknesses": ["Недостаток опыта"]
            },
            "match_prediction": {
                "winner": winner,
                "probability": prob,
                "score": random.choice(["2:0", "2:1", "1:2"]),
                "confidence": random.randint(60, 90),
                "risk": random.choice(["LOW", "MEDIUM", "HIGH"]),
                "metaphor": f"Крепкий матч как {drink}!"
            },
            "key_factors": ["Форма команд", "Мотивация", "Составы"],
            "recommendations": [
                {
                    "bet": f"Победа {winner}",
                    "reason": f"Вероятность {prob}%",
                    "drink": drink
                }
            ],
            "analysis": f"Интересный матч между {team1} и {team2}. Обе команды показывают хорошую игру в этом сезоне.",
            "bar_tip": "Наслаждайтесь игрой и хорошей компанией!",
            "joke": "Бармен советует: играйте ответственно, а пейте - умеренно!",
            "source": "Локальный бармен",
            "analysis_time": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "bar_name": "CS2 Бар 'HeadShot'"
        }

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bar_analyst = BarAnalystAI()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_drink_emoji():
    drinks = ["🍺", "🍷", "🥃", "🍸", "🍾", "🥂", "☕", "🍹"]
    import random
    return random.choice(drinks)

def create_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍺 Заказать анализ", callback_data="analyze")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="ℹ️ О баре", callback_data="about")]
    ])

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    status = "✅ ГОТОВ" if bar_analyst.active else "⚠️ ЛОКАЛЬНЫЙ РЕЖИМ"
    
    await message.answer(
        f"{get_drink_emoji()} <b>CS2 БАР «HEADSHOT»</b>\n\n"
        f"🤖 Бармен: {status}\n"
        f"🕐 {datetime.now().strftime('%H:%M MSK')}\n\n"
        f"<i>Анализ матчей с юмором и стилем!</i>",
        reply_markup=create_main_keyboard()
    )

@dp.callback_query(F.data == "analyze")
async def handle_analyze(callback: types.CallbackQuery):
    await callback.answer("🎯 Готовлю анализ...")
    
    try:
        analysis = await bar_analyst.analyze_match(
            "NAVI", "Vitality", "ESL Pro League", "20:00"
        )
        
        pred = analysis["match_prediction"]
        
        result = f"""
{get_drink_emoji()} <b>АНАЛИЗ ОТ БАРМЕНА</b>

{analysis.get('bar_intro', '🎯 Добро пожаловать!')}

🏆 <b>NAVI vs Vitality</b>
⏰ 20:00 MSK | 🏆 ESL Pro League

📊 <b>ПРОГНОЗ:</b>
• Победитель: <b>{pred.get('winner', 'Сложно сказать')}</b>
• Вероятность: <b>{pred.get('probability', 0)}%</b>
• Счет: <b>{pred.get('score', '?')}</b>
• Риск: <b>{pred.get('risk', 'MEDIUM')}</b>

🍸 <b>РЕКОМЕНДАЦИЯ:</b>
{analysis.get('recommendations', [{}])[0].get('bet', 'Наслаждайтесь игрой!')}
{analysis.get('recommendations', [{}])[0].get('reason', '')}

💡 <b>СОВЕТ:</b> {analysis.get('bar_tip', 'Играйте ответственно!')}

😄 {analysis.get('joke', 'Будет интересно!')}

<i>Источник: {analysis.get('source', 'Бармен')}</i>
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🍺 ЕЩЁ АНАЛИЗ", callback_data="analyze")],
            [InlineKeyboardButton(text="🏠 В БАР", callback_data="back")]
        ])
        
        await callback.message.edit_text(result, reply_markup=keyboard)
        
    except Exception as e:
        await callback.message.edit_text(
            f"{get_drink_emoji()} <b>ОШИБКА</b>\n\n{str(e)[:100]}",
            reply_markup=create_main_keyboard()
        )

@dp.callback_query(F.data == "settings")
async def handle_settings(callback: types.CallbackQuery):
    status = "✅ AI БАРМЕН" if bar_analyst.active else "⚠️ ЛОКАЛЬНЫЙ РЕЖИМ"
    
    await callback.answer("⚙️ Настройки...")
    
    text = f"""
{get_drink_emoji()} <b>НАСТРОЙКИ БАРА</b>

🤖 <b>Режим работы:</b> {status}

{"🎯 AI-бармен активен через OpenRouter" if bar_analyst.active else "🍺 Работает локальный бармен (без AI)"}

💡 <b>Для AI-режима:</b>
1. Зарегистрируйтесь на openrouter.ai
2. Получите API ключ
3. Добавьте в Railway как OPENROUTER_API_KEY
4. Перезапустите бота

📊 <b>Текущие настройки:</b>
• TELEGRAM_BOT_TOKEN: {'✅' if TELEGRAM_BOT_TOKEN else '❌'}
• OPENROUTER_API_KEY: {'✅' if OPENROUTER_API_KEY else '❌'}
"""
    
    await callback.message.edit_text(text, reply_markup=create_main_keyboard())

@dp.callback_query(F.data == "about")
async def handle_about(callback: types.CallbackQuery):
    await callback.answer("🍺 О нашем баре...")
    
    text = f"""
{get_drink_emoji()} <b>О БАРЕ «HEADSHOT»</b>

<i>Где киберспорт встречается с хорошей аналитикой!</i>

🎯 <b>Наша философия:</b>
Делаем анализ CS2 интересным, доступным и с юмором!

🍸 <b>Что предлагаем:</b>
• Анализ матчей от бармена
• Прогнозы и рекомендации
• Барный юмор и атмосферу
• Советы по ставкам (18+)

🤖 <b>Технологии:</b>
• AI-анализ через OpenRouter
• Локальный анализ как fallback
• PandaScore для данных матчей

⚡ <b>Почему мы:</b>
• Уникальный барный стиль
• Бесплатный анализ
• Креативный подход
• Настоящая атмосфера

<i>Заходите чаще - всегда рады гостям!</i>
"""
    
    await callback.message.edit_text(text, reply_markup=create_main_keyboard())

@dp.callback_query(F.data == "back")
async def handle_back(callback: types.CallbackQuery):
    await cmd_start(callback.message)
    await callback.answer()

@dp.message(Command("analyze"))
async def cmd_analyze_command(message: types.Message):
    """Команда анализа"""
    args = message.text.split()
    if len(args) < 3:
        await message.answer("Используйте: /analyze Team1 Team2 [Турнир]")
        return
    
    team1, team2 = args[1], args[2]
    tournament = " ".join(args[3:]) if len(args) > 3 else ""
    
    try:
        msg = await message.answer(f"{get_drink_emoji()} Бармен анализирует...")
        analysis = await bar_analyst.analyze_match(team1, team2, tournament)
        pred = analysis["match_prediction"]
        
        result = f"""
{get_drink_emoji()} <b>{team1} vs {team2}</b>

📊 Победитель: {pred.get('winner')}
🎯 Вероятность: {pred.get('probability')}%
⚡ Счет: {pred.get('score')}
🍸 Риск: {pred.get('risk')}

{analysis.get('bar_tip', 'Удачи!')}
"""
        await msg.edit_text(result)
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)[:100]}")

# ========== ЗАПУСК ==========
async def main():
    logger.info("=" * 50)
    logger.info("🍺 ЗАПУСК CS2 БАРА")
    logger.info("=" * 50)
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Нет TELEGRAM_BOT_TOKEN")
        return
    
    logger.info(f"🤖 Бармен: {'✅ AI РЕЖИМ' if bar_analyst.active else '⚠️ ЛОКАЛЬНЫЙ РЕЖИМ'}")
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())