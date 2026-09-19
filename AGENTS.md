## Learned User Preferences

- Communicates in Vietnamese; prefers explanations and UI copy in Vietnamese.
- Creates git commits only when explicitly asked.
- Reader color presets: dark themes only (no light or sepia options).
- Wants Palatino available as a reading font.
- Reader theme must apply to the full page via `document.documentElement`, not only the reader shell.
- Expects the agent to run pipelines and compare output against expected files (e.g. `raw_china/expect*.txt`) autonomously, without being prompted.

## Learned Workspace Facts

- Web story data: `listStories()` reads `web/public/data/` (gitignored; each fresh clone needs `ln -s ../../crawler/data public/data` or `npm run data:copy`; `npm run dev` does not copy data). Run Next.js from `web/` so `process.cwd()` resolves `public/data` correctly.
- EPUB files live in repo-root `epub/`; web routes are under `web/src/app/epub/`.
- Avoid parsing EPUB on the server during user reads; use disk cache under `epub/.cache/` warmed by `npm run epub:cache` (also runs on prebuild). `web/src/lib/epub-parse.ts` is for build/CLI only; app routes use `web/src/lib/epub.ts` for runtime cache reads.
- Crawl and EPUB reading share `ReaderClient`; scroll position persists via `useProgress` in localStorage.
- Reader appearance uses localStorage key `reader-settings-v1`; themes apply through `applyReaderThemeToDocument` on `documentElement`.
- Do not modify `web/AGENTS.md` (Next.js framework notes).
- TTS: `lib/tts-chunks.ts` uses Read Aloud-inspired placeholder swap for Vietnamese abbreviations (GS., PGS., TS.); Chrome 15s Web Speech API timeout workaround via 10s pause/resume in `useTTS.ts`.
- Chapter content prefetch: `lib/chapter-prefetch.ts` (RAM cache, max 12 entries), `lib/chapter-nav.ts` (URL generation), API route at `api/chapter/[slug]/[chapterIdx]` for crawl stories.
- Reading progress components: `ContinueReadingSection` (horizontal scroll of recently read) and `CardProgressOverlay` (progress bar + badge on book cards) in `web/src/components/`.
- Color scheme: anime aesthetic (midnight navy `#06070f` + sakura pink `#e879a0`) via globals.css, `color.ts` (10 dark-saturated gradient palettes), and `TopNav.tsx` branding.
- zhvi (zh→vi translation CLI) lives in `zhvi/`; translation unit is a book-project (`zhvi init` + `--project`) — without it each source file gets its own workspace `<name>.zhvi/` (glossary.manual.tsv + state.sqlite3). Dict/glossary/config changes hash into the run fingerprint and auto-invalidate the block cache.
- Glossary precedence: base dicts < `zhvi/glossary.manual.tsv` + `zhvi/glossary.d/*.tsv` (env `ZHVI_GLOBAL_GLOSSARY`) < book glossary; format is `zh=vi`. Universal terms belong in `crawler/vietphrase/dicts/Custom.txt` (highest-trust manual layer, shared by old engine and zhvi), never in regenerable `VietPhrase_*.txt` corpora. zhvi QA junk-strip (`zhvi/src/zhvi/qa.py`) runs on the Chinese source pre-translation; anti-repetition rule preserves genuine source reduplication.
