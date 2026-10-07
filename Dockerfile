FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY bot.py /app/bot.py
COPY config /app/config
COPY assets /app/assets
USER 65534:65534
CMD ["python", "bot.py"]
