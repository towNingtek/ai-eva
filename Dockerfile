FROM python:3.11-slim

WORKDIR /app

ENV TZ=Asia/Taipei \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 7860

CMD ["chainlit", "run", "app/main.py", "--host", "0.0.0.0", "--port", "7860", "--headless"]
