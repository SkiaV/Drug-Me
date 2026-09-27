# Drug Me

React + Vite + Tailwind CSS project (created in Figma Make) with a Flask API. "Was this medicine tested on people
like me?" — see README.md for what the product does and how the pieces fit.

## Development Server

Inside Figma Make a Vite development server is **already running** on `$PORT` (default 8443). Locally, run
`PORT=5173 pnpm dev` (the port is strict) next to the Flask API described below.

- Preview URL: The user can access the running app through the preview panel
- Hot reload: Changes to source files are reflected immediately

## Project Structure

This is the canonical project structure. Start with task-relevant files below. Only follow imports or inspect other files when required, when a documented path is missing, or when the repository contradicts this guide.

- `src/main.tsx` - React entrypoint; imports `src/index.css`, `src/home.css`, `src/extra.css` and mounts `src/App.tsx` into the `#root` element
- `src/App.tsx` - Primary application component: the four routes (home, dashboard, advanced search, individual report)
- `src/api.ts` - Frontend models and requests to the Flask API (`/api/v1`)
- `src/homeData.ts` - Numbers behind the home page (live from `/api/v1/meta`, with a snapshot fallback)
- `src/components/` - Banner and Explainer (home page), GroupBars and FaersPanel (report page)
- `src/hooks.ts` - Scroll-in reveal and count-up hooks
- `src/index.css` - Global CSS entrypoint and Tailwind CSS v4 import; `src/home.css` and `src/extra.css` add the home page and the data pages
- `index.html` - Vite HTML shell containing the `#root` element and loading `src/main.tsx`
- `package.json` - Project dependencies and the Vite build, development, preview, and formatting scripts
- `vite.config.ts` - Vite configuration with React, Tailwind CSS v4, and Figma Make plugins, the `@` alias for `src`, and the `/api` proxy to Flask
- `.mise.toml` - Toolchain versions for Node.js and pnpm
- `backend/app.py` - Flask API entrypoint (`/api/v1`), also serves the built app from `dist/`
- `backend/data/registry.sqlite` - Harvested ClinicalTrials.gov registry read by that API
- `Backend copy/SQLite Builder/` - The study-level SQLite store (`ingest.py`) and its query API (`api.py`, port 5001)

## Dependencies

- Runtime: React 19 and React DOM 19
- Styling: Tailwind CSS v4 with the `@tailwindcss/vite` plugin
- Build tooling: Vite 8, TypeScript 5.7, and `@vitejs/plugin-react`
- Formatting: oxfmt
- Backend: Python 3.11+, Flask, flask-cors, requests, python-dotenv, pillow (see `backend/requirements.txt`)

## Flask and SQLite

The frontend calls `/api/v1` on its own origin. In development `vite.config.ts` proxies `/api` to
`http://127.0.0.1:5000` (override with `API_PROXY_TARGET`); set `VITE_API_BASE_URL` to call a Flask server on
another host directly. There is no mock fallback; API errors appear in the relevant page.

The product API is `backend/app.py`. From the workspace root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe backend\app.py        # http://127.0.0.1:5000  (PORT=... to change)
```

It reads `backend/data/registry.sqlite` (committed: every Phase 3 trial with posted results, harmonized, plus one
row per drug) and serves `/api/v1/meta`, `/api/v1/drugs`, `/api/v1/search`, `/api/v1/suggest` and
`/api/v1/drugs/<id>/report`. `GET /api` lists every route. Once `pnpm build` has written `dist/`, Flask serves the
app at the same URL. To rebuild the registry from ClinicalTrials.gov (about 15 requests):

```powershell
.\.venv\Scripts\python.exe backend\harvest.py
.\.venv\Scripts\python.exe backend\build_table.py
```

`Backend copy/SQLite Builder/api.py` is a second, study-level API over `ingest.py`'s `studies.db` (one row per
trial; filters drug, condition, age, sex, race) on port 5001. It is independent of the product API.

## Styling

This project uses **Tailwind CSS v4** through the `@tailwindcss/vite` plugin configured in `vite.config.ts`. `src/index.css` imports Tailwind with `@import 'tailwindcss';`. Use Tailwind utility classes directly in JSX and put global CSS or Tailwind v4 theme customization in `src/index.css`. This scaffold does not need a Tailwind config file or PostCSS config.

`src/main.tsx` imports `src/index.css`, so global font wiring belongs in `src/index.css`. Keep CSS `@import` statements first, then add any `@font-face` rules and font-family defaults there.

## Code quality

- Use double quotes for strings containing apostrophes (`"We're here to help"`), or escape them in single-quoted strings. An unescaped apostrophe in a single-quoted string breaks the build.
- Ensure JSX tags are closed and braces are balanced.
- Export components as default exports.
- Type-check with `npx tsc --noEmit -p tsconfig.json --ignoreDeprecations 5.0`; backend tests with `cd backend && python -m pytest -q`.
