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

# Создаем папки
RUN mkdir -p /app/debug /app/sessions && chmod 777 /app/debug /app/sessions

# Скрипт запуска
RUN echo '#!/bin/bash\n\
echo "🚀 Очистка старых процессов..."\n\
pkill Xvfb 2>/dev/null || true\n\
pkill fluxbox 2>/dev/null || true\n\
pkill x11vnc 2>/dev/null || true\n\
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
echo "✅ Все сервисы запущены"\n\
export DISPLAY=:99\n\
\n\
# Проверка Xvfb\n\
xdpyinfo -display :99 > /dev/null 2>&1\n\
if [ $? -eq 0 ]; then\n\
    echo "✅ Xvfb работает корректно"\n\
else\n\
    echo "❌ Ошибка Xvfb!"\n\
    exit 1\n\
fi\n\
\n\
echo "🚀 Запуск бота..."\n\
python bot.py\n\
' > /app/start.sh && chmod +x /app/start.sh

EXPOSE 5900

CMD ["/app/start.sh"]