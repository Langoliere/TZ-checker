# TZ Checker MVP

Локальный сервис автоматизированной проверки технических заданий DOCX. Детерминированные нарушения отделены от вероятностных LLM-рекомендаций; финальное решение остается за экспертом.

## Архитектура

- FastAPI — REST API; Streamlit — API-only UI.
- Celery + Redis — асинхронный pipeline.
- PostgreSQL — документы, результаты, feedback и RAG chunks; образ pgvector подготовлен для перехода на native vector column.
- Локальное файловое хранилище за интерфейсом `LocalStorage`.
- python-docx — parser; YAML — Rule Engine; Ollama — generation и embeddings.
- Hybrid retrieval объединяет keyword score и cosine similarity на уровне sections.

## Запуск

Требования: Docker Compose, 16 GB RAM минимум для CPU-запуска 14B quantized-модели; рекомендуется 24+ GB RAM и GPU с достаточной VRAM. Первый запуск скачивает модели и требует доступа к Ollama registry; дальнейшая обработка полностью локальна.

```bash
cp .env.example .env
docker compose up --build
```

UI: `http://localhost:8501`, OpenAPI: `http://localhost:8000/docs`.
Для менее мощной машины задайте `OLLAMA_MODEL=qwen2.5:7b-instruct`.

```bash
curl -F "file=@spec.docx" http://localhost:8000/v1/documents
curl http://localhost:8000/v1/documents/<id>/findings
curl -OJ http://localhost:8000/v1/documents/<id>/reports/docx
```

Загрузка эталона:

```bash
curl -F "file=@approved.docx" -F 'metadata={"product_type":"контроллер","domain":"АСУ ТП","status":"approved","version":"1.0"}' http://localhost:8000/v1/references
```

## Разработка

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check
mypy src
```

Новые правила добавляются в `src/tz_checker/rules/default_rules.yaml`: уникальный `rule_id`, severity, scope, condition, message и recommendation. Поддержаны required sections/phrases, forbidden phrases, table columns/completeness, normative regex и consistency parameter.

## Ограничения MVP

- Сложная Word-нумерация, text boxes, tracked changes, формулы и вложенные таблицы извлекаются не полностью; headings определяются стилями и эвристиками.
- Vector хранится JSON и ранжируется приложением; native pgvector/HNSW migration остается обязательной до production.
- LLM reviewer-ы и structured validation реализованы, но полный orchestration пяти reviewer-ов в worker pipeline еще требует подключения к RAG результатам.
- Нет auth/tenant isolation, antivirus, rate limiting, retention/backup, Prometheus и distributed tracing.
- Правила являются стартовым набором и требуют утверждения отраслевым экспертом.
- Качество LLM/RAG не измерено на экспертно размеченном evaluation set.
