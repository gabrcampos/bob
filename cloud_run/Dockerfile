FROM python:3.12-slim

WORKDIR /app

# Dependências do worker
COPY cloud_run/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Módulos do projeto
COPY modulos ./modulos
COPY config ./config

# Entrypoint
COPY cloud_run/main.py ./main.py

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

CMD exec gunicorn --bind :$PORT --workers 1 --threads 2 --timeout 120 "main:create_app()"
