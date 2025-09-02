#1. Используем официальный образ Python#

FROM python:3.10-slim

#2. Устанавливаем системные зависимости, необходимые для pdf2image#

RUN apt-get update && apt-get install -y \
poppler-utils \
ffmpeg \
&& rm -rf /var/lib/apt/lists/*

#3. Устанавливаем рабочую директорию в контейнере#

WORKDIR /app

#4. Копируем файл зависимостей и устанавливаем их#

#Это делается отдельно для эффективного использования кэша Docker#

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#5. Копируем весь остальной код проекта в рабочую директорию#

COPY . .

#Команда для запуска будет передаваться через docker-compose#