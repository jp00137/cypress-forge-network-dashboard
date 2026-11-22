# Hello example add-on

The smallest working Cypress Forge add-on. It exists to prove the add-on seam in
`backend/addons.py` and to be copied as a starting point. MIT, like the core.

What it does:

| Hook | Behavior |
| --- | --- |
| `on_event` | Counts core events by kind |
| `on_snapshot` | Remembers the last stored snapshot's time and client count |
| `routes` | `GET /api/addon/hello/stats` returns those numbers |
| `static_dir` | One page at `/addon/hello/` |

State is in memory only and resets on restart. It never touches core tables or files.

## Install (Windows, from the repo root)

```powershell
.venv\Scripts\python.exe -m pip install -e examples\hello
```

Restart the dashboard, then open:

- http://127.0.0.1:8765/api/addons (lists `hello`)
- http://127.0.0.1:8765/addon/hello/

## Remove

```powershell
.venv\Scripts\python.exe -m pip uninstall -y cf-hello
```

## How discovery works

`pyproject.toml` registers an entry point in the `cypressforge.addons` group:

```toml
[project.entry-points."cypressforge.addons"]
hello = "cf_hello:Hello"
```

The entry point name (`hello`) becomes the URL name. Core instantiates the class with no
arguments. Every hook is optional; errors in a hook are caught and counted, never fatal.
