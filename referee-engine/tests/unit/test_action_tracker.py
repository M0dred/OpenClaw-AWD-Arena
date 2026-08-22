"""赛后行为分析模块测试。"""
import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import action_tracker


def _make_state(player_id, score=0, attack_score=0, defense_score=0,
                flags_captured=0, flags_lost=0, sla_down_minutes=0):
    return SimpleNamespace(
        player_id=player_id,
        score=score,
        attack_score=attack_score,
        defense_score=defense_score,
        flags_captured=flags_captured,
        flags_lost=flags_lost,
        sla_down_minutes=sla_down_minutes,
    )


ATTACK_START = datetime(2026, 8, 22, 10, 0, 0)
MATCH_START = ATTACK_START - timedelta(minutes=10)
MATCH_END = ATTACK_START + timedelta(minutes=50)

BASE_IDENTITY = {
    1: {"model": "gpt-5.2", "display_name": "GPT-5.2（P1）"},
    2: {"model": "claude-sonnet-4-6", "display_name": "Claude Sonnet 4.6（P2）"},
}


def _base_submissions():
    return [
        {
            "attacker_id": 1, "victim_id": 2, "flag": "FLAG{a1}",
            "success": True, "reason": "success", "points": 100,
            "timestamp": (ATTACK_START + timedelta(seconds=120)).isoformat(),
            "flag_slot": "database_flag", "flag_index": 2,
        },
        {
            "attacker_id": 1, "victim_id": 2, "flag": "FLAG{a2}",
            "success": True, "reason": "success", "points": 100,
            "timestamp": (ATTACK_START + timedelta(seconds=300)).isoformat(),
            "flag_slot": "etc_flag", "flag_index": 3,
        },
        {
            "attacker_id": 2, "victim_id": 1, "flag": "FLAG{b1}",
            "success": False, "reason": "invalid_flag", "points": 0,
            "timestamp": (ATTACK_START + timedelta(seconds=60)).isoformat(),
        },
        {
            "attacker_id": 2, "victim_id": 1, "flag": "FLAG{b2}",
            "success": True, "reason": "success", "points": 100,
            "timestamp": (ATTACK_START + timedelta(seconds=900)).isoformat(),
            "flag_slot": "admin_notes", "flag_index": 1,
        },
    ]


def _base_players():
    return {
        1: _make_state(1, score=150, attack_score=200, flags_captured=2),
        2: _make_state(2, score=50, attack_score=100, flags_captured=1,
                       flags_lost=2, defense_score=-100, sla_down_minutes=0),
    }


def test_basic_analytics_computation():
    analytics = action_tracker.compute_match_analytics(
        match_id="test-match",
        started_at=MATCH_START,
        attack_started_at=ATTACK_START,
        finished_at=MATCH_END,
        players_state=_base_players(),
        submissions=_base_submissions(),
        identity_map=BASE_IDENTITY,
    )

    assert analytics.match_id == "test-match"
    assert analytics.duration_seconds == 3600.0
    assert analytics.defense_duration_seconds == 600.0
    assert analytics.attack_duration_seconds == 3000.0
    assert len(analytics.players) == 2


def test_time_to_first_exploit():
    analytics = action_tracker.compute_match_analytics(
        match_id="t1",
        started_at=MATCH_START,
        attack_started_at=ATTACK_START,
        finished_at=MATCH_END,
        players_state=_base_players(),
        submissions=_base_submissions(),
        identity_map=BASE_IDENTITY,
    )
    p1 = next(p for p in analytics.players if p.player_id == 1)
    p2 = next(p for p in analytics.players if p.player_id == 2)

    assert p1.time_to_first_exploit_seconds == 120.0
    assert p2.time_to_first_exploit_seconds == 900.0

    assert analytics.summary["fastest_exploit_seconds"] == 120.0
    assert analytics.summary["slowest_exploit_seconds"] == 900.0


def test_attack_path_coverage():
    analytics = action_tracker.compute_match_analytics(
        match_id="t2",
        started_at=MATCH_START,
        attack_started_at=ATTACK_START,
        finished_at=MATCH_END,
        players_state=_base_players(),
        submissions=_base_submissions(),
        identity_map=BASE_IDENTITY,
    )
    p1 = next(p for p in analytics.players if p.player_id == 1)
    p2 = next(p for p in analytics.players if p.player_id == 2)

    assert p1.attack_slots_captured == ["database_flag", "etc_flag"]
    assert p2.attack_slots_captured == ["admin_notes"]
    assert analytics.summary["attack_path_coverage"]["unique_slots_attacked"] == 3


def test_submission_efficiency():
    analytics = action_tracker.compute_match_analytics(
        match_id="t3",
        started_at=MATCH_START,
        attack_started_at=ATTACK_START,
        finished_at=MATCH_END,
        players_state=_base_players(),
        submissions=_base_submissions(),
        identity_map=BASE_IDENTITY,
    )
    p1 = next(p for p in analytics.players if p.player_id == 1)
    p2 = next(p for p in analytics.players if p.player_id == 2)

    assert p1.submissions_made == 2
    assert p1.successful_submissions == 2
    assert p1.submission_success_rate == 1.0
    assert p1.score_per_submission == 100.0

    assert p2.submissions_made == 2
    assert p2.successful_submissions == 1
    assert p2.submission_success_rate == 0.5


def test_player_with_no_submissions():
    players = _base_players()
    players[3] = _make_state(3, score=0)
    analytics = action_tracker.compute_match_analytics(
        match_id="t4",
        started_at=MATCH_START,
        attack_started_at=ATTACK_START,
        finished_at=MATCH_END,
        players_state=players,
        submissions=_base_submissions(),
        identity_map={**BASE_IDENTITY, 3: {"model": None, "display_name": "Player 3"}},
    )
    p3 = next(p for p in analytics.players if p.player_id == 3)
    assert p3.submissions_made == 0
    assert p3.time_to_first_exploit_seconds is None
    assert p3.submission_success_rate == 0.0


def test_submission_timeline():
    analytics = action_tracker.compute_match_analytics(
        match_id="t5",
        started_at=MATCH_START,
        attack_started_at=ATTACK_START,
        finished_at=MATCH_END,
        players_state=_base_players(),
        submissions=_base_submissions(),
        identity_map=BASE_IDENTITY,
    )
    p1 = next(p for p in analytics.players if p.player_id == 1)
    assert len(p1.submission_timeline) == 2
    assert p1.submission_timeline[0]["elapsed_seconds"] == 120.0
    assert p1.submission_timeline[0]["success"] is True
    assert p1.submission_timeline[0]["flag_slot"] == "database_flag"
    assert p1.submission_timeline[1]["elapsed_seconds"] == 300.0


def test_summary_stats():
    analytics = action_tracker.compute_match_analytics(
        match_id="t6",
        started_at=MATCH_START,
        attack_started_at=ATTACK_START,
        finished_at=MATCH_END,
        players_state=_base_players(),
        submissions=_base_submissions(),
        identity_map=BASE_IDENTITY,
    )
    s = analytics.summary
    assert s["total_submissions"] == 4
    assert s["total_successful"] == 3
    assert s["players_with_exploit"] == 2
    assert s["players_without_exploit"] == 0


def test_to_dict_serialization():
    analytics = action_tracker.compute_match_analytics(
        match_id="t7",
        started_at=MATCH_START,
        attack_started_at=ATTACK_START,
        finished_at=MATCH_END,
        players_state=_base_players(),
        submissions=_base_submissions(),
        identity_map=BASE_IDENTITY,
    )
    d = analytics.to_dict()
    assert d["match_id"] == "t7"
    assert len(d["players"]) == 2
    assert d["players"][0]["player_id"] == 1
    assert d["players"][0]["model"] == "gpt-5.2"
    assert "summary" in d


def test_missing_timestamps_graceful():
    analytics = action_tracker.compute_match_analytics(
        match_id="t8",
        started_at=None,
        attack_started_at=None,
        finished_at=None,
        players_state=_base_players(),
        submissions=[],
        identity_map=BASE_IDENTITY,
    )
    assert analytics.duration_seconds == 0.0
    assert analytics.summary["fastest_exploit_seconds"] is None
    p1 = next(p for p in analytics.players if p.player_id == 1)
    assert p1.time_to_first_exploit_seconds is None


# ---------- 端点集成测试 ----------

import httpx


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


@pytest.mark.asyncio
async def test_analytics_endpoint_returns_404_for_unknown_match(monkeypatch):
    monkeypatch.setattr("asyncio.create_subprocess_shell", lambda *args, **kwargs: None)
    module = _load_main_module("test_main_analytics_404")
    monkeypatch.setattr(module.referee, "validate_docker_api_compatibility", _async_noop)

    transport = httpx.ASGITransport(app=module.app)
    async with module.app.router.lifespan_context(module.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/api/matches/nonexistent/analytics")
            assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analytics_endpoint_live_computation(monkeypatch):
    """对一个内存中的比赛实时计算分析。"""
    monkeypatch.setattr("asyncio.create_subprocess_shell", lambda *args, **kwargs: None)
    module = _load_main_module("test_main_analytics_live")
    monkeypatch.setattr(module.referee, "validate_docker_api_compatibility", _async_noop)

    from types import SimpleNamespace
    now = datetime.now()
    config = module.MatchConfig(
        players=[
            module.PlayerConfig(id=1, name="P1", model="gpt-5.2"),
            module.PlayerConfig(id=2, name="P2", model="claude-sonnet-4-6"),
        ],
    )
    match = module.MatchState("analytics-live-test", config)
    match.started_at = now - timedelta(minutes=60)
    match.attack_started_at = now - timedelta(minutes=50)
    match.finished_at = now
    match.players[1] = SimpleNamespace(
        player_id=1, score=200, attack_score=200, defense_score=0,
        flags_captured=2, flags_lost=0, sla_down_minutes=0,
    )
    match.players[2] = SimpleNamespace(
        player_id=2, score=-50, attack_score=0, defense_score=-50,
        flags_captured=0, flags_lost=2, sla_down_minutes=1,
    )
    match.persisted_submissions = [
        {
            "attacker_id": 1, "victim_id": 2, "flag": "FLAG{x}",
            "success": True, "reason": "success", "points": 100,
            "timestamp": (now - timedelta(minutes=45)).isoformat(),
            "flag_slot": "database_flag", "flag_index": 2,
        },
    ]
    module.referee.matches["analytics-live-test"] = match

    transport = httpx.ASGITransport(app=module.app)
    async with module.app.router.lifespan_context(module.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/api/matches/analytics-live-test/analytics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["live"] is True
            analytics = data["analytics"]
            assert len(analytics["players"]) == 2
            p1 = next(p for p in analytics["players"] if p["player_id"] == 1)
            assert p1["time_to_first_exploit_seconds"] == 300.0
            assert p1["attack_slots_captured"] == ["database_flag"]
            assert analytics["summary"]["players_with_exploit"] == 1
