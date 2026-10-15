FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY bot.py /app/bot.py
COPY config /app/config
CMD ["python", "bot.py"]
