# Mini-Jira

A small Jira-style issue tracker API built with **FastAPI** and **SQLite**.
It was built to practise designing a backend that behaves faithfully like the
SaaS tool it imitates: project-scoped issue keys, an enforced status workflow,
comments, filtering and pagination.

## Features
- Projects with unique keys (`PROJ`) and auto-incrementing issue keys (`PROJ-1`, `PROJ-2`, ...)
- Issue workflow enforced server-side: `todo -> in_progress -> in_review -> done`
  (done issues can be reopened); invalid moves return `409`
- Partial updates (`PATCH`), comments, delete with cascade
- List endpoint with `status` / `assignee` filters and `limit` / `offset` pagination
- Input validation (Pydantic) and consistent `404` / `409` / `422` errors
- Pytest suite, Dockerfile, GitHub Actions CI

## Run locally
macOS / Linux:
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Windows (PowerShell), no virtual environment activation needed:
```powershell
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload
```

Interactive docs: http://localhost:8000/docs

## Run with Docker
```bash
docker build -t mini-jira .
docker run -p 8000:8000 -v minijira-data:/data mini-jira
```

## Run tests
```bash
pytest -q
```

## API overview
| Method | Path | Purpose |
|---|---|---|
| POST | `/projects` | Create a project (`key`: 2-10 capital letters) |
| GET | `/projects` | List projects |
| POST | `/projects/{key}/issues` | Create an issue |
| GET | `/projects/{key}/issues` | List issues (`status`, `assignee`, `limit`, `offset`) |
| GET | `/issues/{ISSUE-KEY}` | Get one issue |
| PATCH | `/issues/{ISSUE-KEY}` | Update title, description, priority, assignee |
| POST | `/issues/{ISSUE-KEY}/transitions` | Move to a new status (workflow-checked) |
| DELETE | `/issues/{ISSUE-KEY}` | Delete an issue and its comments |
| POST / GET | `/issues/{ISSUE-KEY}/comments` | Add / list comments |

## Design notes
- Issue keys are per-project counters stored on the project row, so keys never get reused after a delete.
- Workflow rules live in one dict (`ALLOWED_TRANSITIONS` in `app/schemas.py`), which makes them easy to change and test.
- Plain `sqlite3` is used on purpose to keep the data layer explicit.

## Ideas to extend
Users/auth, issue links, labels, a Slack-like mock, an Alembic migration setup.
