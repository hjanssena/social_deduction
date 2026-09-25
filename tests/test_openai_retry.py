"""The OpenAI-compatible client retries server-side failures, not bad requests."""
from services.openai_service import OpenAIService


class Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text, self.ok = status, text, 200 <= status < 300


def service(monkeypatch, responses):
    calls = []

    def post(*a, **k):
        calls.append(1)
        return responses.pop(0)

    monkeypatch.setattr("services.openai_service.requests.post", post)
    monkeypatch.setattr("services.openai_service.time.sleep", lambda s: None)
    return OpenAIService({"llm": {"openai": {}}}), calls


def test_upstream_failure_is_retried(monkeypatch):
    svc, calls = service(monkeypatch, [Resp(400, '{"error":{"type":"server_error"}}'), Resp(200)])
    assert svc._post({}).ok and len(calls) == 2


def test_a_real_bad_request_is_not_retried(monkeypatch):
    svc, calls = service(monkeypatch, [Resp(400, '{"error":{"type":"invalid_request_error"}}')])
    assert not svc._post({}).ok and len(calls) == 1


def test_gives_up_after_the_retries(monkeypatch):
    svc, calls = service(monkeypatch, [Resp(503)] * 3)
    assert svc._post({}).status_code == 503 and len(calls) == 3
