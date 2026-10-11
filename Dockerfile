FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN useradd --create-home app && mkdir -p /data/uploads /data/reports && chown -R app:app /app /data
USER app
CMD ["uvicorn", "tz_checker.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
