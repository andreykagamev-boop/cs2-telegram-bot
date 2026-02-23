FROM python:3.11-slim

# Установка зависимостей
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    unzip \
    curl \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Установка Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаем папки
RUN mkdir -p /app/debug /app/sessions && chmod 777 /app/debug /app/sessions

# Открываем порты
EXPOSE 8080 5900

# Запуск всех сервисов
CMD ["sh", "-c", "\
    rm -f /tmp/.X99-lock && \
    Xvfb :99 -screen 0 1920x1080x24 & \
    sleep 2 && \
    x11vnc -display :99 -forever -nopw -shared -rfbport 5900 -bg -o /tmp/x11vnc.log & \
    sleep 2 && \
    websockify --web /usr/share/novnc 8080 localhost:5900 & \
    sleep 2 && \
    export DISPLAY=:99 && \
    echo '✅ VNC Server запущен на порту 5900' && \
    echo '✅ noVNC запущен на порту 8080' && \
    echo '🚀 Запускаю бота...' && \
    python bot.py \
"]