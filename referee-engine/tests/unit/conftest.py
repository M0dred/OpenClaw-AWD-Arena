"""单元测试公共 fixture：为每个测试隔离裁判引擎的本地持久化路径。

历史上多个测试共享 referee-engine/openclaw.db，导致数据跨测试、跨运行累积，
产生顺序依赖与偶发失败。这里通过 autouse fixture 把数据库与模板存储指向
每个测试独立的临时目录（配合 database.get_db_path() 的调用时解析生效），
并预先初始化表结构——部分测试直接调用持久化函数，依赖 schema 已存在。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import database  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_referee_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLAW_DB_PATH", str(tmp_path / "referee.db"))
    monkeypatch.setenv("OPENCLAW_TEMPLATES_PATH", str(tmp_path / "templates.json"))
    monkeypatch.delenv("OPENCLAW_EXPORTS_PATH", raising=False)
    database._init_db_sync()
    yield
