# Contributing to MERIDIAN

Thanks for helping. This project is small and maintained by one person, so
small, focused pull requests are the fastest way to get a change in.

## Before you start

- **Bugs and ideas:** open an issue with the bug or feature template first,
  unless the change is a typo or an obvious one-liner.
- **Security issues:** never in a public issue — see [`SECURITY.md`](SECURITY.md).
- By contributing you agree your work is released under the [MIT License](LICENSE)
  and that you will follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Set up

The quickest way to a running stack is Docker:

```bash
cp backend/.env.example backend/.env      # set DB_PASSWORD and NEO4J_PASSWORD
docker compose --env-file backend/.env up -d --build
# UI http://localhost:3000 · API http://localhost:8000/docs
```

Native setup (Python 3.13, Node 22) is in the README under *Setup & Running*.
How every number is calculated is in [`docs/algorithms.md`](docs/algorithms.md).

## Making a change

1. Branch from `main`: `git switch -c fix/short-name` (or `feat/…`, `docs/…`).
2. Keep the change to one idea. Match the surrounding code style; don't
   reformat unrelated lines.
3. Add or update a test for any change in behaviour.
4. Run the same checks CI runs:

   ```bash
   cd backend && python -m pytest -q
   cd frontend && npm run typecheck && NEXT_PUBLIC_API_URL=http://127.0.0.1:9 npm run build && npm run test:e2e
   ```

   Tests use a rolled-back transaction per test, refuse a remote `DB_HOST`
   unless `TEST_DB_ALLOW_REMOTE=1`, and never touch your configured Neo4j.
5. Commit with a [conventional](https://www.conventionalcommits.org/) prefix
   (`fix:`, `feat:`, `docs:`, `chore:`, `test:`) describing *why*, not just what.
6. Open a pull request. The template asks what changed and how you verified
   it; CI (frontend, backend, CodeQL, Docker when relevant) must be green, and
   Cloudflare posts a preview URL for UI changes.

## Ground rules

- **Never commit secrets.** `.env` files stay local; check `git status` before
  committing. GitGuardian scans every PR.
- **Models must state their assumptions.** If you change a formula or a
  constant, update `docs/algorithms.md` and keep any assumption the UI shows
  in sync.
- **No silent fallbacks.** Missing or degraded data must be visible (a status,
  a label, a 503), never shown as a valid-looking result.
- `legacy/frontend/` is kept only for comparison — don't change it.

## Review

Expect a review within about a week. Suggestions from bots (CodeQL,
Dependabot) are inputs, not orders; the maintainer decides.
