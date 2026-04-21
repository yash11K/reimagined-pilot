# ---- build stage ----
FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

# ---- runtime stage ----
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY kb_manager/ ./kb_manager/

EXPOSE 8000

CMD ["uvicorn", "kb_manager.main:app", "--host", "0.0.0.0", "--port", "8000"]
