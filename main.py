import os
import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
PANDASCORE_TOKEN = os.getenv("PANDASCORE_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ========== КЭШИРОВАНИЕ И СТАТИСТИКА ==========
class CacheManager:
    """Менеджер кэширования в памяти"""
    
    def __init__(self):
        self.cache = {}
        self.timestamps = {}
        self.ttl = 300  # 5 минут
        
    def get(self, key: str):
        """Получить данные из кэша"""
        if key in self.cache:
            timestamp = self.timestamps.get(key, 0)
            if (datetime.now().timestamp() - timestamp) < self.ttl:
                logger.info(f"Используется кэш: {key}")
                return self.cache[key]
        return None
    
    def set(self, key: str, data):
        """Сохранить данные в кэш"""
        self.cache[key] = data
        self.timestamps[key] = datetime.now().timestamp()
        
    def clear_old(self):
        """Очистить устаревший кэш"""
        current_time = datetime.now().timestamp()
        to_delete = []
        for key, timestamp in self.timestamps.items():
            if (current_time - timestamp) >= self.ttl:
                to_delete.append(key)
        for key in to_delete:
            self.cache.pop(key, None)
            self.timestamps.pop(key, None)

# Статистика бота
class BotStatistics:
    """Статистика использования бота"""
    
    def __init__(self):
        self.commands = defaultdict(int)
        self.users = set()
        self.start_time = datetime.now()
        self.popular_teams = defaultdict(int)
        
    def track_command(self, command: str, user_id: int):
        """Отслеживание команды"""
        self.commands[command] += 1
        self.users.add(user_id)
        
    def track_team_view(self, team_name: str):
        """Отслеживание просмотров команд"""
        if team_name and team_name != "TBA":
            self.popular_teams[team_name] += 1
    
    def get_stats_text(self) -> str:
        """Получить текст статистики"""
        uptime = datetime.now() - self.start_time
        days = uptime.days
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        
        # Топ-5 популярных команд
        top_teams = sorted(self.popular_teams.items(), key=lambda x: x[1], reverse=True)[:5]
        top_teams_text = "\n".join([f"  • {team}: {count}" for team, count in top_teams]) if top_teams else "  • Нет данных"
        
        return f"""
📊 <b>СТАТИСТИКА БОТА</b>

👥 <b>Пользователи:</b> {len(self.users)}
⏱️ <b>Работает:</b> {days}д {hours}ч {minutes}м
📈 <b>Команды:</b>
  • Всего: {sum(self.commands.values())}
  • /start: {self.commands.get('start', 0)}
  • /today: {self.commands.get('today', 0)}
  • /live: {self.commands.get('live', 0)}

🏆 <b>Популярные команды:</b>
{top_teams_text}
"""

# Инициализация
cache_manager = CacheManager()
bot_stats = BotStatistics()

# ========== УЛУЧШЕННЫЙ API КЛИЕНТ ==========
class PandaScoreAPI:
    """API клиент для CS2 с кэшированием"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
        return self.session
    
    async def get_upcoming_matches(self, days: int = 2):
        """Получить предстоящие матчи с кэшированием"""
        cache_key = f"upcoming_{days}"
        
        # Проверяем кэш
        cached = cache_manager.get(cache_key)
        if cached:
            return cached
        
        # Если нет в кэше, делаем запрос
        matches = await self._get_upcoming_matches_raw(days)
        
        # Сохраняем в кэш
        cache_manager.set(cache_key, matches)
        return matches
    
    async def _get_upcoming_matches_raw(self, days: int = 2):
        """Получить предстоящие матчи - оригинальный метод"""
        try:
            session = await self.get_session()
            
            # Получаем ВСЕ предстоящие матчи
            url = f"{self.base_url}/csgo/matches/upcoming"
            params = {
                "per_page": 100,
                "sort": "scheduled_at",
                "page": 1
            }
            
            logger.info("Запрос предстоящих матчей...")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    logger.info(f"Получено матчей: {len(matches)}")
                    
                    # Фильтруем по дате
                    now = datetime.utcnow()
                    filtered_matches = []
                    
                    for match in matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                
                                # Проверяем что матч в будущем
                                if match_time > now:
                                    # Фильтруем по количеству дней
                                    days_diff = (match_time.date() - now.date()).days
                                    if days_diff < days:
                                        filtered_matches.append(match)
                            except:
                                continue
                    
                    logger.info(f"После фильтрации: {len(filtered_matches)} матчей")
                    return filtered_matches
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка {response.status}: {error_text[:200]}")
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении матчей: {e}")
            return []
    
    async def get_today_matches(self):
        """Получить матчи только на сегодня с кэшированием"""
        cache_key = "today"
        
        cached = cache_manager.get(cache_key)
        if cached:
            return cached
        
        matches = await self._get_today_matches_raw()
        cache_manager.set(cache_key, matches)
        return matches
    
    async def _get_today_matches_raw(self):
        """Получить матчи только на сегодня - оригинальный метод"""
        try:
            session = await self.get_session()
            
            # Получаем текущую дату в UTC
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            
            # Форматируем даты для API
            today_str = today.isoformat()
            tomorrow_str = tomorrow.isoformat()
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{today_str},{tomorrow_str}",
                "per_page": 50,
                "sort": "scheduled_at",
                "filter[status]": "not_started"
            }
            
            logger.info(f"Запрос матчей с {today_str} по {tomorrow_str}")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    
                    # Фильтруем только сегодняшние
                    today_matches = []
                    for match in matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                if match_time.date() == today:
                                    today_matches.append(match)
                            except:
                                continue
                    
                    logger.info(f"Найдено матчей на сегодня: {len(today_matches)}")
                    return today_matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении сегодняшних матчей: {e}")
            return []
    
    async def get_tomorrow_matches(self):
        """Получить матчи только на завтра с кэшированием"""
        cache_key = "tomorrow"
        
        cached = cache_manager.get(cache_key)
        if cached:
            return cached
        
        matches = await self._get_tomorrow_matches_raw()
        cache_manager.set(cache_key, matches)
        return matches
    
    async def _get_tomorrow_matches_raw(self):
        """Получить матчи только на завтра - оригинальный метод"""
        try:
            session = await self.get_session()
            
            # Получаем дату завтра
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            day_after_tomorrow = today + timedelta(days=2)
            
            # Форматируем даты для API
            tomorrow_str = tomorrow.isoformat()
            day_after_tomorrow_str = day_after_tomorrow.isoformat()
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{tomorrow_str},{day_after_tomorrow_str}",
                "per_page": 50,
                "sort": "scheduled_at",
                "filter[status]": "not_started"
            }
            
            logger.info(f"Запрос матчей с {tomorrow_str} по {day_after_tomorrow_str}")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    
                    # Фильтруем только завтрашние
                    tomorrow_matches = []
                    for match in matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                if match_time.date() == tomorrow:
                                    tomorrow_matches.append(match)
                            except:
                                continue
                    
                    logger.info(f"Найдено матчей на завтра: {len(tomorrow_matches)}")
                    return tomorrow_matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении завтрашних матчей: {e}")
            return []
    
    async def get_live_matches(self):
        """Получить live матчи с коротким кэшированием"""
        cache_key = "live"
        
        cached = cache_manager.get(cache_key)
        if cached:
            return cached
        
        matches = await self._get_live_matches_raw()
        # Live матчи кэшируем всего на 60 секунд
        cache_manager.ttl = 60
        cache_manager.set(cache_key, matches)
        cache_manager.ttl = 300  # Возвращаем TTL
        return matches
    
    async def _get_live_matches_raw(self):
        """Получить live матчи - оригинальный метод"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/csgo/matches/running"
            
            params = {
                "per_page": 10,
                "sort": "-begin_at"
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    logger.info(f"Найдено live матчей: {len(matches)}")
                    return matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении live матчей: {e}")
            return []
    
    async def get_tournaments(self, limit: int = 5):
        """Получить текущие турниры"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/csgo/tournaments/running"
            
            params = {
                "per_page": limit,
                "sort": "-begin_at"
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return []
        except Exception as e:
            logger.error(f"Ошибка при получении турниров: {e}")
            return []
    
    async def get_team_info(self, team_name: str):
        """Получить информацию о команде"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/csgo/teams"
            
            params = {
                "search[name]": team_name,
                "per_page": 1
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    teams = await response.json()
                    return teams[0] if teams else None
                else:
                    return None
        except Exception as e:
            logger.error(f"Ошибка при поиске команды: {e}")
            return None
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

# ========== УЛУЧШЕННЫЕ ФУНКЦИИ ФОРМАТИРОВАНИЯ ==========

def format_match_time(scheduled_at: str) -> str:
    """Форматирование времени в MSK с проверкой"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        
        # Если матч сегодня, показываем только время
        now = datetime.utcnow() + timedelta(hours=3)
        if dt_msk.date() == now.date():
            return dt_msk.strftime("%H:%M")
        else:
            return dt_msk.strftime("%d.%m %H:%M")
    except:
        return "Скоро"

def get_team_emoji(team_name: str) -> str:
    """Эмодзи для команд - расширенный список"""
    if not team_name:
        return "🎮"
    
    team_lower = team_name.lower()
    
    emoji_map = {
        "navi": "🟡", "natus": "🟡",
        "vitality": "🐝", "vita": "🐝",
        "faze": "⚡", "faze clan": "⚡",
        "g2": "👑", "g2 esports": "👑",
        "spirit": "🐉", "team spirit": "🐉",
        "cloud9": "☁️", "c9": "☁️",
        "liquid": "💧", "team liquid": "💧",
        "heroic": "⚔️",
        "astralis": "⭐",
        "ence": "🇫🇮",
        "furia": "🔥", "furia esports": "🔥",
        "virtus.pro": "🐻", "vp": "🐻", "virtus pro": "🐻",
        "mouz": "🐭", "mousesports": "🐭",
        "nip": "🤖", "ninjas in pyjamas": "🤖",
        "big": "🇩🇪",
        "og": "⚫",
        "fnatic": "🟠",
        "complexity": "🔴",
        "9z": "9️⃣",
        "imperial": "👑",
        "pain": "😖",
        "saw": "🔪",
        "forze": "💪",
        "betboom": "💣",
        "monte": "🎲",
        "apeks": "🦍",
        "m80": "🎯",
        "flyquest": "✈️",
        "leviatan": "🐉",
        "theunion": "🛡️"
    }
    
    for key, emoji in emoji_map.items():
        if key in team_lower:
            return emoji
    
    return "🎮"

def get_match_format(match: Dict) -> str:
    """Получить формат матча (BO1, BO3 и т.д.)"""
    match_type = match.get("match_type", "").upper()
    if match_type:
        return f" | {match_type}"
    return ""

def format_upcoming_match(match: Dict, index: int) -> str:
    """Форматирование предстоящего матча с деталями"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1 = opponents[0].get("opponent", {})
        team2 = opponents[1].get("opponent", {})
        
        team1_name = team1.get("acronym") or team1.get("name", "TBA")
        team2_name = team2.get("acronym") or team2.get("name", "TBA")
        
        # Трекируем просмотры команд
        bot_stats.track_team_view(team1_name)
        bot_stats.track_team_view(team2_name)
        
        team1_emoji = get_team_emoji(team1_name)
        team2_emoji = get_team_emoji(team2_name)
        
        league = match.get("league", {}).get("name", "")
        scheduled_at = match.get("scheduled_at", "")
        time_str = format_match_time(scheduled_at)
        match_format = get_match_format(match)
        
        # Добавляем флаг страны если есть
        country1 = team1.get("location", "")
        country2 = team2.get("location", "")
        
        country_flag1 = f" {country1}" if country1 else ""
        country_flag2 = f" {country2}" if country2 else ""
        
        return f"{index}. {team1_emoji} <b>{team1_name}</b>{country_flag1}  vs  {team2_emoji} <b>{team2_name}</b>{country_flag2}\n   ⏰ {time_str}{match_format}  |  🏆 {league}"
    
    return ""

def format_live_match(match: Dict, index: int) -> str:
    """Форматирование live матча с улучшениями"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1 = opponents[0].get("opponent", {})
        team2 = opponents[1].get("opponent", {})
        
        team1_name = team1.get("acronym") or team1.get("name", "TBA")
        team2_name = team2.get("acronym") or team2.get("name", "TBA")
        
        # Трекируем просмотры команд
        bot_stats.track_team_view(team1_name)
        bot_stats.track_team_view(team2_name)
        
        team1_emoji = get_team_emoji(team1_name)
        team2_emoji = get_team_emoji(team2_name)
        
        # Получаем счет
        score1, score2 = get_match_score(match)
        league = match.get("league", {}).get("name", "")
        
        # Определяем лидера
        if score1 > score2:
            score_display = f"<b>{score1}</b>:{score2}"
        elif score2 > score1:
            score_display = f"{score1}:<b>{score2}</b>"
        else:
            score_display = f"{score1}:{score2}"
        
        # Добавляем статус матча
        status = match.get("status", "").replace("_", " ").title()
        
        return f"{index}. 🔴 {team1_emoji} <b>{team1_name}</b>  {score_display}  {team2_emoji} <b>{team2_name}</b>\n   ⚡ {status} | 🏆 {league}"
    
    return ""

def get_match_score(match: Dict) -> tuple:
    """Получить счет матча - улучшенный"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1 = opponents[0].get("opponent", {})
        team2 = opponents[1].get("opponent", {})
        
        # Получаем счет из результатов
        results = match.get("results", [])
        if len(results) >= 2:
            return results[0].get("score", 0), results[1].get("score", 0)
        
        # Или из полей команд
        team1_score = team1.get("score", 0)
        team2_score = team2.get("score", 0)
        
        return team1_score, team2_score
    
    return 0, 0

# ========== НОВЫЕ ФУНКЦИИ СООБЩЕНИЙ ==========

def create_next_matches_message(matches: List[Dict], days: int = 7) -> str:
    """Сообщение с ближайшими матчами на N дней"""
    if not matches:
        return f"""
⏳ <b>БЛИЖАЙШИЕ МАТЧИ (на {days} дней)</b>

📭 Нет запланированных матчей на ближайшие {days} дней.
"""
    
    # Группируем матчи по дням
    matches_by_day = {}
    for match in matches[:30]:  # Ограничиваем 30 матчами
        scheduled_at = match.get("scheduled_at")
        if scheduled_at:
            try:
                match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00')) + timedelta(hours=3)
                day_key = match_time.strftime('%d.%m (%A)')
                if day_key not in matches_by_day:
                    matches_by_day[day_key] = []
                matches_by_day[day_key].append(match)
            except:
                continue
    
    lines = [
        f"⏳ <b>БЛИЖАЙШИЕ МАТЧИ CS2</b>",
        f"<i>Расписание на {len(matches_by_day)} дней</i>",
        "",
        "─" * 40,
        ""
    ]
    
    for day, day_matches in sorted(matches_by_day.items()):
        lines.append(f"📅 <b>{day}</b>")
        
        for i, match in enumerate(day_matches[:5], 1):  # Максимум 5 матчей в день
            opponents = match.get("opponents", [])
            if len(opponents) >= 2:
                team1 = opponents[0].get("opponent", {})
                team2 = opponents[1].get("opponent", {})
                team1_name = team1.get("acronym") or team1.get("name", "TBA")
                team2_name = team2.get("acronym") or team2.get("name", "TBA")
                
                time_str = format_match_time(match.get("scheduled_at", ""))
                league = match.get("league", {}).get("name", "")
                
                lines.append(f"   {i}. {get_team_emoji(team1_name)} {team1_name} vs {get_team_emoji(team2_name)} {team2_name}")
                lines.append(f"      ⏰ {time_str} | 🏆 {league[:20]}" + ("..." if len(league) > 20 else ""))
        
        lines.append("")
    
    lines.append(f"📊 <i>Всего матчей: {len(matches)}</i>")
    lines.append(f"⏱️ <i>Время указано в MSK</i>")
    
    return "\n".join(lines)

def create_tournaments_message(tournaments: List[Dict]) -> str:
    """Сообщение с турнирами"""
    if not tournaments:
        return """
🏆 <b>ТЕКУЩИЕ ТУРНИРЫ</b>

📭 Сейчас нет активных турниров CS2.
"""
    
    lines = ["🏆 <b>ТЕКУЩИЕ ТУРНИРЫ CS2</b>", "", "─" * 30, ""]
    
    for i, tournament in enumerate(tournaments, 1):
        name = tournament.get("name", "Без названия")
        prize = tournament.get("prize")
        tier = tournament.get("tier", "").upper()
        
        prize_str = f" | 💰 ${prize:,}" if prize else ""
        tier_str = f" | 🏅 {tier}" if tier else ""
        
        # Даты турнира
        begin_at = tournament.get("begin_at")
        end_at = tournament.get("end_at")
        
        if begin_at and end_at:
            try:
                begin = datetime.fromisoformat(begin_at.replace('Z', '+00:00')) + timedelta(hours=3)
                end = datetime.fromisoformat(end_at.replace('Z', '+00:00')) + timedelta(hours=3)
                date_str = f"{begin.strftime('%d.%m')} - {end.strftime('%d.%m')}"
            except:
                date_str = ""
        else:
            date_str = ""
        
        lines.append(f"{i}. <b>{name}</b>")
        lines.append(f"   📅 {date_str}{prize_str}{tier_str}")
        lines.append("")
    
    return "\n".join(lines)

def create_team_info_message(team: Dict) -> str:
    """Сообщение с информацией о команде"""
    if not team:
        return """
🔍 <b>ИНФОРМАЦИЯ О КОМАНДЕ</b>

❌ Команда не найдена.
"""
    
    name = team.get("acronym") or team.get("name", "Неизвестно")
    full_name = team.get("name", "")
    location = team.get("location", "Не указано")
    
    # Статистика
    stats = team.get("statistics", {})
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    win_rate = (wins / (wins + losses)) * 100 if (wins + losses) > 0 else 0
    
    lines = [
        f"{get_team_emoji(name)} <b>ИНФОРМАЦИЯ О КОМАНДЕ</b>",
        "",
        f"🏷️ <b>Название:</b> {name}",
        f"📍 <b>Страна:</b> {location}",
    ]
    
    if full_name and full_name != name:
        lines.append(f"📝 <b>Полное название:</b> {full_name}")
    
    lines.extend([
        "",
        f"📊 <b>Статистика:</b>",
        f"  • Победы: {wins}",
        f"  • Поражения: {losses}",
        f"  • Винрейт: {win_rate:.1f}%",
    ])
    
    # Игроки если есть
    players = team.get("players", [])
    if players:
        lines.extend(["", "👥 <b>Основной состав:</b>"])
        for player in players[:5]:  # Показываем первых 5 игроков
            player_name = player.get("name", "Игрок")
            lines.append(f"  • {player_name}")
    
    return "\n".join(lines)

# ========== УЛУЧШЕННЫЕ КЛАВИАТУРЫ ==========

def create_main_keyboard():
    """Главное меню - расширенное"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 СЕГОДНЯ", callback_data="today"),
            InlineKeyboardButton(text="📅 ЗАВТРА", callback_data="tomorrow")
        ],
        [
            InlineKeyboardButton(text="🔥 LIVE", callback_data="live"),
            InlineKeyboardButton(text="⏳ НЕДЕЛЯ", callback_data="week")
        ],
        [
            InlineKeyboardButton(text="🏆 ТУРНИРЫ", callback_data="tournaments"),
            InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="botstats")
        ],
        [
            InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh"),
            InlineKeyboardButton(text="ℹ️ ПОМОЩЬ", callback_data="help")
        ]
    ])
    return keyboard

def create_back_keyboard(with_refresh: bool = True):
    """Кнопка назад с возможностью обновления"""
    buttons = []
    if with_refresh:
        buttons.append([InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh_current")])
    buttons.append([InlineKeyboardButton(text="◀️ В МЕНЮ", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_match_details_keyboard(match_id: str, has_stream: bool = False):
    """Клавиатура для деталей матча"""
    keyboard = []
    
    if has_stream:
        keyboard.append([InlineKeyboardButton(text="🎥 СМОТРЕТЬ ТРАНСЛЯЦИЮ", url="https://twitch.tv")])
    
    keyboard.extend([
        [InlineKeyboardButton(text="📊 ДЕТАЛЬНАЯ СТАТИСТИКА", callback_data=f"details_{match_id}")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ========== СУЩЕСТВУЮЩИЕ ФУНКЦИИ СООБЩЕНИЙ (не меняем) ==========

def create_today_message(matches: List[Dict]) -> str:
    """Создать сообщение с матчами на сегодня"""
    today = datetime.utcnow() + timedelta(hours=3)
    today_str = today.strftime('%d.%m')
    
    if not matches:
        return f"""
📅 <b>МАТЧИ НА СЕГОДНЯ ({today_str})</b>

📭 Сегодня нет запланированных матчей CS2.

👉 <i>Проверьте матчи на завтра</i>
"""
    
    # Сортируем по времени
    matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    lines = [
        f"📅 <b>МАТЧИ НА СЕГОДНЯ ({today_str})</b>",
        "",
        f"📊 <i>Найдено матчей: {len(matches)}</i>",
        "─" * 40,
        ""
    ]
    
    for i, match in enumerate(matches, 1):
        match_line = format_upcoming_match(match, i)
        if match_line:
            lines.append(match_line)
            lines.append("")
    
    lines.append(f"⏱️ <i>Все время указано в MSK</i>")
    
    return "\n".join(lines)

def create_tomorrow_message(matches: List[Dict]) -> str:
    """Создать сообщение с матчами на завтра"""
    tomorrow = datetime.utcnow() + timedelta(hours=3) + timedelta(days=1)
    tomorrow_str = tomorrow.strftime('%d.%m')
    
    if not matches:
        return f"""
📅 <b>МАТЧИ НА ЗАВТРА ({tomorrow_str})</b>

📭 Завтра нет запланированных матчей CS2.

👉 <i>Проверьте матчи на сегодня</i>
"""
    
    # Сортируем по времени
    matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    lines = [
        f"📅 <b>МАТЧИ НА ЗАВТРА ({tomorrow_str})</b>",
        "",
        f"📊 <i>Найдено матчей: {len(matches)}</i>",
        "─" * 40,
        ""
    ]
    
    for i, match in enumerate(matches, 1):
        match_line = format_upcoming_match(match, i)
        if match_line:
            lines.append(match_line)
            lines.append("")
    
    lines.append(f"⏱️ <i>Все время указано в MSK</i>")
    
    return "\n".join(lines)

def create_live_message(matches: List[Dict]) -> str:
    """Создать сообщение с live матчами"""
    if not matches:
        return """
🔥 <b>LIVE МАТЧИ CS2</b>

📭 В данный момент нет матчей в прямом эфире.

👉 <i>Проверьте предстоящие матчи на сегодня/завтра</i>
"""
    
    lines = [
        "🔥 <b>LIVE МАТЧИ CS2</b>",
        "",
        f"📡 <i>Матчей в эфире: {len(matches)}</i>",
        "─" * 40,
        ""
    ]
    
    for i, match in enumerate(matches, 1):
        match_line = format_live_match(match, i)
        if match_line:
            lines.append(match_line)
            
            # Ссылка на трансляцию
            stream_url = match.get("official_stream_url") or match.get("live_url") or match.get("stream_url")
            if stream_url:
                lines.append(f"   📺 <a href='{stream_url}'>Смотреть трансляцию</a>")
            
            lines.append("")
    
    return "\n".join(lines)

# ========== НОВЫЕ КОМАНДЫ ==========

@dp.message(Command("week"))
async def cmd_week(message: types.Message):
    """Матчи на неделю"""
    bot_stats.track_command("week", message.from_user.id)
    await show_week(message)

@dp.message(Command("tournaments"))
async def cmd_tournaments(message: types.Message):
    """Текущие турниры"""
    bot_stats.track_command("tournaments", message.from_user.id)
    await show_tournaments(message)

@dp.message(Command("team"))
async def cmd_team(message: types.Message):
    """Поиск команды"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ <b>Укажите название команды</b>\nНапример: <code>/team NAVI</code>")
        return
    
    team_name = " ".join(args[1:])
    await search_team(message, team_name)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Статистика бота"""
    bot_stats.track_command("stats", message.from_user.id)
    await show_bot_stats(message)

@dp.message(Command("clear_cache"))
async def cmd_clear_cache(message: types.Message):
    """Очистить кэш (админ)"""
    cache_manager.clear_old()
    await message.answer("✅ <b>Кэш очищен!</b>")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Расширенная помощь"""
    bot_stats.track_command("help", message.from_user.id)
    help_text = """
🎮 <b>CS2 MATCHES - ПОМОЩЬ</b>

<b>Основные команды:</b>
/start - Запустить бота
/today - Матчи на сегодня  
/tomorrow - Матчи на завтра
/live - Матчи в прямом эфире
/week - Матчи на неделю
/tournaments - Текущие турниры
/team [название] - Поиск команды
/stats - Статистика бота
/help - Эта справка

<b>Кнопки управления:</b>
• Используйте кнопки под сообщениями
• 🔄 Обновить - актуальные данные
• ◀️ Назад - вернуться в меню

<b>Информация:</b>
• Время указано в MSK (Москва)
• Источник: PandaScore API
• Кэширование: 5 минут

<i>Бот обновляется в реальном времени!</i>
"""
    await message.answer(help_text, reply_markup=create_main_keyboard())

# ========== НОВЫЕ ОБРАБОТЧИКИ CALLBACK ==========

@dp.callback_query(F.data == "week")
async def handle_week(callback: types.CallbackQuery):
    """Матчи на неделю через callback"""
    bot_stats.track_command("week", callback.from_user.id)
    await callback.answer("⏳ Загружаю матчи на неделю...")
    await show_week_callback(callback)

@dp.callback_query(F.data == "tournaments")
async def handle_tournaments(callback: types.CallbackQuery):
    """Турниры через callback"""
    bot_stats.track_command("tournaments", callback.from_user.id)
    await callback.answer("🏆 Загружаю турниры...")
    await show_tournaments_callback(callback)

@dp.callback_query(F.data == "botstats")
async def handle_botstats(callback: types.CallbackQuery):
    """Статистика бота через callback"""
    bot_stats.track_command("stats", callback.from_user.id)
    await callback.answer("📊 Загружаю статистику...")
    await show_bot_stats_callback(callback)

@dp.callback_query(F.data == "refresh_current")
async def handle_refresh_current(callback: types.CallbackQuery):
    """Обновить текущий раздел"""
    await callback.answer("🔄 Обновление...")
    
    # Определяем что обновлять по тексту сообщения
    message_text = callback.message.text or ""
    
    if "СЕГОДНЯ" in message_text:
        await handle_today(callback)
    elif "ЗАВТРА" in message_text:
        await handle_tomorrow(callback)
    elif "LIVE" in message_text:
        await handle_live(callback)
    elif "НЕДЕЛЯ" in message_text or "БЛИЖАЙШИЕ" in message_text:
        await handle_week(callback)
    elif "ТУРНИРЫ" in message_text:
        await handle_tournaments(callback)
    else:
        await handle_back(callback)

# ========== СУЩЕСТВУЮЩИЕ ОБРАБОТЧИКИ (с трекингом) ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    bot_stats.track_command("start", message.from_user.id)
    welcome = """
🎮 <b>CS2 MATCHES</b>

Актуальные матчи Counter-Strike 2
Только сегодня, завтра и live трансляции

👇 <b>Выберите раздел:</b>
"""
    
    await message.answer(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    """Матчи сегодня"""
    bot_stats.track_command("today", message.from_user.id)
    await show_today(message)

@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: types.Message):
    """Матчи завтра"""
    bot_stats.track_command("tomorrow", message.from_user.id)
    await show_tomorrow(message)

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Live матчи"""
    bot_stats.track_command("live", message.from_user.id)
    await show_live(message)

@dp.callback_query(F.data == "today")
async def handle_today(callback: types.CallbackQuery):
    """Матчи сегодня"""
    bot_stats.track_command("today", callback.from_user.id)
    await callback.answer("📅 Загружаю матчи на сегодня...")
    await show_today_callback(callback)

@dp.callback_query(F.data == "tomorrow")
async def handle_tomorrow(callback: types.CallbackQuery):
    """Матчи завтра"""
    bot_stats.track_command("tomorrow", callback.from_user.id)
    await callback.answer("📅 Загружаю матчи на завтра...")
    await show_tomorrow_callback(callback)

@dp.callback_query(F.data == "live")
async def handle_live(callback: types.CallbackQuery):
    """Live матчи"""
    bot_stats.track_command("live", callback.from_user.id)
    await callback.answer("🔥 Ищу live матчи...")
    await show_live_callback(callback)

@dp.callback_query(F.data == "back")
async def handle_back(callback: types.CallbackQuery):
    """Назад в меню"""
    welcome = """
🎮 <b>CS2 MATCHES</b>

👇 <b>Выберите раздел:</b>
"""
    
    await callback.message.edit_text(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "refresh")
async def handle_refresh(callback: types.CallbackQuery):
    """Обновить"""
    await callback.answer("🔄 Обновление...")
    await cmd_start(callback.message)

@dp.callback_query(F.data == "info")
async def handle_info(callback: types.CallbackQuery):
    """Информация"""
    info_text = """
ℹ️ <b>ИНФОРМАЦИЯ</b>

🎮 <b>CS2 MATCHES</b>
Простой и удобный бот для отслеживания матчей CS2.

📊 <b>Что показывает:</b>
• Матчи на сегодня
• Матчи на завтра  
• Live трансляции со счетом
• Турниры и расписание

⚙️ <b>Техническая информация:</b>
• Источник: PandaScore API
• Время: MSK (Москва)
• Обновление: по требованию
• Кэширование: 5 минут

<i>Для быстрого доступа к актуальной информации</i>
"""
    
    await callback.message.edit_text(
        info_text,
        reply_markup=create_back_keyboard(with_refresh=False),
        disable_web_page_preview=True
    )
    await callback.answer()

# ========== НОВЫЕ ФУНКЦИИ ПОКАЗА ==========

async def show_week_callback(callback: types.CallbackQuery):
    """Матчи на неделю через callback"""
    await show_week(callback, is_callback=True)

async def show_week(message_or_callback, is_callback: bool = False):
    """Показать матчи на неделю"""
    if is_callback:
        await message_or_callback.message.edit_text("⏳ <b>Загружаю матчи на неделю...</b>")
    else:
        msg = await message_or_callback.answer("⏳ <b>Загружаю матчи на неделю...</b>")
    
    # Получаем матчи на 7 дней
    matches = await panda_api.get_upcoming_matches(days=7)
    
    # Создаем сообщение
    message_text = create_next_matches_message(matches, 7)
    
    if is_callback:
        await message_or_callback.message.edit_text(
            message_text,
            reply_markup=create_back_keyboard(),
            disable_web_page_preview=True
        )
    else:
        await msg.edit_text(
            message_text,
            reply_markup=create_back_keyboard(),
            disable_web_page_preview=True
        )

async def show_tournaments_callback(callback: types.CallbackQuery):
    """Турниры через callback"""
    await show_tournaments(callback, is_callback=True)

async def show_tournaments(message_or_callback, is_callback: bool = False):
    """Показать турниры"""
    if is_callback:
        await message_or_callback.message.edit_text("🏆 <b>Загружаю турниры...</b>")
    else:
        msg = await message_or_callback.answer("🏆 <b>Загружаю турниры...</b>")
    
    # Получаем турниры
    tournaments = await panda_api.get_tournaments(5)
    
    # Создаем сообщение
    message_text = create_tournaments_message(tournaments)
    
    if is_callback:
        await message_or_callback.message.edit_text(
            message_text,
            reply_markup=create_back_keyboard(),
            disable_web_page_preview=True
        )
    else:
        await msg.edit_text(
            message_text,
            reply_markup=create_back_keyboard(),
            disable_web_page_preview=True
        )

async def search_team(message: types.Message, team_name: str):
    """Поиск информации о команде"""
    msg = await message.answer(f"🔍 <b>Ищу информацию о команде {team_name}...</b>")
    
    # Ищем команду
    team = await panda_api.get_team_info(team_name)
    
    # Создаем сообщение
    message_text = create_team_info_message(team)
    
    await msg.edit_text(
        message_text,
        reply_markup=create_back_keyboard(),
        disable_web_page_preview=True
    )

async def show_bot_stats_callback(callback: types.CallbackQuery):
    """Статистика бота через callback"""
    await show_bot_stats(callback, is_callback=True)

async def show_bot_stats(message_or_callback, is_callback: bool = False):
    """Показать статистику бота"""
    message_text = bot_stats.get_stats_text()
    
    if is_callback:
        await message_or_callback.message.edit_text(
            message_text,
            reply_markup=create_back_keyboard(),
            disable_web_page_preview=True
        )
    else:
        await message_or_callback.answer(
            message_text,
            reply_markup=create_back_keyboard(),
            disable_web_page_preview=True
        )

# ========== СУЩЕСТВУЮЩИЕ ФУНКЦИИ ПОКАЗА (не меняем) ==========

async def show_today_callback(callback: types.CallbackQuery):
    """Матчи сегодня через callback"""
    await show_today(callback, is_callback=True)

async def show_today(message_or_callback, is_callback: bool = False):
    """Показать матчи на сегодня"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус загрузки
    if is_callback:
        await message_or_callback.message.edit_text("📅 <b>Загружаю матчи на сегодня...</b>")
    else:
        msg = await message_or_callback.answer("📅 <b>Загружаю матчи на сегодня...</b>")
    
    # Получаем матчи
    matches = await panda_api.get_today_matches()
    
    # Создаем сообщение
    message_text = create_today_message(matches)
    
    # Клавиатура
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="today")],
        [InlineKeyboardButton(text="◀️ В МЕНЮ", callback_data="back")]
    ])
    
    if is_callback:
        await message_or_callback.message.edit_text(
            message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
    else:
        await msg.edit_text(
            message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

async def show_tomorrow_callback(callback: types.CallbackQuery):
    """Матчи завтра через callback"""
    await show_tomorrow(callback, is_callback=True)

async def show_tomorrow(message_or_callback, is_callback: bool = False):
    """Показать матчи на завтра"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус загрузки
    if is_callback:
        await message_or_callback.message.edit_text("📅 <b>Загружаю матчи на завтра...</b>")
    else:
        msg = await message_or_callback.answer("📅 <b>Загружаю матчи на завтра...</b>")
    
    # Получаем матчи
    matches = await panda_api.get_tomorrow_matches()
    
    # Создаем сообщение
    message_text = create_tomorrow_message(matches)
    
    # Клавиатура
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="tomorrow")],
        [InlineKeyboardButton(text="◀️ В МЕНЮ", callback_data="back")]
    ])
    
    if is_callback:
        await message_or_callback.message.edit_text(
            message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
    else:
        await msg.edit_text(
            message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

async def show_live_callback(callback: types.CallbackQuery):
    """Live матчи через callback"""
    await show_live(callback, is_callback=True)

async def show_live(message_or_callback, is_callback: bool = False):
    """Показать live матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус загрузки
    if is_callback:
        await message_or_callback.message.edit_text("🔥 <b>Ищу матчи в прямом эфире...</b>")
    else:
        msg = await message_or_callback.answer("🔥 <b>Ищу матчи в прямом эфире...</b>")
    
    # Получаем live матчи
    matches = await panda_api.get_live_matches()
    
    # Создаем сообщение
    message_text = create_live_message(matches)
    
    # Клавиатура
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="live")],
        [InlineKeyboardButton(text="◀️ В МЕНЮ", callback_data="back")]
    ])
    
    if is_callback:
        await message_or_callback.message.edit_text(
            message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
    else:
        await msg.edit_text(
            message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

# ========== ЗАПУСК БОТА ==========

async def main():
    """Запуск бота"""
    logger.info("🎮 Запускаю CS2 MATCHES...")
    logger.info("📅 Отдельные запросы на сегодня/завтра")
    logger.info("🔥 Live матчи без карты")
    logger.info("➕ Добавлены: кэширование, статистика, турниры")
    
    if not PANDASCORE_TOKEN:
        logger.error("❌ Нет токена PandaScore!")
        return
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Нет токена Telegram!")
        return
    
    try:
        # Очищаем кэш при запуске
        cache_manager.clear_old()
        
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await panda_api.close()

if __name__ == "__main__":
    asyncio.run(main())