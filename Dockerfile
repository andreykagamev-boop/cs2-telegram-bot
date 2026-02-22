FROM selenium/standalone-chrome:latest

USER root

WORKDIR /app

# Устанавливаем Python и зависимости
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-distutils \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Создаем виртуальное окружение с Python 3.11 (совместимая версия)
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Создаем директории
RUN mkdir -p /app/temp /app/debug && chmod 777 /app/temp /app/debug

# Копируем код
COPY bot.py .

# Возвращаем пользователя seluser
USER seluser

# Запускаем бота
CMD ["python3", "/app/bot.py"]