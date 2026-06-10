FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        fastapi uvicorn[standard] \
        dill numpy pandas scikit-learn lightgbm xgboost catboost \
        loguru pyarrow category-encoders

COPY src/ ./src/
COPY settings/ ./settings/
COPY models/ ./models/
COPY metrics.json ./metrics.json

EXPOSE 8000

CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
