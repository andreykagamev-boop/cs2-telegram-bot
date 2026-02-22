# Используем официальный образ Python
FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    unzip \
    curl \
    xvfb \
    x11vnc \
    fluxbox \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Chrome (последнюю стабильную версию)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем ChromeDriver соответствующей версии
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+') \
    && wget -q -O /tmp/chromedriver.zip https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chromedriver-linux64.zip \
    && unzip /tmp/chromedriver.zip -d /tmp/ \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver \
    && rm /tmp/chromedriver.zip

# Проверяем версии
RUN google-chrome --version && chromedriver --version

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Создаем директории
RUN mkdir -p /app/temp /app/debug && chmod 777 /app/temp /app/debug

# Копируем код бота
COPY bot.py .

# Скрипт запуска с Xvfb
RUN echo '#!/bin/bash\n\
Xvfb :99 -screen 0 1920x1080x24 &\n\
export DISPLAY=:99\n\
python bot.py' > /app/start.sh && chmod +x /app/start.sh

ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

CMD ["/app/start.sh"]