"""ELO 等级分模块单元测试。"""
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import httpx
import pytest

import database
import elo


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


def test_expected_score_equal_ratings_is_half():
    assert elo.expected_score(1500.0, 1500.0) == pytest.approx(0.5)


def test_expected_score_favors_stronger_player():
    assert elo.expected_score(1700.0, 1500.0) > 0.5
    assert elo.expected_score(1500.0, 1700.0) < 0.5


def test_expected_score_is_symmetric():
    ea = elo.expected_score(1600.0, 1400.0)
    eb = elo.expected_score(1400.0, 1600.0)
    assert ea + eb == pytest.approx(1.0)


def test_two_player_win_is_zero_sum():
    standings = [("model-a", "Model A", 300), ("model-b", "Model B", 50)]
    updates = elo.compute_updates({}, standings)
    by_key = {u.entity_key: u for u in updates}

    assert by_key["model-a"].result == "win"
    assert by_key["model-b"].result == "loss"
    assert by_key["model-a"].delta == pytest.approx(-by_key["model-b"].delta)
    assert by_key["model-a"].new_rating > elo.DEFAULT_RATING
    assert by_key["model-b"].new_rating < elo.DEFAULT_RATING


def test_draw_between_equal_players_keeps_ratings():
    standings = [("model-a", "Model A", 100), ("model-b", "Model B", 100)]
    updates = elo.compute_updates({}, standings)
    for update in updates:
        assert update.result == "draw"
        assert update.delta == pytest.approx(0.0)


def test_single_player_returns_no_updates():
    assert elo.compute_updates({}, [("solo", "Solo", 100)]) == []


def test_multiplayer_ordering():
    standings = [
        ("a", "A", 500),
        ("b", "B", 300),
        ("c", "C", 100),
        ("d", "D", -100),
    ]
    updates = elo.compute_updates({}, standings)
    by_key = {u.entity_key: u for u in updates}

    assert by_key["a"].result == "win"
    assert by_key["d"].result == "loss"
    assert by_key["a"].delta > by_key["b"].delta > by_key["c"].delta > by_key["d"].delta


def test_upset_moves_ratings_more_than_expected_win():
    # 弱者爆冷应比强者碾压获得更大的分数变动
    upset = elo.compute_updates(
        {"weak": 1400.0, "strong": 1700.0},
        [("weak", "Weak", 100), ("strong", "Strong", 0)],
    )
    routine = elo.compute_updates(
        {"strong": 1700.0, "weak": 1400.0},
        [("strong", "Strong", 100), ("weak", "Weak", 0)],
    )
    upset_gain = next(u for u in upset if u.entity_key == "weak").delta
    routine_gain = next(u for u in routine if u.entity_key == "strong").delta
    assert upset_gain > routine_gain


def test_standings_from_leaderboard_sorts_descending():
    leaderboard = {
        1: {"player_id": 1, "total_score": 50},
        2: {"player_id": 2, "total_score": 300},
        3: {"player_id": 3, "total_score": -20},
    }
    standings = elo.standings_from_leaderboard(leaderboard)
    assert [pid for pid, _ in standings] == [2, 1, 3]


@pytest.mark.asyncio
async def test_apply_rating_update_persists_and_accumulates():
    database._init_db_sync()
    now = datetime.now()

    await database.apply_rating_update(
        "match-1",
        {
            "entity_key": "model-x",
            "display_name": "Model X",
            "old_rating": 1500.0,
            "new_rating": 1516.0,
            "delta": 16.0,
            "result": "win",
        },
        now,
    )
    await database.apply_rating_update(
        "match-2",
        {
            "entity_key": "model-x",
            "display_name": "Model X",
            "old_rating": 1516.0,
            "new_rating": 1508.0,
            "delta": -8.0,
            "result": "loss",
        },
        now,
    )

    ratings = await database.load_ratings()
    row = ratings["model-x"]
    assert row["rating"] == pytest.approx(1508.0)
    assert row["matches_played"] == 2
    assert row["wins"] == 1
    assert row["losses"] == 1
    assert row["draws"] == 0
    assert row["last_match_id"] == "match-2"

@pytest.mark.asyncio
async def test_ratings_endpoint_returns_sorted_rankings(monkeypatch):
    monkeypatch.setattr("asyncio.create_subprocess_shell", lambda *args, **kwargs: None)
    module = _load_main_module("test_main_ratings_endpoint")
    monkeypatch.setattr(module.referee, "validate_docker_api_compatibility", _async_noop)

    now = datetime.now()
    await module.database.apply_rating_update(
        "match-seed",
        {
            "entity_key": "model-strong",
            "display_name": "Model Strong",
            "old_rating": 1500.0,
            "new_rating": 1620.0,
            "delta": 120.0,
            "result": "win",
        },
        now,
    )
    await module.database.apply_rating_update(
        "match-seed",
        {
            "entity_key": "model-weak",
            "display_name": "Model Weak",
            "old_rating": 1500.0,
            "new_rating": 1380.0,
            "delta": -120.0,
            "result": "loss",
        },
        now,
    )

    transport = httpx.ASGITransport(app=module.app)
    async with module.app.router.lifespan_context(module.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/ratings")
            assert response.status_code == 200
            rows = response.json()["ratings"]
            assert [row["entity_key"] for row in rows] == ["model-strong", "model-weak"]
            assert rows[0]["rank"] == 1 and rows[1]["rank"] == 2
            assert rows[0]["rating"] == pytest.approx(1620.0)
