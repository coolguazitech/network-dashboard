FROM python:3.11-slim

LABEL description="NETORA Mock API Server"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY mock_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mock_server/ ./mock_server/

EXPOSE 9999

CMD ["uvicorn", "mock_server.main:app", "--host", "0.0.0.0", "--port", "9999"]
