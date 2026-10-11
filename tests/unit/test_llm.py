import httpx

from tz_checker.config import Settings
from tz_checker.llm.client import OllamaClient
from tz_checker.models.schemas import FindingsResponse


def test_validates_structured_response():
    payload = '{"findings": []}'
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"response": payload}))
    client = OllamaClient(Settings(ollama_retries=0), transport=transport)
    assert client.generate("test", FindingsResponse).findings == []
