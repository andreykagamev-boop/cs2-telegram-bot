FROM python:3.11-slim

# Установка зависимостей
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    unzip \
    curl \
    xvfb \
    x11vnc \
    fluxbox \
    novnc \
    websockify \
    procps \
    psmisc \
    && rm -rf /var/lib/apt/lists/*

# Установка Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /etc/apt/trusted.gpg.d/google.gpg \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/debug && chmod 777 /app/debug

# Скрипт запуска с принудительным запуском Chrome
RUN echo '#!/bin/bash\n\
echo "=========================================="\n\
echo "🚀 ЗАПУСК БРАУЗЕРА"\n\
echo "=========================================="\n\
\n\
killall Xvfb 2>/dev/null\n\
killall fluxbox 2>/dev/null\n\
killall x11vnc 2>/dev/null\n\
killall websockify 2>/dev/null\n\
rm -f /tmp/.X99-lock\n\
sleep 3\n\
\n\
Xvfb :99 -screen 0 1920x1080x24 &\n\
sleep 5\n\
\n\
DISPLAY=:99 fluxbox &\n\
sleep 3\n\
\n\
x11vnc -display :99 -forever -nopw -shared -rfbport 5900 &\n\
sleep 3\n\
\n\
websockify --web /usr/share/novnc 8080 localhost:5900 &\n\
sleep 3\n\
\n\
# Принудительный запуск Chrome с отключенной безопасностью\n\
DISPLAY=:99 google-chrome \\\n\
  --no-sandbox \\\n\
  --disable-web-security \\\n\
  --disable-features=IsolateOrigins,site-per-process \\\n\
  --disable-blink-features=AutomationControlled \\\n\
  --disable-gpu \\\n\
  --disable-dev-shm-usage \\\n\
  --disable-setuid-sandbox \\\n\
  --start-maximized \\\n\
  --new-window \\\n\
  https://optifine.net/login &\n\
\n\
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null)\n\
echo "=========================================="\n\
echo "✅ ВСЕ СЕРВИСЫ ЗАПУЩЕНЫ!"\n\
echo "📱 Открой в браузере на телефоне:"\n\
echo "http://$PUBLIC_IP:8080/vnc.html"\n\
echo "=========================================="\n\
\n\
export DISPLAY=:99\n\
python bot.py\n\
' > /app/start.sh && chmod +x /app/start.sh

EXPOSE 8080 5900

CMD ["/app/start.sh"]