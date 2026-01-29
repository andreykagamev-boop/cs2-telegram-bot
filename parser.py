import requests
from bs4 import BeautifulSoup
import time
from typing import List, Dict

class HLTVParser:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.cache = None
        self.cache_time = 0
        self.cache_duration = 300  # 5 минут
        
    def fetch_matches(self) -> List[Dict]:
        """Парсинг матчей с HLTV"""
        try:
            print("🔄 Загружаю данные с HLTV...")
            response = requests.get(
                "https://www.hltv.org/matches",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code != 200:
                print(f"❌ Ошибка: {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            matches = []
            
            # Простой поиск - находим все div с матчами
            for match_div in soup.find_all('div', class_='upcomingMatch'):
                try:
                    # Ищем названия команд
                    teams = match_div.find_all('div', class_='matchTeamName')
                    if len(teams) >= 2:
                        team1 = teams[0].text.strip()
                        team2 = teams[1].text.strip()
                        
                        # Пропускаем TBD
                        if 'TBD' in team1 or 'TBD' in team2:
                            continue
                            
                        # Ищем событие
                        event_div = match_div.find('div', class_='matchEventName')
                        event = event_div.text.strip() if event_div else "Матч"
                        
                        # Ищем время
                        time_div = match_div.find('div', class_='matchTime')
                        match_time = time_div.text.strip() if time_div else "Скоро"
                        
                        matches.append({
                            'team1': team1,
                            'team2': team2,
                            'event': event,
                            'time': match_time,
                            'stars': 2,  # По умолчанию
                            'format': 'BO3'
                        })
                        
                except:
                    continue
                    
            print(f"✅ Найдено {len(matches)} матчей")
            return matches[:10]  # Только первые 10
            
        except Exception as e:
            print(f"❌ Ошибка парсинга: {e}")
            # Возвращаем тестовые данные если ошибка
            return [
                {'team1': 'NAVI', 'team2': 'Team Spirit', 'event': 'IEM Katowice', 'time': '19:00', 'stars': 3, 'format': 'BO3'},
                {'team1': 'FaZe', 'team2': 'Vitality', 'event': 'ESL Pro League', 'time': '21:00', 'stars': 3, 'format': 'BO3'},
                {'team1': 'G2', 'team2': 'MOUZ', 'event': 'BLAST Premier', 'time': '23:00', 'stars': 2, 'format': 'BO3'}
            ]
    
    def get_upcoming_matches(self) -> List[Dict]:
        """Получение матчей с кэшированием"""
        current_time = time.time()
        
        if self.cache and (current_time - self.cache_time) < self.cache_duration:
            return self.cache
        
        self.cache = self.fetch_matches()
        self.cache_time = current_time
        return self.cache

parser = HLTVParser()
