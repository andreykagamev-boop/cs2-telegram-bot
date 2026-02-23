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
    net-tools \
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

EXPOSE 8080 5900

CMD ["sh", "-c", "\
    Xvfb :99 -screen 0 1920x1080x24 & \
    fluxbox & \
    x11vnc -display :99 -forever -nopw -shared -rfbport 5900 & \
    websockify --web /usr/share/novnc 8080 localhost:5900 & \
    export DISPLAY=:99 && \
    python bot.py \
"]