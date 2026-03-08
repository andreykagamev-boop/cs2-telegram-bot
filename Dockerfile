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

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
