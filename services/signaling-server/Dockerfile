# Build context must be the repo root, e.g.:
#   docker build -f services/signaling-server/Dockerfile -t teleop-signaling-server .
FROM python:3.11-slim

WORKDIR /app

COPY shared/protocol shared/protocol
COPY services/signaling-server services/signaling-server

RUN pip install --no-cache-dir ./shared/protocol ./services/signaling-server

WORKDIR /app/services/signaling-server

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
