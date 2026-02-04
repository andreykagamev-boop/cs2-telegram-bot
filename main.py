import os
import asyncio
import logging
import json
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PANDASCORE_TOKEN = os.getenv("PANDASCORE_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # Ключ Groq

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ========== GROQ AI НЕЙРОСЕТЬ ==========
class GroqNeuralNetwork:
    """Нейросеть через Groq API (Llama, Mixtral, Gemma)"""
    
    def __init__(self):
        self.active = False
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        logger.info("🧠 Инициализация Groq AI...")
        
        if not GROQ_API_KEY:
            logger.error("❌ GROQ_API_KEY не найден")
            logger.info("💡 Получите БЕСПЛАТНЫЙ ключ: https://console.groq.com")
            return
        
        # Проверяем формат ключа
        if not GROQ_API_KEY.startswith('gsk_'):
            logger.error(f"❌ Неверный формат ключа Groq. Должен начинаться с 'gsk_'")
            return
        
        self.active = True
        logger.info("✅ Groq AI активирован")
    
    async def analyze_match(self, team1: str, team2: str, tournament: str = "", 
                          match_time: str = "") -> Dict:
        """Анализ матча через Groq API"""
        if not self.active:
            raise Exception("Groq не активирован. Проверьте GROQ_API_KEY")
        
        try:
            # Промпт в стиле бара
            prompt = self._create_bar_prompt(team1, team2, tournament, match_time)
            
            logger.info(f"🍺 Groq AI анализирует: {team1} vs {team2}")
            
            # Доступные бесплатные модели Groq
            models = [
                "llama3-70b-8192",      # Llama 3 70B - самая мощная
                "mixtral-8x7b-32768",   # Mixtral 8x7B
                "gemma-7b-it"           # Gemma 7B
            ]
            
            # Пробуем модели по очереди
            for model in models:
                try:
                    response = await self._make_groq_request(model, prompt)
                    
                    # Парсим JSON ответ
                    result_text = response["choices"][0]["message"]["content"]
                    result_text = result_text.replace("```json", "").replace("```", "").strip()
                    
                    result = json.loads(result_text)
                    
                    # Добавляем метаданные
                    result["source"] = "Groq AI"
                    result["model"] = model
                    result["analysis_time"] = datetime.now().strftime("%d.%m.%Y %H:%M")
                    result["bar_name"] = "CS2 Бар 'HeadShot'"
                    
                    logger.info(f"✅ Использована модель: {model}")
                    return result
                    
                except Exception as e:
                    logger.warning(f"⚠️ Модель {model} не сработала: {e}")
                    continue
            
            raise Exception("Все модели Groq недоступны")
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            raise Exception(f"AI вернул некорректный JSON")
        except Exception as e:
            logger.error(f"❌ Ошибка анализа: {e}")
            raise Exception(f"Ошибка Groq AI: {str(e)}")
    
    async def _make_groq_request(self, model: str, prompt: str) -> Dict:
        """Запрос к Groq API"""
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system", 
                    "content": "Ты бармен-эксперт по CS2. Отвечай ТОЛЬКО в JSON формате."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"}
        }
        
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=self.headers, json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Groq API error {response.status}: {error_text[:200]}")
    
    def _create_bar_prompt(self, team1: str, team2: str, tournament: str, match_time: str) -> str:
        """Создание промпта для анализа"""
        return f"""
Ты - лучший бармен и аналитик CS2 в мире! Ты работаешь в легендарном баре "HeadShot".
Твои анализы славятся точностью, юмором и креативом.

🎯 ПРОАНАЛИЗИРУЙ МАТЧ:
• Команда 1: {team1}
• Команда 2: {team2}
• Турнир: {tournament if tournament else 'Не указан'}
• Время: {match_time if match_time else 'Скоро'}
• Дата анализа: {datetime.now().strftime('%d.%m.%Y %H:%M MSK')}

📊 ТВОИ ЗАДАЧИ:
1. Оценить силу команд (1-100 баллов)
2. Дать точный прогноз победителя
3. Предсказать счет
4. Проанализировать ключевые факторы
5. Добавить барного юмора и метафор
6. Рекомендовать напитки

🎲 ВЕРНИ ОТВЕТ В СТРОГОМ JSON ФОРМАТЕ:
{{
  "bar_intro": "Креативное приветствие в стиле бара",
  "team1_analysis": {{
    "strength": "число от 1 до 100",
    "nickname": "забавное прозвище в баре",
    "current_form": "описание текущей формы",
    "key_strengths": ["сила1", "сила2", "сила3"],
    "weaknesses": ["слабость1", "слабость2"],
    "recommended_drink": "напиток для команды"
  }},
  "team2_analysis": {{ ... }},
  "match_prediction": {{
    "likely_winner": "название команды",
    "probability": "число от 0 до 100",
    "score_prediction": "например: 2:1",
    "confidence": "число от 0 до 100",
    "risk_level": "LOW/MEDIUM/HIGH",
    "bar_metaphor": "сравнение матча с напитком"
  }},
  "key_factors": ["фактор1", "фактор2", "фактор3", "фактор4"],
  "recommended_bets": [
    {{
      "type": "тип ставки (П1, Тотал и т.д.)",
      "reason": "обоснование с юмором",
      "confidence": "LOW/MEDIUM/HIGH",
      "recommended_drink": "напиток для этой ставки"
    }}
  ],
  "detailed_analysis": "Развернутый анализ на 3-4 предложения",
  "bar_tip": "Мудрый совет бармена",
  "funny_comment": "Забавная шутка про матч"
}}

🔥 БУДЬ КРЕАТИВНЫМ, ТОЧНЫМ И ЗАБАВНЫМ! ДОБАВЬ БАРНОГО ШАРМА!
"""

# ========== ИНИЦИАЛИЗАЦИЯ НЕЙРОСЕТИ ==========
neural_network = GroqNeuralNetwork()

# ========== ПАНДАСКОР API ==========
class PandaScoreAPI:
    """API для получения матчей"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_today_matches(self) -> List[Dict]:
        """Получить матчи на сегодня"""
        if not self.token:
            return []
        
        try:
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{today.isoformat()},{tomorrow.isoformat()}",
                "per_page": 20,
                "sort": "scheduled_at"
            }
            
            if self.session is None:
                self.session = aiohttp.ClientSession(headers=self.headers)
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    logger.info(f"📊 Получено матчей: {len(matches)}")
                    return matches
                return []
        except Exception as e:
            logger.error(f"Ошибка PandaScore: {e}")
            return []

# ========== ИНИЦИАЛИЗАЦИЯ API ==========
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_drink_emoji(drink_type: str = "") -> str:
    """Эмодзи напитков"""
    emoji_map = {
        "пиво": "🍺", "вино": "🍷", "виски": "🥃", 
        "коктейль": "🍸", "шампанское": "🍾", "водка": "🥂",
        "ром": "🏝️", "джин": "🍶", "текила": "🌵",
        "кофе": "☕", "чай": "🫖", "сок": "🧃", "вода": "💧"
    }
    
    if drink_type:
        for key, emoji in emoji_map.items():
            if key in drink_type.lower():
                return emoji
    
    return random.choice(list(emoji_map.values()))

def create_main_keyboard():
    """Главное меню бара"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🍺 Матчи сегодня", callback_data="matches"),
            InlineKeyboardButton(text="🎯 Анализ AI", callback_data="analyze_ai")
        ],
        [
            InlineKeyboardButton(text="⚡ Быстрый анализ", callback_data="quick_analyze"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
        ],
        [
            InlineKeyboardButton(text="ℹ️ О баре", callback_data="about"),
            InlineKeyboardButton(text="💎 Премиум", callback_data="premium")
        ]
    ])

# ========== ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    status = "✅ АКТИВНА" if neural_network.active else "❌ ТРЕБУЕТ КЛЮЧ"
    
    welcome = f"""
{get_drink_emoji()} <b>CS2 БАР «HEADSHOT»</b>

<i>Анализ матчей с настоящей нейросетью!</i>

🤖 <b>AI-бармен:</b> {status}
💎 <b>Технология:</b> Groq AI (Llama 3 70B)
⚡ <b>Скорость:</b> Молниеносная
🎯 <b>Точность:</b> Экспертная

📊 <b>Что умеет нейросеть:</b>
• Анализ силы команд
• Точные прогнозы победителей
• Прогноз счета
• Ключевые факторы матча
• Рекомендации по ставкам
• Барный юмор и метафоры

{f'🍸 <b>Нейросеть готова к работе!</b>' if neural_network.active else '🔑 <b>Для активации добавьте GROQ_API_KEY</b>'}

👇 <b>Выберите действие:</b>
"""
    
    await message.answer(welcome, reply_markup=create_main_keyboard())

@dp.callback_query(F.data == "analyze_ai")
async def handle_analyze_ai(callback: types.CallbackQuery):
    """Анализ от нейросети"""
    await callback.answer("🧠 Запускаю нейросеть...")
    
    if not neural_network.active:
        await callback.message.edit_text(
            f"{get_drink_emoji()} <b>НЕЙРОСЕТЬ НЕ АКТИВНА</b>\n\n"
            f"Для работы AI-бармена нужен GROQ_API_KEY\n\n"
            f"🎯 <b>Как получить БЕСПЛАТНЫЙ ключ:</b>\n"
            f"1. Зайдите на https://console.groq.com\n"
            f"2. Зарегистрируйтесь\n"
            f"3. Создайте API ключ\n"
            f"4. Добавьте в Railway Variables\n\n"
            f"<i>Ключ начинается с <code>gsk_</code></i>",
            reply_markup=create_main_keyboard()
        )
        return
    
    try:
        # Показываем статус анализа
        await callback.message.edit_text(
            f"{get_drink_emoji()} <b>НЕЙРОСЕТЬ АНАЛИЗИРУЕТ...</b>\n\n"
            f"🧠 Модель: Llama 3 70B\n"
            f"🎯 Матч: NAVI vs Vitality\n"
            f"🏆 Турнир: ESL Pro League\n\n"
            f"<i>Идет глубокий анализ. Это займет 10-15 секунд...</i>",
            disable_web_page_preview=True
        )
        
        # Запускаем анализ через нейросеть
        analysis = await neural_network.analyze_match(
            "NAVI", "Vitality", "ESL Pro League", "20:00"
        )
        
        # Форматируем результат
        pred = analysis.get("match_prediction", {})
        
        result = f"""
{get_drink_emoji()} <b>АНАЛИЗ ОТ НЕЙРОСЕТИ</b>
<i>{analysis.get('bar_intro', '🎯 Экспертный анализ от AI!')}</i>

🏆 <b>NAVI vs Vitality</b>
⏰ 20:00 MSK | 🏆 ESL Pro League

📊 <b>ПРОГНОЗ AI:</b>
• 🏆 Победитель: <b>{pred.get('likely_winner', '?')}</b>
• 🎯 Вероятность: <b>{pred.get('probability', 0)}%</b>
• ⚡ Счет: <b>{pred.get('score_prediction', '?')}</b>
• 💪 Уверенность: <b>{pred.get('confidence', 0)}%</b>
• 🎲 Риск: <b>{pred.get('risk_level', 'MEDIUM')}</b>

🍸 <b>МЕТАФОРА:</b> {pred.get('bar_metaphor', 'Интересный матч!')}

🎯 <b>КЛЮЧЕВЫЕ ФАКТОРЫ:</b>
"""
        
        # Добавляем факторы
        factors = analysis.get("key_factors", [])
        for factor in factors[:3]:
            result += f"• {factor}\n"
        
        # Добавляем рекомендации
        bets = analysis.get("recommended_bets", [])
        if bets:
            result += f"\n💰 <b>РЕКОМЕНДАЦИИ AI:</b>\n"
            for bet in bets[:2]:
                drink_emoji = get_drink_emoji(bet.get("recommended_drink", ""))
                result += f"• {drink_emoji} <b>{bet.get('type', '?')}</b>\n"
                result += f"  <i>{bet.get('reason', '')}</i>\n"
        
        result += f"""
💡 <b>СОВЕТ БАРМЕНА:</b>
{analysis.get('bar_tip', 'Наслаждайтесь игрой!')}

😄 <b>КОММЕНТАРИЙ:</b>
{analysis.get('funny_comment', 'Будет жарко!')}

🤖 <i>Анализ от {analysis.get('source', 'AI')} ({analysis.get('model', '?')})</i>
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 ЗАКАЗАТЬ СВОЙ АНАЛИЗ", callback_data="custom_ai")],
            [InlineKeyboardButton(text="🍺 ДРУГОЙ МАТЧ", callback_data="analyze_ai")],
            [InlineKeyboardButton(text="🏠 В БАР", callback_data="back")]
        ])
        
        await callback.message.edit_text(result, reply_markup=keyboard, disable_web_page_preview=True)
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка анализа: {error_msg}")
        
        await callback.message.edit_text(
            f"{get_drink_emoji()} <b>ОШИБКА АНАЛИЗА</b>\n\n"
            f"Нейросеть не справилась:\n"
            f"<code>{error_msg[:150]}</code>\n\n"
            f"<i>Попробуйте снова или проверьте API ключ</i>",
            reply_markup=create_main_keyboard()
        )

@dp.callback_query(F.data == "custom_ai")
async def handle_custom_ai(callback: types.CallbackQuery):
    """Заказ кастомного анализа"""
    await callback.answer("📝 Готовлю форму заказа...")
    
    await callback.message.edit_text(
        f"{get_drink_emoji()} <b>ЗАКАЗ АНАЛИЗА ОТ НЕЙРОСЕТИ</b>\n\n"
        f"Чтобы нейросеть проанализировала конкретный матч,\n"
        f"используйте команду:\n\n"
        f"<code>/ai NAVI Vitality</code>\n\n"
        f"Или с турниром:\n"
        f"<code>/ai FaZe G2 BLAST Premier</code>\n\n"
        f"🎯 <b>Примеры:</b>\n"
        f"<code>/ai Spirit Cloud9</code>\n"
        f"<code>/ai Heroic Astralis IEM Katowice</code>\n\n"
        f"<i>Нейросеть проведет глубокий анализ за 15-20 секунд</i>",
        reply_markup=create_main_keyboard()
    )

@dp.callback_query(F.data == "matches")
async def handle_matches(callback: types.CallbackQuery):
    """Матчи сегодня"""
    await callback.answer("📊 Загружаю матчи...")
    
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await callback.message.edit_text(
            f"{get_drink_emoji()} <b>СЕГОДНЯ ТИХО</b>\n\n"
            f"На сегодня нет запланированных матчей CS2.\n\n"
            f"<i>Используйте команду /ai для анализа любого матча!</i>",
            reply_markup=create_main_keyboard()
        )
        return
    
    text = f"{get_drink_emoji()} <b>МАТЧИ СЕГОДНЯ</b>\n\n"
    
    for i, match in enumerate(matches[:8], 1):
        opponents = match.get("opponents", [])
        if len(opponents) >= 2:
            t1 = opponents[0].get("opponent", {}).get("name", "?")
            t2 = opponents[1].get("opponent", {}).get("name", "?")
            
            time = match.get("scheduled_at", "")
            if time:
                try:
                    dt = datetime.fromisoformat(time.replace('Z', '+00:00'))
                    dt = dt + timedelta(hours=3)  # MSK
                    time_str = dt.strftime("%H:%M")
                except:
                    time_str = "Скоро"
            else:
                time_str = "Скоро"
            
            text += f"{i}. <b>{t1}</b> 🆚 <b>{t2}</b>\n"
            text += f"   ⏰ {time_str} MSK\n\n"
    
    text += "<i>Используйте команду /ai Team1 Team2 для анализа</i>"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 ПРОАНАЛИЗИРОВАТЬ МАТЧ", callback_data="analyze_ai")],
        [InlineKeyboardButton(text="🏠 В БАР", callback_data="back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.message(Command("ai"))
async def cmd_ai_analyze(message: types.Message):
    """Анализ матча через команду"""
    args = message.text.split()
    
    if len(args) < 3:
        await message.answer(
            f"{get_drink_emoji()} <b>ИСПОЛЬЗУЙТЕ:</b>\n"
            f"<code>/ai NAVI Vitality</code>\n\n"
            f"Или с турниром:\n"
            f"<code>/ai FaZe G2 ESL Pro League</code>"
        )
        return
    
    if not neural_network.active:
        await message.answer(
            f"{get_drink_emoji()} <b>НЕЙРОСЕТЬ НЕ АКТИВНА</b>\n\n"
            f"Добавьте GROQ_API_KEY в настройки"
        )
        return
    
    team1 = args[1]
    team2 = args[2]
    tournament = " ".join(args[3:]) if len(args) > 3 else ""
    
    try:
        status_msg = await message.answer(
            f"{get_drink_emoji()} <b>🧠 ЗАПУСКАЮ НЕЙРОСЕТЬ...</b>\n\n"
            f"🎯 Анализирую: {team1} vs {team2}\n"
            f"🏆 {tournament if tournament else 'Матч'}\n\n"
            f"<i>Глубокий анализ займет 15-20 секунд...</i>"
        )
        
        analysis = await neural_network.analyze_match(team1, team2, tournament)
        pred = analysis.get("match_prediction", {})
        
        result = f"""
{get_drink_emoji()} <b>АНАЛИЗ НЕЙРОСЕТИ</b>

🎯 <b>{team1} 🆚 {team2}</b>
{f'🏆 {tournament}' if tournament else ''}

📊 <b>ПРОГНОЗ AI:</b>
• 🏆 Победитель: <b>{pred.get('likely_winner', '?')}</b>
• 🎯 Вероятность: <b>{pred.get('probability', 0)}%</b>
• ⚡ Счет: <b>{pred.get('score_prediction', '?')}</b>
• 💪 Уверенность: <b>{pred.get('confidence', 0)}%</b>
• 🎲 Риск: <b>{pred.get('risk_level', 'MEDIUM')}</ <b>ПРОГНОЗ AI:</b>
• 🏆 Победитель: <b>{pred.get('likely_winner', '?')}</b>
• 🎯 Вероятность: <b>{pred.get('probability', 0)}%</b>
• ⚡ Счет: <b>{pred.get('score_prediction', '?')}</b>
• 💪 Уверенность: <b>{pred.get('confidence', 0)}%</b>
• 🎲 Риск: <b>{pred.get('risk_level', 'MEDIUMb>

🍸 <b>МЕТАФОРА:</b>
{pred.get('bar_metaphor', 'Интересный матч!')}

💡 <b>СОВЕТ БАРМЕНА:</b>
{analysis.get('bar_tip', 'Наслаждайтесь игрой!')}

🤖 <i>Анализ от {analysis.get('source', 'AI')}</')}</b>

🍸 <b>МЕТАФОРА:</b>
{pred.get('bar_metaphor', 'Интересный матч!')}

💡 <b>СОВЕТ БАРМЕНА:</b>
{analysis.get('bar_tip', 'Наслаждайтесь игрой!')}

🤖 <i>Анализ от {analysis.get('source', 'AI')}</i>
"""
        
        await status_msg.edit_text(result, disable_web_page_preview=True)
        
    except Exception as e:
        await message.answer(
            f"{get_drink_emoji()} <b>ОШИБКА АНАЛИЗА</b>\n\n"
            f"<code>{str(e)[:150]}</code>"
        )

@dp.callback_query(F.data == "settings")
async def handle_settings(callback: types.CallbackQuery):
    """Настройки"""
    status = "✅ АКТИВНА" if neural_network.active else "❌ ТРЕБУЕТ КЛЮЧ"
    
    text = f"""
{get_drink_emoji()} <b>НАСТРОЙКИ НЕЙРОСЕТИ</b>

🤖 <b>Статус AI:</b> {status}
💎 <b>Провайдер:</b> Groq Cloud
🚀 <b>Модель:</b> Llama 3 70B (бесплатно)
⚡ <b>Скорость:</b> 300+ tokens/сек

🔑 <b>Требуется:</b> GROQ_API_KEY
🎯 <b>Как получить:</b>
1. Зайдите на console.groq.com
2. Зарегистрируйтесь
3. Создайте API ключ
4. Добавьте в Railway Variables

📊 <b>Текущие настройки:</b>
• TEi>
"""
        
        await status_msg.edit_text(result, disable_web_page_preview=True)
        
    except Exception as e:
        await message.answer(
            f"{get_drink_emoji()} <b>ОШИБКА АНАЛИЗА</b>\n\n"
            f"<code>{str(e)[:150]}</code>"
        )

@dp.callback_query(F.data == "settings")
async def handle_settings(callback: types.CallbackQuery):
    """Настройки"""
    status = "✅ АКТИВНА" if neural_network.active else "❌ ТРЕБУЕТ КЛЮЧ"
    
    text = f"""
{get_drink_emoji()} <b>НАСТРОЙКИ НЕЙРОСЕТИ</b>

🤖 <b>Статус AI:</b> {status}
💎 <b>Провайдер:</b> Groq Cloud
🚀 <b>Модель:</b> Llama 3 70B (бесплатно)
⚡ <b>Скорость:</b> 300+ tokens/сек

🔑 <b>Требуется:</b> GROQ_API_KEY
🎯 <b>Как получить:</b>
1. Зайдите на console.groq.com
2. Зарегистрируйтесь
3. Создайте API ключ
4. Добавьте в Railway Variables

📊 <b>Текущие настройки:</b>
• TELEGRAMLEGRAM_BOT_BOT_TOKEN:_TOKEN: {'✅ {'✅' if' if TELEGRAM_BOT_TOKEN else '❌ TELEGRAM_BOT_TOKEN else '❌'}
•'}
• GROQ GROQ_API_KEY_API_KEY: {': {'✅'✅' if GRO if GROQ_API_KEY elseQ_API_KEY else ' '❌'}
❌'}
• P• PANDASCANDASCORE_TOKENORE_TOKEN: {': {'✅'✅' if PANDASCORE_TOKEN else '❌'}

{f'🍸 <b>Нейросеть готова к работе!</b>' if neural_network.active else '🔑 <b>Добавьте GROQ_API_KEY для активации</b>'}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ПРОВЕРИТЬ ПОДКЛЮЧЕНИЕ", callback_data="check_ai")],
        [InlineKeyboardButton(text="🍺 В БАР", callback_data="back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data == if PANDASCORE_TOKEN else '❌'}

{f'🍸 <b>Нейросеть готова к работе!</b>' if neural_network.active else '🔑 <b>Добавьте GROQ_API_KEY для активации</b>'}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ПРОВЕРИТЬ ПОДКЛЮЧЕНИЕ", callback_data="check_ai")],
        [InlineKeyboardButton(text="🍺 В БАР", callback_data="back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data == "back")
async def handle_back(callback: types.C "back")
async def handle_back(callback: types.CallbackQuery):
   allbackQuery):
    """Назад"""
    await cmd_start(callback.message)
    await """Назад"""
    await cmd_start(callback.message)
    await callback.answer()

# ========== ЗАПУСК ==========
async def callback.answer()

# ========== ЗАПУСК ==========
async def main():
    """Запуск бота"""
    logger.info("=" * 50)
    main():
    """Запуск бота"""
    logger.info("=" * 50)
    logger.info("🤖 ЗАПУСК CS2 БАРА С НЕЙРОСЕТЬЮ")
    logger.info("=" * 50)
 logger.info("🤖 ЗАПУСК CS2 БАРА С НЕЙРОСЕТЬЮ")
    logger.info("=" * 50)
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Нет TELEGRAM_BOT_TOKEN")
        return
    
    logger.info(f"🤖 Нейросеть: {'✅ АКТИВНА' if neural_network.active else '❌    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Нет TELEGRAM_BOT_TOKEN")
        return
    
    logger.info(f"🤖 Нейросеть: {'✅ АКТИВНА' if neural_network.active else '❌ ТРЕБУЕТ КЛЮЧ'}")
    
    if not neural_network.active:
        logger.info("💡 Для активации добавьте GROQ_API_KEY в Railway Variables")
        logger.info ТРЕБУЕТ КЛЮЧ'}")
    
    if not neural_network.active:
        logger.info("💡 Для активации добавьте GROQ_API_KEY в Railway Variables")
        logger.info("("🔗 Получите ключ: https://console.groq.com")
    
    try:
        logger.info("🚀 Запускаю бота...")
        await dp.start_polling🔗 Получите ключ: https://console.groq.com")
    
    try:
        logger.info("🚀 Запускаю бота...")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

if __name__ == "__main(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())