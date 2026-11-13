# MERIDIAN — Energy Supply Chain Resilience OS

Compressed project context. Read this first; open the linked files only when
the task needs them.

- @.claude/context/architecture.md — services, data flow, where code lives
- @.claude/context/scoring.md — SDI formula, risk aggregation, data-health rules
- @.claude/context/operations.md — run, test, deploy, CI, env vars
- @.claude/context/decisions.md — non-obvious choices and known gaps

## Rules for working in this repo

- **Never commit or push** unless the user asks in that turn. They run git.
- **No Claude attribution** in commits or PRs (no Co-Authored-By, no footer).
- Never print or commit `backend/.env` (live API keys). Scan diffs for keys.
- `frontend/` is the live UI (MERIDIAN). `legacy/frontend/` is the old UI,
  kept only for comparison — don't edit it unless asked.
- Before claiming done: `pytest` (backend), `npm run typecheck && npm run build
  && npm run test:e2e` (frontend). CI runs the same.
- Windows host: Git Bash + PowerShell. Backend venv is `backend/venv`.
