FROM python:3.12-slim

WORKDIR /app/backend

RUN pip install --no-cache-dir uv

COPY backend/ ./
RUN uv sync --frozen --no-dev --no-cache

ENV LISTEN_URL=0.0.0.0:8080
ENV DATABASE_PATH=/app/backend/data/firesimplefin.db

RUN mkdir -p /app/backend/data

EXPOSE 8080

CMD ["uv", "run", "--no-dev", "--frozen", "uvicorn", "firesimplefin.main:app", "--host", "0.0.0.0", "--port", "8080"]
