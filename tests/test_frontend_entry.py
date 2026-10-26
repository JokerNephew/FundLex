"""Default workbench selection must not depend on a leftover Vite build."""
import re

from fastapi.testclient import TestClient

from fundlex.api import create_app


def test_v1_entry_and_bookmarks(tmp_path, monkeypatch):
    monkeypatch.delenv("FUNDLEX_FRONTEND_VERSION", raising=False)
    monkeypatch.delenv("FUNDLEX_FRONTEND_BASE_PATH", raising=False)
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    client = TestClient(create_app(tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="view-overview"' in response.text
    assert 'id="view-compare"' in response.text
    assert 'id="login-form"' in response.text
    assert 'id="root"' not in response.text
    assert "独立合同对比工作台" not in response.text
    assert "no-store" in response.headers["cache-control"]
    assets = re.findall(r'(?:src|href)="(/static/[^"?]+\.(?:js|css)\?v=[a-f0-9]+)"', response.text)
    assert len(assets) == 4
    for asset in assets:
        assert client.get(asset).status_code == 200
    for path, view in (("/compare", "compare"), ("/tasks", "overview"),
                       ("/tasks/new", "import"), ("/guides", "guide")):
        redirect = client.get(path, follow_redirects=False)
        assert redirect.status_code == 307
        assert redirect.headers["location"] == f"/#{view}"
    deep_link = client.get("/tasks/task-id_1", follow_redirects=False)
    assert deep_link.status_code == 307
    assert deep_link.headers["location"] == "/?task=task-id_1#task"
    assert client.get("/api/nonexistent").status_code == 404
    assert client.get("/src/main.tsx").status_code == 404


def test_explicit_v2_entry_remains_available(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_FRONTEND_VERSION", "v2")
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    client = TestClient(create_app(tmp_path))
    for path in ("/", "/compare", "/tasks/new"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'id="root"' in response.text


def test_v1_entry_preserves_test_proxy_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_FRONTEND_VERSION", "v1")
    monkeypatch.setenv("FUNDLEX_FRONTEND_BASE_PATH", "/test")
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    client = TestClient(create_app(tmp_path))
    html = client.get("/").text
    assert 'src="/test/static/app.js?v=' in html
    assert 'href="/test/static/compare.css?v=' in html
    for path, view in (("/compare", "compare"), ("/tasks/new", "import")):
        assert client.get(path, follow_redirects=False).headers["location"] == f"/test/#{view}"
    deep_link = client.get("/tasks/task-id_1", follow_redirects=False)
    assert deep_link.headers["location"] == "/test/?task=task-id_1#task"
