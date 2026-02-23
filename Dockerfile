FROM python:3.11-slim

# Установка Chrome и зависимостей
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    unzip \
    curl \
    xvfb \
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

# Запуск с Xvfb (без VNC)
CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 & export DISPLAY=:99 && python bot.py"]