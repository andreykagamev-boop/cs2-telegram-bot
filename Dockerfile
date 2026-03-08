FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget gnupg2 curl unzip \
    xvfb libxi6 libgconf-2-4 \
    libnss3 libxss1 libasound2 \
    libatk1.0-0 libatk-bridge2.0-0 \
    libgtk-3-0 libdrm2 libgbm1 \
    libxshmfence1 fonts-liberation \
    chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV DISPLAY=:99

WORKDIR /app

RUN pip install --no-cache-dir \
    python-telegram-bot==21.9 \
    requests==2.32.3 \
    selenium==4.27.1 \
    undetected-chromedriver==3.5.5

COPY . .

CMD ["python", "main.py"]
