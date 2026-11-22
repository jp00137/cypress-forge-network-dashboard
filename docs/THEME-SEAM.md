# Colour tokens and add-on client scripts (2026-11-21)

Status: **Approved and implemented** (2026-11-21).

The plan ([THEME-SEAM-PLAN.md](THEME-SEAM-PLAN.md)) changed the token set, with the owner's approval:

- **Tokens:** 22 instead of the 14 in the table below, made up of a 12-step neutral scale, `--cf-n0` to `--cf-n11`,
  plus the accent and status tokens. The names in the table are kept as aliases and are the contract.
- **Acceptance:** "a small, measured amount", meaning at most ΔE 3.5 in OKLab, instead of "no difference".
- **Result:** 27,459 computed colours across 11 views were compared at desktop and phone width. 79% moved by less than
  ΔE 1, and none by more than ΔE 3.5.
- **The final list:** see the Theming section of [ADDON-DESIGN.md](ADDON-DESIGN.md).

## Goal

Make it possible for an add-on to recolour the dashboard, without core itself offering a colour choice.

The free dashboard keeps exactly one look, today's dark theme. This change only does two things:

1. It moves core's colours into named CSS variables.
2. It lets an add-on load one script on core's page.

Like the sidebar links (ADDON-NAV-LINKS.md), this is generic seam behaviour. It names no paid add-on and copies no
add-on code.

## Why the core change is needed

- **Colours:** today about 225 colours are written out directly across `style.css`, `workspace.css`, `firewall.css`
  and the chart in `main.tsx`. An add-on stylesheet could only override them rule by rule, which breaks whenever core
  changes. Named variables give add-ons a small, stable set to override.
- **Scripts:** an add-on can only serve its own pages (`static_dir`). Nothing an add-on ships runs on core's page, so
  it can't apply a colour choice there.

## Behaviour

### 1. Colour tokens (no visible change)

`style.css` gets a `:root` block of named colours. Every colour in the core stylesheets and in the chart's SVG
attributes is replaced by one of them. The proposed set (about 14) is below; each value is today's dark value.

| Token | Used for | Today's value |
| --- | --- | --- |
| `--cf-bg` | page background | `#0b111b` |
| `--cf-panel` | sidebar, cards | `#0e1520` |
| `--cf-panel-2` | raised controls, inputs | `#151f2c` |
| `--cf-line` | borders, chart grid | `#202b39` |
| `--cf-line-2` | stronger borders | `#2b3949` |
| `--cf-text` | body text | `#dbe4ef` |
| `--cf-muted` | secondary text, axis labels | `#7b92a7` |
| `--cf-accent` | links, focus ring, active nav, RX line | `#65e0be` |
| `--cf-accent-soft` | accent backgrounds (badges, icon tiles) | `#15362f` |
| `--cf-accent-2` | second series (TX line) | `#7c9dff` |
| `--cf-ok` | healthy status | (today's green) |
| `--cf-warn` | warnings | `#e1c994` |
| `--cf-bad` | errors, offline | `#f49ba4` |
| `--cf-on-accent` | text on accent backgrounds | (today's value) |

- **Merging near-duplicates:** many current colours are near-duplicates (for example the teal is written as
  `#65e0be`, `#67dbbb`, `#62d9b5`, `#6edbbb` and `#59d9bb`). They are merged into the nearest token.
- **Translucent colours:** `rgba()` colours, if any are found, use `color-mix()` with a token.
- **Acceptance:** side-by-side screenshots of every view before and after show no difference a user would notice.
  Merged shades may move by a few units.
- **Charts:** the chart's `stroke` and `fill` attributes in `main.tsx` move into CSS classes that use the tokens, so a
  theme can recolour the charts too.
- **Contract:** the token names and the list above become the documented contract for add-ons, in ADDON-DESIGN.md.
  After this change, renaming or removing a token is a breaking change for add-ons.

### 2. Add-on client script

- **Declaring it:** an add-on object can have a `client` attribute: a file name inside its `static_dir`, for example
  `client = "client.js"`.
- **Checks when mounting:** core accepts it only if:
  - the add-on also mounted a `static_dir`;
  - the name matches `^[A-Za-z0-9._-]+\.js$`;
  - the file exists.

  Anything else is recorded as an add-on error (`client: not found` or `client: invalid name`) and ignored.
- **The API:** `GET /api/addons` gains `client`: `"/addon/<name>/<file>"`, or `null`.
- **Loading:** the frontend loads each accepted client once, when the app mounts, with `import(url)`. It uses the same
  `/api/addons` response the sidebar already fetches, so there is no extra request.
- **Path check:** the frontend loads only paths that match `^/addon/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\.js$`, the same
  defence-in-depth rule as the sidebar links.
- **Failures are silent:** a script that fails to load or throws is ignored (caught, nothing logged), and the dashboard
  works as before.
- **What a client may do:** core makes no promise beyond "it runs once on the dashboard page". A client may set
  attributes on `<html>` and add a `<link rel="stylesheet">` to its own add-on path. The documented use is overriding
  the `--cf-*` tokens.

## Safety rules (unchanged core rules)

- **CSP is unchanged.** `script-src 'self'` already allows same-origin modules, and the client is served by core's own
  static mount. No inline script is added.
- **Local-only and GET-only are unchanged.** There is no new route and no new write path.
- **Trust:** an add-on already runs Python inside the server process, so running its script in the page adds no new
  trust. Add-ons are installed only by the owner.

## Files to touch

| File | Change |
| --- | --- |
| `frontend/src/style.css`, `workspace.css`, `firewall.css` | Add the token block, then replace the literal colours with tokens. |
| `frontend/src/main.tsx` | Move the chart's SVG colours into classes. Load add-on clients from the `/api/addons` result. |
| `frontend/src/AddonNav.tsx` | Return `client` paths next to the links (validated as above). |
| `backend/addons.py` | Read and validate `client` in `mount()`; add `client` to `info()`. |
| `docs/ADDON-DESIGN.md` | Document the token list and the `client` attribute. |
| `tests/` | Backend tests for `client` (accepted, missing file, bad name, no `static_dir`). |
| `frontend/tests/` | Frontend tests for path validation and for a failed import being ignored. |

## Success criteria

1. Every view looks the same before and after (screenshot comparison on the demo data, desktop and phone width).
2. No literal colour is left in the three core stylesheets or the chart markup, apart from the token block.
   A grep test enforces this.
3. With no add-on installed, `/api/addons` is unchanged except for the new `client: null`, and no script loads.
4. A test add-on with `client = "client.js"` that sets `--cf-bg: red` on `<html>` turns the page red. One with a
   missing or misnamed file is reported in `/api/addons` errors and doesn't break the page.
5. Backend tests, frontend tests, the strict TypeScript check and the build all pass.

## Out of scope

- Any colour choice in core: no light theme, no picker and no setting. The free dashboard stays dark only.
- Following the system light/dark setting in core.
- Applying a choice before first paint. That would need an inline script, which the CSP forbids. An add-on's colours
  therefore appear a moment after the page loads (see the Plus spec).

## Open questions

- None blocking. If you'd rather not add a general script seam, the narrower alternative is a stylesheet-only seam
  (`stylesheet` instead of `client`). But a stylesheet alone can't read a saved choice, so the colour choice would
  have to live in the add-on's `config.toml` instead of a picker.
