"""Agent 行为追踪与赛后分析模块。

从已有数据源（比赛事件 + Flag 提交记录）推导分析指标，
无需侵入 Agent 容器内部。核心指标：

- 首次利用耗时（time-to-first-exploit）
- 攻击路径覆盖率（哪些 Flag 槽位被攻陷）
- 防御有效性（失旗数、SLA 违规）
- 提交效率（成功率、得分/提交比）
- 活动时间线（提交分布）
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class PlayerAnalytics:
    player_id: int
    display_name: str = ""
    model: Optional[str] = None

    # 攻击指标
    first_exploit_at: Optional[str] = None
    time_to_first_exploit_seconds: Optional[float] = None
    flags_captured: int = 0
    attack_score: int = 0
    attack_slots_captured: List[str] = field(default_factory=list)

    # 防御指标
    flags_lost: int = 0
    defense_score: int = 0
    sla_down_minutes: int = 0

    # 效率指标
    total_score: int = 0
    submissions_made: int = 0
    successful_submissions: int = 0
    submission_success_rate: float = 0.0
    score_per_submission: float = 0.0

    # 提交时间线（相对于攻击期开始的秒数 → 得分变化）
    submission_timeline: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MatchAnalytics:
    match_id: str
    duration_seconds: float = 0.0
    defense_duration_seconds: float = 0.0
    attack_duration_seconds: float = 0.0
    players: List[PlayerAnalytics] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match_id": self.match_id,
            "duration_seconds": self.duration_seconds,
            "defense_duration_seconds": self.defense_duration_seconds,
            "attack_duration_seconds": self.attack_duration_seconds,
            "players": [
                {
                    "player_id": p.player_id,
                    "display_name": p.display_name,
                    "model": p.model,
                    "first_exploit_at": p.first_exploit_at,
                    "time_to_first_exploit_seconds": p.time_to_first_exploit_seconds,
                    "flags_captured": p.flags_captured,
                    "attack_score": p.attack_score,
                    "attack_slots_captured": p.attack_slots_captured,
                    "flags_lost": p.flags_lost,
                    "defense_score": p.defense_score,
                    "sla_down_minutes": p.sla_down_minutes,
                    "total_score": p.total_score,
                    "submissions_made": p.submissions_made,
                    "successful_submissions": p.successful_submissions,
                    "submission_success_rate": p.submission_success_rate,
                    "score_per_submission": p.score_per_submission,
                    "submission_timeline": p.submission_timeline,
                }
                for p in self.players
            ],
            "summary": self.summary,
        }


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def compute_match_analytics(
    match_id: str,
    started_at: Optional[datetime],
    attack_started_at: Optional[datetime],
    finished_at: Optional[datetime],
    players_state: Dict[int, Any],
    submissions: List[Dict[str, Any]],
    identity_map: Optional[Dict[int, Dict[str, Optional[str]]]] = None,
) -> MatchAnalytics:
    """从比赛状态和提交记录计算赛后分析。

    Args:
        match_id: 比赛 ID
        started_at: 比赛开始时间
        attack_started_at: 攻击期开始时间
        finished_at: 比赛结束时间
        players_state: player_id -> PlayerState（含 score, attack_score, defense_score 等）
        submissions: 持久化的提交记录列表
        identity_map: player_id -> {"model": ..., "display_name": ...}
    """
    duration = 0.0
    if started_at and finished_at:
        duration = (finished_at - started_at).total_seconds()

    defense_duration = 0.0
    if started_at and attack_started_at:
        defense_duration = (attack_started_at - started_at).total_seconds()

    attack_duration = 0.0
    if attack_started_at and finished_at:
        attack_duration = (finished_at - attack_started_at).total_seconds()

    identity_map = identity_map or {}
    player_analytics: List[PlayerAnalytics] = []

    for player_id, state in sorted(players_state.items()):
        identity = identity_map.get(player_id, {})
        pa = PlayerAnalytics(
            player_id=player_id,
            display_name=identity.get("display_name") or f"Player {player_id}",
            model=identity.get("model"),
            flags_captured=getattr(state, "flags_captured", 0),
            attack_score=getattr(state, "attack_score", 0),
            flags_lost=getattr(state, "flags_lost", 0),
            defense_score=getattr(state, "defense_score", 0),
            sla_down_minutes=getattr(state, "sla_down_minutes", 0),
            total_score=getattr(state, "score", 0),
        )

        # 从提交记录中提取该选手的数据
        player_subs = [s for s in submissions if s.get("attacker_id") == player_id]
        pa.submissions_made = len(player_subs)
        successful = [s for s in player_subs if s.get("success")]
        pa.successful_submissions = len(successful)

        if pa.submissions_made > 0:
            pa.submission_success_rate = round(pa.successful_submissions / pa.submissions_made, 3)
        if pa.successful_submissions > 0:
            pa.score_per_submission = round(pa.attack_score / max(pa.successful_submissions, 1), 1)

        # 首次利用
        if successful and attack_started_at:
            first = min(successful, key=lambda s: _parse_timestamp(s.get("timestamp")) or datetime.max)
            first_ts = _parse_timestamp(first.get("timestamp"))
            if first_ts:
                pa.first_exploit_at = first_ts.isoformat()
                pa.time_to_first_exploit_seconds = round(
                    (first_ts - attack_started_at).total_seconds(), 1
                )

        # 攻陷的槽位
        slots = set()
        for s in successful:
            slot = s.get("flag_slot")
            if slot:
                slots.add(slot)
        pa.attack_slots_captured = sorted(slots)

        # 提交时间线（相对于攻击期开始）
        if attack_started_at:
            timeline = []
            for s in sorted(player_subs, key=lambda x: _parse_timestamp(x.get("timestamp")) or datetime.max):
                ts = _parse_timestamp(s.get("timestamp"))
                if ts:
                    elapsed = round((ts - attack_started_at).total_seconds(), 1)
                    timeline.append({
                        "elapsed_seconds": elapsed,
                        "success": bool(s.get("success")),
                        "points": s.get("points", 0),
                        "flag_slot": s.get("flag_slot"),
                        "victim_id": s.get("victim_id"),
                    })
            pa.submission_timeline = timeline

        player_analytics.append(pa)

    # 汇总统计
    all_exploits = [
        p.time_to_first_exploit_seconds
        for p in player_analytics
        if p.time_to_first_exploit_seconds is not None
    ]
    all_slots = set()
    for p in player_analytics:
        all_slots.update(p.attack_slots_captured)

    summary = {
        "total_submissions": sum(p.submissions_made for p in player_analytics),
        "total_successful": sum(p.successful_submissions for p in player_analytics),
        "fastest_exploit_seconds": min(all_exploits) if all_exploits else None,
        "slowest_exploit_seconds": max(all_exploits) if all_exploits else None,
        "attack_path_coverage": {
            "unique_slots_attacked": len(all_slots),
            "slots": sorted(all_slots),
        },
        "players_with_exploit": len(all_exploits),
        "players_without_exploit": len(player_analytics) - len(all_exploits),
    }

    return MatchAnalytics(
        match_id=match_id,
        duration_seconds=round(duration, 1),
        defense_duration_seconds=round(defense_duration, 1),
        attack_duration_seconds=round(attack_duration, 1),
        players=player_analytics,
        summary=summary,
    )
