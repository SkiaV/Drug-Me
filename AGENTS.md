# figma-make-app

React + Vite + Tailwind CSS project running inside Figma Make.

## Development Server

A Vite development server is **already running** on `$PORT` (default 8443). You don't need to start it manually.

- Preview URL: The user can access the running app through the preview panel
- Hot reload: Changes to source files are reflected immediately

## Project Structure

This is the canonical project structure. Start with task-relevant files below. Only follow imports or inspect other files when required, when a documented path is missing, or when the repository contradicts this guide.

- `src/main.tsx` - React entrypoint; imports `src/index.css` and mounts `src/App.tsx` into the `#root` element
- `src/App.tsx` - Primary application component and the usual starting point for UI work
- `src/api.ts` - Frontend models and requests to the Flask studies API
- `src/index.css` - Global CSS entrypoint and Tailwind CSS v4 import
- `index.html` - Vite HTML shell containing the `#root` element and loading `src/main.tsx`
- `package.json` - Project dependencies and the Vite build, development, preview, and formatting scripts
- `vite.config.ts` - Vite configuration with React, Tailwind CSS v4, and Figma Make plugins plus the `@` alias for `src`
- `.mise.toml` - Toolchain versions for Node.js and pnpm
- `Backend/SQLite Builder/api.py` - Flask studies API entrypoint
- `Backend/SQLite/data/studies.db` - SQLite database read by that API

## Dependencies

- Runtime: React 19 and React DOM 19
- Styling: Tailwind CSS v4 with the `@tailwindcss/vite` plugin
- Build tooling: Vite 8, TypeScript 5.7, and `@vitejs/plugin-react`
- Formatting: oxfmt

## Flask and SQLite

The frontend calls `http://127.0.0.1:5001` by default. Set
`VITE_API_BASE_URL` to override it. There is no mock fallback; API errors appear
in the relevant page.

The studies API is `Backend/SQLite Builder/api.py`. `Backend/main.py` is a
separate route stub and does not serve the studies database. From the workspace
root, install and start the studies API with:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r Backend\requirements.txt
.\.venv\Scripts\python.exe "Backend\SQLite Builder\api.py"
```

The API reads `Backend/SQLite/data/studies.db` by default and serves
`/api/studies`, `/api/studies/stats`, and `/api/studies/aggregate` on port 5001.
To download and load the ClinicalTrials.gov dataset, run:

```powershell
.\.venv\Scripts\python.exe "Backend\SQLite Builder\ingest.py"
```

Supported study filters are drug, condition, age, sex, and race. API list
requests cap at 200 studies; dashboard drug summaries use the first 200 studies,
while displayed database totals come from `/api/studies/stats`.

## Styling

This project uses **Tailwind CSS v4** through the `@tailwindcss/vite` plugin configured in `vite.config.ts`. `src/index.css` imports Tailwind with `@import 'tailwindcss';`. Use Tailwind utility classes directly in JSX and put global CSS or Tailwind v4 theme customization in `src/index.css`. This scaffold does not need a Tailwind config file or PostCSS config.

`src/main.tsx` imports `src/index.css`, so global font wiring belongs in `src/index.css`. Keep CSS `@import` statements first, then add any `@font-face` rules and font-family defaults there.

## Code quality

- Use double quotes for strings containing apostrophes (`"We're here to help"`), or escape them in single-quoted strings. An unescaped apostrophe in a single-quoted string breaks the build.
- Ensure JSX tags are closed and braces are balanced.
- Export components as default exports.
