FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY worker worker
COPY procedures procedures
RUN useradd --no-create-home --uid 10001 balancer
USER balancer
