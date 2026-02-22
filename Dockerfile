# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    ffmpeg \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libxss1 \
    libappindicator3-1 \
    libindicator7 \
    xvfb \
    x11vnc \
    fluxbox \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Chrome 114 (стабильная версия для undetected-chromedriver)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable=114.0.5735.90-1 \
    && rm -rf /var/lib/apt/lists/*

# Проверяем версию Chrome
RUN google-chrome --version

# Копируем requirements.txt
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Создаем директорию для временных файлов
RUN mkdir -p /app/temp && chmod 777 /app/temp

# Копируем код бота
COPY bot.py .

# Создаем скрипт запуска с Xvfb для виртуального дисплея
RUN echo '#!/bin/bash\n\
Xvfb :99 -screen 0 1920x1080x24 &\n\
export DISPLAY=:99\n\
python bot.py' > /app/start.sh && chmod +x /app/start.sh

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

# Запускаем бота
CMD ["/app/start.sh"]