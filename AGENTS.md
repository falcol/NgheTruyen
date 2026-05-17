## Learned User Preferences

- Communicates in Vietnamese; prefers explanations and UI copy in Vietnamese.
- Creates git commits only when explicitly asked.
- Reader color presets: dark themes only (no light or sepia options).
- Wants Palatino available as a reading font.
- Reader theme must apply to the full page via `document.documentElement`, not only the reader shell.

## Learned Workspace Facts

- Web story data: `listStories()` reads `web/public/data/` only; dev needs `ln -s ../../crawler/data public/data` from `web/` or `npm run data:copy`; `npm run dev` does not copy data.
- Run the Next.js app from `web/` so `process.cwd()` resolves `public/data` correctly.
- `public/data` is gitignored; each fresh clone needs symlink or copy again.
- EPUB files live in repo-root `epub/`; web routes are under `web/src/app/epub/`.
- Avoid parsing EPUB on the server during user reads; use disk cache under `epub/.cache/` warmed by `npm run epub:cache` (also runs on prebuild).
- `web/src/lib/epub-parse.ts` is for build/CLI only; app routes use `web/src/lib/epub.ts` for runtime cache reads.
- Crawl and EPUB reading share `ReaderClient`; scroll position persists via `useProgress` in localStorage.
- Reader appearance uses localStorage key `reader-settings-v1`; themes apply through `applyReaderThemeToDocument` on `documentElement`.
- Do not modify `web/AGENTS.md` (Next.js framework notes).
