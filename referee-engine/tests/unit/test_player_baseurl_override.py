"""选手级 baseUrl 覆盖：让同一场比赛的不同选手直连不同厂商。"""
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backends.hermes_backend import HermesBackendAdapter  # noqa: E402
from backends.openclaw_backend import OpenClawBackendAdapter  # noqa: E402


GLOBAL_BASE_URL = "https://api.openai.com/v1"
PLAYER_BASE_URL = "https://api.anthropic.com/v1"


def _build_match_config():
    return SimpleNamespace(
        agent_image="alpine/openclaw:latest",
        llm=SimpleNamespace(
            apiKey="global-key",
            baseUrl=GLOBAL_BASE_URL,
            model="gpt-5.2",
            proxy="",
        ),
    )


def _build_player_config(*, base_url=None, api_key=None, model=None):
    return SimpleNamespace(
        apiKey=api_key,
        baseUrl=base_url,
        model=model,
        backend_config=SimpleNamespace(image=None, extra_env={}),
    )


def test_openclaw_client_uses_player_base_url_when_set():
    adapter = OpenClawBackendAdapter()
    client = adapter.create_client(
        _build_match_config(),
        _build_player_config(base_url=PLAYER_BASE_URL),
    )
    assert client.llm_base_url == PLAYER_BASE_URL


def test_openclaw_client_falls_back_to_global_base_url():
    adapter = OpenClawBackendAdapter()
    client = adapter.create_client(
        _build_match_config(),
        _build_player_config(base_url=None),
    )
    assert client.llm_base_url == GLOBAL_BASE_URL


def test_openclaw_client_ignores_blank_player_base_url():
    adapter = OpenClawBackendAdapter()
    client = adapter.create_client(
        _build_match_config(),
        _build_player_config(base_url="   "),
    )
    # 空白字符串视为未覆盖，回退全局
    assert client.llm_base_url == GLOBAL_BASE_URL


def test_hermes_container_env_uses_player_base_url():
    adapter = HermesBackendAdapter()
    spec = adapter.build_agent_container_spec(
        _build_match_config(),
        _build_player_config(base_url=PLAYER_BASE_URL, api_key="player-key"),
    )
    assert spec.environment["OPENAI_BASE_URL"] == PLAYER_BASE_URL
    assert spec.environment["OPENAI_API_KEY"] == "player-key"


def test_hermes_container_env_falls_back_to_global_base_url():
    adapter = HermesBackendAdapter()
    spec = adapter.build_agent_container_spec(
        _build_match_config(),
        _build_player_config(base_url=None),
    )
    assert spec.environment["OPENAI_BASE_URL"] == GLOBAL_BASE_URL


def test_hermes_client_uses_player_base_url_when_set():
    adapter = HermesBackendAdapter()
    client = adapter.create_client(
        _build_match_config(),
        _build_player_config(base_url=PLAYER_BASE_URL),
    )
    assert client.llm_base_url == PLAYER_BASE_URL


def test_player_config_accepts_base_url_field():
    import importlib.util

    spec = importlib.util.spec_from_file_location("test_main_player_cfg", ROOT / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    player = module.PlayerConfig(id=1, name="P1", baseUrl="https://api.deepseek.com/v1")
    assert player.baseUrl == "https://api.deepseek.com/v1"

    default_player = module.PlayerConfig(id=2, name="P2")
    assert default_player.baseUrl is None
