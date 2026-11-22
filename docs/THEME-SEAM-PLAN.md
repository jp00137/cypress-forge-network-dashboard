# Plan: colour tokens and add-on client scripts (2026-11-21)

Status: **Approved and implemented** (2026-11-21).

## What the inventory found (it changes one part of the spec)

I counted the colours in `style.css`, `workspace.css` and `firewall.css`:

- **Distinct colours:** about **225**. Nearly every one is used exactly once.
- **Gradients:** 2.
- **Translucent colours:** 8 (`#rrggbbaa`).
- **The chart in `main.tsx`:** 4 literal colours.

They fall into four families:

| Family | Count | Examples |
| --- | --- | --- |
| Dark surfaces and borders (navy) | about 90 | `#0b111b` … `#354455` |
| Grey-blue text, from dim to bright | about 85 | `#4a5a68` … `#dce5f0` |
| Teal accent: text, plus dark teal tints for badges and tiles | about 40 | `#65e0be`, `#67dbbb`, `#15362f`, `#214b40` |
| Warm status: amber and red text and tints | about 12 | `#e1c994`, `#d5b477`, `#4d4430`, `#663b45` |

**The problem:** the spec's 14 tokens can't absorb about 175 neutral shades "with no visible difference". Squeezing
them into 6 or 7 greys would visibly flatten the dashboard.

**Proposed fix (needs your OK):** it's a different split, not more work.

1. **Accent family:** this is what Plus recolours, so it is tokenized properly.
   - Every teal colour becomes one of **4 accent tokens**: `--cf-accent`, `--cf-accent-2`, `--cf-accent-soft` and
     `--cf-on-accent`.
   - Shades in between are written as `color-mix(in oklab, var(--cf-accent) N%, var(--cf-bg))`, with N picked so the
     result matches today's colour. When Plus changes the accent, every tint, border and badge follows automatically.
2. **Neutral family:** each colour snaps to the nearest step of a **12-step neutral scale**, `--cf-n0` (darkest
   background) to `--cf-n11` (brightest text).
   - The steps are chosen from today's colours, so each one moves by a barely visible amount at most.
   - The **contract** for add-ons is the documented names (`--cf-bg`, `--cf-panel`, `--cf-text`, `--cf-muted` and so
     on), which are aliases of scale steps. That keeps a later Light theme possible without another refactor.
3. **Warm status:** `--cf-warn` and `--cf-bad`, with tints made by `color-mix` the same way.

The result is about 22 tokens. Spec success criterion 1 becomes:

> No view changes by more than a small, measured amount. Each colour moves by at most ΔE 3 in OKLab, which is about the
> smallest difference people notice side by side.

The replacement script prints any colour beyond that so it can be checked by hand.

## Steps

Work happens on a new branch `theme-seam`, cut from `origin/main` in this worktree. The live dashboard checkout
(`C:\AI\CypressForge`) is not touched.

### T1. Baseline screenshots
- Build the current frontend.
- Run a second server from this worktree on another port (not 8765) in **demo mode**.
- Take screenshots of every view (Overview, Devices, Ports, Firewall, DHCP, Workspace) at desktop width and at 375 px,
  saved in the scratchpad.

### T2. Colour mapping script (a throwaway tool, not shipped)
A Node script in the scratchpad that:
1. lists every colour in the three stylesheets with its selector and property;
2. sorts each colour into a family by hue and chroma in OKLCH;
3. proposes a replacement: a neutral step, an accent token, or a `color-mix(…)`;
4. prints the ΔE for each and flags anything over 3.

I review the mapping table and adjust the 12 neutral steps until nothing is flagged, or the few flagged ones are
justified.

### T3. Apply tokens
- Add the `:root` token block at the top of `style.css`, with the dark values as today.
- Apply the reviewed replacements to the three stylesheets.
- The 2 gradients and 8 translucent colours become `color-mix` with `transparent`.
- **Chart (`main.tsx`):** replace `stroke="#…"` and `fill="#…"` with class names (`chart-grid`, `chart-axis`,
  `chart-rx`, `chart-tx`), styled in `style.css` with the tokens.
- The `theme-color` meta in `index.html` stays as it is (literal, today's background).

### T4. Guard test
New `frontend/tests/tokens.test.mjs`. It fails if:
- any hex or `rgb()` colour appears in the three stylesheets outside the token block;
- any `.tsx` file contains a `#rrggbb` literal.

It's added to `run.mjs`.

### T5. Visual check
- Rebuild, then take the same screenshots as T1.
- Compare them side by side.
- If Pillow is available in the venv, also compute a per-pixel difference report. Otherwise compare by eye.

**Gate:** I show you the before and after pairs for approval before going on.

### T6. Backend: `client` attribute
`backend/addons.py`:
- `Addon.__init__` sets `self.client = None`.
- In `mount()`, after a successful `static_dir` mount, read `getattr(obj, 'client', None)`:
  - If it's a string matching `^[A-Za-z0-9._-]+\.js$` and the file exists in the folder, set
    `client = f'/addon/{name}/{file}'`.
  - If it's a bad name, record `client: invalid name`. If the file is missing, record `client: not found`. If there's
    no `static_dir`, record `client: no static_dir`.
- `info()` gains `client`.

Tests in `tests/test_addons.py`, extending the `test_routes_static_and_listing` pattern:
- accepted;
- missing file;
- bad names (`../x.js`, `x.mjs`, `a/b.js`);
- no `static_dir`;
- `client: null` when the attribute isn't declared.

### T7. Frontend: load clients
`AddonNav.tsx`:
- **`addonClients(payload)`:** a pure validator that keeps strings matching
  `^/addon/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\.js$` without `..`, and drops duplicates.
- **Shared fetch:** `loadAddonLinks` becomes `loadAddons`, returning `{links, clients}` from the one `/api/addons`
  request.
- **Loading:** `useAddonLinks` imports each client with `import(/* @vite-ignore */ url)`. The importer can be swapped
  for tests. Each import is wrapped so a rejection is swallowed.
- **StrictMode double mount:** the browser caches modules by URL, so a client runs once.

Tests in `addonNav.test.mjs`:
- path validation (`javascript:`, `//host/x.js`, `/assets/x.js`, `..`);
- a failing import is ignored;
- no clients means no import calls.

`main.tsx` needs no change beyond T3.

### T8. Test add-on check
- Point the T1 server at a throwaway add-on in the scratchpad, installed in a temporary venv or loaded through the
  `hello` example's test pattern.
- Its `client.js` sets `--cf-accent: #d050f0`.
- Confirm in the browser that the whole dashboard (nav, badges, chart RX line, focus ring) turns purple.
- Then rename the file and confirm the error shows in `/api/addons` while the page still works.

### T9. Docs and finish
- `docs/ADDON-DESIGN.md`: a "Theming" section with the contract token names and the `client` attribute.
- `CHANGELOG.md` entry.
- Mark THEME-SEAM.md "Approved and implemented".
- Run the full backend suite. The 9 `test_router_access` errors from `/bin/sh` on native Windows are known and
  unrelated. Also run the frontend tests and `npm run build`.

**Gate:** commit, push and PR only with your OK. The live dashboard on 8765 picks this up only when you choose to
update and restart it.

## Risks
- **Some neutral shade moves visibly.** Mitigation: the ΔE report in T2 and the T5 comparison. Any colour that has to
  stay exact keeps its own step.
- **`color-mix` support:** it needs Chromium 111+, Firefox 113+ or Safari 16.2+ (all from 2023). The dashboard is opened
  in a current browser on the same PC, so this is acceptable. It's noted in ADDON-DESIGN.md.
- **Vite and dynamic `import()` of a runtime URL:** handled with `@vite-ignore`. The build check in T9 confirms it.

## Size
- **T2 and T3 (mapping and applying):** the bulk of the work.
- **T6 to T8:** small.
- **Estimate:** one to two working sessions, plus your review at the two gates.
