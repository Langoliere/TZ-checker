# Команды проекта

- Установка: `python -m pip install -e ".[dev]"`
- Тесты: `pytest -q`
- Проверка стиля: `ruff check`
- Проверка конфигурации Compose: `docker compose config`
- Локальный запуск: скопировать `.env.example` в `.env`, затем выполнить `docker compose up --build`.
