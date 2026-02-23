FROM python:3.11-slim

# Установка зависимостей
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    unzip \
    curl \
    xvfb \
    fluxbox \
    procps \
    net-tools \
    xterm \
    libgtk-3-0 \
    libx11-xcb1 \
    libdbus-glib-1-2 \
    libxtst6 \
    && rm -rf /var/lib/apt/lists/*

# Установка Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /etc/apt/trusted.gpg.d/google.gpg \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Установка AnyDesk
RUN wget -qO - https://keys.anydesk.com/repos/DEB-GPG-KEY | apt-key add - \
    && echo "deb http://deb.anydesk.com/ all main" > /etc/apt/sources.list.d/anydesk-stable.list \
    && apt-get update \
    && apt-get install -y anydesk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаем папки
RUN mkdir -p /app/debug /app/sessions && chmod 777 /app/debug /app/sessions

# Скрипт запуска
RUN echo '#!/bin/bash\n\
echo "=========================================="\n\
echo "🚀 ЗАПУСК OPTIFINE CHECKER (AnyDesk)"\n\
echo "=========================================="\n\
\n\
echo "📌 Шаг 1: Очистка старых процессов..."\n\
pkill Xvfb 2>/dev/null || true\n\
pkill fluxbox 2>/dev/null || true\n\
pkill anydesk 2>/dev/null || true\n\
rm -f /tmp/.X99-lock\n\
sleep 2\n\
\n\
echo "📌 Шаг 2: Запуск Xvfb..."\n\
Xvfb :99 -screen 0 1920x1080x24 -ac &\n\
sleep 5\n\
\n\
echo "📌 Шаг 3: Запуск Fluxbox..."\n\
fluxbox &\n\
sleep 3\n\
\n\
echo "📌 Шаг 4: Запуск AnyDesk..."\n\
export DISPLAY=:99\n\
anydesk --service &\n\
sleep 5\n\
\n\
echo "📌 Шаг 5: Получение AnyDesk ID..."\n\
ANYDESK_ID=$(anydesk --get-id)\n\
echo "🔑 ANYDESK ID: $ANYDESK_ID" > /app/anydesk_id.txt\n\
echo "✅ AnyDesk ID: $ANYDESK_ID"\n\
\n\
echo "=========================================="\n\
echo "✅ Все сервисы запущены!"\n\
echo "📱 ANYDESK ID: $ANYDESK_ID"\n\
echo "=========================================="\n\
\n\
echo "📌 Шаг 6: Запуск бота..."\n\
python bot.py\n\
' > /app/start.sh && chmod +x /app/start.sh

CMD ["/app/start.sh"]