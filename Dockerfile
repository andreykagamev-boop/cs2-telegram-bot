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
    procps \
    && rm -rf /var/lib/apt/lists/*

# Установка Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /etc/apt/trusted.gpg.d/google.gpg \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Установка Ngrok
RUN wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz \
    && tar -xzf ngrok-v3-stable-linux-amd64.tgz \
    && mv ngrok /usr/local/bin/ \
    && rm ngrok-v3-stable-linux-amd64.tgz

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаем папки
RUN mkdir -p /app/debug /app/sessions && chmod 777 /app/debug /app/sessions

# Скрипт запуска (исправленный)
RUN echo '#!/bin/bash\n\
echo "🚀 Убиваем старые процессы..."\n\
pkill Xvfb || true\n\
pkill fluxbox || true\n\
pkill x11vnc || true\n\
rm -f /tmp/.X99-lock\n\
sleep 2\n\
\n\
echo "🚀 Запуск Xvfb..."\n\
Xvfb :99 -screen 0 1920x1080x24 &\n\
sleep 5\n\
\n\
echo "🖥️ Запуск Fluxbox..."\n\
fluxbox &\n\
sleep 3\n\
\n\
echo "🔌 Запуск VNC сервера..."\n\
x11vnc -display :99 -forever -nopw -shared -rfbport 5900 -bg -o /tmp/x11vnc.log\n\
sleep 3\n\
\n\
echo "🌐 Запуск Ngrok..."\n\
ngrok authtoken ${NGROK_TOKEN}\n\
ngrok tcp 5900 --log=stdout > /app/ngrok.log 2>&1 &\n\
sleep 5\n\
\n\
echo "✅ Все сервисы запущены"\n\
export DISPLAY=:99\n\
\n\
# Проверяем что Xvfb работает\n\
xdpyinfo -display :99 > /dev/null 2>&1\n\
if [ $? -eq 0 ]; then\n\
    echo "✅ Xvfb работает корректно"\n\
else\n\
    echo "❌ Xvfb не работает!"\n\
    exit 1\n\
fi\n\
\n\
python bot.py\n\
' > /app/start.sh && chmod +x /app/start.sh

CMD ["/app/start.sh"]