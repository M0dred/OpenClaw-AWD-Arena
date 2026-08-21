"""动态模型列表代理：URL 推导 + 端点集成（mock aiohttp）。"""
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_main_module(module_name: str) -> Any:
    main_path = ROOT / "main.py"
    spec = importlib.util.spec_from_file_location(module_name, main_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


async def _async_noop(*args, **kwargs):
    return None


@pytest.mark.parametrize(
    "base_url,expected",
    [
        ("https://api.openai.com/v1", "https://api.openai.com/v1/models"),
        ("https://api.openai.com/v1/", "https://api.openai.com/v1/models"),
        ("https://api.openai.com/v1/chat/completions", "https://api.openai.com/v1/models"),
        ("https://api.openai.com/v1/completions", "https://api.openai.com/v1/models"),
    ],
)
def test_list_models_url_derives_endpoint(base_url, expected):
    module = _load_main_module(f"test_main_models_url_{abs(hash(base_url))}")
    assert module._list_models_url(base_url) == expected


@pytest.mark.asyncio
async def test_list_models_endpoint_parses_openai_shape(monkeypatch):
    """用 monkeypatch aiohttp 的 post/get 包装，验证端点解析 + 响应字段"""
    monkeypatch.setattr("asyncio.create_subprocess_shell", lambda *args, **kwargs: None)
    module = _load_main_module("test_main_models_endpoint")

    captured: dict = {}

    class _MockResponse:
        status = 200

        async def text(self):
            return json.dumps({
                "object": "list",
                "data": [
                    {"id": "gpt-5.2", "object": "model"},
                    {"id": "claude-sonnet-4-6", "object": "model"},
                    {"id": "deepseek-chat", "object": "model"},
                ],
            })

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _MockSession:
        def get(self, url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return _MockResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: _MockSession())

    monkeypatch.setattr(module.referee, "validate_docker_api_compatibility", _async_noop)

    transport = httpx.ASGITransport(app=module.app)
    async with module.app.router.lifespan_context(module.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/list-models",
                json={
                    "baseUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-test-key",
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is True
            assert payload["models"] == ["gpt-5.2", "claude-sonnet-4-6", "deepseek-chat"]
            assert captured["url"] == "https://api.openai.com/v1/models"
            auth = captured["kwargs"]["headers"]["Authorization"]
            assert auth == "Bearer sk-test-key"


@pytest.mark.asyncio
async def test_list_models_endpoint_handles_non_json(monkeypatch):
    monkeypatch.setattr("asyncio.create_subprocess_shell", lambda *args, **kwargs: None)
    module = _load_main_module("test_main_models_endpoint_bad")

    class _MockResponse:
        status = 200

        async def text(self):
            return "<html>not json</html>"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _MockSession:
        def get(self, url, **kwargs):
            return _MockResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: _MockSession())
    monkeypatch.setattr(module.referee, "validate_docker_api_compatibility", _async_noop)

    transport = httpx.ASGITransport(app=module.app)
    async with module.app.router.lifespan_context(module.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/list-models",
                json={"baseUrl": "https://broken.example/v1"},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is False
            assert "非 JSON" in payload["error"]


@pytest.mark.asyncio
async def test_list_models_endpoint_propagates_http_error(monkeypatch):
    monkeypatch.setattr("asyncio.create_subprocess_shell", lambda *args, **kwargs: None)
    module = _load_main_module("test_main_models_endpoint_http")

    class _MockResponse:
        status = 401

        async def text(self):
            return "unauthorized"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _MockSession:
        def get(self, url, **kwargs):
            return _MockResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: _MockSession())
    monkeypatch.setattr(module.referee, "validate_docker_api_compatibility", _async_noop)

    transport = httpx.ASGITransport(app=module.app)
    async with module.app.router.lifespan_context(module.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/list-models",
                json={"baseUrl": "https://locked.example/v1", "apiKey": "bad"},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is False
            assert "401" in payload["error"]