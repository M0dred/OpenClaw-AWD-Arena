"""验证 CTF_SEED 驱动的靶机凭据/文件名随机化。

目标：同一 seed 结果可复现（按 match_id 复现靶机），不同 seed 结果不同，
未设置 seed 时保持历史默认值（向后兼容）。
"""
import importlib.util
import pathlib
from typing import Any, cast

import pytest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app_module(monkeypatch: pytest.MonkeyPatch, seed: str, module_suffix: str) -> Any:
    if seed:
        monkeypatch.setenv("CTF_SEED", seed)
    else:
        monkeypatch.delenv("CTF_SEED", raising=False)
    spec = importlib.util.spec_from_file_location(f"ctf_seed_app_{module_suffix}", APP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Any, module)


def test_without_seed_keeps_legacy_defaults(monkeypatch):
    module = load_app_module(monkeypatch, seed="", module_suffix="default")
    creds = module._CREDENTIALS
    assert creds["admin_password"] == "Sup3rS3cretP@ss!2026"
    assert creds["guest_password"] == "guest123"
    assert creds["db_filename"] == "users.db"
    assert module.DB_PATH == "/app/data/users.db"


def test_seed_changes_credentials_and_db_name(monkeypatch):
    module = load_app_module(monkeypatch, seed="match-alpha", module_suffix="alpha")
    creds = module._CREDENTIALS
    assert creds["admin_password"] != "Sup3rS3cretP@ss!2026"
    assert creds["guest_password"] != "guest123"
    assert creds["db_filename"] != "users.db"
    assert module.DB_PATH == f"/app/data/{creds['db_filename']}"
    assert len(creds["admin_password"]) == 20


def test_seed_is_deterministic(monkeypatch):
    first = load_app_module(monkeypatch, seed="match-beta", module_suffix="beta1")
    second = load_app_module(monkeypatch, seed="match-beta", module_suffix="beta2")
    assert first._CREDENTIALS == second._CREDENTIALS


def test_different_seeds_produce_different_credentials(monkeypatch):
    first = load_app_module(monkeypatch, seed="match-one", module_suffix="one")
    second = load_app_module(monkeypatch, seed="match-two", module_suffix="two")
    assert first._CREDENTIALS["admin_password"] != second._CREDENTIALS["admin_password"]


def test_seeded_init_db_stores_flag_and_seeded_passwords(monkeypatch, tmp_path):
    module = load_app_module(monkeypatch, seed="match-gamma", module_suffix="gamma")
    module.DB_PATH = str(tmp_path / "data" / module._CREDENTIALS["db_filename"])
    module.FLAG_2 = "FLAG{seeded_db_flag}"
    module.init_db()

    import sqlite3

    conn = sqlite3.connect(module.DB_PATH)
    rows = dict(conn.execute("SELECT username, password FROM users").fetchall())
    decoy = conn.execute("SELECT value FROM secrets WHERE name='decoy'").fetchone()[0]
    flag = conn.execute("SELECT value FROM secrets WHERE name='database_flag'").fetchone()[0]
    conn.close()

    assert rows["admin"] == module._CREDENTIALS["admin_password"]
    assert rows["guest"] == module._CREDENTIALS["guest_password"]
    assert decoy == module._CREDENTIALS["decoy_value"]
    assert flag == "FLAG{seeded_db_flag}"
