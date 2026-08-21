"""密钥脱敏与 test-llm URL 归一化测试。"""
import importlib.util
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


# ---------- _mask_secret ----------

def test_mask_secret_keeps_head_and_tail():
    module = _load_main_module("test_main_mask_basic")
    masked = module._mask_secret("sk-abcdef1234567890WXYZ")
    assert masked.startswith("sk-a")
    assert masked.endswith("WXYZ")
    assert "abcdef1234567890" not in masked


def test_mask_secret_hides_short_values_entirely():
    module = _load_main_module("test_main_mask_short")
    assert module._mask_secret("short1") == "****"


def test_mask_secret_passthrough_empty_and_none():
    module = _load_main_module("test_main_mask_empty")
    assert module._mask_secret(None) is None
    assert module._mask_secret("") == ""


def test_is_masked_secret_detects_masked_values():
    module = _load_main_module("test_main_mask_detect")
    assert module._is_masked_secret("sk-a…WXYZ") is True
    assert module._is_masked_secret("****") is True
    assert module._is_masked_secret("sk-real-secret-value") is False
    assert module._is_masked_secret(None) is False


# ---------- _mask_config_dict / _mask_template ----------

def _sample_config():
    return {
        "llm": {"provider": "openai", "baseUrl": "https://api.openai.com/v1", "apiKey": "sk-verylongsecretkey1234"},
        "players": [
            {"id": 1, "name": "P1", "model": "gpt-5.2", "apiKey": "sk-playeronesecretkey9"},
            {"id": 2, "name": "P2", "model": "claude-sonnet-4-6"},
        ],
    }


def test_mask_config_dict_masks_llm_and_player_keys():
    module = _load_main_module("test_main_mask_cfg")
    config = _sample_config()
    masked = module._mask_config_dict(config)

    assert masked["llm"]["apiKey"].startswith("sk-v")
    assert "verylongsecretkey" not in masked["llm"]["apiKey"]
    assert masked["players"][0]["apiKey"].startswith("sk-p")
    assert "playeronesecretkey" not in masked["players"][0]["apiKey"]
    # 无 key 的选手不受影响，非敏感字段原样保留
    assert "apiKey" not in masked["players"][1] or masked["players"][1]["apiKey"] in (None, "")
    assert masked["llm"]["baseUrl"] == "https://api.openai.com/v1"
    assert masked["players"][0]["model"] == "gpt-5.2"


def test_mask_config_dict_does_not_mutate_original():
    module = _load_main_module("test_main_mask_orig")
    config = _sample_config()
    module._mask_config_dict(config)
    assert config["llm"]["apiKey"] == "sk-verylongsecretkey1234"
    assert config["players"][0]["apiKey"] == "sk-playeronesecretkey9"


def test_mask_template_keeps_store_object_plaintext():
    module = _load_main_module("test_main_mask_tpl")
    template = {"id": "tpl-1", "name": "demo", "config": _sample_config()}
    masked = module._mask_template(template)
    assert template["config"]["llm"]["apiKey"] == "sk-verylongsecretkey1234"
    assert masked["config"]["llm"]["apiKey"] != "sk-verylongsecretkey1234"
    assert masked["id"] == "tpl-1"
    # 掩码副本与原对象不共享引用
    assert masked["config"] is not template["config"]


# ---------- _normalize_chat_completions_url ----------

@pytest.mark.parametrize(
    "base_url,expected",
    [
        ("https://api.openai.com/v1", "https://api.openai.com/v1/chat/completions"),
        ("https://api.openai.com/v1/", "https://api.openai.com/v1/chat/completions"),
        ("  https://api.openai.com/v1  ", "https://api.openai.com/v1/chat/completions"),
        ("https://api.openai.com/v1/chat/completions", "https://api.openai.com/v1/chat/completions"),
        ("https://gw.local/v1/completions", "https://gw.local/v1/chat/completions"),
        ("https://gw.local/v1/chat/completions/", "https://gw.local/v1/chat/completions"),
    ],
)
def test_normalize_chat_completions_url(base_url, expected):
    module = _load_main_module(f"test_main_url_norm_{abs(hash(base_url))}")
    assert module._normalize_chat_completions_url(base_url) == expected


# ---------- 端点集成：模板 API 返回脱敏 ----------

@pytest.mark.asyncio
async def test_template_endpoints_return_masked_keys(monkeypatch):
    monkeypatch.setattr("asyncio.create_subprocess_shell", lambda *args, **kwargs: None)
    module = _load_main_module("test_main_mask_endpoint")
    monkeypatch.setattr(module.referee, "validate_docker_api_compatibility", _async_noop)

    secret = "sk-endpointintegration-key"
    payload = {
        "name": "Masked Template",
        "description": "",
        "tags": [],
        # 显式要求模板保存 API Key（TemplateStore 默认会剥除），
        # 以此验证"即使内部保留了明文，API 返回也必须是掩码"
        "saveOptions": {"includeAPIKeys": True},
        "config": {
            "llm": {"provider": "openai", "baseUrl": "https://api.openai.com/v1", "apiKey": secret},
            "players": [{"id": 1, "name": "P1", "model": "gpt-5.2", "apiKey": "sk-player-level-secret"}],
        },
    }

    transport = httpx.ASGITransport(app=module.app)
    async with module.app.router.lifespan_context(module.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post("/api/templates", json=payload)
            assert created.status_code == 200
            body = created.json()
            template_id = body["templateId"]
            assert secret not in __import__("json").dumps(body)
            assert "sk-player-level-secret" not in __import__("json").dumps(body)

            listed = await client.get("/api/templates")
            assert listed.status_code == 200
            assert secret not in listed.text

            fetched = await client.get(f"/api/templates/{template_id}")
            assert fetched.status_code == 200
            assert secret not in fetched.text

            # 内部存储仍为明文（比赛启动等内部流程依赖完整凭据）
            stored = module.template_store.get(template_id)
            assert stored["config"]["llm"]["apiKey"] == secret
