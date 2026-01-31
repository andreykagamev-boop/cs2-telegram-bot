import requests
from datetime import datetime

PANDASCORE_TOKEN = "5BwPN0K33bfYs7O-ysugJkaxa1NP2DWEAeN9In9XhLRUt9rNflA"
BASE_URL = "https://api.pandascore.co"
HEADERS = {"Authorization": f"Bearer {PANDASCORE_TOKEN}"}

# Правильные slug для игр в PandaScore:
# CS2 = "csgo" (они до сих пор используют csgo для Counter-Strike 2)
# Dota 2 = "dota-2"

def get_upcoming_matches(game_slug="csgo", limit=5):
    """Получает предстоящие матчи для указанной игры"""
    url = f"{BASE_URL}/{game_slug}/matches/upcoming"
    try:
        params = {
            "per_page": limit,
            "sort": "scheduled_at",
            "page": 1
        }
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Ошибка API ({game_slug}): {response.status_code} - {response.text[:200]}")
            return []
    except Exception as e:
        print(f"Ошибка запроса: {e}")
        return []

def format_match(match):
    """Форматирует информацию о матче"""
    league = match.get("league", {}).get("name", "Без лиги")
    series = match.get("serie", {}).get("name", "")
    
    # Получаем команды
    teams = []
    for opponent in match.get("opponents", []):
        team_name = opponent.get("opponent", {}).get("name", "TBA")
        teams.append(team_name)
    
    if len(teams) < 2:
        teams = ["TBA", "TBA"]
    
    # Форматируем время
    scheduled_time = match.get("scheduled_at")
    if scheduled_time:
        try:
            dt = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
            time_str = dt.strftime("%d.%m.%Y %H:%M")
        except:
            time_str = "Время неизвестно"
    else:
        time_str = "Время неизвестно"
    
    return f"🏆 {league}\n⚔️ {teams[0]} vs {teams[1]}\n🕐 {time_str}\n"

def get_cs2_matches(limit=5):
    """Матчи по CS2"""
    return get_upcoming_matches("csgo", limit)

def get_dota2_matches(limit=5):
    """Матчи по Dota 2"""
    return get_upcoming_matches("dota-2", limit)

# ТЕСТ
if __name__ == "__main__":
    print("=" * 50)
    print("ПРОВЕРКА CS2 МАТЧЕЙ:")
    print("=" * 50)
    cs2_matches = get_cs2_matches(3)
    if cs2_matches:
        for i, match in enumerate(cs2_matches, 1):
            print(f"Матч #{i}:")
            print(format_match(match))
    else:
        print("Нет предстоящих матчей по CS2")
    
    print("\n" + "=" * 50)
    print("ПРОВЕРКА DOTA 2 МАТЧЕЙ:")
    print("=" * 50)
    dota2_matches = get_dota2_matches(3)
    if dota2_matches:
        for i, match in enumerate(dota2_matches, 1):
            print(f"Матч #{i}:")
            print(format_match(match))
    else:
        print("Нет предстоящих матчей по Dota 2")