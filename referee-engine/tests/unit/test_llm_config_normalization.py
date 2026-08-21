"""LLM 配置归一化测试：provider 预设补全 baseUrl。"""
import importlib.util
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_main_module(module_name: str):
    main_path = ROOT / "main.py"
    spec = importlib.util.spec_from_file_location(module_name, main_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


async def _async_noop(*args, **kwargs):
    return None


def _config(module: Any, provider: str, base_url: str = ""):
    return module.MatchConfig(
        llm=module.LLMConfig(provider=provider, baseUrl=base_url),
        players=[module.PlayerConfig(id=1, name="P1")],
    )


def test_fills_base_url_from_known_provider():
    module = _load_main_module("test_main_llm_norm_basic")
    config = _config(module, provider="anthropic")
    result = module.RefereeEngine._normalize_llm_config(config)
    assert result.llm.baseUrl == "https://api.anthropic.com/v1"


def test_provider_lookup_is_case_insensitive():
    module = _load_main_module("test_main_llm_norm_case")
    config = _config(module, provider="OpenAI")
    result = module.RefereeEngine._normalize_llm_config(config)
    assert result.llm.baseUrl == "https://api.openai.com/v1"


def test_explicit_base_url_is_not_overridden():
    module = _load_main_module("test_main_llm_norm_keep")
    config = _config(module, provider="openai", base_url="https://my-proxy.local/v1")
    result = module.RefereeEngine._normalize_llm_config(config)
    assert result.llm.baseUrl == "https://my-proxy.local/v1"


@pytest.mark.parametrize("provider", ["custom", "", "unknown-provider"])
def test_unknown_or_custom_provider_keeps_base_url(provider):
    module = _load_main_module(f"test_main_llm_norm_custom_{provider or 'empty'}")
    config = _config(module, provider=provider)
    result = module.RefereeEngine._normalize_llm_config(config)
    assert result.llm.baseUrl == ""


def test_all_preset_base_urls_are_https_or_localhost():
    module = _load_main_module("test_main_llm_norm_urls")
    for provider, base_url in module.RefereeEngine.PROVIDER_BASE_URLS.items():
        assert base_url.startswith(("https://", "http://localhost", "http://host.docker.internal")), (
            f"{provider}: {base_url}"
        )


@pytest.mark.asyncio
async def test_start_match_applies_provider_normalization(monkeypatch):
    """经 /api/matches/start 的完整路径验证：provider=openai 且 baseUrl 为空时自动补全。"""
    monkeypatch.setattr("asyncio.create_subprocess_shell", lambda *args, **kwargs: None)
    module = _load_main_module("test_main_llm_norm_start")

    async def fake_setup_containers(match):
        match.players[1] = module.PlayerState(
            player_id=1,
            container_name="claw_norm_1",
            target_container="target_norm_1",
            target_ip="10.0.0.8",
            network_name="awd_norm_network",
        )
        match.agent_sessions[1] = module.AgentSession(
            player_id=1,
            container_name="claw_norm_1",
            target_container="target_norm_1",
            target_ip="10.0.0.8",
        )
        match.player_ssh_key_materials[1] = module.PlayerSSHKeyMaterial(
            player_id=1,
            private_key="PRIVATE\n",
            public_key="PUBLIC\n",
            helper_path="/usr/local/bin/target-ssh",
        )

    async def fake_initialize_agents(match):
        match.players[1].ready_status = "READY"
        return 1

    async def fake_generate_and_inject(self, players):
        return {1: {"database_flag": "FLAG{norm}"}}

    monkeypatch.setattr(module.referee, "validate_docker_api_compatibility", _async_noop)
    monkeypatch.setattr(module.referee, "broadcast", _async_noop)
    monkeypatch.setattr(module.referee, "_setup_containers", fake_setup_containers)
    monkeypatch.setattr(module.referee, "_initialize_agents", fake_initialize_agents)
    monkeypatch.setattr(module.FlagManager, "generate_and_inject", fake_generate_and_inject)
    monkeypatch.setattr(module.referee, "_flag_refresh_loop", _async_noop)
    monkeypatch.setattr(module.referee, "_match_timer", _async_noop)
    monkeypatch.setattr(module.SLAChecker, "start", lambda self, players, broadcast_callback=None: None)

    payload = {
        "match": {"name": "norm", "duration": 600, "phases": {"defense": 300, "attack": 300}},
        "llm": {"provider": "deepseek", "baseUrl": "", "apiKey": "", "model": "deepseek-chat"},
        "players": [{"id": 1, "name": "P1", "model": None, "apiKey": None, "gatewayPort": None}],
    }

    transport = httpx.ASGITransport(app=module.app)
    async with module.app.router.lifespan_context(module.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/matches/start", json=payload)
            assert response.status_code == 200
            match_id = response.json()["match_id"]

            match = module.referee.matches[match_id]
            await match._startup_task
            assert match.config.llm.baseUrl == "https://api.deepseek.com/v1"
