# Используем официальный образ Python
FROM python:3.11-slim

WORKDIR /app

# Устанавливаем только необходимые зависимости
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Chrome 114
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable=114.0.5735.90-1 \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY bot.py .

# Создаем директорию для временных файлов
RUN mkdir -p /app/temp && chmod 777 /app/temp

# Запускаем (undetected-chromedriver сам создаст виртуальный дисплей)
CMD ["python", "bot.py"]