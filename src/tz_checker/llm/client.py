import json
import re
import time
from typing import Any, TypeVar

import httpx
import structlog
from pydantic import BaseModel, ValidationError

from tz_checker.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)
log = structlog.get_logger()


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = httpx.Client(base_url=self.settings.ollama_base_url, timeout=self.settings.ollama_timeout, transport=transport)

    # Healthcheck не пробрасывает сетевую ошибку, чтобы агрегированный endpoint продолжал отвечать.
    def healthcheck(self) -> bool:
        try:
            return self.client.get("/api/tags").is_success
        except httpx.HTTPError:
            return False

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self.client.post("/api/embed", json={"model": self.settings.ollama_embedding_model, "input": texts})
        response.raise_for_status()
        return response.json()["embeddings"]

    def generate(self, prompt: str, schema: type[T], context: dict[str, Any] | None = None, template_name: str = "unknown") -> T:
        # Схема передается прямо в prompt, так как native JSON mode поддерживается не всеми моделями.
        schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        full_prompt = f"{prompt}\nКонтекст:\n{json.dumps(context or {}, ensure_ascii=False)}\nJSON Schema:\n{schema_text}\nОтветь только валидным JSON."
        errors: list[str] = []
        for _attempt in range(self.settings.ollama_retries + 1):
            started = time.perf_counter()
            response = self.client.post("/api/generate", json={
                "model": self.settings.ollama_model, "prompt": full_prompt, "stream": False,
                "options": {"temperature": self.settings.ollama_temperature, "num_predict": self.settings.ollama_max_tokens},
            })
            response.raise_for_status()
            raw = response.json().get("response", "")
            try:
                payload = self._json(raw)
                parsed = schema.model_validate(payload)
                log.info("llm_call", model=self.settings.ollama_model, template=template_name, latency_ms=round((time.perf_counter() - started) * 1000), input_token_estimate=len(full_prompt) // 4, output_token_estimate=len(raw) // 4, success=True)
                return parsed
            except (ValueError, ValidationError) as exc:
                # Следующая попытка получает причину ошибки и должна исправить только структуру JSON.
                errors.append(str(exc))
                full_prompt += f"\nПредыдущий ответ невалиден: {exc}. Исправь JSON без пояснений."
        log.error("llm_call", model=self.settings.ollama_model, template=template_name, success=False, validation_errors=errors)
        raise OllamaError("LLM returned invalid structured output")

    # Модели иногда оборачивают корректный JSON в Markdown-блок, который безопасно удаляется.
    @staticmethod
    def _json(raw: str) -> Any:
        cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        return json.loads(cleaned)
