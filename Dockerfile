FROM python:3.11-slim

# Установка зависимостей (только самое необходимое)
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

# Упрощенный скрипт запуска
RUN echo '#!/bin/bash\n\
echo "=========================================="\n\
echo "🚀 ЗАПУСК БРАУЗЕРА С ДОСТУПОМ ЧЕРЕЗ БРАУЗЕР"\n\
echo "=========================================="\n\
\n\
# Убиваем старые процессы\n\
pkill Xvfb 2>/dev/null || true\n\
pkill fluxbox 2>/dev/null || true\n\
pkill x11vnc 2>/dev/null || true\n\
rm -f /tmp/.X99-lock\n\
sleep 2\n\
\n\
# Запуск Xvfb\n\
Xvfb :99 -screen 0 1920x1080x24 &\n\
XVFB_PID=$!\n\
sleep 3\n\
\n\
# Проверка Xvfb\n\
if ! kill -0 $XVFB_PID 2>/dev/null; then\n\
    echo "❌ Xvfb не запустился"\n\
    exit 1\n\
fi\n\
echo "✅ Xvfb запущен (PID: $XVFB_PID)"\n\
\n\
# Запуск Fluxbox\n\
fluxbox &\n\
sleep 2\n\
\n\
# Запуск VNC\n\
x11vnc -display :99 -forever -nopw -shared -rfbport 5900 &\n\
VNC_PID=$!\nsleep 2\n\
\n\
# Запуск noVNC (веб-доступ)\n\
websockify --web /usr/share/novnc 8080 localhost:5900 &\n\
WEBSOCKIFY_PID=$!\nsleep 3\n\
\n\
export DISPLAY=:99\n\
\n\
echo "=========================================="\n\
echo "✅ Все сервисы запущены!"\n\
echo "📱 Открой в браузере: http://localhost:8080/vnc.html"\n\
echo "🌐 Railway даст публичный URL для порта 8080"\n\
echo "=========================================="\n\
\n\
# Запуск бота\n\
python bot.py\n\
' > /app/start.sh && chmod +x /app/start.sh

EXPOSE 8080 5900

CMD ["/app/start.sh"]