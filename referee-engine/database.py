import asyncio
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "openclaw.db")


def get_db_path() -> str:
    """在调用时解析数据库路径，保证运行期修改 OPENCLAW_DB_PATH 立即生效（测试 monkeypatch 依赖此行为）。"""
    return os.environ.get("OPENCLAW_DB_PATH") or _DEFAULT_DB_PATH


# 兼容旧引用；新代码请使用 get_db_path()
DB_PATH = get_db_path()


def _connect() -> sqlite3.Connection:
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _to_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def _init_db_sync() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS matches (
              match_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              config_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              finished_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              match_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              data_json TEXT NOT NULL,
              timestamp TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              match_id TEXT NOT NULL,
              attacker_id INTEGER NOT NULL,
              victim_id INTEGER,
              declared_target_player_id INTEGER,
              flag TEXT NOT NULL,
              success INTEGER NOT NULL,
              reason TEXT NOT NULL,
              points INTEGER NOT NULL,
              timestamp TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS loops (
              loop_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              repeat_count INTEGER NOT NULL,
              current_iteration INTEGER NOT NULL,
              current_match_id TEXT,
              last_match_id TEXT,
              config_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              stopped_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ratings (
              entity_key TEXT PRIMARY KEY,
              display_name TEXT NOT NULL,
              rating REAL NOT NULL,
              matches_played INTEGER NOT NULL DEFAULT 0,
              wins INTEGER NOT NULL DEFAULT 0,
              losses INTEGER NOT NULL DEFAULT 0,
              draws INTEGER NOT NULL DEFAULT 0,
              last_match_id TEXT,
              updated_at TEXT
            )
            """
        )
        existing_submission_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(submissions)").fetchall()
        }
        if "flag_slot" not in existing_submission_columns:
            conn.execute("ALTER TABLE submissions ADD COLUMN flag_slot TEXT")
        if "flag_index" not in existing_submission_columns:
            conn.execute("ALTER TABLE submissions ADD COLUMN flag_index INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_match_time ON events(match_id, timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_match_time ON submissions(match_id, timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_loops_updated_at ON loops(updated_at)")
        conn.commit()
    finally:
        conn.close()


def _save_match_sync(match_id: str, status: str, config_dict: Dict[str, Any], created_at: datetime) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO matches(match_id, status, config_json, created_at, finished_at)
            VALUES(?, ?, ?, ?, NULL)
            ON CONFLICT(match_id) DO UPDATE SET
              status=excluded.status,
              config_json=excluded.config_json,
              created_at=excluded.created_at
            """,
            (match_id, status, json.dumps(config_dict, ensure_ascii=False), created_at.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _update_match_status_sync(match_id: str, status: str, finished_at: Optional[datetime]) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE matches
            SET status = ?, finished_at = COALESCE(?, finished_at)
            WHERE match_id = ?
            """,
            (status, _to_iso(finished_at), match_id),
        )
        conn.commit()
    finally:
        conn.close()


def _save_event_sync(match_id: str, event_type: str, data: Dict[str, Any], timestamp: datetime) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO events(match_id, event_type, data_json, timestamp)
            VALUES(?, ?, ?, ?)
            """,
            (match_id, event_type, json.dumps(data, ensure_ascii=False), timestamp.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _save_loop_sync(
    loop_id: str,
    status: str,
    repeat_count: int,
    current_iteration: int,
    config_dict: Dict[str, Any],
    created_at: datetime,
    updated_at: datetime,
    current_match_id: Optional[str] = None,
    last_match_id: Optional[str] = None,
    stopped_at: Optional[datetime] = None,
) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO loops(
              loop_id,
              status,
              repeat_count,
              current_iteration,
              current_match_id,
              last_match_id,
              config_json,
              created_at,
              updated_at,
              stopped_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(loop_id) DO UPDATE SET
              status=excluded.status,
              repeat_count=excluded.repeat_count,
              current_iteration=excluded.current_iteration,
              current_match_id=excluded.current_match_id,
              last_match_id=excluded.last_match_id,
              config_json=excluded.config_json,
              updated_at=excluded.updated_at,
              stopped_at=excluded.stopped_at
            """,
            (
                loop_id,
                status,
                repeat_count,
                current_iteration,
                current_match_id,
                last_match_id,
                json.dumps(config_dict, ensure_ascii=False),
                created_at.isoformat(),
                updated_at.isoformat(),
                _to_iso(stopped_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _get_loop_sync(loop_id: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT loop_id, status, repeat_count, current_iteration, current_match_id, last_match_id,
                   config_json, created_at, updated_at, stopped_at
            FROM loops
            WHERE loop_id = ?
            """,
            (loop_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "loop_id": row["loop_id"],
            "status": row["status"],
            "repeat_count": row["repeat_count"],
            "current_iteration": row["current_iteration"],
            "current_match_id": row["current_match_id"],
            "last_match_id": row["last_match_id"],
            "config": json.loads(row["config_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "stopped_at": row["stopped_at"],
        }
    finally:
        conn.close()


def _list_loops_sync() -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT loop_id, status, repeat_count, current_iteration, current_match_id, last_match_id,
                   config_json, created_at, updated_at, stopped_at
            FROM loops
            ORDER BY datetime(updated_at) DESC, datetime(created_at) DESC
            """
        ).fetchall()
        return [
            {
                "loop_id": row["loop_id"],
                "status": row["status"],
                "repeat_count": row["repeat_count"],
                "current_iteration": row["current_iteration"],
                "current_match_id": row["current_match_id"],
                "last_match_id": row["last_match_id"],
                "config": json.loads(row["config_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "stopped_at": row["stopped_at"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def _load_all_matches_sync() -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        matches = conn.execute(
            """
            SELECT match_id, status, config_json, created_at, finished_at
            FROM matches
            ORDER BY datetime(created_at) DESC
            """
        ).fetchall()

        output: List[Dict[str, Any]] = []
        for row in matches:
            event_rows = conn.execute(
                """
                SELECT event_type, data_json, timestamp
                FROM events
                WHERE match_id = ?
                ORDER BY datetime(timestamp) ASC
                """,
                (row["match_id"],),
            ).fetchall()

            events = [
                {
                    "type": event_row["event_type"],
                    "data": json.loads(event_row["data_json"]),
                    "timestamp": event_row["timestamp"],
                    "match_id": row["match_id"],
                }
                for event_row in event_rows
            ]

            output.append(
                {
                    "match_id": row["match_id"],
                    "status": row["status"],
                    "config": json.loads(row["config_json"]),
                    "created_at": row["created_at"],
                    "finished_at": row["finished_at"],
                    "events": events,
                }
            )

        return output
    finally:
        conn.close()


def _save_submission_sync(match_id: str, submission: Dict[str, Any]) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO submissions(
              match_id,
              attacker_id,
              victim_id,
              declared_target_player_id,
              flag,
              flag_slot,
              flag_index,
              success,
              reason,
              points,
              timestamp
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                int(submission.get("attacker_id", 0)),
                int(submission["victim_id"]) if submission.get("victim_id") is not None else None,
                submission.get("declared_target_player_id"),
                str(submission.get("flag", "")),
                submission.get("flag_slot"),
                int(submission["flag_index"]) if submission.get("flag_index") is not None else None,
                1 if submission.get("success") else 0,
                str(submission.get("reason", "unknown")),
                int(submission.get("points", 0)),
                str(submission.get("timestamp", "")),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _load_submissions_sync(match_id: str) -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT attacker_id, victim_id, declared_target_player_id, flag, flag_slot, flag_index, success, reason, points, timestamp
            FROM submissions
            WHERE match_id = ?
            ORDER BY datetime(timestamp) ASC, id ASC
            """,
            (match_id,),
        ).fetchall()

        submissions: List[Dict[str, Any]] = []
        for row in rows:
            submission: Dict[str, Any] = {
                "attacker_id": row["attacker_id"],
                "victim_id": row["victim_id"],
                "declared_target_player_id": row["declared_target_player_id"],
                "flag": row["flag"],
                "success": bool(row["success"]),
                "reason": row["reason"],
                "points": row["points"],
                "timestamp": row["timestamp"],
            }
            if row["flag_slot"] is not None:
                submission["flag_slot"] = row["flag_slot"]
            if row["flag_index"] is not None:
                submission["flag_index"] = row["flag_index"]
            submissions.append(submission)

        return submissions
    finally:
        conn.close()


async def init_db() -> None:
    await asyncio.to_thread(_init_db_sync)


async def save_match(match_id: str, status: str, config_dict: Dict[str, Any], created_at: datetime) -> None:
    await asyncio.to_thread(_save_match_sync, match_id, status, config_dict, created_at)


async def update_match_status(match_id: str, status: str, finished_at: Optional[datetime] = None) -> None:
    await asyncio.to_thread(_update_match_status_sync, match_id, status, finished_at)


async def save_event(match_id: str, event_type: str, data: Dict[str, Any], timestamp: datetime) -> None:
    await asyncio.to_thread(_save_event_sync, match_id, event_type, data, timestamp)


async def load_all_matches() -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_load_all_matches_sync)


def _list_matches_summary_sync() -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT match_id, status, config_json, created_at, finished_at
            FROM matches
            ORDER BY datetime(created_at) DESC
            """
        ).fetchall()
        output: List[Dict[str, Any]] = []
        for row in rows:
            config = json.loads(row["config_json"])
            players = config.get("players") or []
            output.append(
                {
                    "match_id": row["match_id"],
                    "status": row["status"],
                    "player_count": len(players),
                    "created_at": row["created_at"],
                    "finished_at": row["finished_at"],
                }
            )
        return output
    finally:
        conn.close()


async def list_matches_summary() -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_list_matches_summary_sync)


async def save_loop(
    loop_id: str,
    status: str,
    repeat_count: int,
    current_iteration: int,
    config_dict: Dict[str, Any],
    created_at: datetime,
    updated_at: datetime,
    current_match_id: Optional[str] = None,
    last_match_id: Optional[str] = None,
    stopped_at: Optional[datetime] = None,
) -> None:
    await asyncio.to_thread(
        _save_loop_sync,
        loop_id,
        status,
        repeat_count,
        current_iteration,
        config_dict,
        created_at,
        updated_at,
        current_match_id,
        last_match_id,
        stopped_at,
    )


async def get_loop(loop_id: str) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(_get_loop_sync, loop_id)


async def list_loops() -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_list_loops_sync)


async def save_submission(match_id: str, submission: Dict[str, Any]) -> None:
    await asyncio.to_thread(_save_submission_sync, match_id, submission)


async def load_submissions(match_id: str) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_load_submissions_sync, match_id)


# ==================== Ratings (ELO) ====================

def _load_ratings_sync() -> Dict[str, Dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT entity_key, display_name, rating, matches_played,
                   wins, losses, draws, last_match_id, updated_at
            FROM ratings
            """
        ).fetchall()
        return {
            row["entity_key"]: {
                "entity_key": row["entity_key"],
                "display_name": row["display_name"],
                "rating": row["rating"],
                "matches_played": row["matches_played"],
                "wins": row["wins"],
                "losses": row["losses"],
                "draws": row["draws"],
                "last_match_id": row["last_match_id"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        }
    finally:
        conn.close()


def _apply_rating_update_sync(match_id: str, update: Dict[str, Any], now: datetime) -> None:
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT matches_played, wins, losses, draws FROM ratings WHERE entity_key = ?",
            (update["entity_key"],),
        ).fetchone()
        if existing:
            wins_delta = 1 if update.get("result") == "win" else 0
            losses_delta = 1 if update.get("result") == "loss" else 0
            draws_delta = 1 if update.get("result") == "draw" else 0
            conn.execute(
                """
                UPDATE ratings
                SET display_name = ?, rating = ?, matches_played = matches_played + 1,
                    wins = wins + ?, losses = losses + ?, draws = draws + ?,
                    last_match_id = ?, updated_at = ?
                WHERE entity_key = ?
                """,
                (
                    update["display_name"],
                    update["new_rating"],
                    wins_delta,
                    losses_delta,
                    draws_delta,
                    match_id,
                    _to_iso(now),
                    update["entity_key"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO ratings (
                    entity_key, display_name, rating, matches_played,
                    wins, losses, draws, last_match_id, updated_at
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    update["entity_key"],
                    update["display_name"],
                    update["new_rating"],
                    1 if update.get("result") == "win" else 0,
                    1 if update.get("result") == "loss" else 0,
                    1 if update.get("result") == "draw" else 0,
                    match_id,
                    _to_iso(now),
                ),
            )
        conn.commit()
    finally:
        conn.close()


async def load_ratings() -> Dict[str, Dict[str, Any]]:
    return await asyncio.to_thread(_load_ratings_sync)


async def apply_rating_update(match_id: str, update: Dict[str, Any], now: datetime) -> None:
    await asyncio.to_thread(_apply_rating_update_sync, match_id, update, now)
