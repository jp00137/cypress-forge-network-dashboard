# Paid add-on design (draft, 2026-11-18)

Status: built (updated 2026-11-21). Tasks 1–8 are done: the core seam is in this repo (PRs #5–#7), and the
closed add-on reached its first installable release, 0.2.0. Follows the Licensing decision in DECISIONS.md:
MIT core in this repo, paid features in a separate closed add-on that is never committed here.
Where the build differs from this draft, it says so under "As built".

## Scope of the first paid release

1. **Long history**: months-to-years trends kept cheaply as rollups.
2. **Alerts**: rules over core events and snapshots, delivered to phone, email or desktop.

Everything else on the candidate list (themes, phone access, multi-router) waits.

## Why long history is rollups, not raw retention

The MIT core already lets anyone set `retention_days` up to 90 in config (`collector.py`, `store.py`).
Selling "more than 7 days of raw snapshots" would sell something the free code already does.
The paid value is instead:

- Hourly rollups kept 400 days, daily rollups kept indefinitely.
- Year-over-year and month-over-month views, reboot and outage counts, per-device presence time.
- Small storage: one row per metric per hour, not one full JSON snapshot per minute.

Raw snapshots stay in core under core retention. The add-on never changes core tables.

## Boundary rules

- Core runs fully with no add-on installed. Core never imports add-on code by name.
- The add-on only uses the public hook API below and its own SQLite file
  (`data/addon-history.sqlite3`). It never patches or monkeypatches core.
- The add-on lives in its own private repo (`cypress-forge-addon`), ships as a Python wheel
  plus a prebuilt frontend bundle, and installs into the same venv.
- Secrets (SMTP password, ntfy token) live in a local, git-ignored add-on config.

## Core seam (MIT, small, lives in this repo)

A generic add-on loader that any add-on, paid or free, can use. Proposed new file `backend/addons.py`:

- Discovers add-ons with `importlib.metadata.entry_points(group="cypressforge.addons")`.
- Each add-on object may implement:
  - `on_snapshot(snapshot, previous)`: called after `Store.add` succeeds in `poll_once`.
  - `on_event(event)`: called for every event written by `Store._event`.
  - `routes()`: returns a FastAPI `APIRouter`, mounted under `/api/addon/<name>/`.
  - `static_dir()`: optional built frontend, served at `/addon/<name>/`.
- Hook errors are caught and logged; a broken add-on can never stop collection.
- `GET /api/addons` lists loaded add-ons so the core UI can show a nav link per add-on.
- Local-only middleware and TrustedHost rules apply to add-on routes too.

### Theming: colour tokens and client scripts (added 2026-11-21, [THEME-SEAM.md](THEME-SEAM.md))

- **Client script:** an add-on with a `static_dir` may set `client = "file.js"`.
  - The name must be a plain file name matching `[A-Za-z0-9._-]+\.js`, the file must exist in that folder, and it
    can't start with a dot.
  - Core lists it in `GET /api/addons` as `client: "/addon/<name>/<file>"` and the dashboard imports it once.
  - A bad name or a missing file is reported as the add-on's `last_error` (`client: invalid name`,
    `client: not found` or `client: no static_dir`), and nothing is loaded.
  - A script that fails to load or throws is ignored.
- **Colour tokens:** all of core's colours are CSS custom properties, set on `:root` in the `cf-tokens` block at the
  top of `frontend/src/style.css`. A test keeps literal colours out of the rest of core's styles.
  - **The contract for add-ons is these names.** Renaming or removing one is a breaking change.

    | Token | Meaning |
    | --- | --- |
    | `--cf-bg` | page background |
    | `--cf-panel` | sidebar and cards |
    | `--cf-panel-2` | raised controls and inputs |
    | `--cf-line` | borders and chart grid |
    | `--cf-line-2` | stronger borders |
    | `--cf-text` | body text |
    | `--cf-muted` | secondary text |
    | `--cf-accent` | links, focus ring, active nav, and the RX line; every teal tint is derived from it |
    | `--cf-accent-2` | second series (the TX line) |
    | `--cf-accent-soft` | accent backgrounds |
    | `--cf-on-accent` | text on the accent |
    | `--cf-ok` | healthy status |
    | `--cf-warn` | warnings |
    | `--cf-bad` | errors |
    | `--cf-shadow` | shadows |

  - The contract names are aliases of a 12-step neutral scale, `--cf-n0` (darkest) to `--cf-n11` (brightest). Core's
    styles use the scale directly, so a full background theme overrides `--cf-n0` to `--cf-n11`.
  - An accent theme overrides `--cf-accent`, and optionally `--cf-accent-2` and `--cf-ok`. Tints follow through
    `color-mix(in oklab, …)`.
  - `color-mix` needs Chromium 111+, Firefox 113+ or Safari 16.2+.
- **Timing:** core paints its default colours first. An add-on's override applies once its client has loaded, because
  the CSP forbids an inline script that could run before the first paint.

## Long history design (closed add-on)

Tables in `addon-history.sqlite3`:

| Table | Key | Columns |
| --- | --- | --- |
| `hourly` | hour_start, metric, subject | avg, max, min, samples |
| `daily` | day, metric, subject | avg, max, min, samples |
| `presence` | day, mac | minutes_seen, first_ts, last_ts |
| `counts` | day, kind | event_count |

Metrics from each snapshot: `wan.rx_mbps`, `wan.tx_mbps`, `clients.count`, per-port rx/tx Mbps,
router uptime. Counts come from `on_event` (reboots, device_observed, collector_failure, config changes).
Rollup runs in `on_snapshot`; hourly rows older than 400 days are pruned daily.

UI: one History+ page with a range picker (30 d, 90 d, 1 y, all), WAN trend line, client count
line, outage/reboot bars per week, and a device presence table.

## Alerts design (closed add-on)

Rules (each on/off, with threshold and cooldown):

| Rule | Trigger |
| --- | --- |
| Router rebooted | `router_reboot` event |
| Collector failing | `collector_failure` with no `collector_recovered` within N minutes |
| New device | `device_observed` for a MAC never seen before |
| Watched device missing | `device_missing` for a starred MAC, lasting N polls |
| Config changed | `firewall_config_changed`, `firewall_runtime_changed`, `dhcp_config_changed` |
| WAN busy | `wan.rx_mbps` or `tx_mbps` above X for N minutes |

Delivery channels, in build order: ntfy (phone push, self-hostable), SMTP email, Windows toast.
Shared behavior: quiet hours, per-rule cooldown, de-duplication, a "send test" button,
and an alert log table so every sent alert is visible in the UI.

Wording follows core evidence rules: "absent from router records", never "offline".

## As built (differences from this draft)

- **New device** is decided from live snapshots against the add-on's own list of known devices, not from
  `device_observed`. The first snapshot after install records every present device without alerting.
- **Watched device missing** counts consecutive live snapshots without the device. Core sends `device_missing`
  only once, at the moment a device disappears, so it cannot measure "N polls".
- **"Send test"** is a command-line test command in the add-on, not a button: core serves add-on routes behind
  its read-only, GET-only middleware, and this core stays unchanged for it.
- The **alert log** also records each delivery's outcome per channel (sent, failed, held for quiet hours, skipped).
  Alerts and delivery records are kept 400 days.
- **Add-on files on a buyer's machine:** settings, secrets and the license live in `<core>/data/plus/`.
  Core already git-ignores `data/`, so they cannot be committed to a core checkout.
- **Packaging:** the History+ page is plain HTML/JS/CSS shipped inside the wheel, so there is no separate frontend
  build. The release is a zip with the wheel, install and uninstall scripts, and install notes.

## Tasks

| # | Task | Repo | Size | Status |
| --- | --- | --- | --- | --- |
| 1 | `backend/addons.py` loader + hooks in `main.py`/`store.py` + `/api/addons` + tests | core (MIT) | M | done (PR #5) |
| 2 | Example free add-on (`hello`) to prove the seam, in `examples/` | core (MIT) | S | done (PR #7) |
| 3 | Create private `cypress-forge-addon` repo, package skeleton, entry point | add-on | S | done |
| 4 | Rollup tables, `on_snapshot` rollups, pruning, tests | add-on | M | done |
| 5 | History+ API and page | add-on | M | done |
| 6 | Alert rules engine + alert log + tests | add-on | M | done |
| 7 | ntfy channel, then SMTP, then Windows toast | add-on | M | done |
| 8 | Packaging: wheel + bundle, install steps, license check | add-on | M | done (0.2.0) |

The sidebar "ADD-ONS" links for any add-on with a page came in core PR #6.

## Decisions (were open questions)

- **License check: a signed offline license file.** It is checked locally with the standard library only, with
  no network and no activation. Without a valid license, the add-on still records history and alerts and shows
  them, but sends nothing to phone, email or desktop. (Also in DECISIONS.md.)
- **First delivery channel: ntfy**, then SMTP email, then Windows toast, as planned.
- **Long history: hourly rollups kept 400 days, daily rollups kept indefinitely**, as planned.

## Still open

- Whether 400 days of hourly data is enough, or hourly should be kept forever (revisit with real use).
