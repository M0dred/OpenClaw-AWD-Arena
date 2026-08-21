"""ELO 等级分引擎 — 跨比赛的模型能力排名。

单场比赛的得分受场次随机性影响较大，无法直接横向比较不同模型。
本模块在每场比赛结束后，根据最终排名对参赛实体（默认为模型）做
成对 ELO 更新，积累出跨场次的稳定排名。

设计要点：
- 多人场展开为成对对局：排名高者得 1 分，低者 0 分，同分视为平局各 0.5
- 实体键优先使用模型名（player.model），缺省回退到选手名；
  同分平局不会剧烈拉动分数，K 因子保持保守
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

DEFAULT_RATING = 1500.0
DEFAULT_K_FACTOR = 32.0

# 排名差超过该分数时视为必胜/必败，避免 ELO 在极端分差下抖动
RATING_CAP_DIFF = 400.0


@dataclass
class RatingUpdate:
    entity_key: str
    display_name: str
    old_rating: float
    new_rating: float
    delta: float
    result: str  # "win" | "loss" | "draw"
    matches_played_delta: int = field(default=1)


def expected_score(rating_a: float, rating_b: float) -> float:
    """A 对 B 的期望得分（0~1）。"""
    diff = max(-RATING_CAP_DIFF, min(RATING_CAP_DIFF, rating_a - rating_b))
    return 1.0 / (1.0 + 10.0 ** (-diff / 400.0))


def standings_from_leaderboard(leaderboard: Dict[int, Dict]) -> List[Tuple[int, int]]:
    """从排行榜提取 (player_id, total_score) 列表，保持总分降序。"""
    rows: List[Tuple[int, int]] = []
    for player_id, row in leaderboard.items():
        if not isinstance(row, dict):
            continue
        score = row.get("total_score", row.get("score", 0))
        if not isinstance(score, (int, float)):
            score = 0
        rows.append((int(player_id), int(score)))
    rows.sort(key=lambda item: item[1], reverse=True)
    return rows


def compute_updates(
    ratings: Dict[str, float],
    standings: List[Tuple[str, str, int]],
    k_factor: float = DEFAULT_K_FACTOR,
) -> List[RatingUpdate]:
    """根据最终排名计算 ELO 更新。

    Args:
        ratings: 现有评分表 entity_key -> rating（缺省按 DEFAULT_RATING 处理）
        standings: [(entity_key, display_name, total_score)]，顺序不限
        k_factor: K 因子

    Returns:
        每个参赛实体一条 RatingUpdate
    """
    ordered = sorted(standings, key=lambda item: item[2], reverse=True)
    if len(ordered) < 2:
        return []

    deltas: Dict[str, float] = {key: 0.0 for key, _, _ in ordered}
    results: Dict[str, Tuple[int, int, int]] = {key: (0, 0, 0) for key, _, _ in ordered}

    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            key_a, _, score_a = ordered[i]
            key_b, _, score_b = ordered[j]
            if key_a == key_b:
                continue
            rating_a = ratings.get(key_a, DEFAULT_RATING)
            rating_b = ratings.get(key_b, DEFAULT_RATING)

            if score_a > score_b:
                actual_a, actual_b, result_a, result_b = 1.0, 0.0, "win", "loss"
            elif score_a < score_b:
                actual_a, actual_b, result_a, result_b = 0.0, 1.0, "loss", "win"
            else:
                actual_a, actual_b, result_a, result_b = 0.5, 0.5, "draw", "draw"

            deltas[key_a] += k_factor * (actual_a - expected_score(rating_a, rating_b))
            deltas[key_b] += k_factor * (actual_b - expected_score(rating_b, rating_a))

            wins_a, losses_a, draws_a = results[key_a]
            wins_b, losses_b, draws_b = results[key_b]
            results[key_a] = (
                wins_a + (result_a == "win"),
                losses_a + (result_a == "loss"),
                draws_a + (result_a == "draw"),
            )
            results[key_b] = (
                wins_b + (result_b == "win"),
                losses_b + (result_b == "loss"),
                draws_b + (result_b == "draw"),
            )

    display_names = {key: display for key, display, _ in ordered}
    updates: List[RatingUpdate] = []
    for key, _, score in ordered:
        old = ratings.get(key, DEFAULT_RATING)
        delta = round(deltas[key], 2)
        wins, losses, draws = results[key]
        if wins > losses:
            outcome = "win"
        elif losses > wins:
            outcome = "loss"
        else:
            outcome = "draw"
        updates.append(
            RatingUpdate(
                entity_key=key,
                display_name=display_names.get(key) or key,
                old_rating=round(old, 2),
                new_rating=round(old + delta, 2),
                delta=delta,
                result=outcome,
            )
        )
    return updates
