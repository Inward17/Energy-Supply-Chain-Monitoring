## What changed

<!-- One or two sentences. What does this PR do, and why? -->

## How to verify

<!-- Steps a reviewer can follow. For UI changes, the Cloudflare Pages bot
     comments a preview URL on this PR — link the page to look at. -->

- [ ] Preview deployment checked (desktop and phone width)
- [ ] Light and dark theme checked (UI changes)

## Checklist

- [ ] CI is green (frontend: typecheck, build, smoke tests · backend: pytest)
- [ ] No secrets, API keys or `.env` files in the diff
- [ ] Backend changes: new env vars are listed below and set on Render
- [ ] Schema changes: `init_schema()` stays idempotent (CI runs it against a fresh DB and a Neon branch)

## Deployment notes

<!-- Anything Render / Cloudflare / Neon needs before or after merge
     (env vars, migrations, CORS). Write "none" if nothing. -->
