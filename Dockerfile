FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY config ./config
COPY data ./data
COPY src ./src
COPY scripts ./scripts

EXPOSE 8000 8501

CMD ["uvicorn", "backoffice_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
