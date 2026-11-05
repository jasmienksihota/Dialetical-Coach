# Privacy and data flow

- **Local by default.** Server binds to `127.0.0.1`; requests with a non-local `Host` or a
  cross-origin `Origin` on writes are refused. No accounts, no telemetry, no analytics.
- **Where data lives.** `data/` (originals, `tutor.db` with extracted text, sessions, flags). It is
  git-ignored. Delete the folder to erase everything.
- **Secrets.** `ANTHROPIC_API_KEY` is read from the environment/`.env` by the Python server only.
  It is never sent to the browser, logged, stored in the database, or included in exports or error
  messages (tests check this). `.env` is git-ignored.
- **Demo mode** stays on your machine.
- **Live mode** sends, per turn, the retrieved passages from your approved documents and the bounded
  conversation context (and your messages) to the configured model provider. It is opt-in per
  session, requires you to configure a key and model, and confirms before first use in the UI.
- **Cloud development vs local running.** Building this app in a Claude Code cloud session and
  running it on your computer are separate. The app's data does not live in the cloud session, and
  Claude Code promotional credits do not configure or fund this app's inference API.
- **No outside tools.** The tutor has no web search or autonomous acquisition.
- **Your answers** are stored in your sessions only; they are never indexed as library sources.
- **Exports** are plain Markdown files you save yourself; the app never uploads them anywhere.
