FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY . .

RUN chmod +x scripts/start_prod.sh \
    && mkdir -p data exports

ENV PYTHONUNBUFFERED=1 \
    MEMORY_BACKEND=disabled \
    ENABLE_SCHEDULER=false \
    ENABLE_LOCAL_EMBEDDINGS=false \
    EXPOSE_APP=false \
    DATABASE_URL=sqlite:///data/arxiv_papers.db

EXPOSE 8000

CMD ["scripts/start_prod.sh"]
