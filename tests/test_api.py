import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Fresh database for every test.
    monkeypatch.setattr("app.db.DB_PATH", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as c:
        yield c


def make_project(client, key="PROJ"):
    return client.post("/projects", json={"key": key, "name": "Demo"})


def make_issue(client, key="PROJ", **extra):
    return client.post(f"/projects/{key}/issues", json={"title": "Fix bug", **extra})


def test_create_project_and_duplicate_key(client):
    assert make_project(client).status_code == 201
    assert make_project(client).status_code == 409


def test_project_key_validation(client):
    r = client.post("/projects", json={"key": "bad key", "name": "x"})
    assert r.status_code == 422


def test_issue_keys_increment_per_project(client):
    make_project(client, "AAA")
    make_project(client, "BBB")
    assert make_issue(client, "AAA").json()["key"] == "AAA-1"
    assert make_issue(client, "AAA").json()["key"] == "AAA-2"
    assert make_issue(client, "BBB").json()["key"] == "BBB-1"


def test_new_issue_defaults(client):
    make_project(client)
    issue = make_issue(client).json()
    assert issue["status"] == "todo"
    assert issue["priority"] == "medium"
    assert issue["assignee"] is None


def test_issue_in_missing_project_is_404(client):
    assert make_issue(client, "NOPE").status_code == 404


def test_get_missing_or_malformed_issue_is_404(client):
    make_project(client)
    assert client.get("/issues/PROJ-99").status_code == 404
    assert client.get("/issues/garbage").status_code == 404


def test_update_issue_fields(client):
    make_project(client)
    make_issue(client)
    r = client.patch("/issues/PROJ-1", json={"assignee": "ken", "priority": "high"})
    assert r.status_code == 200
    assert r.json()["assignee"] == "ken"
    assert r.json()["priority"] == "high"
    assert r.json()["title"] == "Fix bug"  # untouched


def test_valid_workflow_path(client):
    make_project(client)
    make_issue(client)
    for status in ["in_progress", "in_review", "done"]:
        r = client.post("/issues/PROJ-1/transitions", json={"status": status})
        assert r.status_code == 200
        assert r.json()["status"] == status


def test_invalid_transition_is_409(client):
    make_project(client)
    make_issue(client)
    r = client.post("/issues/PROJ-1/transitions", json={"status": "done"})
    assert r.status_code == 409
    assert client.get("/issues/PROJ-1").json()["status"] == "todo"


def test_reopen_done_issue(client):
    make_project(client)
    make_issue(client)
    for status in ["in_progress", "in_review", "done", "in_progress"]:
        assert client.post(
            "/issues/PROJ-1/transitions", json={"status": status}
        ).status_code == 200


def test_list_filter_and_pagination(client):
    make_project(client)
    for i in range(5):
        make_issue(client, assignee="ken" if i % 2 == 0 else "ada")
    r = client.get("/projects/PROJ/issues", params={"assignee": "ken"})
    assert r.json()["total"] == 3
    page = client.get("/projects/PROJ/issues", params={"limit": 2, "offset": 2}).json()
    assert [i["key"] for i in page["issues"]] == ["PROJ-3", "PROJ-4"]
    assert page["total"] == 5


def test_comments(client):
    make_project(client)
    make_issue(client)
    r = client.post("/issues/PROJ-1/comments", json={"author": "ken", "body": "On it"})
    assert r.status_code == 201
    comments = client.get("/issues/PROJ-1/comments").json()
    assert len(comments) == 1 and comments[0]["body"] == "On it"


def test_delete_issue_removes_comments(client):
    make_project(client)
    make_issue(client)
    client.post("/issues/PROJ-1/comments", json={"author": "ken", "body": "hi"})
    assert client.delete("/issues/PROJ-1").status_code == 204
    assert client.get("/issues/PROJ-1").status_code == 404
    assert client.get("/issues/PROJ-1/comments").status_code == 404
