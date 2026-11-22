# Add-on links in the sidebar (2026-11-20)

Status: **Approved and implemented** (2026-11-20). Open questions were settled with the
defaults below: the group sits under `OBSERVATORY`, and links keep the API order.

## Goal

The core dashboard sidebar shows one link for each loaded add-on that serves a page.
Today an add-on page at `/addon/<name>/` can only be reached by typing its URL.

This is generic core behavior. It works the same for any add-on that uses the
`cypressforge.addons` entry-point group. It names no paid add-on, and no add-on code is copied here.

## Behavior

- A new sidebar group labelled `ADD-ONS` sits under the existing `OBSERVATORY` nav and above
  the "Local by design" card.
- It has one link per entry in `GET /api/addons` whose `ui` is not null. The link text is the
  add-on's `title`.
- The link is a plain `<a href="/addon/<name>/">`. It opens in the same tab: no `target`,
  no `window.open`. The browser back button returns to the dashboard.
- **None:** if no add-on has a page, the whole group (label included) is not rendered.
- **Error:** if the request fails for any reason (network error, non-2xx status, bad JSON,
  unexpected shape), the group is not rendered. There is no banner, no `role="alert"`, and
  the existing "Dashboard connection lost" banner is not touched. Nothing is logged to the
  console.
- **Loading:** nothing is rendered until the response arrives. There is no spinner, so the
  layout does not jump for users who have no add-ons.
- The list is fetched once, when the app mounts, with no polling. Add-ons are discovered
  only at server start, so the list cannot change while the page is open.

## Safety rules (unchanged core rules)

- **CSP is unchanged.** The fetch is same-origin (`connect-src 'self'`). The links are plain
  navigations. No inline script or style is added.
- **Local-only and read-only are unchanged.** The request is a `GET` to the same host and
  goes through the existing middleware. There is no backend change.
- **Titles are text.** The title is rendered as a React text child (`{link.title}`), which
  React escapes. No `dangerouslySetInnerHTML` is used.
- **Only add-on paths become links (defense in depth).** The frontend keeps an entry only if
  `ui` is a string that matches `^/addon/[A-Za-z0-9._-]+/$` and does not contain `..`. Today
  the backend only ever produces `/addon/<name>/`. The check means a bad or tampered response
  can never produce a `javascript:` link, an off-site link (`https://…`, `//host`), or a link
  to a core path.
- Title cleanup: a non-string or empty title falls back to `name`. Whitespace is trimmed and
  the title is cut to 60 characters. CSS ellipsis covers anything that still overflows.
- Duplicate `ui` values are dropped. Links keep the API's order.

## Files to touch

| File | Change |
| --- | --- |
| `frontend/src/AddonNav.tsx` (new) | `type AddonLink = {name:string; title:string; ui:string}`.<br>`addonLinks(payload: unknown): AddonLink[]`, a pure validator and normalizer that never throws.<br>`loadAddonLinks(fetchFn = fetch, signal?): Promise<AddonLink[]>`, which resolves to `[]` on any failure and never rejects.<br>`useAddonLinks()`, which calls `loadAddonLinks` once on mount with an `AbortController` (safe under StrictMode's double mount).<br>`AddonNav({links})`, which returns `null` for an empty list, otherwise the label and `<nav aria-label="Add-ons">` of `<a>` links. |
| `frontend/src/main.tsx` | Import `AddonNav` and `useAddonLinks`. Call the hook in `App`. Render `<AddonNav links={addonLinks}/>` right after the existing `</nav>` in the sidebar. No other changes. |
| `frontend/src/style.css` | Make `nav a` look like `nav button` (layout, padding, colors, hover). Add `text-decoration:none` and an ellipsis on the label. In the existing `max-width:850px` block, collapse `nav a` to icon only, the same way `nav button` collapses. |
| `frontend/tests/run.mjs` | Add `AddonNav` to the transpile list and the import-rewrite regex. Pass the new test file to `node --test`. |
| `frontend/tests/addonNav.test.mjs` (new) | The tests below. |

Each link uses the lucide `Puzzle` icon, which is already a dependency. At narrow widths the
label is hidden, so every link also gets `title={link.title}` (a tooltip) and
`aria-label={link.title}`. Both are plain attribute text that React escapes.

There is no backend change and no Python test change. `GET /api/addons` already returns
`ui` and `title`, and `tests/test_addons.py` already covers it.

## Tests (`frontend/tests/addonNav.test.mjs`)

These are run by `npm test`, which runs `node tests/run.mjs`. They use the same pattern as
`workspace.test.mjs`: `renderToStaticMarkup` with no DOM.

1. **Validator keeps good entries.** For
   `{addons:[{name:'hello',title:'Hello',ui:'/addon/hello/'}]}` it returns one link.
2. **Validator drops bad entries.** It drops entries where `ui` is `null`, missing,
   `javascript:alert(1)`, `https://evil.example/`, `//evil.example/`, `/api/dashboard`,
   `/addon/../api/` or `/addon/x` (no trailing slash). It also drops entries that are not objects.
3. **Malformed payloads give `[]` without throwing.** Tested with `null`, `{}`,
   `{addons:'x'}`, `[]` and `'text'`.
4. **Title rules.** A missing or numeric title falls back to `name`, a 200-character title is
   cut to 60, and duplicate `ui` values are dropped.
5. **Load failures stay quiet.** `loadAddonLinks` is given a stub `fetch` that rejects, one
   that returns `{ok:false,status:500}`, and one whose `json()` throws. Each resolves to
   `[]`. A good stub returns the parsed links.
6. **Empty list renders nothing.** `renderToStaticMarkup(AddonNav({links:[]}))` is `''`.
   It contains no `ADD-ONS` text and no `role="alert"`.
7. **Rendered links are correct and escaped.** One link renders
   `href="/addon/hello/"` and the text `Hello`, with no `target=`. A title of
   `<img src=x onerror=alert(1)>` shows up as `&lt;img` and never as `<img`.

## Checking it in a browser with the `hello` example

Do not use or restart the live dashboard. It runs from `C:\AI\CypressForge` on port 8765.

`examples/hello` is only on the `example-hello` branch for now, not on `main`, which this
branch is based on. The check copies it out of git into the scratchpad and does not merge
it. Everything runs from this worktree, with its own venv, on port **8766**.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend; npm ci; npm run build; cd ..
New-Item -ItemType Directory -Force $env:TEMP\cf-hello-check | Out-Null
git archive example-hello examples/hello | tar -x -C $env:TEMP\cf-hello-check
```

1. **No add-ons.** Start
   `.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8766`
   and open `http://127.0.0.1:8766/`. There should be no `ADD-ONS` group, no banner, and no
   console errors.
2. **With hello.** Stop the server and run
   `.venv\Scripts\python.exe -m pip install -e $env:TEMP\cf-hello-check\examples\hello`.
   Start the server again and reload. The sidebar should show `ADD-ONS` with one `Hello` link.
3. **Same tab.** Click `Hello`. The tab should go to `/addon/hello/` and show the hello page,
   and the back button should return to the dashboard.
4. **Quiet failure.** Block `/api/addons` in DevTools (Network → Block request URL) and
   reload. There should be no group, no banner, and the rest of the dashboard should work.
5. **Narrow width.** Make the viewport narrower than 850px. The link should show as an icon
   only, and hovering it should show the "Hello" tooltip.
6. **CSP.** The console should show no CSP violations.
7. **Clean up.** Stop the server. The worktree `.venv` and `frontend/dist` are gitignored and
   can be deleted.

Note: the backend's Origin allow-list names only port 8765. Browsers send an `Origin` header
when they load the page's module script, even from the same origin, so a plain server on
8766 answers 403 for `/assets/*` and the app does not render. The check therefore runs core
through a small test-only ASGI wrapper kept outside the repo (in a scratch folder). It
rewrites `Origin: http://127.0.0.1:8766` to the allowed `:8765` value, and passes every
other Origin through untouched. With `CF_FAIL_ADDONS=1` it also answers 500 for
`/api/addons`, which replaces step 4's DevTools blocking. Core's allow-list is not changed.

Result (2026-11-20, built-in browser): all of steps 1 to 6 passed. With no add-ons there was
no group. With hello there was one `Hello` link to `/addon/hello/` with no `target`; it
opened in the same tab, and back returned to the dashboard. With a forced 500 there was no
group, no alert, and the dashboard rendered. At 800px the link showed as an icon only, with
a tooltip. There were no CSP messages.

## Out of scope

- A "back to dashboard" link on add-on pages. Each add-on owns its own page.
- Showing add-on errors (`errors`, `last_error`) or versions in the UI.
- Icons supplied by add-ons, ordering hints, or embedding add-on pages inside the dashboard
  shell (an iframe would also run into `frame-ancestors 'none'`).
- Any change to `backend/addons.py`, `/api/addons`, the CSP or the middleware.

## Decisions at review

1. Placement: under `OBSERVATORY` (the default).
2. Order: the API order (the default).
